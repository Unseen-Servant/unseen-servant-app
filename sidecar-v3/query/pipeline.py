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

from typing import Callable, Sequence


def dense_search(store, embed_fn: Callable[[Sequence[str]], object], query: str,
                 k: int = 25) -> list[dict]:
    """Rung 1 — dense-only retrieval. Returns ranked, hydrated result dicts
    ({unit_id, rank, relevance, text, section_heading, filename, source,
    page_start, page_end, doc_id})."""
    qvec = embed_fn([query])[0]
    hits = store.search_dense(qvec, k=k)
    meta = store.hydrate([uid for uid, _ in hits])
    return [
        {"unit_id": uid, "rank": rank, "relevance": score, **meta.get(uid, {})}
        for rank, (uid, score) in enumerate(hits)
    ]
