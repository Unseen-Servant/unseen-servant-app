"""Persisted FTS5 lexical retrieval over the indexed chunks (S5 fixed 2026-09).

Backs the experimental, default-off ``hybrid`` flag on ``/api/search``
(BM25 re-test per the 2026-07-01 roadmap's REOPEN item): a BM25 ranking
over the same chunks is fused with the dense ranking via reciprocal-rank
fusion. The indexed text is the heading-prepended text — the same view
the embedder (``_embed_text``) and the reranker score — so the lexical
side gets the breadcrumb signal too (the prior spike fused a plain-BM25
index and never tested the heading-prepended one it built).

The rows live in ``parents_store.unit_fts``, written per document inside
the same swap as the Chroma upsert (roadmap 1.6, S5). Nothing is built
at search time: the predecessor rebuilt an in-memory FTS5 table from a
full Chroma scan on the first hybrid search and again whenever the chunk
count changed, holding every document and metadata dict in RAM.
"""
from __future__ import annotations

import logging
import re

from parents_store import count_units_fts, search_units_fts

logger = logging.getLogger(__name__)

RRF_K = 60  # standard reciprocal-rank-fusion constant

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")

# An index written before the rows existed has none: hybrid would then
# quietly degrade to dense-only. Warn the first time it happens, not on
# every query.
_EMPTY_STORE_WARNED = False


class PersistedLexicalIndex:
    """FTS5 rows live in the parents SQLite (parents_store.unit_fts),
    written at index time; nothing is rebuilt at search time."""

    def __init__(self, data_dir, collection) -> None:
        self._data_dir = data_dir
        self._collection = collection

    def search(self, query: str, k: int, where: dict | None = None) -> list[str]:
        """Top-k chunk ids by BM25, best first.

        ``where`` mirrors the dense query's scope and applies as SQL over
        the FTS table's metadata columns.

        An index written before the FTS rows existed has none, and hybrid
        would silently be dense-only — warn once per process. The count is
        only paid when a real query found nothing, since any hit already
        proves the table is populated.
        """
        match = fts_match(query)
        if not match:
            return []
        ids = search_units_fts(self._data_dir, match, k, where)
        if not ids:
            self._warn_if_store_is_empty()
        return ids

    def _warn_if_store_is_empty(self) -> None:
        global _EMPTY_STORE_WARNED
        if _EMPTY_STORE_WARNED or not self._data_dir:
            return
        if count_units_fts(self._data_dir) == 0:
            _EMPTY_STORE_WARNED = True
            logger.warning(
                "unit_fts is empty — reindex to enable lexical search"
            )

    def lookup(self, ids: list[str]) -> dict[str, tuple[dict, str]]:
        """Fetch (metadata, document) from Chroma for BM25-only hits.

        One ``get`` by id — ids whose Chroma twin vanished mid-reindex are
        simply absent from the result.
        """
        if not ids:
            return {}
        got = self._collection.get(ids=ids, include=["metadatas", "documents"])
        return {
            cid: (meta, doc)
            for cid, meta, doc in zip(
                got["ids"], got["metadatas"], got["documents"]
            )
        }


def fts_match(query: str) -> str:
    """Build an FTS5 MATCH expression from a free-text query.

    Query terms are OR'd: BM25's term weighting does the ranking, and
    requiring all terms would zero out any query with one word the chunk
    lacks. Tokens are quoted so FTS5 operators in user text are literal.
    """
    tokens = _TOKEN_RE.findall(query)
    return " OR ".join(f'"{t}"' for t in tokens)


def rrf_fuse(rankings: list[list[str]], k: int = RRF_K) -> list[tuple[str, float]]:
    """Reciprocal-rank fusion: score(id) = Σ 1/(k + rank) over rankings.

    Returns (id, score) pairs, best first. Ties keep the order ids were
    first seen (earlier rankings win), so fusion is deterministic.
    """
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, cid in enumerate(ranking):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda item: item[1], reverse=True)
