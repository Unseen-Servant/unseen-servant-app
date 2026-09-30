"""BM25 hybrid retrieval (the `hybrid` search flag, default-on since 2026-09-23).

Per the 2026-07-01 roadmap's BM25 REOPEN item: a BM25 index over the
heading-prepended chunk texts (the same view the embedder and reranker
see) is fused with the dense candidate ranking via reciprocal-rank
fusion, then handed to the unchanged boost/rerank/dedupe pipeline.

Since roadmap 1.6 (S5) the BM25 rows are persisted (now in the library
store's `unit_fts`), written at index time in the same transaction as the
rest of a book. The scope is a list of document ids shared with the dense
side (`LibraryStore.scope_document_ids`, tested in `test_library_store.py`).
"""

import logging

import pytest

from legend_lore import lexical
from legend_lore.granularity import EmbedUnit
from legend_lore.lexical import PersistedLexicalIndex, fts_match, rrf_fuse
from legend_lore.library_store import LibraryStore
from tests.conftest import seed_book


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


def test_fts_match_prefix_last_makes_the_last_word_a_prefix_term():
    assert fts_match("goblin armor cla", prefix_last=True) == (
        '"goblin" OR "armor" OR "cla"*'
    )
    # Committed queries are unchanged.
    assert fts_match("goblin armor cla") == '"goblin" OR "armor" OR "cla"'


def test_fts_match_prefix_last_drops_a_too_short_last_word():
    assert fts_match("goblin armor cl", prefix_last=True) == '"goblin" OR "armor"'
    assert fts_match("gr", prefix_last=True) == ""


def test_fts_match_prefix_last_keeps_a_stopword_looking_prefix():
    # "the" may be the start of "thief": a prefix is not a stopword yet.
    assert fts_match("rogue skills the", prefix_last=True) == (
        '"rogue" OR "skills" OR "the"*'
    )


def test_fts_match_keeps_an_all_stopword_query():
    """Dropping every term would leave nothing to match; keep them all."""
    assert fts_match("Who are you") == '"Who" OR "are" OR "you"'


def test_fts_match_keeps_accented_tokens_whole():
    """unicode61 indexes "écran" as one token; the query must too."""
    assert fts_match("écran du MJ") == '"écran" OR "du" OR "MJ"'


# ---------------------------------------------------------------------------
# PersistedLexicalIndex (unit, over real persisted rows)
# ---------------------------------------------------------------------------

def _unit(path: str, ordinal: int, text: str, parent_id: str = "p1") -> EmbedUnit:
    return EmbedUnit(
        chunk_id=f"c{ordinal}", text=text, parent_id=f"{path}#{parent_id}",
        chunk_type="prose", section_heading=None, source_pdf=path,
        page_start=1, page_end=1, ordinal=ordinal,
    )


def _small_store(tmp_path) -> LibraryStore:
    return LibraryStore.open(tmp_path / "library.sqlite3", "m", 2)


def _write(store, path, fts_texts, game_system="OSR") -> list[int]:
    """Write one book whose FTS rows are `fts_texts` (what the embedder
    would see); returns its unit ids in ordinal order."""
    units = [_unit(path, i, t) for i, t in enumerate(fts_texts)]
    store.replace_document(path, game_system, (), units, list(fts_texts),
                           [[1.0, 0.0]] * len(units), [])
    return [r[0] for r in store.conn().execute(
        "SELECT u.id FROM units u JOIN documents d ON d.id = u.document_id "
        "WHERE d.path = ? ORDER BY u.ordinal", (path,))]


def test_bm25_ranks_exact_term_first(tmp_path):
    store = _small_store(tmp_path)
    c1, c2 = _write(store, "/lib/x.pdf", [
        "initiative is rolled at the start of combat with owlbear",
        "the owlbear has THAC0 15 and 5 hit dice",
    ])
    idx = PersistedLexicalIndex(store)
    # Both mention owlbear; only c2 also has THAC0. A chunk matching
    # neither term doesn't match the OR query at all.
    assert idx.search("owlbear THAC0", k=5) == [c2, c1]
    assert idx.search("initiative", k=5) == [c1]


