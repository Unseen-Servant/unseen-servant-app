"""Tests for /api/search-settings and knob resolution in /api/search.

Search-pipeline knobs (rerank, pool size, spell correction, experimental
flags) persist sidecar-side in ``search_settings.json`` so every caller —
desktop UI and MCP alike — inherits them. Explicit request fields still
override: resolution order is request field > persisted setting >
built-in default (docs/retrieval/2026-07-11-search-settings-design.md).
"""

import json

import pytest

import server
from server import (
    RERANK_POOL_MAX,
    RERANK_POOL_MIN,
    SearchRequest,
    SearchSettings,
    load_search_settings,
    resolve_search_knobs,
    save_search_settings,
)


@pytest.fixture
def indexed_client(client, sample_pdf_path):
    client.post("/api/index-files", json={"paths": [str(sample_pdf_path)]})
    return client


# ---------------------------------------------------------------------------
# GET / PUT endpoints
# ---------------------------------------------------------------------------

def test_get_settings_defaults(client):
    response = client.get("/api/search-settings")
    assert response.status_code == 200
    assert response.json() == {
        "rerank": True,
        "rerank_candidates": 50,
        "spell_correction": True,
        "hybrid": True,
        "variant_expansion": False,
    }


def test_put_partial_update_merges(client):
    response = client.put("/api/search-settings", json={"rerank": False})
    assert response.status_code == 200
    body = response.json()
    assert body["rerank"] is False
    assert body["spell_correction"] is True  # untouched keys keep defaults

    # A second partial update must not clobber the first.
    response = client.put(
        "/api/search-settings", json={"rerank_candidates": 30}
    )
    body = response.json()
    assert body["rerank"] is False
    assert body["rerank_candidates"] == 30

    assert client.get("/api/search-settings").json() == body


def test_pool_size_clamped(client):
    assert client.put(
        "/api/search-settings", json={"rerank_candidates": 5}
    ).json()["rerank_candidates"] == RERANK_POOL_MIN
    assert client.put(
        "/api/search-settings", json={"rerank_candidates": 9999}
    ).json()["rerank_candidates"] == RERANK_POOL_MAX


def test_put_invalid_type_rejected(client):
    response = client.put("/api/search-settings", json={"rerank": "banana"})
    assert response.status_code == 422


def test_settings_survive_on_disk(client, tmp_path):
    client.put("/api/search-settings", json={"hybrid": False})
    assert (tmp_path / "search_settings.json").exists()
    assert load_search_settings(tmp_path).hybrid is False


def test_v1_file_hybrid_false_is_the_old_default(tmp_path):
    """v1 files wrote every field, so `hybrid: false` there is the old
    default rather than a choice: it gives way to the new default-on.
    Other v1 values are kept."""
    (tmp_path / "search_settings.json").write_text(
        '{"rerank": false, "hybrid": false}')
    loaded = load_search_settings(tmp_path)
    assert loaded.hybrid is True
    assert loaded.rerank is False


def test_v2_file_keeps_an_explicit_hybrid_off(client, tmp_path):
    client.put("/api/search-settings", json={"hybrid": False})
    raw = json.loads((tmp_path / "search_settings.json").read_text())
    assert raw["version"] == 2
    assert load_search_settings(tmp_path).hybrid is False


def test_corrupt_settings_file_falls_back(client, tmp_path):
    (tmp_path / "search_settings.json").write_text("{not json")
    response = client.get("/api/search-settings")
    assert response.status_code == 200
    assert response.json()["rerank"] is True


def test_unknown_keys_ignored(tmp_path):
    (tmp_path / "search_settings.json").write_text(
        '{"rerank": false, "future_knob": 42}'
    )
    settings = load_search_settings(tmp_path)
    assert settings.rerank is False


# ---------------------------------------------------------------------------
# Resolution order: request field > persisted setting > built-in default
# ---------------------------------------------------------------------------

def test_resolution_defaults_without_settings(tmp_path):
    knobs = resolve_search_knobs(SearchRequest(query="q"), tmp_path)
    assert knobs == SearchSettings()


def test_resolution_uses_persisted_settings(tmp_path):
    save_search_settings(
        tmp_path, SearchSettings(rerank=False, rerank_candidates=30)
    )
    knobs = resolve_search_knobs(SearchRequest(query="q"), tmp_path)
    assert knobs.rerank is False
    assert knobs.rerank_candidates == 30


def test_resolution_request_overrides_persisted(tmp_path):
    save_search_settings(
        tmp_path, SearchSettings(rerank=False, rerank_candidates=30)
    )
    knobs = resolve_search_knobs(
        SearchRequest(query="q", rerank=True, rerank_candidates=20), tmp_path
    )
    assert knobs.rerank is True
    assert knobs.rerank_candidates == 20
    # Unspecified fields still come from the persisted settings.
    knobs = resolve_search_knobs(SearchRequest(query="q", rerank=True), tmp_path)
    assert knobs.rerank_candidates == 30


def test_resolution_clamps_request_pool_size(tmp_path):
    knobs = resolve_search_knobs(
        SearchRequest(query="q", rerank_candidates=1), tmp_path
    )
    assert knobs.rerank_candidates == RERANK_POOL_MIN


def test_resolution_without_data_dir_uses_defaults():
    knobs = resolve_search_knobs(SearchRequest(query="q"), None)
    assert knobs == SearchSettings()


# ---------------------------------------------------------------------------
# The persisted settings actually drive /api/search
# ---------------------------------------------------------------------------

def test_persisted_rerank_off_skips_reranker(indexed_client, monkeypatch):
    """A search that doesn't mention rerank honors the persisted off."""
    def boom(query, docs):
        raise AssertionError("rerank_scores must not run: persisted rerank=off")

    monkeypatch.setattr(server, "rerank_scores", boom)
    indexed_client.put("/api/search-settings", json={"rerank": False})

    response = indexed_client.post("/api/search", json={
        "query": "dragon", "n_results": 5,
    })
    assert response.status_code == 200


def test_request_rerank_overrides_persisted_off(indexed_client, monkeypatch):
    """rerank=true in the request wins over persisted rerank=off."""
    called = {}

    def fake_scores(query, docs):
        called["docs"] = docs
        return [0.5] * len(docs)

    monkeypatch.setattr(server, "rerank_scores", fake_scores)
    indexed_client.put("/api/search-settings", json={"rerank": False})

    response = indexed_client.post("/api/search", json={
        "query": "dragon", "n_results": 5, "rerank": True,
    })
    assert response.status_code == 200
    assert called, "explicit rerank=true should invoke the reranker"
