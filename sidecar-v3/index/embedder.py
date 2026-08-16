"""bge-m3 dense embeddings, in-process ONNX (no Ollama) — plan §3.3.

The embed_parity spike's verdict is **fp32** (BAAI's own bge-m3 ONNX): perfect
parity with Ollama f16 (drift 1e-05, so prior evidence transfers with no
re-baseline). int8 was faster but failed the <0.01 parity gate, so it's shelved.
Tokenizer is the Rust `tokenizers` lib — no PyTorch (constitution #1).

Throughput (the Phase-2 timing gate): two levers, both measured on real bfrpg
units (char len min=4/med=75/max=400) —
  1. `intra_op_num_threads = min(8, cores)` — on Apple Silicon `os.cpu_count()`
     counts the 2 efficiency cores, and every fork-join op waits on the slowest
     thread; dropping them lifted ~6→8.5 u/s.
  2. length-bucketed batching — `enable_padding()` pads each batch to its longest
     row, so a 400-char unit batched with 25-char units wastes ~4× on padding.
     Sorting by length before batching (then scattering back) lifted 8.5→~16 u/s,
     enough to bring 400pp under the 15-min gate.
No import from sidecar/.
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
        so.intra_op_num_threads = min(8, os.cpu_count() or 1)  # skip efficiency cores (lever 1)
        self.sess = ort.InferenceSession(model_path, so, providers=["CPUExecutionProvider"])
        self.tok = Tokenizer.from_file(tokenizer_path)
        self.tok.enable_truncation(max_length)
        self.tok.enable_padding()

    def embed(self, texts, batch: int = 32) -> np.ndarray:
        """(N, 1024) L2-normalized dense vectors, aligned to input order. bge-m3
        ONNX outputs `sentence_embedding` directly — no manual pooling. Units are
        length-bucketed before batching (lever 2) and scattered back, so output
        order matches input regardless of the internal sort."""
        texts = list(texts)
        n = len(texts)
        if n == 0:
            return np.zeros((0, DIM), np.float32)
        order = sorted(range(n), key=lambda i: len(texts[i]))  # similar lengths batch together
        out = np.empty((n, DIM), np.float32)
        for i in range(0, n, batch):
            idx = order[i:i + batch]
            enc = self.tok.encode_batch([texts[j] for j in idx])
            ids = np.array([e.ids for e in enc], np.int64)
            mask = np.array([e.attention_mask for e in enc], np.int64)
            out[idx] = self.sess.run(["sentence_embedding"],
                                     {"input_ids": ids, "attention_mask": mask})[0]
        return out / np.clip(np.linalg.norm(out, axis=1, keepdims=True), 1e-9, None)
