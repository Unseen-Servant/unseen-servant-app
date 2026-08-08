"""Experimental BM25 hybrid retrieval (default-off `hybrid` search flag).

Per the 2026-07-01 roadmap's BM25 REOPEN item: a BM25 index over the
heading-prepended chunk texts (the same view the embedder and reranker
see) is fused with the dense candidate ranking via reciprocal-rank
fusion, then handed to the unchanged boost/rerank/dedupe pipeline. The
flag defaults to off and must not change production search behavior.
"""

import pytest

from lexical import LexicalIndex, matches_where, rrf_fuse


# ---------------------------------------------------------------------------
# LexicalIndex (unit)
# ---------------------------------------------------------------------------

def _index(rows):
    idx = LexicalIndex()
    for cid, doc, meta in rows:
        idx.add(cid, doc, meta)
    return idx


def test_bm25_ranks_exact_term_first():
    idx = _index([
        ("c1", "initiative is rolled at the start of combat with owlbear", {}),
        ("c2", "the owlbear has THAC0 15 and 5 hit dice", {}),
    ])
    # Both mention owlbear; only c2 also has THAC0. A chunk matching
    # neither term doesn't match the OR query at all.
    assert idx.search("owlbear THAC0", k=5) == ["c2", "c1"]
    assert idx.search("initiative", k=5) == ["c1"]


def test_heading_text_is_searchable():
    idx = _index([
        ("c1", "AC 14, HP 45, fire breath",
         {"section_heading": "Monsters > Fire Drake"}),
        ("c2", "generic travel rules", {}),
    ])
    assert idx.search("fire drake", k=1) == ["c1"]


def test_porter_stemming_matches_inflected_query():
    idx = _index([("c1", "dragons hoard treasure in caves", {})])
    assert idx.search("dragon", k=1) == ["c1"]


def test_query_with_no_indexable_tokens_returns_nothing():
    idx = _index([("c1", "some text", {})])
    assert idx.search("???", k=5) == []


def test_allowed_predicate_filters_candidates():
    idx = _index([
        ("c1", "fireball spell details", {"filename": "a.pdf"}),
        ("c2", "fireball spell details", {"filename": "b.pdf"}),
    ])
    hits = idx.search(
        "fireball", k=5, allowed=lambda m: m["filename"] == "b.pdf")
    assert hits == ["c2"]


def test_from_collection_indexes_every_chunk(test_collection):
    test_collection.add(
        ids=["c1", "c2"],
        documents=["the owlbear stat block", "grappling rules"],
        metadatas=[
            {"section_heading": "Monsters"},
            {"section_heading": "Combat"},
        ],
    )
    idx = LexicalIndex.from_collection(test_collection, batch_size=1)
    assert idx.search("owlbear", k=1) == ["c1"]
    assert idx.search("grappling", k=1) == ["c2"]


# ---------------------------------------------------------------------------
# rrf_fuse (unit)
# ---------------------------------------------------------------------------

def test_rrf_agreement_beats_single_list_top():
    fused = rrf_fuse([["a", "b"], ["b", "c"]], k=60)
    assert [cid for cid, _ in fused] == ["b", "a", "c"]
    scores = dict(fused)
    assert scores["b"] == pytest.approx(1 / 62 + 1 / 61)


def test_rrf_tie_keeps_first_ranking_order():
    fused = rrf_fuse([["a"], ["b"]], k=60)
    assert [cid for cid, _ in fused] == ["a", "b"]


# ---------------------------------------------------------------------------
# matches_where (unit) — must mirror the clauses /api/search builds
# ---------------------------------------------------------------------------

def test_where_none_matches_everything():
    assert matches_where({"filename": "a.pdf"}, None)


def test_where_equality_and_in():
    assert matches_where({"filename": "a.pdf"}, {"filename": "a.pdf"})
    assert not matches_where({"filename": "b.pdf"}, {"filename": "a.pdf"})
    assert matches_where(
        {"source": "/x/a.pdf"}, {"source": {"$in": ["/x/a.pdf"]}})
    assert not matches_where(
        {"source": "/x/b.pdf"}, {"source": {"$in": ["/x/a.pdf"]}})


