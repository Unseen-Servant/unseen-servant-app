"""Extraction-QA grading on golden pages (§2 of the v3 scaffold).

Three metrics per golden page, graded on the engine's per-page extraction
(what feeds indexing) against hand-authored, ref+PDF-verified specs:

- content_recall  — fraction of expected phrases that survived extraction.
- reading_order   — of the ordered fragments found, how many adjacent pairs
                    are in the right order (catches the "sentences
                    interleaved out of order → confidently wrong" failure).
- table_cells     — fraction of expected cells present *contiguously*
                    (catches header/value splitting and cell mangling).

Normalization matches the retrieval grader (token-boundary), so a phrase
must appear as whole tokens, not a substring of a longer word.
"""
from __future__ import annotations

from collections import defaultdict

from evals.retrieval.grade import normalize

METRICS = ["content_recall", "reading_order", "table_cells"]


def _wrapped(text: str) -> str:
    return f" {normalize(text)} "


def _present(text_wrapped: str, phrase) -> bool:
    """True if the phrase (str, or any-of list) appears as a contiguous
    token-boundary substring of the already-normalized+wrapped text."""
    alts = phrase if isinstance(phrase, list) else [phrase]
    return any(f" {normalize(a)} " in text_wrapped for a in alts)


def content_recall(text: str, phrases: list) -> float:
    w = _wrapped(text)
    return sum(_present(w, p) for p in phrases) / len(phrases)


def table_cells(text: str, cells: list) -> float:
    w = _wrapped(text)
    return sum(_present(w, c) for c in cells) / len(cells)


def reading_order(text: str, fragments: list) -> float | None:
    """1 − inversions / C(n_found, 2) over the fragments found, by their
    position in the extraction. None if <2 found (order is undefined —
    content_recall already accounts for the missing text)."""
    w = _wrapped(text)
    positions = []
    for frag in fragments:
        f = f" {normalize(frag) if not isinstance(frag, list) else normalize(frag[0])} "
        i = w.find(f)
        if i >= 0:
            positions.append(i)
    n = len(positions)
    if n < 2:
        return None
    inversions = sum(
        1 for a in range(n) for b in range(a + 1, n) if positions[a] > positions[b]
    )
    return 1.0 - inversions / (n * (n - 1) / 2)


def grade_page(spec: dict, page_text: str) -> dict:
    """Score one golden page. Absent metrics (no spec) are omitted; a
    reading_order that can't be scored is None."""
    out = {"id": spec["id"], "doc": spec["doc"], "page": spec["page"], "kind": spec["kind"]}
    if spec.get("content"):
        out["content_recall"] = content_recall(page_text, spec["content"])
    if spec.get("order"):
        out["reading_order"] = reading_order(page_text, spec["order"])
    if spec.get("cells"):
        out["table_cells"] = table_cells(page_text, spec["cells"])
    return out


def aggregate(graded: list[dict], key: str = "kind") -> dict[str, dict]:
    """Mean of each metric per bucket (by ``key``) plus 'all'; None values
    (unscorable reading_order) are excluded from that metric's mean."""
    buckets: dict[str, list[dict]] = defaultdict(list)
    for g in graded:
        buckets[g[key]].append(g)
        buckets["all"].append(g)
    out: dict[str, dict] = {}
    for bucket, rows in buckets.items():
        entry = {"pages": len(rows)}
        for m in METRICS:
            vals = [r[m] for r in rows if r.get(m) is not None]
            entry[m] = sum(vals) / len(vals) if vals else None
        out[bucket] = entry
    return out
