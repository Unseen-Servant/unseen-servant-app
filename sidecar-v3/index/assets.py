"""Model-asset resolution (the corpus.py pattern, for ONNX models).

The two Phase-1-winner models aren't in git (size): PP-DocLayout-M (build once
via the experiments repo's `layout_model_spike/convert_m.py`, staged into
`sidecar-v3/models/`) and bge-m3 (BAAI ships an ONNX; lands in the HF cache).
Resolve by env override → `models/` → HF cache, with a clear error if absent.
Packaging these for distribution is a Phase-4 concern; this unblocks local
end-to-end runs. No import from sidecar/.
"""
from __future__ import annotations

import os
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]  # sidecar-v3/
MODELS = HERE / "models"
HF = Path(os.path.expanduser("~/.cache/huggingface/hub"))


class AssetError(RuntimeError):
    """Raised when a required model asset can't be resolved."""


def layout_model() -> str:
    env = os.environ.get("LL_V3_LAYOUT_MODEL")
    if env:
        return env
    p = MODELS / "ppdoclayout_m.onnx"
    if p.exists():
        return str(p)
    raise AssetError(
        "PP-DocLayout-M ONNX not found. Convert it with the experiments repo's "
        "layout_model_spike/convert_m.py and copy to sidecar-v3/models/ppdoclayout_m.onnx, "
        "or set $LL_V3_LAYOUT_MODEL."
    )


def _hf_bge_m3(name: str) -> str | None:
    hits = sorted(HF.rglob(f"models--BAAI--bge-m3/**/onnx/{name}")) if HF.exists() else []
    return str(hits[0]) if hits else None


def embed_model() -> tuple[str, str]:
    onnx = os.environ.get("LL_V3_EMBED_MODEL") or _hf_bge_m3("model.onnx")
    tok = os.environ.get("LL_V3_EMBED_TOKENIZER") or _hf_bge_m3("tokenizer.json")
    if not (onnx and tok):
        raise AssetError(
            "bge-m3 ONNX/tokenizer not found in the HF cache. Run "
            "`huggingface-cli download BAAI/bge-m3` or set $LL_V3_EMBED_MODEL / $LL_V3_EMBED_TOKENIZER."
        )
    return onnx, tok


def _hf_minilm(name: str) -> str | None:
    hits = (sorted(HF.rglob(f"models--cross-encoder--ms-marco-MiniLM-L6-v2/**/{name}"))
            if HF.exists() else [])
    return str(hits[0]) if hits else None


def rerank_model() -> tuple[str, str]:
    """MiniLM cross-encoder (rerank_latency spike winner, int8 ONNX) + its BERT
    tokenizer (HF cache). Model staged into models/ from the spike outputs."""
    onnx = os.environ.get("LL_V3_RERANK_MODEL")
    if not onnx:
        p = MODELS / "minilm-rerank-int8.onnx"
        onnx = str(p) if p.exists() else None
    tok = os.environ.get("LL_V3_RERANK_TOKENIZER") or _hf_minilm("tokenizer.json")
    if not (onnx and tok):
        raise AssetError(
            "MiniLM reranker ONNX/tokenizer not found. Copy "
            "rerank_latency_spike/outputs/minilm-int8.onnx to "
            "sidecar-v3/models/minilm-rerank-int8.onnx and ensure the "
            "cross-encoder/ms-marco-MiniLM-L6-v2 tokenizer is in the HF cache "
            "(or set $LL_V3_RERANK_MODEL / $LL_V3_RERANK_TOKENIZER)."
        )
    return onnx, tok


def available() -> bool:
    try:
        layout_model()
        embed_model()
        return True
    except AssetError:
        return False


def load_layout_session():
    """A threaded onnxruntime CPU session for the layout model."""
    import onnxruntime as ort

    so = ort.SessionOptions()
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    so.intra_op_num_threads = os.cpu_count() or 1
    return ort.InferenceSession(layout_model(), so, providers=["CPUExecutionProvider"])


def load_embedder():
    from index.embedder import Embedder

    onnx, tok = embed_model()
    return Embedder(onnx, tok)


def load_reranker():
    from query.rerank import Reranker

    onnx, tok = rerank_model()
    return Reranker(onnx, tok)
