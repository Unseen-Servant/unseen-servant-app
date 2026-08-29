"""Answer-evidence grading, including multi-unit cross-page answers."""
from evals.engines.base import SearchResponse, SearchResult
from evals.retrieval.grade import grade_response
from evals.retrieval.verify_anchors import _declared_pages


def _result(text: str) -> SearchResult:
    return SearchResult(
        text=text, filename="SRD.pdf", source="SRD", section_heading="Kraken",
        page_start=324, page_end=324, relevance=1.0, tier="strong", reranked=False,
    )


def test_cross_page_answer_completes_when_facts_are_in_separate_results():
    query = {
        "category": "cross_page",
        "anchors": ["kraken", "armor class 18", "ink cloud"],
        "pages": "324-325",
    }
    response = SearchResponse(results=[
        _result("Kraken. Armor Class 18 (natural armor)."),
        _result("Ink Cloud. The kraken creates a cloud of ink."),
    ], latency_ms=1.0)
    assert grade_response(response, query, "SRD.pdf")["rels"] == [False, True]


def test_cross_page_answer_respects_source_scope():
    query = {"category": "cross_page", "anchors": ["kraken", "ink cloud"]}
    response = SearchResponse(results=[_result("Kraken Ink Cloud")], latency_ms=1.0)
    assert grade_response(response, query, "Other.pdf")["rels"] == [False]


def test_declared_pages_support_multiple_ranges():
    assert _declared_pages("4-5|9") == {4, 5, 9}
