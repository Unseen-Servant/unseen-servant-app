"""/api/search variant expansion (typo-tolerance design, section B).

Spacing variants of the (corrected) query are embedded alongside it in
one call, each gets its own dense ranking, and they fuse with RRF: a query that joins what
the corpus splits — or splits what it joins — converges on the same
results. Default OFF — the 2026-07-10 eval gate failed (spacing
variants gained nothing, clean queries regressed; findings in the
design doc). The `variant_expansion` flag is independent of
`spell_correction` (shared vocabulary, separate mechanisms); expansion
applies to the corrected query when both are on. A query with no
variants follows the single-query path untouched; under `hybrid` the
BM25 ranking joins the same fusion.
"""

import pytest
from fastapi.testclient import TestClient

from legend_lore.granularity import EmbedUnit
from server import create_app
from tests.conftest import TEST_EMBED_DIM, seed_book


# Gives the vocabulary owlbear=3 and bear=3 (owl stays at 0 — protected
# as general English, and join only needs the concatenation in-vocab).
JOIN_DOC = "a bear and an owlbear; the bear meets the owlbear; bear owlbear"
PROSE_DOC = "combat happens in rounds and each round has phases"


def _flat(texts):
    """Placeholder vectors: every dense ranking here is scripted."""
    return [[1.0] + [0.0] * (TEST_EMBED_DIM - 1) for _ in texts]


def _book(store, filename, text):
    """Index one unit at /corpus/<filename>; returns its unit id."""
    path = f"/corpus/{filename}"
    unit = EmbedUnit(
        chunk_id="c0", text=text, parent_id=f"p-{filename}",
        chunk_type="prose", section_heading=None, source_pdf=path,
        page_start=1, page_end=1, ordinal=0,
    )
    seed_book(store, _flat, path, [unit], game_system="OSR")
    return store.conn().execute(
        "SELECT u.id FROM units u JOIN documents d ON d.id = u.document_id "
        "WHERE d.path = ?", (path,)
    ).fetchone()[0]


@pytest.fixture
def dense(test_store, tmp_path, monkeypatch):
    """App whose dense side is scripted per query text.

    Records the texts of each embed call in ``state["query_texts"]``; the
    knn calls that follow (one per text, in order) return
    ``state["rankings"][text]`` — (unit_id, distance) pairs — or
    ``state["default"]`` for a text with no scripted ranking.
    """
    state: dict = {"query_texts": None, "rankings": {}, "default": []}
    pending: list[str] = []

    def embed(texts):
        state["query_texts"] = list(texts)
        pending[:] = list(texts)
        return _flat(texts)

    def knn(vec, k, doc_ids=None):
        text = pending.pop(0)
        return list(state["rankings"].get(text, state["default"]))

    monkeypatch.setattr(test_store, "knn", knn)
    client = TestClient(
        create_app(store=test_store, data_dir=tmp_path, embed_fn=embed)
    )
    return client, state


@pytest.fixture
def capture_client(dense, test_store):
    """Each query text gets its own fixed ranking so tests can see fusion
    across the variants."""
    client, state = dense
    stat = _book(test_store, "monsters.pdf", JOIN_DOC)
    prose = _book(test_store, "rules.pdf", PROSE_DOC)
    state["rankings"] = {"owl bear": [(prose, 0.4)], "owlbear": [(stat, 0.2)]}
    state["default"] = [(stat, 0.3)]
    return client, state


def _search(client, **overrides):
    payload = {
        "query": "owl bear",
        "n_results": 5,
        "rerank": False,
        "variant_expansion": True,
        **overrides,
    }
    resp = client.post("/api/search", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_spacing_query_searches_variant_and_fuses(capture_client):
    client, captured = capture_client
    body = _search(client)
    # The joined variant rode along in the same embed call...
    assert captured["query_texts"] == ["owl bear", "owlbear"]
    # ...and the fused pool contains parents from both rankings.
    assert {r["filename"] for r in body["results"]} == {
        "rules.pdf", "monsters.pdf"
    }
    # No misspelling was involved: expansion alone is not a correction.
    assert body["corrected_query"] is None


def test_expansion_applies_to_the_corrected_query(capture_client):
    client, captured = capture_client
    body = _search(client, query="owl baer")
    assert body["corrected_query"] == "owl bear"
    assert captured["query_texts"] == ["owl bear", "owlbear"]


def test_query_without_variants_stays_single(capture_client):
    client, captured = capture_client
    _search(client, query="nothing special here")
    assert captured["query_texts"] == ["nothing special here"]


def test_expansion_defaults_off(capture_client):
    client, captured = capture_client
    # hybrid off: BM25 would add the stat unit ("bear") on its own.
    payload = {
        "query": "owl bear", "n_results": 5,
        "rerank": False, "hybrid": False,
    }
    resp = client.post("/api/search", json=payload)
    assert resp.status_code == 200, resp.text
    assert captured["query_texts"] == ["owl bear"]
    assert [r["filename"] for r in resp.json()["results"]] == ["rules.pdf"]


def test_expansion_runs_without_correction(capture_client):
    # Independent flags over a shared vocabulary: correction off does
    # not disable expansion, it just expands the raw query.
    client, captured = capture_client
    body = _search(client, spell_correction=False)
    assert captured["query_texts"] == ["owl bear", "owlbear"]
    assert body["corrected_query"] is None


def test_fused_distance_is_minimum_across_rankings(dense, test_store):
    """The same candidate found by primary and variant reports the
    better (smaller) of its cosine distances."""
    client, state = dense
    stat = _book(test_store, "monsters.pdf", JOIN_DOC)
    state["rankings"] = {"owl bear": [(stat, 0.5)], "owlbear": [(stat, 0.1)]}

    body = _search(client)
    assert [r["relevance"] for r in body["results"]] == [0.9]


def test_composes_with_hybrid(dense, test_store):
    """BM25 joins the same fusion. The stat doc says only "owlbear", so
    FTS5 can't reach it from the query "owl bear" — it surfaces solely
    through the dense variant ranking, next to the BM25-only chunk."""
    client, state = dense
    stat = _book(
        test_store, "monsters.pdf",
        "the owlbear hunts; an owlbear sleeps; the owlbear tracks prey",
    )
    _book(test_store, "lex.pdf", "the owl and the bear live in a cave")
    prose = _book(test_store, "rules.pdf", PROSE_DOC)
    state["rankings"] = {"owl bear": [(prose, 0.4)], "owlbear": [(stat, 0.2)]}

    body = _search(client, hybrid=True)
    assert state["query_texts"] == ["owl bear", "owlbear"]
    assert {r["filename"] for r in body["results"]} == {
        "rules.pdf", "monsters.pdf", "lex.pdf"
    }