def test_heading_prepended_text_is_searchable(tmp_path):
    """Rows carry exactly what the embedder sees (`_embed_text`), so the
    section breadcrumb is part of the BM25 text."""
    store = _small_store(tmp_path)
    c1, _ = _write(store, "/lib/x.pdf", [
        "Monsters > Fire Drake\n\nAC 14, HP 45, fire breath",
        "generic travel rules",
    ])
    assert PersistedLexicalIndex(store).search("fire drake", k=1) == [c1]


def test_porter_stemming_matches_inflected_query(tmp_path):
    store = _small_store(tmp_path)
    (c1,) = _write(store, "/lib/x.pdf", ["dragons hoard treasure in caves"])
    assert PersistedLexicalIndex(store).search("dragon", k=1) == [c1]


def test_query_with_no_indexable_tokens_returns_nothing(tmp_path):
    store = _small_store(tmp_path)
    _write(store, "/lib/x.pdf", ["some text"])
    assert PersistedLexicalIndex(store).search("???", k=5) == []


def test_search_applies_the_doc_id_scope(tmp_path):
    store = _small_store(tmp_path)
    _write(store, "/lib/a.pdf", ["fireball spell details"])
    (c2,) = _write(store, "/lib/b.pdf", ["fireball spell details"])
    idx = PersistedLexicalIndex(store)
    scope = store.scope_document_ids(filename="b.pdf")
    assert idx.search("fireball", k=5, doc_ids=scope) == [c2]
    assert idx.search("fireball", k=5, doc_ids=[]) == []


def test_lookup_skips_an_id_the_store_no_longer_has(tmp_path):
    """A BM25 hit whose book was removed mid-search is simply absent —
    the fusion loop drops it rather than inventing a row."""
    store = _small_store(tmp_path)
    (c1,) = _write(store, "/lib/a.pdf", ["the owlbear stat block"])
    idx = PersistedLexicalIndex(store)
    got = idx.lookup([c1, c1 + 999])
    assert set(got) == {c1}
    assert got[c1][0]["filename"] == "a.pdf"
    assert got[c1][1] == "the owlbear stat block"
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

HYBRID_DOCS = [
    "combat happens in rounds and each round has phases",
    "the owlbear has THAC0 15 and attacks with claws",
]
RULES = "/corpus/rules.pdf"
MONSTERS = "/corpus/monsters.pdf"


def _unit_ids(store, path: str) -> list[int]:
    return [r[0] for r in store.conn().execute(
        "SELECT u.id FROM units u JOIN documents d ON d.id = u.document_id "
        "WHERE d.path = ? ORDER BY u.ordinal", (path,))]


def _stage_hybrid_chunks(store, embed_fn, rules_texts=(HYBRID_DOCS[0],)):
    """The rules book (prose) and the monsters book (the stat block), with
    their FTS rows — the BM25 side."""
    seed_book(store, embed_fn, RULES,
              [_unit(RULES, i, t, f"p{i}") for i, t in enumerate(rules_texts)],
              game_system="OSR")
    seed_book(store, embed_fn, MONSTERS, [_unit(MONSTERS, 0, HYBRID_DOCS[1])],
              game_system="OSR")


def _pin_dense(monkeypatch, store, distances):
    """Fake dense ranking: the rules book's units in ordinal order with
    `distances`; the monsters book never — dense 'misses' the stat block,
    so any stat-block hit must come through BM25 fusion. Resolved per
    call, so the ids follow a restaged store."""
    def knn(vector, k, doc_ids=None):
        return list(zip(_unit_ids(store, RULES), distances))
    monkeypatch.setattr(store, "knn", knn)


@pytest.fixture
def hybrid_client(client, test_store, test_embed_fn, monkeypatch):
    """Two chunks with their persisted FTS rows; a fake dense pool that
    only ever returns the prose chunk."""
    _stage_hybrid_chunks(test_store, test_embed_fn)
    _pin_dense(monkeypatch, test_store, [0.2])
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