def test_where_and_or_nesting():
    where = {"$and": [
        {"filename": "a.pdf"},
        {"$or": [
            {"game_system": "OSR"},
            {"source": {"$in": ["/x/a.pdf"]}},
        ]},
    ]}
    assert matches_where(
        {"filename": "a.pdf", "game_system": "OSR", "source": "/y"}, where)
    assert matches_where(
        {"filename": "a.pdf", "game_system": "5E", "source": "/x/a.pdf"}, where)
    assert not matches_where(
        {"filename": "a.pdf", "game_system": "5E", "source": "/y"}, where)


def test_where_unknown_operator_raises():
    with pytest.raises(ValueError):
        matches_where({"page_start": 3}, {"page_start": {"$gte": 2}})


# ---------------------------------------------------------------------------
# /api/search hybrid flag (integration, deterministic fake dense pool)
# ---------------------------------------------------------------------------

def _meta(parent_id: str, filename: str) -> dict:
    return {
        "parent_id": parent_id,
        "filename": filename,
        "source": f"/corpus/{filename}",
        "game_system": "OSR",
        "section_heading": "",
        "page_start": 1,
        "page_end": 1,
    }


@pytest.fixture
def hybrid_client(client, test_collection, monkeypatch):
    """Two chunks in the real collection (BM25 side); a fake dense pool
    that only ever returns the prose chunk — dense 'misses' the stat
    block, so any stat-block hit must come through BM25 fusion."""
    test_collection.add(
        ids=["c-prose", "c-stat"],
        documents=[
            "combat happens in rounds and each round has phases",
            "the owlbear has THAC0 15 and attacks with claws",
        ],
        metadatas=[_meta("p-prose", "rules.pdf"), _meta("p-stat", "monsters.pdf")],
    )
    fake_dense = {
        "ids": [["c-prose"]],
        "documents": [["combat happens in rounds and each round has phases"]],
        "metadatas": [[_meta("p-prose", "rules.pdf")]],
        "distances": [[0.2]],
    }
    monkeypatch.setattr(
        type(test_collection), "query", lambda self, **kw: fake_dense)
    return client


def _search(client, **overrides):
    payload = {
        "query": "owlbear THAC0",
        "n_results": 5,
        "rerank": False,
        **overrides,
    }
    resp = client.post("/api/search", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["results"]


def test_hybrid_off_by_default(hybrid_client):
    """Without the flag the BM25-only chunk must not appear."""
    filenames = [r["filename"] for r in _search(hybrid_client)]
    assert filenames == ["rules.pdf"]


def test_hybrid_pulls_in_bm25_only_candidate(hybrid_client):
    """The stat block dense missed entirely is retrieved via BM25.

    Dense rank 1 and BM25 rank 1 tie on RRF score; the tie deterministically
    keeps the dense candidate first."""
    filenames = [r["filename"] for r in _search(hybrid_client, hybrid=True)]
    assert filenames == ["rules.pdf", "monsters.pdf"]


def test_hybrid_bm25_only_candidate_has_floor_relevance(hybrid_client):
    """No cosine distance exists for a BM25-only candidate: with rerank
    off it reports the sentinel 0.0 rather than a made-up score."""
    results = _search(hybrid_client, hybrid=True)
    assert results[0]["relevance"] == pytest.approx(0.8)  # 1 - 0.2, untouched
    assert results[1]["relevance"] == 0.0


def test_hybrid_respects_source_scope(hybrid_client):
    """The BM25 side mirrors the dense where-clause: scoping to the
    prose file must keep the other file's stat block out."""
    results = _search(
        hybrid_client, hybrid=True, source_paths=["/corpus/rules.pdf"])
    assert [r["filename"] for r in results] == ["rules.pdf"]


def test_hybrid_reranker_rescores_bm25_only_candidate(hybrid_client, monkeypatch):
    """With rerank on, the cross-encoder gives the BM25-only candidate a
    real score on the same scale as everything else."""
    import server

    monkeypatch.setattr(
        server, "rerank_scores",
        lambda q, docs: [0.9 if "owlbear" in d else 0.1 for d in docs])
    results = _search(hybrid_client, hybrid=True, rerank=True)
    assert [r["filename"] for r in results] == ["monsters.pdf", "rules.pdf"]
    assert results[0]["relevance"] == pytest.approx(0.9)
    assert results[0]["reranked"] is True
