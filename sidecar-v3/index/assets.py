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
