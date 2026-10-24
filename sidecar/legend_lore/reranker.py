"""Cross-encoder re-ranker for search candidates.

Wraps fastembed's TextCrossEncoder. The cross-encoder scores
(query, candidate-text) pairs jointly, which is meaningfully more
accurate than embedding-cosine similarity when several candidates are
topically adjacent (e.g., a question about grappling versus a list of
conditions that contains the word "grappled").

Runs entirely locally on CPU via ONNX runtime — same shape as the
existing bge-m3 embedding pipeline. No PyTorch dependency, no API
calls. The app ships the default model's files (``BUNDLED_MODELS_DIR``,
see ``_bundled_dir``); elsewhere the weights download once on first use
and are then cached under ``FASTEMBED_CACHE_PATH``, which the sidecar
points into its data dir.

The default is MS-MARCO MiniLM-L-6 with int8 weights (Xenova's
``onnx/model_quantized.onnx``, registered below as a fastembed custom
model): 222 ms for 60 real ~1000-char pairs on an M-series CPU vs 491 ms
for L-6 fp32 and 981 ms for the previous default L-12 (2026-09-23,
roadmap 3.2), with scores correlating 0.996 with fp32 L-6. BGE-family
rerankers take seconds per 50 pairs on CPU — unusable interactively.
``RERANK_MODEL`` overrides the default.

The reranker is loaded lazily on first use and cached. If loading or
scoring fails (model missing, network down, etc.) we return None so
the caller can fall back to the underlying vector ordering — search
must keep working even without the reranker available.

Configuration via env vars:

* ``RERANK_MODEL`` — fastembed model name. Default
  ``legend-lore/ms-marco-MiniLM-L-6-v2-q8`` (~23 MB). Previous default:
  ``Xenova/ms-marco-MiniLM-L-12-v2`` (120 MB). Heavier (1+ GB, slower):
  ``BAAI/bge-reranker-base``, ``jinaai/jina-reranker-v2-base-multilingual``.
* ``RERANK_DISABLED`` — set to ``1`` to short-circuit and skip loading
  the model entirely. Useful in tests or for users who want to ship
  without the dependency.
"""
from __future__ import annotations

import logging
import math
import os
import tempfile
import threading


logger = logging.getLogger(__name__)

DEFAULT_MODEL = "legend-lore/ms-marco-MiniLM-L-6-v2-q8"

# int8 variants of Xenova's MS-MARCO cross-encoders, registered as
# fastembed custom models: name → (HF repo, size in GB).
_QUANTIZED = {
    DEFAULT_MODEL: ("Xenova/ms-marco-MiniLM-L-6-v2", 0.023),
    "legend-lore/ms-marco-MiniLM-L-12-v2-q8": (
        "Xenova/ms-marco-MiniLM-L-12-v2", 0.034),
}

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
            if model_name in _QUANTIZED:
                _reranker = _load_quantized(TextCrossEncoder, model_name)
            else:
                _reranker = TextCrossEncoder(model_name=model_name)
        except Exception as e:
            logger.warning(
                "Re-ranker load failed (%s); falling back to vector order", e
            )
            _load_failed = True
            return None
    return _reranker


def _load_quantized(TextCrossEncoder, model_name: str):
    """An int8 MS-MARCO cross-encoder, registered as a fastembed custom
    model (Xenova's ``onnx/model_quantized.onnx``).

    Each gets its own cache directory: its HF repo is the same one as the
    built-in fp32 model, and fastembed treats a cached snapshot of that
    repo as complete, so it would never fetch the quantized file.
    """
    from fastembed.common.model_description import ModelSource

    repo, size = _QUANTIZED[model_name]
    bundled = _bundled_dir(model_name)
    try:
        TextCrossEncoder.add_custom_model(
            model_name,
            sources=ModelSource(hf=repo),
            model_file="onnx/model_quantized.onnx",
            size_in_gb=size,
        )
    except ValueError:
        pass  # already registered in this process
    if bundled:
        logger.info("Re-ranker files from %s", bundled)
        return TextCrossEncoder(
            model_name=model_name,
            specific_model_path=bundled,
            local_files_only=True,
        )
    base = os.getenv("FASTEMBED_CACHE_PATH") or os.path.join(
        tempfile.gettempdir(), "fastembed_cache")
    return TextCrossEncoder(
        model_name=model_name,
        cache_dir=os.path.join(base, "legend-lore-rerank-q8"),
    )


def _bundled_dir(model_name: str) -> str | None:
    """The model's folder among the models shipped with the app, or None.

    ``BUNDLED_MODELS_DIR`` is set by server.py from ``--models-dir``.
    Without it, as under pytest and the evals, the model downloads.
    """
    from legend_lore import bundled

    path = bundled.model_dir(os.getenv("BUNDLED_MODELS_DIR"), "rerank", model_name)
    return str(path) if path else None


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
