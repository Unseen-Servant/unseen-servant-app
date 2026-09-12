"""The v2 adapter's response mapping.

Since roadmap 2.1 the sidecar answers a hit with the assembled section in
``text`` and names the unit that matched in ``matched_text``; the adapter
must carry that through without touching graded text. Driven against a
stub client so the test needs neither the sidecar env nor Ollama.
"""
from evals.engines.base import SearchOptions, SearchResult
from evals.engines.v2 import V2Engine


class _StubResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _StubClient:
    def __init__(self, payload):
        self._payload = payload

    def post(self, path, json=None):
        return _StubResponse(self._payload)


def _engine(results):
    engine = V2Engine()
    engine._client = _StubClient({"results": results})
    return engine


def test_matched_text_defaults_to_empty_for_an_engine_that_omits_it():
    assert SearchResult(
        text="t", filename="f", source="s", section_heading="h",
        page_start=1, page_end=1, relevance=1.0, tier="strong", reranked=False,
    ).matched_text == ""


def test_search_carries_matched_text_and_leaves_grading_text_alone():
    engine = _engine([{
        "text": "Kraken. AC 18.\n\nInk cloud.",
        "filename": "SRD.pdf",
        "source": "/corpus/SRD.pdf",
        "section_heading": "Monsters > Kraken",
        "page_start": 324,
        "page_end": 325,
        "relevance": 0.8,
        "tier": "strong",
        "reranked": False,
        "matched_text": "Tentacle attack text",
    }])
    result = engine.search("kraken", SearchOptions()).results[0]
    assert result.matched_text == "Tentacle attack text"
    assert result.grading_text == "Monsters > Kraken\nKraken. AC 18.\n\nInk cloud."


def test_a_result_without_matched_text_maps_to_empty_string():
    engine = _engine([{"text": "body", "section_heading": "h"}])
    assert engine.search("kraken", SearchOptions()).results[0].matched_text == ""
