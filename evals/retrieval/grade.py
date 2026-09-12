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
import sys
from pathlib import Path

from evals.engines.base import SearchResponse, SearchResult

# leaf_title lives in sidecar/near_dup.py (roadmap 2.3). APPEND (never
# insert): both the repo root and sidecar/ contain a package named
# `evals`, and the top-level one — this harness — must keep winning the
# import race (same pattern as evals/engines/v2.py._import_sidecar).
sys.path.append(str(Path(__file__).resolve().parents[2] / "sidecar"))
from near_dup import leaf_title  # noqa: E402


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


BUDGET_CHARS = 8000  # the 4B-model context budget (roadmap §4 Phase 0.7 / Phase 2.2)


def top3_fits(response: SearchResponse, budget: int = BUDGET_CHARS) -> float:
    """1.0 when the top-3 results (heading + text) fit inside the budget.
    Tracks compactness before the Phase-2 packer exists, so 'payload shrank'
    and 'the answer still ships' are measured together."""
    top = response.results[:3]
    return 1.0 if sum(len(r.text) + len(r.section_heading) for r in top) <= budget else 0.0


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


def _allowed(doc_filename: str | set[str] | None) -> set[str] | None:
    """None = any file; a str = exactly that file; a set = any of those
    (edition twins such as SRD 5.1 / 5.2.1 for a 'dnd 5e' cue)."""
    if doc_filename is None:
        return None
    return {doc_filename} if isinstance(doc_filename, str) else set(doc_filename)


def is_relevant(result: SearchResult, query: dict, doc_filename: str | set[str] | None) -> bool:
    allowed = _allowed(doc_filename)
    if allowed is not None and result.filename not in allowed:
        return False
    return anchors_match(result.grading_text, query["anchors"])


def _matched_anchors(result: SearchResult, query: dict, doc_filename: str | set[str] | None) -> set[int]:
    allowed = _allowed(doc_filename)
    if allowed is not None and result.filename not in allowed:
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


def dup_titles_at(results: list[SearchResult], k: int = 10) -> int:
    """Cross-edition twins among the top k: a result whose `leaf_title`
    matches an earlier one's from a DIFFERENT file — the user-visible
    duplicate `dup_sections@10` cannot see, because it keys on the full
    breadcrumb and an SRD 5.1/5.2.1 twin never shares that key. An empty
    `leaf_title` (an un-headed result, a normal pipeline output) never
    counts — "" == "" is not "same leaf_title"."""
    top = results[:k]
    seen: list[tuple[str, str]] = []  # (leaf_title, filename) so far
    dups = 0
    for r in top:
        title = leaf_title(r.section_heading)
        if title and any(t == title and fn != r.filename for t, fn in seen):
            dups += 1
        seen.append((title, r.filename))
    return dups


def grade_response(response: SearchResponse, query: dict, doc_filename: str | set[str] | None) -> dict:
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
        "dup_titles@10": dup_titles_at(response.results, 10),
        "top3_fit@8k": top3_fits(response),
        # secondary: did the anchor-relevant hit also land on the GT page(s)?
        "page_hit": any(
            _page_hit(r, query.get("pages"))
            for r, rel in zip(response.results, rels)
            if rel
        ),
    }
