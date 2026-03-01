"""
Tests for game system management endpoints.

- GET /api/game-systems — list distinct game systems in the index
- POST /api/set-game-system — override a file's game system tag
- GET /api/sources — verify game_system appears in source listings
"""

import json

from server import MANIFEST_FILENAME


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
# POST /api/set-game-system
# ---------------------------------------------------------------------------

def test_set_game_system_updates_metadata(
    client, untagged_pdf_path, test_collection
):
    """Setting game system should update all chunk metadata."""
    client.post("/api/index-files", json={
        "paths": [str(untagged_pdf_path)]
    })

    response = client.post("/api/set-game-system", json={
        "filename": "random_supplement.pdf",
        "game_system": "Savage Worlds",
    })

    assert response.status_code == 200
    data = response.json()
    assert data["game_system"] == "Savage Worlds"
    assert data["chunks_updated"] > 0

    # Verify metadata in ChromaDB
    results = test_collection.get(include=["metadatas"])
    for metadata in results["metadatas"]:
        assert metadata["game_system"] == "Savage Worlds"


def test_set_game_system_updates_manifest(
    client, untagged_pdf_path, tmp_path
):
    """Setting game system should also update the manifest."""
    client.post("/api/index-files", json={
        "paths": [str(untagged_pdf_path)]
    })

    client.post("/api/set-game-system", json={
        "filename": "random_supplement.pdf",
        "game_system": "GURPS",
    })

    manifest_raw = json.loads((tmp_path / MANIFEST_FILENAME).read_text())
    entry = manifest_raw["files"][str(untagged_pdf_path)]
    assert entry["game_system"] == "GURPS"


def test_set_game_system_nonexistent_source(client):
    """Setting game system on a non-indexed file should return 404."""
    response = client.post("/api/set-game-system", json={
        "filename": "ghost_book.pdf",
        "game_system": "D&D 5E",
    })

    assert response.status_code == 404


def test_set_game_system_reflected_in_search(
    client, untagged_pdf_path
):
    """After setting game system, search results should show the new tag."""
    client.post("/api/index-files", json={
        "paths": [str(untagged_pdf_path)]
    })

    client.post("/api/set-game-system", json={
        "filename": "random_supplement.pdf",
        "game_system": "Blades in the Dark",
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
