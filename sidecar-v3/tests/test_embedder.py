"""Stage G — bge-m3 embedder (plan §3.3). Integration: uses BAAI's bge-m3 ONNX +
tokenizer from the HF cache; skipped if the asset isn't present (CI without the
model). The store's write path is unit-tested with fake vectors in test_store.py."""
import os
from pathlib import Path

import numpy as np
import pytest

from index.embedder import DIM, Embedder

_CACHE = Path(os.path.expanduser("~/.cache/huggingface/hub"))


def _find(name):
    hits = list(_CACHE.rglob(f"models--BAAI--bge-m3/**/{name}")) if _CACHE.exists() else []
    return str(hits[0]) if hits else None


MODEL, TOK = _find("model.onnx"), _find("tokenizer.json")


@pytest.mark.skipif(not (MODEL and TOK), reason="bge-m3 ONNX/tokenizer not in HF cache")
def test_embed_returns_normalized_distinct_vectors():
    v = Embedder(MODEL, TOK).embed(["a goblin has armor class 15", "fireball deals 8d6 fire damage"])
    assert v.shape == (2, DIM)
    assert np.allclose(np.linalg.norm(v, axis=1), 1.0, atol=1e-4)  # L2-normalized
    assert not np.allclose(v[0], v[1])  # distinct texts → distinct vectors


@pytest.mark.skipif(not (MODEL and TOK), reason="bge-m3 ONNX/tokenizer not in HF cache")
def test_embed_preserves_input_order_across_length_buckets():
    # Throughput fix: embed() length-buckets units before batching (a 400-char
    # unit batched with 25-char units wastes ~4x on padding). Bucketing must NOT
    # scramble output order — row i must always be text i's vector, regardless of
    # length. Varied lengths + a small batch force the reorder path.
    e = Embedder(MODEL, TOK)
    texts = [
        "short",
        "a much longer sentence about dungeons and dragons and goblins " * 6,
        "medium length text about goblins and armor",
        "x",
        "another very long passage concerning spells and fireballs and damage " * 6,
        "tiny",
    ]
    batched = e.embed(texts, batch=2)
    assert batched.shape == (len(texts), DIM)
    for i, t in enumerate(texts):
        assert np.allclose(batched[i], e.embed([t])[0], atol=1e-4), f"row {i} misaligned to input"
