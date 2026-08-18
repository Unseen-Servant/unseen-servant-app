"""Single-pass cross-encoder rerank (plan §3.4, §5; ladder rung 8).

MiniLM-L6-v2 cross-encoder (rerank_latency spike winner: int8 ONNX, ~187 ms/25
pairs CPU, Apache-2.0). Scores (query, passage) pairs jointly — the quality lever
a bi-encoder can't match — and the pipeline reorders the top pool by it. Replaces
v2's two-pass rerank. Rust `tokenizers`, no PyTorch (constitution #1). MiniLM is a
BERT arch, so it needs `token_type_ids` (0=query, 1=passage). No import from sidecar/.
"""
from __future__ import annotations

import os

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer


class Reranker:
    def __init__(self, model_path: str, tokenizer_path: str, max_length: int = 512):
        so = ort.SessionOptions()
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        so.intra_op_num_threads = min(8, os.cpu_count() or 1)  # skip efficiency cores (embed lever)
        self.sess = ort.InferenceSession(model_path, so, providers=["CPUExecutionProvider"])
        self.tok = Tokenizer.from_file(tokenizer_path)
        self.tok.enable_truncation(max_length)
        self.tok.enable_padding()

    def rerank(self, query: str, docs, batch: int = 32) -> list[float]:
        """Relevance logit per doc, aligned to input order. Encodes (query, doc)
        pairs → BERT inputs (incl. token_type_ids) → the model's single logit."""
        out: list[float] = []
        for i in range(0, len(docs), batch):
            enc = self.tok.encode_batch([(query, d) for d in docs[i:i + batch]])
            ids = np.array([e.ids for e in enc], np.int64)
            mask = np.array([e.attention_mask for e in enc], np.int64)
            types = np.array([e.type_ids for e in enc], np.int64)
            logits = self.sess.run(
                ["logits"],
                {"input_ids": ids, "attention_mask": mask, "token_type_ids": types},
            )[0]
            out.extend(float(x) for x in logits[:, 0])
        return out
