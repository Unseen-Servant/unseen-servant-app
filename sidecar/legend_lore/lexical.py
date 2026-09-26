"""Persisted FTS5 lexical retrieval over the indexed chunks (S5 fixed 2026-09).

Backs the experimental, default-off ``hybrid`` flag on ``/api/search``
(BM25 re-test per the 2026-07-01 roadmap's REOPEN item): a BM25 ranking
over the same chunks is fused with the dense ranking via reciprocal-rank
fusion. The indexed text is the heading-prepended text — the same view
the embedder (``_embed_text``) and the reranker score — so the lexical
side gets the breadcrumb signal too (the prior spike fused a plain-BM25
index and never tested the heading-prepended one it built).

The rows live in the library store's ``unit_fts``, written in the same
transaction as the rest of a book (roadmap 1.6, S5). Nothing is built at
search time: the predecessor rebuilt an in-memory FTS5 table from a full
Chroma scan on the first hybrid search and again whenever the chunk
count changed, holding every document and metadata dict in RAM.
"""
from __future__ import annotations

import logging
import re

from .library_store import LibraryStore

logger = logging.getLogger(__name__)

RRF_K = 60  # standard reciprocal-rank-fusion constant

# RRF weight of the BM25 ranking against 1.0 for each dense ranking
# (roadmap 3.1; sidecar-v3 landed 0.3 — 1:1 cost natural-language
# queries). `SearchRequest.lex_weight` overrides it for eval sweeps.
LEXICAL_RRF_WEIGHT = 0.3

# BM25 top-M that joins the dense top-N in the hybrid rerank pool
# (union, not fused order: a down-weighted BM25-only hit can never
# rank into a fused top-N). `SearchRequest.lex_pool` overrides it.
LEXICAL_RERANK_POOL = 10

# Unicode word characters minus "_" — matches what FTS5's unicode61
# tokenizer treats as a token, so accented terms ("écran") stay whole.
_TOKEN_RE = re.compile(r"[^\W_]+")

# Question/function words carry no lexical signal and, OR'd in, let BM25
# rank chunks on "what"/"the" matches (ported from sidecar-v3's
# `_STOPWORDS`, roadmap 3.1).
_STOPWORDS = frozenset(
    "how what when where why who which whose whom does do did is are was were can "
    "could should would will may might have has a an the of to in for on at by from "
    "with as that this these those it its and or not you your they their he she his "
    "her we our i me my but if then than into about over under out up down off no".split())

# An index written before the rows existed has none: hybrid would then
# quietly degrade to dense-only. Warn the first time it happens, not on
# every query.
_EMPTY_STORE_WARNED = False


class PersistedLexicalIndex:
    """FTS5 rows live in the library store (``unit_fts``), written at
    index time; nothing is rebuilt at search time."""

    def __init__(self, store: LibraryStore) -> None:
        self._store = store

    def search(
        self, query: str, k: int, doc_ids: list[int] | None = None
    ) -> list[int]:
        """Top-k unit ids by BM25, best first.

        ``doc_ids`` is the dense query's scope (``None`` = whole library).

        An index written before the FTS rows existed has none, and hybrid
        would silently be dense-only — warn once per process. The count is
        only paid when a real query found nothing, since any hit already
        proves the table is populated.
        """
        match = fts_match(query)
        if not match:
            return []
        ids = self._store.fts(match, k, doc_ids)
        if not ids:
            self._warn_if_store_is_empty()
        return ids

    def _warn_if_store_is_empty(self) -> None:
        global _EMPTY_STORE_WARNED
        if _EMPTY_STORE_WARNED:
            return
        if self._store.count_units() == 0:
            _EMPTY_STORE_WARNED = True
            logger.warning(
                "unit_fts is empty — reindex to enable lexical search"
            )

    def lookup(self, ids: list[int]) -> dict[int, tuple[dict, str]]:
        """(metadata, text) for BM25-only hits; ids whose book was removed
        mid-search are simply absent."""
        return {
            uid: (unit.metadata, unit.text)
            for uid, unit in self._store.hydrate(ids).items()
        }


def fts_match(query: str) -> str:
    """Build an FTS5 MATCH expression from a free-text query.

    Query terms are OR'd: BM25's term weighting does the ranking, and
    requiring all terms would zero out any query with one word the chunk
    lacks. Stopwords are dropped unless the query is nothing but
    stopwords. Tokens are quoted so FTS5 operators in user text are
    literal.
    """
    tokens = _TOKEN_RE.findall(query)
    content = [t for t in tokens if t.lower() not in _STOPWORDS]
    return " OR ".join(f'"{t}"' for t in content or tokens)


def rrf_fuse(
    rankings: list[list[str]],
    weights: list[float] | None = None,
    k: int = RRF_K,
) -> list[tuple[str, float]]:
    """Weighted reciprocal-rank fusion: score(id) = Σ w/(k + rank).

    ``weights`` pairs with ``rankings`` (all 1.0 when omitted). Returns
    (id, score) pairs, best first. Ties keep the order ids were first
    seen (earlier rankings win), so fusion is deterministic.
    """
    if weights is None:
        weights = [1.0] * len(rankings)
    scores: dict[str, float] = {}
    for ranking, w in zip(rankings, weights):
        for rank, cid in enumerate(ranking):
            scores[cid] = scores.get(cid, 0.0) + w / (k + rank + 1)
    return sorted(scores.items(), key=lambda item: item[1], reverse=True)
