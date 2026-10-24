"""Unit tests for the reranker module — model load is mocked or disabled."""

import json
import os
from pathlib import Path

import pytest

from legend_lore import reranker


@pytest.fixture(autouse=True)
def _reset():
    reranker.reset_for_tests()
    yield
    reranker.reset_for_tests()


def test_disabled_returns_none(monkeypatch):
    """RERANK_DISABLED=1 should short-circuit before touching fastembed."""
    monkeypatch.setenv("RERANK_DISABLED", "1")
    assert reranker.rerank_scores("query", ["doc"]) is None


def test_empty_docs_returns_empty_list(monkeypatch):
    """No docs to score = no scores; should not load the model."""
    monkeypatch.setenv("RERANK_DISABLED", "1")
    assert reranker.rerank_scores("query", []) == []


def test_load_failure_returns_none(monkeypatch):
    """If the model load raises, fall back gracefully (caller reverts to cosine)."""
    monkeypatch.delenv("RERANK_DISABLED", raising=False)

    class Boom:
        @classmethod
        def add_custom_model(cls, *a, **kw):
            pass

        def __init__(self, model_name, **kw):
            raise RuntimeError("simulated load failure")

    class FakeModule:
        TextCrossEncoder = Boom

    import sys
    monkeypatch.setitem(sys.modules, "fastembed.rerank.cross_encoder", FakeModule)
    assert reranker.rerank_scores("q", ["d"]) is None


def test_scoring_failure_returns_none(monkeypatch):
    """If the model loads but scoring raises, fall back."""
    monkeypatch.delenv("RERANK_DISABLED", raising=False)

    class FakeReranker:
        @classmethod
        def add_custom_model(cls, *a, **kw):
            pass

        def __init__(self, model_name, **kw):
            pass

        def rerank(self, query, docs):
            raise RuntimeError("simulated score failure")

    class FakeModule:
        TextCrossEncoder = FakeReranker

    import sys
    monkeypatch.setitem(sys.modules, "fastembed.rerank.cross_encoder", FakeModule)
    assert reranker.rerank_scores("q", ["d"]) is None


def test_sigmoid_normalises_into_0_to_1(monkeypatch):
    """Cross-encoder logits get sigmoid-mapped to [0, 1]."""
    monkeypatch.delenv("RERANK_DISABLED", raising=False)

    class FakeReranker:
        @classmethod
        def add_custom_model(cls, *a, **kw):
            pass

        def __init__(self, model_name, **kw):
            pass

        def rerank(self, query, docs):
            # Wide raw-logit range covering negative and positive values.
            return iter([-12.0, -0.5, 0.0, 4.5])

    class FakeModule:
        TextCrossEncoder = FakeReranker

    import sys
    monkeypatch.setitem(sys.modules, "fastembed.rerank.cross_encoder", FakeModule)
    scores = reranker.rerank_scores("q", ["a", "b", "c", "d"])
    assert scores is not None
    assert all(0.0 <= s <= 1.0 for s in scores)
    # Monotonic — higher logit yields higher sigmoid.
    assert scores == sorted(scores)


def test_load_failure_is_cached(monkeypatch):
    """A failed load should not retry on every call (would be slow + noisy)."""
    monkeypatch.delenv("RERANK_DISABLED", raising=False)

    calls = {"n": 0}

    class CountingLoader:
        @classmethod
        def add_custom_model(cls, *a, **kw):
            pass

        def __init__(self, model_name, **kw):
            calls["n"] += 1
            raise RuntimeError("nope")

    class FakeModule:
        TextCrossEncoder = CountingLoader

    import sys
    monkeypatch.setitem(sys.modules, "fastembed.rerank.cross_encoder", FakeModule)

    reranker.rerank_scores("q", ["a"])
    reranker.rerank_scores("q", ["b"])
    reranker.rerank_scores("q", ["c"])
    assert calls["n"] == 1


