"""Unit tests for the reranker module — model load is mocked or disabled."""

import os

import pytest

import reranker


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
