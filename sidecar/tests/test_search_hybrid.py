"""Experimental BM25 hybrid retrieval (default-off `hybrid` search flag).

Per the 2026-07-01 roadmap's BM25 REOPEN item: a BM25 index over the
heading-prepended chunk texts (the same view the embedder and reranker
see) is fused with the dense candidate ranking via reciprocal-rank
fusion, then handed to the unchanged boost/rerank/dedupe pipeline. The
flag defaults to off and must not change production search behavior.

Since roadmap 1.6 (S5) the BM25 rows are persisted in the parents SQLite
(`parents_store.unit_fts`), written at index time — the search path never
scans the collection. The SQL translation of the dense `where` clause is
tested in `test_parents_store.py` (`where_to_sql`).
"""

import logging

import pytest

import lexical
from lexical import PersistedLexicalIndex, fts_match, rrf_fuse
from parents_store import upsert_units_fts


# ---------------------------------------------------------------------------
# fts_match (unit)
# ---------------------------------------------------------------------------

def test_fts_match_ors_quoted_tokens():
    assert fts_match("owlbear THAC0") == '"owlbear" OR "THAC0"'


def test_fts_match_quotes_away_fts5_syntax():
    """Punctuation is dropped and every token is quoted, so FTS5
    operators in user text are matched literally instead of parsed."""
    assert fts_match("fire-breath NEAR *") == '"fire" OR "breath" OR "NEAR"'


def test_fts_match_of_a_tokenless_query_is_empty():
    assert fts_match("???") == ""


def test_fts_match_drops_stopwords():
    assert fts_match("How does the owlbear attack?") == '"owlbear" OR "attack"'


def test_fts_match_keeps_an_all_stopword_query():
    """Dropping every term would leave nothing to match; keep them all."""
    assert fts_match("Who are you") == '"Who" OR "are" OR "you"'


def test_fts_match_keeps_accented_tokens_whole():
    """unicode61 indexes "écran" as one token; the query must too."""
    assert fts_match("écran du MJ") == '"écran" OR "du" OR "MJ"'


# ---------------------------------------------------------------------------
# PersistedLexicalIndex (unit, over real persisted rows)
# ---------------------------------------------------------------------------

def _persisted(tmp_path, rows, collection=None):
    upsert_units_fts(tmp_path, "/lib/x.pdf", rows)
    return PersistedLexicalIndex(tmp_path, collection)


def test_bm25_ranks_exact_term_first(tmp_path):
    idx = _persisted(tmp_path, [
        ("c1", 0, "x.pdf", "OSR", "p1",
         "initiative is rolled at the start of combat with owlbear"),
        ("c2", 1, "x.pdf", "OSR", "p1",
         "the owlbear has THAC0 15 and 5 hit dice"),
    ])
    # Both mention owlbear; only c2 also has THAC0. A chunk matching
    # neither term doesn't match the OR query at all.
    assert idx.search("owlbear THAC0", k=5) == ["c2", "c1"]
    assert idx.search("initiative", k=5) == ["c1"]


def test_heading_prepended_text_is_searchable(tmp_path):
    """Rows carry exactly what the embedder sees (`_embed_text`), so the
    section breadcrumb is part of the BM25 text."""
    idx = _persisted(tmp_path, [
        ("c1", 0, "x.pdf", "OSR", "p1",
         "Monsters > Fire Drake\n\nAC 14, HP 45, fire breath"),
        ("c2", 1, "x.pdf", "OSR", "p1", "generic travel rules"),
    ])
    assert idx.search("fire drake", k=1) == ["c1"]


def test_porter_stemming_matches_inflected_query(tmp_path):
    idx = _persisted(
        tmp_path,
        [("c1", 0, "x.pdf", "OSR", "p1", "dragons hoard treasure in caves")],
    )
    assert idx.search("dragon", k=1) == ["c1"]


def test_query_with_no_indexable_tokens_returns_nothing(tmp_path):
    idx = _persisted(tmp_path, [("c1", 0, "x.pdf", "OSR", "p1", "some text")])
    assert idx.search("???", k=5) == []