def test_hybrid_on_by_default(hybrid_client):
    """Default-on since 2026-09-23: without the flag the BM25-only chunk
    appears; switched off, it doesn't."""
    assert [r["filename"] for r in _search(hybrid_client)] == [
        "rules.pdf", "monsters.pdf"]
    assert [r["filename"] for r in _search(hybrid_client, hybrid=False)] == [
        "rules.pdf"]


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
def deep_dense_client(client, test_store, test_embed_fn, monkeypatch):
    """Twelve dense candidates — more than the minimum rerank pool of 10 —
    plus the BM25-only stat block, which weighted RRF ranks last."""
    _stage_hybrid_chunks(test_store, test_embed_fn,
                         [f"combat prose {i}" for i in range(12)])
    _pin_dense(monkeypatch, test_store, [0.1 + i / 100 for i in range(12)])
    return client


def _scored_docs(client, monkeypatch, **overrides):
    from legend_lore import service

    scored = []
    monkeypatch.setattr(service, "rerank_scores",
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
    """The BM25 side searches the dense side's scope: scoping to the
    prose file must keep the other file's stat block out."""
    results = _search(
        hybrid_client, hybrid=True, source_paths=[RULES])
    assert [r["filename"] for r in results] == ["rules.pdf"]


def test_hybrid_reranker_rescores_bm25_only_candidate(hybrid_client, monkeypatch):
    """With rerank on, the cross-encoder gives the BM25-only candidate a
    real score on the same scale as everything else."""
    from legend_lore import service

    monkeypatch.setattr(service, "rerank_scores",
        lambda q, docs: [0.9 if "owlbear" in d else 0.1 for d in docs])
    results = _search(hybrid_client, hybrid=True, rerank=True)
    assert [r["filename"] for r in results] == ["monsters.pdf", "rules.pdf"]
    assert results[0]["relevance"] == pytest.approx(0.9)
    assert results[0]["reranked"] is True


def test_hybrid_drops_a_bm25_id_the_store_no_longer_has(
    hybrid_client, test_store, monkeypatch
):
    """A BM25 id whose book was removed between the FTS query and the
    lookup is skipped, not surfaced with fabricated metadata."""
    real = PersistedLexicalIndex.search
    monkeypatch.setattr(
        PersistedLexicalIndex, "search",
        lambda self, q, k, doc_ids=None, **kw: [10_000, *real(self, q, k, doc_ids, **kw)],
    )
    filenames = [r["filename"] for r in _search(hybrid_client, hybrid=True)]
    assert filenames == ["rules.pdf", "monsters.pdf"]


def test_hybrid_after_delete_index_and_reindex(
    hybrid_client, test_store, test_embed_fn
):
    """/api/delete-index empties the store; books indexed afterwards are
    found by the BM25 side again."""
    assert hybrid_client.post("/api/delete-index").status_code == 200
    assert _search(hybrid_client, hybrid=True) == []

    _stage_hybrid_chunks(test_store, test_embed_fn)
    filenames = [r["filename"] for r in _search(hybrid_client, hybrid=True)]
    assert filenames == ["rules.pdf", "monsters.pdf"]


def test_empty_fts_store_warns_once(tmp_path, caplog, monkeypatch):
    """A pre-Task-9 index has no rows: hybrid would quietly degrade to
    dense-only and an eval run would mislabel it. Say so — once."""
    monkeypatch.setattr(lexical, "_EMPTY_STORE_WARNED", False)
    idx = PersistedLexicalIndex(_small_store(tmp_path))
    with caplog.at_level(logging.WARNING, logger="lexical"):
        assert idx.search("owlbear THAC0", k=5) == []
        assert idx.search("fireball", k=5) == []
    warned = [r for r in caplog.records if "unit_fts is empty" in r.getMessage()]
    assert len(warned) == 1
    assert "reindex" in warned[0].getMessage()


def test_populated_store_does_not_warn(tmp_path, caplog, monkeypatch):
    """A miss against a populated store is an ordinary empty result."""
    monkeypatch.setattr(lexical, "_EMPTY_STORE_WARNED", False)
    store = _small_store(tmp_path)
    _write(store, "/lib/a.pdf", ["owlbear THAC0 15"])
    idx = PersistedLexicalIndex(store)
    with caplog.at_level(logging.WARNING, logger="lexical"):
        assert idx.search("basilisk", k=5) == []
    assert not [r for r in caplog.records if "unit_fts is empty" in r.getMessage()]
