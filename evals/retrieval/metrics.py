"""Rank + cost metrics over binary relevance vectors.

Ported from sidecar/evals/scorer.py so the shared srd_5_1 slice stays
comparable to the old baselines, with the scaffold's additions (§2):
precision@3 as the headline, plus per-response cost metrics (payload
chars, duplicate sections@10) folded into the aggregate.

A relevance vector ``rels`` is a list of bools in rank order (index 0 =
rank 1). Judging (which result is relevant) lives in grade.py; this
module is pure arithmetic.
"""
from __future__ import annotations

import math
from collections import defaultdict

# Rank metrics reported per category/style. precision@3 leads (§2 headline).
RANK_METRICS = ["precision@3", "ndcg@10", "mrr@5", "recall@5", "recall@10"]
# Cost metrics averaged alongside them (from the SearchResponse, not rels).
COST_METRICS = ["payload_chars", "dup_sections@10"]


def mrr_at(rels: list[bool], k: int = 5) -> float:
    for i, rel in enumerate(rels[:k]):
        if rel:
            return 1.0 / (i + 1)
    return 0.0


def precision_at(rels: list[bool], k: int) -> float:
    """Fraction of the top k that are relevant; missing slots count against."""
    return sum(rels[:k]) / k


def recall_at(rels: list[bool], k: int) -> float:
    """Hit rate: 1 if any relevant result in the top k (total relevant per
    query is unknown, so set-recall is not computable)."""
    return 1.0 if any(rels[:k]) else 0.0


def ndcg_at(rels: list[bool], k: int = 10) -> float:
    top = rels[:k]
    dcg = sum(1.0 / math.log2(i + 2) for i, rel in enumerate(top) if rel)
    n_rel = sum(top)
    if n_rel == 0:
        return 0.0
    idcg = sum(1.0 / math.log2(i + 2) for i in range(n_rel))
    return dcg / idcg


def rank_metrics(rels: list[bool]) -> dict[str, float]:
    return {
        "precision@3": precision_at(rels, 3),
        "ndcg@10": ndcg_at(rels, 10),
        "mrr@5": mrr_at(rels, 5),
        "recall@5": recall_at(rels, 5),
        "recall@10": recall_at(rels, 10),
    }


def aggregate(per_query: list[dict], key: str = "category") -> dict[str, dict]:
    """Mean of every metric per bucket (by ``key``) plus an 'all' bucket.

    Each ``per_query`` entry needs the bucket key and a flat ``metrics``
    dict holding RANK_METRICS + COST_METRICS.
    """
    buckets: dict[str, list[dict]] = defaultdict(list)
    for e in per_query:
        buckets[e[key]].append(e["metrics"])
        buckets["all"].append(e["metrics"])
    metrics = RANK_METRICS + COST_METRICS
    out: dict[str, dict] = {}
    for bucket, rows in buckets.items():
        out[bucket] = {"queries": len(rows)}
        for m in metrics:
            out[bucket][m] = sum(r[m] for r in rows) / len(rows)
    return out


def latency_stats(latencies_ms: list[float]) -> dict[str, float]:
    """mean / p50 / p95 (nearest-rank, always an observed value)."""
    n = len(latencies_ms)
    if n == 0:
        return {"count": 0, "mean_ms": 0.0, "p50_ms": 0.0, "p95_ms": 0.0}
    o = sorted(latencies_ms)
    mid = n // 2
    p50 = o[mid] if n % 2 else (o[mid - 1] + o[mid]) / 2
    return {
        "count": n,
        "mean_ms": sum(o) / n,
        "p50_ms": p50,
        "p95_ms": o[math.ceil(0.95 * n) - 1],
    }


def format_report(summary: dict[str, dict], title: str = "category") -> str:
    metrics = RANK_METRICS + COST_METRICS
    cats = sorted(c for c in summary if c != "all") + ["all"]
    widths = {"precision@3": 12, "ndcg@10": 9, "mrr@5": 8, "recall@5": 9,
              "recall@10": 10, "payload_chars": 15, "dup_sections@10": 16}

    def cell(m: str, v: float) -> str:
        return f"{int(round(v)):>{widths[m]}}" if m == "payload_chars" else f"{v:>{widths[m]}.3f}"

    header = f"{title:<16}{'queries':>8}" + "".join(f"{m:>{widths[m]}}" for m in metrics)
    lines = [header, "-" * len(header)]
    for cat in cats:
        row = summary[cat]
        lines.append(f"{cat:<16}{row['queries']:>8}" + "".join(cell(m, row[m]) for m in metrics))
    return "\n".join(lines)
