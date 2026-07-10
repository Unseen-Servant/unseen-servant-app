"""In-memory BM25 lexical index over the indexed chunks.

Backs the experimental, default-off ``hybrid`` flag on ``/api/search``
(BM25 re-test per the 2026-07-01 roadmap's REOPEN item): a BM25 ranking
over the same chunks is fused with the dense ranking via reciprocal-rank
fusion. The index stores the heading-prepended text — the same view the
embedder (``_embed_text``) and the reranker score — so the lexical side
gets the breadcrumb signal too (the prior spike fused a plain-BM25 index
and never tested the heading-prepended one it built).

Pure stdlib: sqlite3 FTS5 with the porter/unicode61 tokenizer, held in
memory. No ML dependencies, millisecond queries at library scale.
"""
from __future__ import annotations

import re
import sqlite3

RRF_K = 60  # standard reciprocal-rank-fusion constant

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


class LexicalIndex:
    """BM25 index over chunk texts, queryable by chunk id."""

    def __init__(self) -> None:
        self._db = sqlite3.connect(":memory:", check_same_thread=False)
        self._db.execute(
            "CREATE VIRTUAL TABLE chunks USING "
            "fts5(chunk_id UNINDEXED, text, tokenize='porter unicode61')"
        )
        self.metadatas: dict[str, dict] = {}
        self.documents: dict[str, str] = {}

    def add(self, chunk_id: str, document: str, metadata: dict | None) -> None:
        metadata = metadata or {}
        heading = metadata.get("section_heading") or ""
        indexed = f"{heading}\n\n{document}" if heading else document
        self._db.execute(
            "INSERT INTO chunks (chunk_id, text) VALUES (?, ?)",
            (chunk_id, indexed),
        )
        self.metadatas[chunk_id] = metadata
        self.documents[chunk_id] = document

    @classmethod
    def from_collection(cls, collection, batch_size: int = 1000) -> "LexicalIndex":
        """Build from every chunk in a ChromaDB collection."""
        index = cls()
        offset = 0
        while True:
            batch = collection.get(
                include=["documents", "metadatas"],
                limit=batch_size,
                offset=offset,
            )
            if not batch["ids"]:
                break
            for cid, doc, meta in zip(
                batch["ids"], batch["documents"], batch["metadatas"]
            ):
                index.add(cid, doc, meta)
            offset += len(batch["ids"])
        return index

    def search(self, query: str, k: int, allowed=None) -> list[str]:
        """Top-k chunk ids by BM25, best first.

        ``allowed`` optionally filters candidates by their metadata dict
        (used to mirror the dense query's scope). Query terms are OR'd:
        BM25's term weighting does the ranking, and requiring all terms
        would zero out any query with one word the chunk lacks.
        """
        tokens = _TOKEN_RE.findall(query)
        if not tokens:
            return []
        match = " OR ".join(f'"{t}"' for t in tokens)
        cursor = self._db.execute(
            "SELECT chunk_id FROM chunks WHERE chunks MATCH ? ORDER BY rank",
            (match,),
        )
        out: list[str] = []
        for (cid,) in cursor:
            if allowed is None or allowed(self.metadatas[cid]):
                out.append(cid)
                if len(out) >= k:
                    break
        return out


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


def matches_where(metadata: dict, where: dict | None) -> bool:
    """Mirror a ChromaDB ``where`` clause against a chunk's metadata.

    Supports exactly the shapes /api/search builds: field equality,
    ``{"$in": [...]}``, ``$and``, and ``$or``. Anything else raises so a
    new clause shape can't silently widen the lexical side of a scoped
    hybrid search.
    """
    if not where:
        return True
    if "$and" in where:
        return all(matches_where(metadata, w) for w in where["$and"])
    if "$or" in where:
        return any(matches_where(metadata, w) for w in where["$or"])
    ((field, condition),) = where.items()
    value = metadata.get(field)
    if isinstance(condition, dict):
        if "$in" in condition:
            return value in condition["$in"]
        raise ValueError(f"unsupported where operator: {condition}")
    return value == condition
