"""Cross-encoder re-ranker for search candidates.

Wraps fastembed's TextCrossEncoder. The cross-encoder scores
(query, candidate-text) pairs jointly, which is meaningfully more
accurate than embedding-cosine similarity when several candidates are
topically adjacent (e.g., a question about grappling versus a list of
conditions that contains the word "grappled").

Runs entirely locally on CPU via ONNX runtime — same shape as the
existing bge-m3 embedding pipeline. No PyTorch dependency, no API
calls; the model weights download once on first use and are then
cached under ``~/.cache/huggingface/``.

The default model is ``Xenova/ms-marco-MiniLM-L-12-v2`` rather than a
BGE-family reranker for performance reasons: the smallest BGE
reranker (``BAAI/bge-reranker-base``) takes ~6 seconds to score 50
candidates on CPU, which is unusable for interactive search. The
MS-MARCO L-12 model scores the same batch in ~100 ms. If quality
becomes a problem, ``RERANK_MODEL`` can be overridden.

The reranker is loaded lazily on first use and cached. If loading or
scoring fails (model missing, network down, etc.) we return None so
the caller can fall back to the underlying vector ordering — search
must keep working even without the reranker available.

Configuration via env vars:

* ``RERANK_MODEL`` — fastembed model name. Default
  ``Xenova/ms-marco-MiniLM-L-12-v2`` (120 MB, English, ~100 ms / 50
  docs). Lighter still: ``Xenova/ms-marco-MiniLM-L-6-v2`` (80 MB,
  ~50 ms). Heavier (1+ GB, slower): ``BAAI/bge-reranker-base``,
  ``jinaai/jina-reranker-v2-base-multilingual``.
* ``RERANK_DISABLED`` — set to ``1`` to short-circuit and skip loading
  the model entirely. Useful in tests or for users who want to ship
  without the dependency.
"""
from __future__ import annotations

import logging
import math
import os
import threading


logger = logging.getLogger(__name__)

DEFAULT_MODEL = "Xenova/ms-marco-MiniLM-L-12-v2"

_lock = threading.Lock()
_reranker = None
_load_failed = False


def _sigmoid(x: float) -> float:
    """Cross-encoder logits → [0, 1] relevance score."""
    if x >= 0:
        return 1 / (1 + math.exp(-x))
    ex = math.exp(x)
    return ex / (1 + ex)


def _get_reranker():
    global _reranker, _load_failed
    if _load_failed:
        return None
    if _reranker is not None:
        return _reranker
    if os.getenv("RERANK_DISABLED") == "1":
        _load_failed = True
        return None
    with _lock:
        if _reranker is not None or _load_failed:
            return _reranker
        try:
            from fastembed.rerank.cross_encoder import TextCrossEncoder
            model_name = os.getenv("RERANK_MODEL", DEFAULT_MODEL)
            logger.info("Loading re-ranker: %s", model_name)
            _reranker = TextCrossEncoder(model_name=model_name)
        except Exception as e:
            logger.warning(
                "Re-ranker load failed (%s); falling back to vector order", e
            )
            _load_failed = True
            return None
    return _reranker


def rerank_scores(query: str, docs: list[str]) -> list[float] | None:
    """Score ``(query, doc)`` pairs with the cross-encoder.

    Returns sigmoid-normalised scores in ``[0, 1]`` (higher = more
    relevant), one per doc. Returns ``None`` if the reranker is
    unavailable, so callers can fall back to cosine ordering.
    """
    if not docs:
        return []
    rk = _get_reranker()
    if rk is None:
        return None
    try:
        raw = list(rk.rerank(query, docs))
    except Exception as e:
        logger.warning("Re-rank scoring failed (%s); falling back", e)
        return None
    return [_sigmoid(s) for s in raw]


def reset_for_tests() -> None:
    """Wipe the cached reranker. Tests only."""
    global _reranker, _load_failed
    with _lock:
        _reranker = None
        _load_failed = False
