"""Fuse dense and lexical result lists (plan §3.4, ladder rung 5).

Reciprocal Rank Fusion: each ranker contributes w / (k_rrf + rank) to an item's
score, summed across rankers. Rank-based (not score-based) so the incompatible
cosine and BM25 scales never have to be reconciled. `weights` lets the harness
tune the dense/lexical balance; the hybrid on/off verdict (v2's BM25 NO-GO,
re-litigated) is decided by the Phase-0 harness. No import from sidecar/.
"""
from __future__ import annotations

from typing import Sequence

K_RRF = 60  # standard RRF damping — rank 0 ≈ 1/61, tail contributions decay slowly


def rrf(rankings: Sequence[Sequence[str]], weights: Sequence[float] | None = None,
        k_rrf: int = K_RRF) -> list[tuple[str, float]]:
    """Fuse ranked id-lists → (id, score) descending. Ties broken by id for
    determinism. An id present in only one ranker still appears."""
    weights = list(weights) if weights is not None else [1.0] * len(rankings)
    scores: dict[str, float] = {}
    for ranking, w in zip(rankings, weights):
        for rank, id_ in enumerate(ranking):
            scores[id_] = scores.get(id_, 0.0) + w / (k_rrf + rank + 1)
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
