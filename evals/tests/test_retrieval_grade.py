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


def _from(filename: str, text: str) -> SearchResult:
    return SearchResult(
        text=text, filename=filename, source=filename, section_heading="Magic Missile",
        page_start=1, page_end=1, relevance=1.0, tier="strong", reranked=False,
    )


def test_doc_set_accepts_any_listed_file():
    query = {"category": "exact_name", "anchors": ["magic missile", "1d4 1"]}
    response = SearchResponse(results=[
        _from("OSRIC.pdf", "magic missile 1d4 1"),
        _from("SRD_CC_v5.2.1.pdf", "magic missile 1d4 1"),
        _from("SRD_CC_v5.1.pdf", "magic missile 1d4 1"),
    ], latency_ms=1.0)
    rels = grade_response(response, query, {"SRD_CC_v5.1.pdf", "SRD_CC_v5.2.1.pdf"})["rels"]
    assert rels == [False, True, True]


def test_doc_string_still_means_exactly_one_file():
    query = {"category": "exact_name", "anchors": ["magic missile"]}
    response = SearchResponse(results=[_from("SRD_CC_v5.2.1.pdf", "magic missile")], latency_ms=1.0)
    assert grade_response(response, query, "SRD_CC_v5.1.pdf")["rels"] == [False]


from evals.retrieval import metrics
from evals.retrieval.grade import BUDGET_CHARS, top3_fits


def test_top3_fits_when_three_results_fit_the_budget():
    response = SearchResponse(results=[_result("a" * 2000)] * 3 + [_result("b" * 9000)], latency_ms=1.0)
    assert top3_fits(response) == 1.0


def test_top3_does_not_fit_when_the_third_result_overflows():
    response = SearchResponse(results=[_result("a" * 3000), _result("a" * 3000), _result("a" * 3000)],
                              latency_ms=1.0)
    assert top3_fits(response) == 0.0


def test_grade_response_reports_the_budget_column():
    query = {"category": "prose_rule", "anchors": ["kraken"]}
    response = SearchResponse(results=[_result("Kraken")], latency_ms=1.0)
    g = grade_response(response, query, None)
    assert g["top3_fit@8k"] == 1.0
    assert "top3_fit@8k" in metrics.COST_METRICS
    assert BUDGET_CHARS == 8000


from evals.retrieval.grade import dup_titles_at


def test_dup_titles_at_counts_a_cross_edition_repeat():
    assert dup_titles_at([
        _from("SRD_5.1.pdf", "text"), _from("SRD_5.2.1.pdf", "text"),
    ]) == 1


def test_dup_titles_at_ignores_same_file_repeats():
    assert dup_titles_at([
        _from("SRD_5.1.pdf", "text"), _from("SRD_5.1.pdf", "text"),
    ]) == 0


def _unheaded(filename: str) -> SearchResult:
    return SearchResult(
        text="text", filename=filename, source=filename, section_heading="",
        page_start=1, page_end=1, relevance=1.0, tier="strong", reranked=False,
    )


def test_dup_titles_at_never_counts_an_empty_leaf_title():
    """"" == "" is not "same leaf_title" — two un-headed results from
    different files must never count as a duplicate."""
    assert dup_titles_at([_unheaded("A.pdf"), _unheaded("B.pdf")]) == 0
