"""
Tests for game system management endpoints.

- GET /api/game-systems — list distinct game systems in the index
- POST /api/set-game-systems — override a file's game system tags
- GET /api/sources — verify game_system appears in source listings
"""

import json

from legend_lore.service import MANIFEST_FILENAME


# ---------------------------------------------------------------------------
# GET /api/game-systems
# ---------------------------------------------------------------------------

def test_game_systems_empty(client):
    """Empty collection should return no game systems."""
    response = client.get("/api/game-systems")

    assert response.status_code == 200
    data = response.json()
    assert data["game_systems"] == []
    assert data["count"] == 0


def test_game_systems_after_indexing(client, dnd5e_pdf_path, untagged_pdf_path):
    """Should return distinct systems found across indexed files."""
    client.post("/api/index-files", json={
        "paths": [str(dnd5e_pdf_path), str(untagged_pdf_path)]
    })

    response = client.get("/api/game-systems")
    data = response.json()

    assert "D&D 5E" in data["game_systems"]
    assert "unknown" in data["game_systems"]
    assert data["count"] == 2


def test_game_systems_sorted(client, dnd5e_pdf_path, dragonbane_pdf_path):
    """Game systems should be returned in sorted order."""
    client.post("/api/index-files", json={
        "paths": [str(dragonbane_pdf_path), str(dnd5e_pdf_path)]
    })

    response = client.get("/api/game-systems")
    data = response.json()
    assert data["game_systems"] == sorted(data["game_systems"])


# ---------------------------------------------------------------------------
# POST /api/set-game-systems — single tag
# ---------------------------------------------------------------------------

def test_set_game_system_updates_metadata(
    client, untagged_pdf_path, test_store, tmp_path
):
    """Setting game system should update the tag every chunk reports."""
    client.post("/api/index-files", json={
        "paths": [str(untagged_pdf_path)]
    })

    response = client.post("/api/set-game-systems", json={
        "filename": "random_supplement.pdf",
        "game_systems": ["Savage Worlds"],
    })

    assert response.status_code == 200
    data = response.json()
    assert data["game_system"] == "Savage Worlds"
    assert data["chunks_updated"] > 0

    # Every unit reads its tag from the book's documents row.
    (doc,) = test_store.documents()
    assert doc.game_system == "Savage Worlds"
    unit_ids = test_store.fts('"tables"', 10)
    assert unit_ids
    assert {u.metadata["game_system"]
            for u in test_store.hydrate(unit_ids).values()} == {"Savage Worlds"}

    # A game_system-scoped lexical search follows the retag: it scopes
    # through the same documents row, not a copy of the tag.
    assert test_store.fts(
        '"tables"', 10, test_store.scope_document_ids(systems=["Savage Worlds"])
    )
    assert test_store.fts(
        '"tables"', 10, test_store.scope_document_ids(systems=["unknown"])
    ) == []


def test_set_game_system_updates_manifest(
    client, untagged_pdf_path, tmp_path
):
    """Setting game system should also update the manifest."""
    client.post("/api/index-files", json={
        "paths": [str(untagged_pdf_path)]
    })

    client.post("/api/set-game-systems", json={
        "filename": "random_supplement.pdf",
        "game_systems": ["GURPS"],
    })

    manifest_raw = json.loads((tmp_path / MANIFEST_FILENAME).read_text())
    entry = manifest_raw["files"][str(untagged_pdf_path)]
    assert entry["game_system"] == "GURPS"


def test_set_game_system_nonexistent_source(client):
    """Setting game system on a non-indexed file should return 404."""
    response = client.post("/api/set-game-systems", json={
        "filename": "ghost_book.pdf",
        "game_systems": ["D&D 5E"],
    })

    assert response.status_code == 404


def test_set_game_system_reflected_in_search(
    client, untagged_pdf_path
):
    """After setting game system, search results should show the new tag."""
    client.post("/api/index-files", json={
        "paths": [str(untagged_pdf_path)]
    })

    client.post("/api/set-game-systems", json={
        "filename": "random_supplement.pdf",
        "game_systems": ["Blades in the Dark"],
    })

    response = client.post("/api/search", json={
        "query": "random tables",
        "game_system": "Blades in the Dark",
    })

    data = response.json()
    assert len(data["results"]) > 0
    for result in data["results"]:
        assert result["game_system"] == "Blades in the Dark"