def test_search_applies_the_where_scope(tmp_path):
    upsert_units_fts(tmp_path, "/lib/a.pdf", [
        ("c1", 0, "a.pdf", "OSR", "p1", "fireball spell details")])
    upsert_units_fts(tmp_path, "/lib/b.pdf", [
        ("c2", 0, "b.pdf", "OSR", "p1", "fireball spell details")])
    idx = PersistedLexicalIndex(tmp_path, None)
    assert idx.search("fireball", k=5, where={"filename": "b.pdf"}) == ["c2"]


def test_lookup_skips_an_id_chroma_no_longer_has(test_collection):
    """A BM25 hit whose Chroma twin vanished mid-reindex is simply
    absent — the fusion loop drops it rather than inventing a row."""
    test_collection.add(
        ids=["c1"],
        documents=["the owlbear stat block"],
        metadatas=[{"filename": "a.pdf"}],
    )
    idx = PersistedLexicalIndex(None, test_collection)
    got = idx.lookup(["c1", "c-gone"])
    assert set(got) == {"c1"}
    assert got["c1"][0]["filename"] == "a.pdf"
    assert got["c1"][1] == "the owlbear stat block"
    assert idx.lookup([]) == {}


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


def test_rrf_weights_scale_each_ranking():
    fused = rrf_fuse([["a"], ["b"]], weights=[1.0, 2.0], k=60)
    assert [cid for cid, _ in fused] == ["b", "a"]
    assert dict(fused)["b"] == pytest.approx(2 / 61)


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


HYBRID_DOCS = [
    "combat happens in rounds and each round has phases",
    "the owlbear has THAC0 15 and attacks with claws",
]


def _stage_hybrid_chunks(collection, data_dir):
    """Put the two chunks in Chroma and their rows in the FTS store."""
    collection.add(
        ids=["c-prose", "c-stat"],
        documents=HYBRID_DOCS,
        metadatas=[_meta("p-prose", "rules.pdf"), _meta("p-stat", "monsters.pdf")],
    )
    upsert_units_fts(data_dir, "/corpus/rules.pdf", [
        ("c-prose", 0, "rules.pdf", "OSR", "p-prose", HYBRID_DOCS[0])])
    upsert_units_fts(data_dir, "/corpus/monsters.pdf", [
        ("c-stat", 0, "monsters.pdf", "OSR", "p-stat", HYBRID_DOCS[1])])


