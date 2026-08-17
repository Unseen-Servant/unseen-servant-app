"""Phase 3 rung 5 — Reciprocal Rank Fusion of dense + lexical rankings (plan
§3.4). Pure over id-lists; no store/model needed."""
from query.fuse import rrf


def test_rrf_ranks_item_top_of_both_first():
    fused = rrf([["a", "b", "c"], ["a", "d", "e"]])
    assert fused[0][0] == "a"  # top of both rankers → highest fused score


def test_rrf_surfaces_item_from_only_one_ranker():
    ids = [i for i, _ in rrf([["a", "b"], ["c"]])]
    assert "c" in ids  # a lexical-only hit still appears in the fused list


def test_rrf_weights_bias_toward_heavier_ranker():
    fused = rrf([["a"], ["b"]], weights=[1.0, 3.0])
    assert fused[0][0] == "b"  # heavier ranker's top wins when items are disjoint


def test_rrf_scores_descending_and_deterministic():
    fused = rrf([["a", "b"], ["b", "a"]])
    assert [s for _, s in fused] == sorted((s for _, s in fused), reverse=True)
    assert set(i for i, _ in fused) == {"a", "b"}
