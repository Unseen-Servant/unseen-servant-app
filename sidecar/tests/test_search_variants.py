"""/api/search variant expansion (typo-tolerance design, section B).

Spacing variants of the (corrected) query are searched alongside it in
one multi-query Chroma call and fused with RRF: a query that joins what
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

from parents_store import upsert_units_fts


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


# Gives the vocabulary owlbear=3 and bear=3 (owl stays at 0 — protected
# as general English, and join only needs the concatenation in-vocab).
JOIN_DOC = "a bear and an owlbear; the bear meets the owlbear; bear owlbear"
PROSE_DOC = "combat happens in rounds and each round has phases"


@pytest.fixture
def capture_client(client, test_collection, monkeypatch):
    """Dense query calls are captured; each query text gets its own
    fixed ranking so tests can see fusion across the variants."""
    test_collection.add(
        ids=["c-stat"],
        documents=[JOIN_DOC],
        metadatas=[_meta("p-stat", "monsters.pdf")],
    )
    captured: dict = {}
    rankings = {
        "owl bear": ("c-prose", PROSE_DOC, _meta("p-prose", "rules.pdf"), 0.4),
        "owlbear": ("c-stat", JOIN_DOC, _meta("p-stat", "monsters.pdf"), 0.2),
    }

    def fake_query(self, **kwargs):
        captured.update(kwargs)
        out = {"ids": [], "documents": [], "metadatas": [], "distances": []}
        for q in kwargs["query_texts"]:
            cid, doc, meta, dist = rankings.get(
                q, ("c-stat", JOIN_DOC, _meta("p-stat", "monsters.pdf"), 0.3)
            )
            out["ids"].append([cid])
            out["documents"].append([doc])
            out["metadatas"].append([meta])
            out["distances"].append([dist])
        return out

    monkeypatch.setattr(type(test_collection), "query", fake_query)
    return client, captured


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
    # The joined variant rode along in one multi-query call...
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
    payload = {
        "query": "owl bear", "n_results": 5,
        "rerank": False,
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


def test_fused_distance_is_minimum_across_rankings(
    client, test_collection, monkeypatch
):
    """The same candidate found by primary and variant reports the
    better (smaller) of its cosine distances."""
    test_collection.add(
        ids=["c-stat"],
        documents=[JOIN_DOC],
        metadatas=[_meta("p-stat", "monsters.pdf")],
    )
    distances = {"owl bear": 0.5, "owlbear": 0.1}

    def fake_query(self, **kwargs):
        return {
            "ids": [["c-stat"] for _ in kwargs["query_texts"]],
            "documents": [[JOIN_DOC] for _ in kwargs["query_texts"]],
            "metadatas": [
                [_meta("p-stat", "monsters.pdf")]
                for _ in kwargs["query_texts"]
            ],
            "distances": [[distances[q]] for q in kwargs["query_texts"]],
        }

    monkeypatch.setattr(type(test_collection), "query", fake_query)
    body = _search(client)
    assert [r["relevance"] for r in body["results"]] == [0.9]


def test_composes_with_hybrid(client, test_collection, tmp_path, monkeypatch):
    """BM25 joins the same fusion. The stat doc says only "owlbear", so
    FTS5 can't reach it from the query "owl bear" — it surfaces solely
    through the dense variant ranking, next to the BM25-only chunk."""
    stat_doc = "the owlbear hunts; an owlbear sleeps; the owlbear tracks prey"
    lex_doc = "the owl and the bear live in a cave"
    test_collection.add(
        ids=["c-stat", "c-lex"],
        documents=[stat_doc, lex_doc],
        metadatas=[_meta("p-stat", "monsters.pdf"), _meta("p-lex", "lex.pdf")],
    )
    upsert_units_fts(tmp_path, "/corpus/monsters.pdf", [
        ("c-stat", 0, "monsters.pdf", "OSR", "p-stat", stat_doc)])
    upsert_units_fts(tmp_path, "/corpus/lex.pdf", [
        ("c-lex", 0, "lex.pdf", "OSR", "p-lex", lex_doc)])
    rankings = {
        "owl bear": ("c-prose", PROSE_DOC, _meta("p-prose", "rules.pdf"), 0.4),
        "owlbear": ("c-stat", stat_doc, _meta("p-stat", "monsters.pdf"), 0.2),
    }
    captured: dict = {}

    def fake_query(self, **kwargs):
        captured.update(kwargs)
        out = {"ids": [], "documents": [], "metadatas": [], "distances": []}
        for q in kwargs["query_texts"]:
            cid, doc, meta, dist = rankings[q]
            out["ids"].append([cid])
            out["documents"].append([doc])
            out["metadatas"].append([meta])
            out["distances"].append([dist])
        return out

    monkeypatch.setattr(type(test_collection), "query", fake_query)
    body = _search(client, hybrid=True)
    assert captured["query_texts"] == ["owl bear", "owlbear"]
    assert {r["filename"] for r in body["results"]} == {
        "rules.pdf", "monsters.pdf", "lex.pdf"
    }
