"""Query orchestration: correct → embed → dense + lexical retrieve → fuse →
boost → single-pass rerank → dedupe-by-section → assemble (plan §3.4).

Phase 3 ablation ladder (§4). **Rung 1 = dense-only** is the baseline every later
rung must beat: embed the query → sqlite-vec KNN (binary prefilter + f32 rescore,
in store.search_dense) → hydrate to result rows. Later rungs (heading-prepend,
table-row units, parents & dedupe, BM25 fusion, boost, spell-correct, rerank,
tier calibration) layer on and are kept only if they pay on the Phase-0 harness.

query/ returns plain dicts and owns no engine types — the evals adapter maps them
to SearchResult. No import from sidecar/ (v2).
"""
from __future__ import annotations

import re
from typing import Callable, Sequence

from query.boost import boost_order, detect_sources
from query.fuse import rrf

_TERMS = re.compile(r"[a-z0-9]+")
LEX_WEIGHT = 0.3  # RRF lexical weight (dense=1.0). Dense-leaning: beat dense on every
#                   metric AND both keyword/nl with no regression; ≥0.4 or 1:1 nicks NL.
RERANK_WEIGHT = 0.5  # RRF rerank blend weight (retrieval=1.0). A nudge: sweep sweet spot —
#                      beats no-rerank on all aggregate metrics; a hard reorder regressed uncued/tables.
# Function words dropped from the FTS/BM25 match: RRF fuses on rank (not BM25's
# IDF-weighted score), so a stopword hit still earns rank credit and displaces
# good dense results. Matching on content terms only removes that noise (it was
# the NL regression's cause).
_STOPWORDS = frozenset(
    "how what when where why who which whose whom does do did is are was were can "
    "could should would will may might have has a an the of to in for on at by from "
    "with as that this these those it its and or not you your they their he she his "
    "her we our i me my but if then than into about over under out up down off no".split())


def _fts_query(query: str) -> str:
    """FTS5 MATCH string: OR the query's content terms (stopwords dropped; recall
    over the strict implicit-AND default, BM25 handles precision). Falls back to
    all terms if the query is only stopwords, so the match is never empty."""
    terms = _TERMS.findall(query.lower())
    content = [t for t in terms if t not in _STOPWORDS]
    return " OR ".join(content or terms)


def dense_search(store, embed_fn: Callable[[Sequence[str]], object], query: str,
                 k: int = 25) -> list[dict]:
    """Rung 1 — dense-only retrieval. Returns ranked, hydrated result dicts
    ({unit_id, rank, relevance, text, section_heading, filename, source,
    page_start, page_end, doc_id, chunk_id, section_id, chunk_text})."""
    qvec = embed_fn([query])[0]
    hits = store.search_dense(qvec, k=k)
    meta = store.hydrate([uid for uid, _ in hits])
    return [
        {"unit_id": uid, "rank": rank, "relevance": score, **meta.get(uid, {})}
        for rank, (uid, score) in enumerate(hits)
    ]


def search(store, embed_fn: Callable[[Sequence[str]], object], query: str,
           k: int = 25, pool: int = 200, assemble_parents: bool = True,
           hybrid: bool = False, weights: Sequence[float] | None = None,
           system_map: dict | None = None,
           rerank_fn: Callable[[str, list], list] | None = None, rerank_pool: int = 50,
           rerank_weight: float | None = None, doc_id: str | None = None) -> list[dict]:
    """Rungs 4–8 — fuse → rerank → boost → dedupe → parents (query-time). Over-
    fetch dense units; with `hybrid`, RRF-fuse against FTS/BM25 (rung 5). With
    `rerank_fn`, a cross-encoder re-scores the top `rerank_pool` and is **blended**
    into the ranking by RRF (`weights=[1.0, rerank_weight]`) — a nudge, not a hard
    override, so it can't unilaterally demote a confident retrieval #1 (rung 8; a
    hard reorder regressed uncued/tables). With `system_map`, a named system's
    sources are soft-boosted to the front (rung 6) — AFTER rerank, keeping the
    final say on disambiguation. Then keep the best-scoring unit per parent
    section; `matched_text` is the unit that hit and, with `assemble_parents`,
    `text` is the fuller parent chunk."""
    qvec = embed_fn([query])[0]
    dense = store.search_dense(qvec, k=pool, doc_id=doc_id)  # [(uid, cosine)]; doc_id = source_filter
    dense_ids = [uid for uid, _ in dense]
    if hybrid:
        fq = _fts_query(query)
        lex = store.search_fts(fq, doc_id=doc_id)[:pool] if fq else []
        fused = rrf([dense_ids, lex], weights=weights or [1.0, LEX_WEIGHT])
        ranked, relevance = [uid for uid, _ in fused], dict(fused)
    else:
        ranked, relevance = dense_ids, dict(dense)

    meta = store.hydrate(ranked)
    reranked: set[str] = set()
    if rerank_fn is not None and ranked:  # rung 8: cross-encoder re-score, blended by RRF
        top = ranked[:rerank_pool]
        docs = [f"{meta.get(u, {}).get('section_heading', '')}\n{meta.get(u, {}).get('text', '')}".strip()
                for u in top]
        scores = rerank_fn(query, docs)
        rerank_order = [top[i] for i in sorted(range(len(top)), key=lambda i: -scores[i])]
        w = RERANK_WEIGHT if rerank_weight is None else rerank_weight
        blended = rrf([top, rerank_order], weights=[1.0, w])  # nudge, not override
        ranked = [uid for uid, _ in blended] + ranked[rerank_pool:]
        relevance.update(dict(blended))
        reranked = set(top)
    if system_map:  # rung 6: name a system → soft-boost its sources to the front (final say)
        matched = detect_sources(query, system_map)
        ranked = boost_order(ranked, {u: meta.get(u, {}).get("filename") for u in ranked}, matched)
    seen: set[str] = set()
    out: list[dict] = []
    for uid in ranked:
        m = meta.get(uid)
        if m is None:
            continue
        key = m.get("section_id") or f"c:{m.get('chunk_id')}"
        if key in seen:
            continue
        seen.add(key)
        row = {"unit_id": uid, "rank": len(out), "relevance": relevance.get(uid, 0.0),
               "reranked": uid in reranked, **m, "matched_text": m["text"]}
        if assemble_parents:
            row["text"] = m.get("chunk_text") or m["text"]
        out.append(row)
        if len(out) >= k:
            break
    return out
