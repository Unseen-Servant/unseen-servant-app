"""Relevance judging — anchor-in-chunk grading (§3).

Change from the old scorer: §3 makes ``pages`` a *secondary* check, never
the primary signal. A result is relevant when

  1. every anchor matches its heading+body text (the view the embedder and
     reranker score, and the UI shows), and
  2. it comes from the query's ``doc`` (unless ``doc: any``).

Pages are recorded as a soft cross-check, not a gate. Anchor matching and
normalization are identical to sidecar/evals/scorer.py so the shared
srd_5_1 slice stays comparable.
"""
from __future__ import annotations

import re

from evals.engines.base import SearchResponse, SearchResult


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def anchors_match(text: str, anchors: list) -> bool:
    """Every anchor present; an anchor that is a list means any-of."""
    haystack = f" {normalize(text)} "
    for anchor in anchors:
        alts = anchor if isinstance(anchor, list) else [anchor]
        if not any(f" {normalize(a)} " in haystack for a in alts):
            return False
    return True


def matched_anchor_indexes(text: str, anchors: list) -> set[int]:
    """Return the query facts supplied by one evidence unit."""
    haystack = f" {normalize(text)} "
    matched: set[int] = set()
    for i, anchor in enumerate(anchors):
        alts = anchor if isinstance(anchor, list) else [anchor]
        if any(f" {normalize(a)} " in haystack for a in alts):
            matched.add(i)
    return matched


def _page_hit(result: SearchResult, pages: str | None) -> bool:
    """Soft check: does the result's page range overlap the declared range?"""
    if not pages or result.page_start is None:
        return False
    got = (result.page_start, result.page_end or result.page_start)
    for piece in str(pages).split("|"):
        lo, _, hi = piece.partition("-")
        try:
            rng = (int(lo), int(hi or lo))
        except ValueError:
            continue
        if got[0] <= rng[1] and rng[0] <= got[1]:
            return True
    return False


def is_relevant(result: SearchResult, query: dict, doc_filename: str | None) -> bool:
    if doc_filename is not None and result.filename != doc_filename:
        return False
    return anchors_match(result.grading_text, query["anchors"])


def _matched_anchors(result: SearchResult, query: dict, doc_filename: str | None) -> set[int]:
    if doc_filename is not None and result.filename != doc_filename:
        return set()
    return matched_anchor_indexes(result.grading_text, query["anchors"])


def dup_sections_at(results: list[SearchResult], k: int = 10) -> int:
    """Repeated (file, section) among the top k — a redundancy/cost signal."""
    top = results[:k]
    seen: set[tuple[str, str]] = set()
    dups = 0
    for r in top:
        key = (r.filename, r.section_heading)
        if key in seen:
            dups += 1
        else:
            seen.add(key)
    return dups


def grade_response(response: SearchResponse, query: dict, doc_filename: str | None) -> dict:
    """Judge one response: the relevance vector plus cost signals."""
    if query.get("category") == "cross_page":
        # A cross-page answer is complete when the retrieved evidence set
        # covers every required fact, even when no single unit contains them.
        covered: set[int] = set()
        rels = []
        for result in response.results:
            covered.update(_matched_anchors(result, query, doc_filename))
            rels.append(len(covered) == len(query["anchors"]))
    else:
        rels = [is_relevant(r, query, doc_filename) for r in response.results]
    return {
        "rels": rels,
        "payload_chars": response.payload_chars,
        "dup_sections@10": dup_sections_at(response.results, 10),
        # secondary: did the anchor-relevant hit also land on the GT page(s)?
        "page_hit": any(
            _page_hit(r, query.get("pages"))
            for r, rel in zip(response.results, rels)
            if rel
        ),
    }
