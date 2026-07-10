"""Unit tests for the retrieval eval scorer (evals/scorer.py).

CI-safe: pure metric math plus queries.yaml schema validation — no
Ollama, no corpus PDFs. The live eval run is a manual command
(see evals/README.md), not part of the test suite.
"""

import math
from pathlib import Path

import yaml

from evals import scorer

QUERIES_PATH = Path(__file__).parent.parent / "evals" / "queries.yaml"

CATEGORIES = {"stat_block", "table", "prose", "cross_page", "cross_system"}


# ---------------------------------------------------------------------------
# normalize / anchors
# ---------------------------------------------------------------------------

def test_normalize_collapses_layout_noise():
    assert scorer.normalize("Armor Class:\n22") == "armor class 22"
    assert scorer.normalize("|Armor Class:|22|") == "armor class 22"
    assert scorer.normalize("  Falling   Damage ") == "falling damage"


def test_anchors_all_of():
    text = "Goblin\nArmor Class: 14 (11)\nDamage: 1d6 or by weapon"
    assert scorer.anchors_match(text, ["goblin", "1d6 or by weapon"])
    assert not scorer.anchors_match(text, ["goblin", "2d8"])


def test_anchors_any_of_alternatives():
    text = "Dragon, Cloud — Armor Class: 22"
    assert scorer.anchors_match(text, [["cloud dragon", "dragon cloud"], "armor class 22"])
    assert not scorer.anchors_match(text, [["red dragon", "green dragon"]])


def test_anchor_matches_whole_words_only():
    # "22" must not match inside "220".
    assert not scorer.anchors_match("armor class 220", ["armor class 22"])


# ---------------------------------------------------------------------------
# is_relevant: source + page overlap + anchors
# ---------------------------------------------------------------------------

QUERY = {
    "text": "Goblin attack bonus and damage",
    "source": "Basic-Fantasy",
    "pages": "115-130|108-109",
    "category": "stat_block",
    "answer": ["goblin", "1d6 or by weapon"],
}


def _result(**over):
    base = {
        "filename": "Basic-Fantasy-RPG-Rules-r142.pdf",
        "page_start": 108,
        "page_end": 109,
        "section_heading": "",
        "text": "Goblin\nArmor Class: 14 (11)\nDamage: 1d6 or by weapon",
    }
    base.update(over)
    return base


def test_relevant_hit():
    assert scorer.is_relevant(_result(), QUERY)


def test_anchor_in_section_heading_counts():
    # The identifying phrase is often the section heading (monster name,
    # rule heading) rather than body text — the judge sees heading + text,
    # mirroring what the embedder and reranker score.
    r = _result(
        section_heading="PART 6:  MONSTERS > Goblin",
        text="Armor Class: 14 (11)\nDamage: 1d6 or by weapon",
    )
    assert scorer.is_relevant(r, QUERY)


def test_wrong_source_rejected():
    assert not scorer.is_relevant(_result(filename="SRD_CC_v5.1.pdf"), QUERY)


def test_page_overlap_alone_is_not_enough():
    # Right pages, wrong content — the page-overlap metric would have
    # counted this; answer-chunk grading must not.
    assert not scorer.is_relevant(_result(text="Gnoll\nDamage: 2d4"), QUERY)


def test_answer_text_outside_declared_pages_rejected():
    assert not scorer.is_relevant(_result(page_start=200, page_end=201), QUERY)


def test_multi_range_pages():
    assert scorer.is_relevant(_result(page_start=115, page_end=116), QUERY)


def test_source_any_skips_source_check():
    q = dict(QUERY, source="any", pages="108-109")
    assert scorer.is_relevant(_result(filename="whatever.pdf"), q)


# ---------------------------------------------------------------------------
# metrics
# ---------------------------------------------------------------------------

def test_mrr_at_5():
    assert scorer.mrr_at([False, True, False], 5) == 0.5
    assert scorer.mrr_at([False] * 5 + [True], 5) == 0.0
    assert scorer.mrr_at([], 5) == 0.0


def test_precision_at_k_counts_missing_slots_as_misses():
    assert scorer.precision_at([True, True], 5) == 2 / 5
    assert scorer.precision_at([True] * 10, 10) == 1.0


def test_recall_at_k_is_hit_rate():
    assert scorer.recall_at([False, False, True], 5) == 1.0
    assert scorer.recall_at([False, False, True], 2) == 0.0


def test_ndcg_perfect_ranking_is_1():
    assert scorer.ndcg_at([True, True, False, False], 10) == 1.0


def test_ndcg_penalizes_late_hits():
    late = scorer.ndcg_at([False, False, True], 10)
    assert 0 < late < 1
    # Ideal: the hit at rank 1 → DCG 1/log2(3), IDCG 1/log2(2).
    assert math.isclose(late, (1 / math.log2(4)) / 1.0)


def test_ndcg_no_hits_is_0():
    assert scorer.ndcg_at([False] * 10, 10) == 0.0
    assert scorer.ndcg_at([], 10) == 0.0


def test_aggregate_per_category_and_all():
    per_query = [
        {"category": "table", "metrics": scorer.score_query([True])},
        {"category": "table", "metrics": scorer.score_query([False])},
        {"category": "prose", "metrics": scorer.score_query([True])},
    ]
    summary = scorer.aggregate(per_query)
    assert summary["table"]["queries"] == 2
    assert summary["table"]["mrr@5"] == 0.5
    assert summary["all"]["queries"] == 3
    assert math.isclose(summary["all"]["recall@5"], 2 / 3)


def test_format_report_has_all_metrics_and_categories():
    per_query = [
        {"category": "prose", "metrics": scorer.score_query([True])},
        {"category": "stat_block", "metrics": scorer.score_query([False, True])},
    ]
    report = scorer.format_report(scorer.aggregate(per_query))
    for name in scorer.METRIC_NAMES:
        assert name in report
    for cat in ("prose", "stat_block", "all"):
        assert cat in report


# ---------------------------------------------------------------------------
# queries.yaml ground truth sanity
# ---------------------------------------------------------------------------

def _queries():
    return yaml.safe_load(QUERIES_PATH.read_text())["queries"]


def test_queries_yaml_schema():
    queries = _queries()
    assert len(queries) == 40
    for q in queries:
        assert q["category"] in CATEGORIES, q["text"]
        assert isinstance(q["text"], str) and q["text"]
        ranges = scorer.parse_pages(q["pages"])
        assert all(lo <= hi and lo >= 1 for lo, hi in ranges), q["text"]
        assert q["answer"], f"missing answer anchors: {q['text']}"
        for anchor in q["answer"]:
            alts = anchor if isinstance(anchor, list) else [anchor]
            for a in alts:
                # Anchors must already be in normalized form.
                assert a == scorer.normalize(a), f"non-normalized anchor {a!r} in {q['text']}"


def test_queries_yaml_category_counts_match_spike():
    queries = _queries()
    counts = {}
    for q in queries:
        counts[q["category"]] = counts.get(q["category"], 0) + 1
    assert counts == {
        "stat_block": 6, "table": 10, "prose": 11,
        "cross_page": 3, "cross_system": 10,
    }