# ---------------------------------------------------------------------------
# GET /api/sources — game_system field
# ---------------------------------------------------------------------------

def test_sources_include_game_system(client, dnd5e_pdf_path):
    """Sources listing should include game_system for each source."""
    client.post("/api/index-files", json={
        "paths": [str(dnd5e_pdf_path)]
    })

    response = client.get("/api/sources")
    data = response.json()

    assert len(data["sources"]) == 1
    assert data["sources"][0]["game_system"] == "D&D 5E"


def test_sources_unknown_game_system(client, untagged_pdf_path):
    """Untagged sources should show game_system='unknown'."""
    client.post("/api/index-files", json={
        "paths": [str(untagged_pdf_path)]
    })

    response = client.get("/api/sources")
    data = response.json()
    assert data["sources"][0]["game_system"] == "unknown"


# ---------------------------------------------------------------------------
# POST /api/set-game-systems (multi-tag, issue #98)
# ---------------------------------------------------------------------------

def test_set_game_systems_multi(
    client, untagged_pdf_path, test_store, tmp_path
):
    """Setting multiple tags stores the primary and full list with the book
    and in the manifest."""
    client.post("/api/index-files", json={"paths": [str(untagged_pdf_path)]})

    response = client.post("/api/set-game-systems", json={
        "filename": "random_supplement.pdf",
        "game_systems": ["D&D 5E", "PF2E"],
    })

    assert response.status_code == 200
    data = response.json()
    assert data["game_system"] == "D&D 5E"
    assert data["game_systems"] == ["D&D 5E", "PF2E"]
    assert data["chunks_updated"] > 0

    # Units report the primary; the book carries every tag for scoping.
    (doc,) = test_store.documents()
    assert doc.game_system == "D&D 5E"
    assert doc.systems == ("D&D 5E", "PF2E")
    assert test_store.scope_document_ids(systems=["PF2E"]) != []

    # Manifest carries the full list.
    manifest_raw = json.loads((tmp_path / MANIFEST_FILENAME).read_text())
    entry = manifest_raw["files"][str(untagged_pdf_path)]
    assert entry["game_system"] == "D&D 5E"
    assert entry["game_systems"] == ["D&D 5E", "PF2E"]


def test_set_game_systems_clear(client, untagged_pdf_path, tmp_path):
    """Empty list clears tags back to 'unknown' / []."""
    client.post("/api/index-files", json={"paths": [str(untagged_pdf_path)]})
    client.post("/api/set-game-systems", json={
        "filename": "random_supplement.pdf",
        "game_systems": ["D&D 5E"],
    })

    response = client.post("/api/set-game-systems", json={
        "filename": "random_supplement.pdf",
        "game_systems": [],
    })

    assert response.status_code == 200
    assert response.json()["game_system"] == "unknown"

    manifest_raw = json.loads((tmp_path / MANIFEST_FILENAME).read_text())
    entry = manifest_raw["files"][str(untagged_pdf_path)]
    assert entry["game_system"] == "unknown"
    assert entry["game_systems"] == []


def test_manifest_auto_populates_legacy(tmp_path):
    """A manifest written before multi-tag support backfills game_systems on load."""
    from legend_lore.service import (
        IndexManifest,
        ManifestEntry,
        load_manifest,
        save_manifest,
    )

    legacy_entry = ManifestEntry.model_construct(
        filename="legacy.pdf",
        mtime=0.0,
        chunk_count=0,
        indexed_at="2025-01-01T00:00:00Z",
        game_system="D&D 5E",
        game_systems=[],
        content_hash="",
        file_size=0,
    )
    legacy = IndexManifest(version=1, files={"/path/to/legacy.pdf": legacy_entry})
    save_manifest(tmp_path, legacy)

    # Re-read: model_post_init should have backfilled.
    reloaded = load_manifest(tmp_path)
    entry = reloaded.files["/path/to/legacy.pdf"]
    assert entry.game_system == "D&D 5E"
    assert entry.game_systems == ["D&D 5E"]