@pytest.fixture
def hybrid_client(client, test_collection, tmp_path, monkeypatch):
    """Two chunks in the real collection with their persisted FTS rows
    (BM25 side); a fake dense pool that only ever returns the prose
    chunk — dense 'misses' the stat block, so any stat-block hit must
    come through BM25 fusion.

    `tmp_path` is the client's data_dir, so the rows land where the app
    reads them."""
    _stage_hybrid_chunks(test_collection, tmp_path)
    fake_dense = {
        "ids": [["c-prose"]],
        "documents": [[HYBRID_DOCS[0]]],
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


def test_lex_weight_sets_the_bm25_share(hybrid_client):
    """At the default weight dense rank 1 outranks BM25 rank 1; a lexical
    weight above 1.0 flips them."""
    filenames = [
        r["filename"]
        for r in _search(hybrid_client, hybrid=True, lex_weight=2.0)
    ]
    assert filenames == ["monsters.pdf", "rules.pdf"]


@pytest.fixture
def deep_dense_client(client, test_collection, tmp_path, monkeypatch):
    """Twelve dense candidates — more than the minimum rerank pool of 10 —
    plus the BM25-only stat block, which weighted RRF ranks last."""
    _stage_hybrid_chunks(test_collection, tmp_path)
    ids = [f"c-d{i}" for i in range(12)]
    fake_dense = {
        "ids": [ids],
        "documents": [[f"combat prose {i}" for i in range(12)]],
        "metadatas": [[_meta(f"p-d{i}", "rules.pdf") for i in range(12)]],
        "distances": [[0.1 + i / 100 for i in range(12)]],
    }
    monkeypatch.setattr(
        type(test_collection), "query", lambda self, **kw: fake_dense)
    return client


def _scored_docs(client, monkeypatch, **overrides):
    import server

    scored = []
    monkeypatch.setattr(
        server, "rerank_scores",
        lambda q, docs: scored.extend(docs) or [0.5] * len(docs))
    _search(client, hybrid=True, rerank=True, rerank_candidates=10,
            spell_correction=False, **overrides)
    return scored


def test_hybrid_rerank_pool_adds_the_bm25_top_m(deep_dense_client, monkeypatch):
    """The pool is the head of the order plus the BM25 top-M — not the
    fused top-N, which a down-weighted BM25-only hit can never reach."""
    scored = _scored_docs(deep_dense_client, monkeypatch, lex_pool=1)
    assert len(scored) == 11
    assert any("owlbear" in d for d in scored)


def test_hybrid_lex_pool_zero_is_the_fused_head(deep_dense_client, monkeypatch):
    scored = _scored_docs(deep_dense_client, monkeypatch, lex_pool=0)
    assert len(scored) == 10
    assert not any("owlbear" in d for d in scored)


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


def test_hybrid_drops_an_fts_id_chroma_no_longer_has(hybrid_client, test_collection):
    """Mid-reindex the FTS rows can outlive their Chroma twins: the
    orphan is skipped, not surfaced with fabricated metadata."""
    test_collection.delete(ids=["c-stat"])
    filenames = [r["filename"] for r in _search(hybrid_client, hybrid=True)]
    assert filenames == ["rules.pdf"]


def test_first_hybrid_search_does_not_scan_the_collection(
    hybrid_client, test_collection, monkeypatch
):
    """The lexical ranking comes from the persisted FTS rows; Chroma is
    touched only to look the BM25-only ids up. Spell correction is off
    here because its vocabulary pass is a separate lazy scan that this
    task leaves alone."""
    calls = []
    orig = type(test_collection).get

    def spy(self, **kw):
        calls.append(kw)
        return orig(self, **kw)

    monkeypatch.setattr(type(test_collection), "get", spy)
    results = _search(hybrid_client, hybrid=True, spell_correction=False)
    assert [r["filename"] for r in results] == ["rules.pdf", "monsters.pdf"]
    assert calls  # the BM25-only id lookup happened
    assert all("ids" in kw for kw in calls)  # never a paginated scan


def test_hybrid_survives_a_recreated_collection(
    hybrid_client, test_chroma_client, test_collection, test_embedding_function,
    tmp_path,
):
    """/api/delete-index drops and recreates the Chroma collection. The
    BM25-only lookup must go to the live collection — a handle bound once
    at app creation is dead after the swap and 500s the search."""
    name = test_collection.name
    assert hybrid_client.post("/api/delete-index").status_code == 200

    fresh = test_chroma_client.get_collection(
        name=name, embedding_function=test_embedding_function)
    _stage_hybrid_chunks(fresh, tmp_path)

    filenames = [r["filename"] for r in _search(hybrid_client, hybrid=True)]
    assert filenames == ["rules.pdf", "monsters.pdf"]


def test_empty_fts_store_warns_once(tmp_path, caplog, monkeypatch):
    """A pre-Task-9 index has no rows: hybrid would quietly degrade to
    dense-only and an eval run would mislabel it. Say so — once."""
    monkeypatch.setattr(lexical, "_EMPTY_STORE_WARNED", False)
    idx = PersistedLexicalIndex(tmp_path, None)
    with caplog.at_level(logging.WARNING, logger="lexical"):
        assert idx.search("owlbear THAC0", k=5) == []
        assert idx.search("fireball", k=5) == []
    warned = [r for r in caplog.records if "unit_fts is empty" in r.getMessage()]
    assert len(warned) == 1
    assert "reindex" in warned[0].getMessage()


def test_populated_store_does_not_warn(tmp_path, caplog, monkeypatch):
    """A miss against a populated store is an ordinary empty result."""
    monkeypatch.setattr(lexical, "_EMPTY_STORE_WARNED", False)
    upsert_units_fts(tmp_path, "/lib/a.pdf", [
        ("c1", 0, "a.pdf", "OSR", "p1", "owlbear THAC0 15")])
    idx = PersistedLexicalIndex(tmp_path, None)
    with caplog.at_level(logging.WARNING, logger="lexical"):
        assert idx.search("basilisk", k=5) == []
    assert not [r for r in caplog.records if "unit_fts is empty" in r.getMessage()]