def test_default_model_is_the_int8_l6_in_its_own_cache(monkeypatch, tmp_path):
    """The default registers Xenova's quantized L-6 file and loads it from
    a dedicated cache dir (a cached fp32 snapshot of the same repo would
    otherwise make fastembed skip the quantized download)."""
    monkeypatch.delenv("RERANK_DISABLED", raising=False)
    monkeypatch.delenv("RERANK_MODEL", raising=False)
    monkeypatch.setenv("FASTEMBED_CACHE_PATH", str(tmp_path))
    seen = {}

    class FakeReranker:
        @classmethod
        def add_custom_model(cls, model, sources, model_file, **kw):
            seen["registered"] = (model, sources.hf, model_file)

        def __init__(self, model_name, **kw):
            seen["loaded"] = (model_name, kw.get("cache_dir"))

        def rerank(self, query, docs):
            return iter([0.0] * len(docs))

    class FakeModule:
        TextCrossEncoder = FakeReranker

    import sys
    monkeypatch.setitem(sys.modules, "fastembed.rerank.cross_encoder", FakeModule)
    assert reranker.rerank_scores("q", ["d"]) == [0.5]
    assert seen["registered"] == (
        reranker.DEFAULT_MODEL, "Xenova/ms-marco-MiniLM-L-6-v2",
        "onnx/model_quantized.onnx")
    assert seen["loaded"] == (
        reranker.DEFAULT_MODEL, str(tmp_path / "legend-lore-rerank-q8"))


def _bundle(root, files=("config.json", "onnx/model_quantized.onnx")):
    """A models dir whose manifest lists ``files`` for the default model."""
    model_dir = root / "rerank" / "l6"
    (root / "manifest.json").write_text(json.dumps({"models": [{
        "role": "rerank", "name": reranker.DEFAULT_MODEL, "dir": "rerank/l6",
        "files": [{"path": f} for f in ("config.json", "onnx/model_quantized.onnx")],
    }]}))
    for f in files:
        (model_dir / f).parent.mkdir(parents=True, exist_ok=True)
        (model_dir / f).write_text("x")
    return model_dir


def test_bundled_dir_needs_every_listed_file(monkeypatch, tmp_path):
    """A shipped model counts only when all its manifest files are there."""
    monkeypatch.setenv("BUNDLED_MODELS_DIR", str(tmp_path))
    _bundle(tmp_path, files=("config.json",))
    assert reranker._bundled_dir(reranker.DEFAULT_MODEL) is None
    model_dir = _bundle(tmp_path)
    assert reranker._bundled_dir(reranker.DEFAULT_MODEL) == str(model_dir)
    assert reranker._bundled_dir("some/other-model") is None
    monkeypatch.delenv("BUNDLED_MODELS_DIR")
    assert reranker._bundled_dir(reranker.DEFAULT_MODEL) is None


def test_bundled_model_loads_from_disk_offline(monkeypatch, tmp_path):
    """With the files shipped, fastembed reads them in place: no download."""
    monkeypatch.delenv("RERANK_DISABLED", raising=False)
    monkeypatch.delenv("RERANK_MODEL", raising=False)
    monkeypatch.setenv("BUNDLED_MODELS_DIR", str(tmp_path))
    model_dir = _bundle(tmp_path)
    seen = {}

    class FakeReranker:
        @classmethod
        def add_custom_model(cls, *a, **kw):
            pass

        def __init__(self, model_name, **kw):
            seen.update(kw)

        def rerank(self, query, docs):
            return iter([0.0] * len(docs))

    class FakeModule:
        TextCrossEncoder = FakeReranker

    import sys
    monkeypatch.setitem(sys.modules, "fastembed.rerank.cross_encoder", FakeModule)
    assert reranker.rerank_scores("q", ["d"]) == [0.5]
    assert seen == {"specific_model_path": str(model_dir), "local_files_only": True}


REPO_MODELS = Path(__file__).resolve().parents[2] / "models"


@pytest.mark.skipif(
    not (REPO_MODELS / "rerank").is_dir(),
    reason="models/ not fetched (node scripts/fetch-models.mjs)",
)
def test_fetched_model_scores_offline(monkeypatch):
    """The real fetched files load through fastembed with the network off."""
    monkeypatch.delenv("RERANK_DISABLED", raising=False)
    monkeypatch.delenv("RERANK_MODEL", raising=False)
    monkeypatch.setenv("BUNDLED_MODELS_DIR", str(REPO_MODELS))
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    scores = reranker.rerank_scores(
        "how does grappling work",
        ["Grappling: when you want to grab a creature, you make a special melee attack.",
         "Coins come in copper, silver and gold pieces."],
    )
    assert scores is not None and scores[0] > scores[1]
