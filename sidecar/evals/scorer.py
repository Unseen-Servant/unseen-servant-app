"""Retrieval eval scorer — relevance judgment and rank metrics.

Ported from unseen-legend-lore-experiments/hybrid_retrieval_spike/score_retrieval.py
per the 2026-07-09 search-quality goal (Phase 2), with the grading rule
changed from page overlap to the specific answer chunk: a retrieved chunk
is relevant only if it comes from the expected source, its page range
overlaps a declared ground-truth range, AND its text contains all of the
query's answer anchors. Page overlap alone saturates (a wrong chunk from
the right page counted as a hit); the anchor requirement pins the metric
to the chunk that actually answers the query.

Metric definitions (binary relevance, per query, averaged per category):

- MRR@5        — 1/rank of the first relevant result in the top 5, else 0.
- precision@k  — fraction of the top k results that are relevant.
- recall@k     — 1 if any relevant result appears in the top k, else 0
                 (hit rate; the total number of relevant chunks per query
                 is unknown, so set-recall is not computable).
- nDCG@10      — DCG over the top 10 with binary gains, normalized by the
                 ideal DCG of the observed relevance vector (all retrieved
                 relevant results ranked first). 0 if nothing relevant
                 was retrieved.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict


def normalize(text: str) -> str:
    """Lowercase and collapse every run of non-alphanumeric chars to one space.

    Makes anchor matching robust to the layout differences between raw PDF
    text, markdown tables, and linearized table rows ("Armor Class:\n22",
    "|Armor Class:|22|", "Armor Class: 22" all normalize the same way).
    """
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def parse_pages(spec: str) -> list[tuple[int, int]]:
    """Parse single-range 'lo-hi' or multi-range 'lo-hi|lo-hi|...'."""
    out: list[tuple[int, int]] = []
    for piece in spec.split("|"):
        lo, hi = piece.split("-", 1)
        out.append((int(lo), int(hi)))
    return out


def _overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] <= b[1] and b[0] <= a[1]


def anchors_match(text: str, anchors: list) -> bool:
    """True if every anchor is present in the normalized text.

    Each anchor is either a string (must be a substring) or a list of
    alternative strings (at least one must be a substring).
    """
    haystack = f" {normalize(text)} "
    for anchor in anchors:
        alternatives = anchor if isinstance(anchor, list) else [anchor]
        if not any(f" {normalize(a)} " in haystack for a in alternatives):
            return False
    return True


def is_relevant(result: dict, query: dict) -> bool:
    """Judge one search result against one ground-truth query.

    ``result`` is an item from the production /api/search response
    (needs ``filename``, ``page_start``, ``page_end``, ``text``, and
    optionally ``section_heading``). ``query`` is a record from
    queries.yaml (``source``, ``pages``, ``answer`` anchors).

    Anchors are matched against the section-heading breadcrumb plus the
    chunk text — the same view the embedder and reranker score
    (``_embed_text`` prepends the heading) and the UI displays. Judging
    the body alone marks correctly retrieved sections irrelevant when
    the identifying phrase is the heading itself (e.g. a monster name
    above a stat block).
    """
    source = query["source"]
    if source not in (None, "", "any"):
        if not result["filename"].startswith(source):
            return False
    got = (int(result["page_start"]), int(result["page_end"]))
    if not any(_overlaps(got, e) for e in parse_pages(query["pages"])):
        return False
    judged_text = f"{result.get('section_heading', '')}\n{result['text']}"
    return anchors_match(judged_text, query["answer"])


# ---------------------------------------------------------------------------
# Rank metrics over a binary relevance vector (rank order, index 0 = rank 1)
# ---------------------------------------------------------------------------

def mrr_at(rels: list[bool], k: int = 5) -> float:
    for i, rel in enumerate(rels[:k]):
        if rel:
            return 1.0 / (i + 1)
    return 0.0


def precision_at(rels: list[bool], k: int) -> float:
    top = rels[:k]
    # A query that returned fewer than k results is still penalized:
    # missing slots count as non-relevant.
    return sum(top) / k


def recall_at(rels: list[bool], k: int) -> float:
    return 1.0 if any(rels[:k]) else 0.0


def ndcg_at(rels: list[bool], k: int = 10) -> float:
    top = rels[:k]
    dcg = sum(1.0 / math.log2(i + 2) for i, rel in enumerate(top) if rel)
    n_rel = sum(top)
    if n_rel == 0:
        return 0.0
    idcg = sum(1.0 / math.log2(i + 2) for i in range(n_rel))
    return dcg / idcg


def score_query(rels: list[bool]) -> dict[str, float]:
    """All Phase-2 metrics for one query's relevance vector."""
    return {
        "ndcg@10": ndcg_at(rels, 10),
        "mrr@5": mrr_at(rels, 5),
        "precision@5": precision_at(rels, 5),
        "precision@10": precision_at(rels, 10),
        "recall@5": recall_at(rels, 5),
        "recall@10": recall_at(rels, 10),
    }


METRIC_NAMES = ["ndcg@10", "mrr@5", "precision@5", "precision@10", "recall@5", "recall@10"]


def aggregate(per_query: list[dict]) -> dict[str, dict]:
    """Mean metrics per category plus 'all'.

    ``per_query`` items need ``category`` and ``metrics`` keys.
    """
    buckets: dict[str, list[dict]] = defaultdict(list)
    for entry in per_query:
        buckets[entry["category"]].append(entry["metrics"])
        buckets["all"].append(entry["metrics"])
    out: dict[str, dict] = {}
    for cat, rows in buckets.items():
        out[cat] = {
            "queries": len(rows),
            **{m: sum(r[m] for r in rows) / len(rows) for m in METRIC_NAMES},
        }
    return out


def format_report(summary: dict[str, dict]) -> str:
    """Fixed-width per-category metrics table."""
    cats = sorted(c for c in summary if c != "all") + ["all"]
    header = f"{'category':<14}{'queries':>8}" + "".join(f"{m:>14}" for m in METRIC_NAMES)
    lines = [header, "-" * len(header)]
    for cat in cats:
        row = summary[cat]
        lines.append(
            f"{cat:<14}{row['queries']:>8}"
            + "".join(f"{row[m]:>14.3f}" for m in METRIC_NAMES)
        )
    return "\n".join(lines)
