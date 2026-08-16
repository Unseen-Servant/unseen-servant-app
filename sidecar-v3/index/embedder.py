"""bge-m3 dense embeddings, in-process ONNX (no Ollama) — plan §3.3.

The embed_parity spike's verdict is **fp32** (BAAI's own bge-m3 ONNX): perfect
parity with Ollama f16 (drift 1e-05, so prior evidence transfers with no
re-baseline), ~36-40 units/s CPU — but ONLY with the threading lever below
(`intra_op_num_threads` + graph opt made it ~6× faster than ORT defaults). int8
was faster but failed the <0.01 parity gate, so it's shelved. Tokenizer is the
Rust `tokenizers` lib — no PyTorch (constitution #1). No import from sidecar/.
"""
from __future__ import annotations

import os

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

DIM = 1024


class Embedder:
    def __init__(self, model_path: str, tokenizer_path: str, max_length: int = 8192):
        so = ort.SessionOptions()
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        so.intra_op_num_threads = os.cpu_count() or 1  # the ~6× lever (embed_parity)
        self.sess = ort.InferenceSession(model_path, so, providers=["CPUExecutionProvider"])
        self.tok = Tokenizer.from_file(tokenizer_path)
        self.tok.enable_truncation(max_length)
        self.tok.enable_padding()

    def embed(self, texts, batch: int = 64) -> np.ndarray:
        """(N, 1024) L2-normalized dense vectors. bge-m3 ONNX outputs
        `sentence_embedding` directly — no manual pooling."""
        out = []
        for i in range(0, len(texts), batch):
            enc = self.tok.encode_batch(list(texts[i:i + batch]))
            ids = np.array([e.ids for e in enc], np.int64)
            mask = np.array([e.attention_mask for e in enc], np.int64)
            out.append(self.sess.run(["sentence_embedding"],
                                     {"input_ids": ids, "attention_mask": mask})[0])
        v = np.concatenate(out).astype(np.float32) if out else np.zeros((0, DIM), np.float32)
        return v / np.clip(np.linalg.norm(v, axis=1, keepdims=True), 1e-9, None)
