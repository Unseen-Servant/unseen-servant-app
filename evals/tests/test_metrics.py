"""Pinned values for the rank and latency arithmetic every GO/NO-GO reads.

`rels` is a list of bools in rank order (index 0 = rank 1).
"""
import math

import pytest

from evals.retrieval.metrics import (
    COST_METRICS,
    RANK_METRICS,
    aggregate,
    latency_stats,
    mrr_at,
    ndcg_at,
    rank_metrics,
    recall_at,
)

F, T = False, True


@pytest.mark.parametrize("rels, expected", [
    ([T, F, F], 1.0),
    ([F, F, T], 1 / 3),
    ([F, T, T], 1 / 2),        # first relevant counts, not the best
    ([F, F, F, F, F, T], 0.0),  # rank 6 is outside @5
    ([], 0.0),
])
def test_mrr_at_5(rels, expected):
    assert mrr_at(rels, 5) == pytest.approx(expected)


@pytest.mark.parametrize("rels, k, expected", [
    ([F, F, T], 3, 1.0),
    ([F, F, F, T], 3, 0.0),
    ([T, T, T], 3, 1.0),       # a hit rate, not a count
    ([], 3, 0.0),
])
def test_recall_at_is_a_hit_rate(rels, k, expected):
    assert recall_at(rels, k) == expected


def test_ndcg_is_one_when_relevant_results_lead():
    assert ndcg_at([T, T, F], 10) == pytest.approx(1.0)


def test_ndcg_discounts_by_log2_of_rank():
    # One relevant result at rank 2: (1/log2 3) / (1/log2 2).
    assert ndcg_at([F, T], 10) == pytest.approx(1 / math.log2(3))
    # Ranks 1 and 3 against an ideal of ranks 1 and 2.
    expected = (1 + 1 / math.log2(4)) / (1 + 1 / math.log2(3))
    assert ndcg_at([T, F, T], 10) == pytest.approx(expected)


def test_ndcg_ideal_counts_only_relevant_results_retrieved_in_the_top_k():
    # The total number of relevant chunks per query is unknown, so the
    # ideal ranking is built from those retrieved: one hit at rank 1 is a
    # perfect 1.0 however many other relevant chunks the library holds.
    # Changing this changes every baseline — do it on purpose.
    assert ndcg_at([T, F, F], 10) == pytest.approx(1.0)
    assert ndcg_at([F] * 10 + [T], 10) == 0.0   # rank 11 is outside @10


def test_rank_metrics_reports_every_rank_metric():
    assert set(rank_metrics([F, T])) == set(RANK_METRICS)


def _row(bucket: str, value: float) -> dict:
    return {"category": bucket, "metrics": {m: value for m in RANK_METRICS + COST_METRICS}}


def test_aggregate_means_per_bucket_and_over_all():
    out = aggregate([_row("a", 1.0), _row("a", 0.0), _row("b", 0.5)])

    assert out["a"]["queries"] == 2 and out["a"]["mrr@5"] == pytest.approx(0.5)
    assert out["b"]["queries"] == 1 and out["b"]["mrr@5"] == pytest.approx(0.5)
    assert out["all"]["queries"] == 3


def test_aggregate_all_is_the_mean_over_queries_not_over_buckets():
    out = aggregate([_row("a", 1.0), _row("a", 1.0), _row("b", 0.0)])
    assert out["all"]["mrr@5"] == pytest.approx(2 / 3)   # buckets' mean: 0.5


def test_latency_stats_odd_count():
    s = latency_stats([30.0, 10.0, 20.0])
    assert s == {"count": 3, "mean_ms": 20.0, "p50_ms": 20.0, "p95_ms": 30.0}


def test_latency_stats_even_count_averages_the_middle_pair():
    assert latency_stats([10.0, 20.0, 30.0, 40.0])["p50_ms"] == 25.0


def test_latency_p95_is_nearest_rank_an_observed_value():
    samples = [float(i) for i in range(1, 21)]  # 1..20
    assert latency_stats(samples)["p95_ms"] == 19.0  # ceil(0.95 * 20) = 19th


def test_latency_stats_empty():
    assert latency_stats([]) == {"count": 0, "mean_ms": 0.0, "p50_ms": 0.0, "p95_ms": 0.0}
