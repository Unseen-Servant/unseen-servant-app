"""System/game boost — the disambiguation lever (plan §3.4; cued scope).

When the query names a game system, the results from that system's source(s)
should win over other-system-same-topic hits. Detection is keyword matching over
the query text; the boost is a **stable soft-partition** (matched sources to the
front, order preserved, unmatched kept below as fallback) — never a hard filter,
so a mis-detection or a legitimately-elsewhere answer still surfaces.

The keyword→sources map is *data*, agnostic to origin: the eval builds it from
the corpus manifest + default aliases; production feeds it the user's tag keyword
lists (user-defined + defaults). No import from sidecar/.
"""
from __future__ import annotations

import re

_TERM = re.compile(r"[a-z0-9]+")


def _matches(keyword: str, query_lc: str) -> bool:
    # Multi-word or punctuated keyword ("basic fantasy", "d&d") → substring;
    # a bare single token ("cairn", "5e") → word boundary so it can't fire mid-word.
    if " " in keyword or any(not c.isalnum() and c != " " for c in keyword):
        return keyword in query_lc
    return re.search(rf"\b{re.escape(keyword)}\b", query_lc) is not None


def detect_sources(query: str, keyword_map: dict[str, set[str]]) -> set[str]:
    """Sources whose keyword appears in the query (union across matches)."""
    q = query.lower()
    hit: set[str] = set()
    for keyword, sources in keyword_map.items():
        if _matches(keyword, q):
            hit |= set(sources)
    return hit


def boost_order(ranked, source_of: dict, matched_sources: set[str]) -> list:
    """Stable soft-boost: ids from `matched_sources` move to the front keeping
    their relative order, the rest follow. No-op if nothing was detected."""
    if not matched_sources:
        return list(ranked)
    return sorted(ranked, key=lambda uid: 0 if source_of.get(uid) in matched_sources else 1)
