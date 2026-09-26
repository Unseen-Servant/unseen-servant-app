"""
Tests for game system management endpoints.

- GET /api/game-systems — list distinct game systems in the index
- POST /api/set-game-systems — override a file's game system tags
- GET /api/sources — verify game_system appears in source listings
"""

import json

from legend_lore.parents_store import search_units_fts
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
    client, untagged_pdf_path, test_collection, tmp_path
):
    """Setting game system should update all chunk metadata."""
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

    # Verify metadata in ChromaDB
    results = test_collection.get(include=["metadatas"])
    for metadata in results["metadatas"]:
        assert metadata["game_system"] == "Savage Worlds"

    # The persisted FTS rows carry the same scope columns, so the retag
    # has to reach them too or a game_system-scoped hybrid search would
    # still see the old tag.
    assert search_units_fts(
        tmp_path, '"tables"', 10, {"game_system": "Savage Worlds"}
    )
    assert search_units_fts(
        tmp_path, '"tables"', 10, {"game_system": "unknown"}
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
    client, untagged_pdf_path, test_collection, tmp_path
):
    """Setting multiple tags writes the primary to Chroma and full list to manifest."""
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

    # Chroma chunks store only the primary scalar.
    results = test_collection.get(include=["metadatas"])
    for metadata in results["metadatas"]:
        assert metadata["game_system"] == "D&D 5E"

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


def test_set_game_systems_batches_the_chunk_update(
    client, large_text_pdf_path, test_collection, monkeypatch
):
    """Tagging a file with more chunks than Chroma's cap still succeeds.

    ChromaDB rejects any single update carrying more records than its max
    batch size (5461 for a local client), so a rulebook that chunks into
    six or thirteen thousand pieces cannot have its tags rewritten in one
    call. Patching the batch size down to 1 exercises the multi-batch path
    without indexing a 5000-chunk PDF.
    """
    from legend_lore import router

    client.post("/api/index-files", json={"paths": [str(large_text_pdf_path)]})
    total = len(test_collection.get()["ids"])
    assert total > 1, "fixture must produce several chunks to exercise batching"

    monkeypatch.setattr(router, "METADATA_UPDATE_BATCH_SIZE", 1)

    # Record the size of every update call so the cap is verified directly,
    # not just inferred from the endpoint returning 200.
    batch_sizes = []
    original_update = test_collection.update

    def spy_update(ids, **kwargs):
        batch_sizes.append(len(ids))
        return original_update(ids=ids, **kwargs)

    monkeypatch.setattr(test_collection, "update", spy_update)

    response = client.post("/api/set-game-systems", json={
        "filename": "core_rules.pdf",
        "game_systems": ["OSR"],
    })

    assert response.status_code == 200, response.text
    assert response.json()["chunks_updated"] == total

    assert batch_sizes, "expected at least one update call"
    assert max(batch_sizes) <= 1, f"a batch exceeded the cap: {batch_sizes}"
    assert sum(batch_sizes) == total, "every chunk should be covered exactly once"

    results = test_collection.get(include=["metadatas"])
    assert all(m["game_system"] == "OSR" for m in results["metadatas"])


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
