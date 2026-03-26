"""
Tests for custom game system CRUD and merge logic.

- POST /api/custom-game-systems — create a custom system
- PUT /api/custom-game-systems/{tag} — update a custom system
- DELETE /api/custom-game-systems/{tag} — remove a custom system
- POST /api/custom-game-systems/toggle-builtin — disable/enable a built-in
- GET /api/known-game-systems — merged list with is_builtin flag
"""

import json

from server import CUSTOM_SYSTEMS_FILENAME


# ---------------------------------------------------------------------------
# POST /api/custom-game-systems — create
# ---------------------------------------------------------------------------

def test_create_custom_system(client):
    """Creating a custom system should return the new entry."""
    response = client.post("/api/custom-game-systems", json={
        "tag": "Cairn",
        "game_system": "Cairn",
        "keywords": ["cairn", "cairn 2e"],
    })

    assert response.status_code == 200
    data = response.json()
    assert data["tag"] == "Cairn"
    assert data["game_system"] == "Cairn"
    assert data["keywords"] == ["cairn", "cairn 2e"]


def test_create_duplicate_tag_rejected(client):
    """Creating a system with an existing tag should return 409."""
    # "D&D 5E" is a built-in tag
    response = client.post("/api/custom-game-systems", json={
        "tag": "D&D 5E",
        "game_system": "D&D",
        "keywords": ["5e"],
    })
    assert response.status_code == 409


def test_create_duplicate_custom_tag_rejected(client):
    """Creating two custom systems with the same tag should fail."""
    client.post("/api/custom-game-systems", json={
        "tag": "Mothership",
        "game_system": "Mothership",
        "keywords": ["mothership"],
    })

    response = client.post("/api/custom-game-systems", json={
        "tag": "Mothership",
        "game_system": "Mothership RPG",
        "keywords": ["mothership rpg"],
    })
    assert response.status_code == 409


def test_create_empty_tag_rejected(client):
    """Tag must not be empty."""
    response = client.post("/api/custom-game-systems", json={
        "tag": "  ",
        "game_system": "Nothing",
    })
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/known-game-systems — merged list
# ---------------------------------------------------------------------------

def test_custom_system_in_known_list(client):
    """Custom systems should appear in known-game-systems with is_builtin=False."""
    client.post("/api/custom-game-systems", json={
        "tag": "Cairn",
        "game_system": "Cairn",
        "keywords": ["cairn"],
    })

    response = client.get("/api/known-game-systems")
    data = response.json()

    cairn = next(s for s in data["systems"] if s["tag"] == "Cairn")
    assert cairn["is_builtin"] is False
    assert cairn["game_system"] == "Cairn"
    assert "cairn" in cairn["keywords"]


def test_builtins_have_is_builtin_true(client):
    """Built-in systems should have is_builtin=True."""
    response = client.get("/api/known-game-systems")
    data = response.json()

    dnd = next(s for s in data["systems"] if s["tag"] == "D&D 5E")
    assert dnd["is_builtin"] is True


def test_known_systems_include_keywords(client):
    """Known-game-systems response should include keywords."""
    response = client.get("/api/known-game-systems")
    data = response.json()

    dnd = next(s for s in data["systems"] if s["tag"] == "D&D 5E")
    assert isinstance(dnd["keywords"], list)
    assert len(dnd["keywords"]) > 0


# ---------------------------------------------------------------------------
# PUT /api/custom-game-systems/{tag} — update
# ---------------------------------------------------------------------------

def test_update_custom_system(client):
    """Updating a custom system should change its fields."""
    client.post("/api/custom-game-systems", json={
        "tag": "Cairn",
        "game_system": "Cairn",
        "keywords": ["cairn"],
    })

    response = client.put("/api/custom-game-systems/Cairn", json={
        "tag": "Cairn",
        "game_system": "Cairn 2E",
        "keywords": ["cairn", "cairn 2e", "cairn second edition"],
    })

    assert response.status_code == 200
    data = response.json()
    assert data["game_system"] == "Cairn 2E"
    assert "cairn 2e" in data["keywords"]


def test_cannot_edit_builtin(client):
    """Editing a built-in system should return 400."""
    response = client.put("/api/custom-game-systems/D%26D%205E", json={
        "tag": "D&D 5E",
        "game_system": "DnD",
        "keywords": ["dnd"],
    })
    assert response.status_code == 400


def test_update_nonexistent_custom_system(client):
    """Updating a non-existent custom system should return 404."""
    response = client.put("/api/custom-game-systems/Ghost", json={
        "tag": "Ghost",
        "game_system": "Ghost RPG",
        "keywords": [],
    })
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/custom-game-systems/{tag} — delete
# ---------------------------------------------------------------------------

def test_delete_custom_system(client):
    """Deleting a custom system should remove it from the known list."""
    client.post("/api/custom-game-systems", json={
        "tag": "Cairn",
        "game_system": "Cairn",
        "keywords": ["cairn"],
    })

    response = client.delete("/api/custom-game-systems/Cairn")
    assert response.status_code == 200
    assert response.json()["deleted"] == "Cairn"

    # Verify it's gone from the known list
    known = client.get("/api/known-game-systems").json()
    tags = [s["tag"] for s in known["systems"]]
    assert "Cairn" not in tags


def test_cannot_delete_builtin(client):
    """Deleting a built-in system should return 400."""
    response = client.delete("/api/custom-game-systems/D%26D%205E")
    assert response.status_code == 400


def test_delete_nonexistent_custom_system(client):
    """Deleting a non-existent custom system should return 404."""
    response = client.delete("/api/custom-game-systems/Ghost")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/custom-game-systems/toggle-builtin — disable/enable
# ---------------------------------------------------------------------------

def test_disable_builtin(client):
    """Disabling a built-in should remove it from the known list."""
    response = client.post("/api/custom-game-systems/toggle-builtin", json={
        "tag": "GURPS",
        "disabled": True,
    })
    assert response.status_code == 200

    known = client.get("/api/known-game-systems").json()
    tags = [s["tag"] for s in known["systems"]]
    assert "GURPS" not in tags


def test_reenable_builtin(client):
    """Re-enabling a disabled built-in should restore it to the known list."""
    client.post("/api/custom-game-systems/toggle-builtin", json={
        "tag": "GURPS",
        "disabled": True,
    })
    client.post("/api/custom-game-systems/toggle-builtin", json={
        "tag": "GURPS",
        "disabled": False,
    })

    known = client.get("/api/known-game-systems").json()
    tags = [s["tag"] for s in known["systems"]]
    assert "GURPS" in tags


def test_toggle_nonbuiltin_rejected(client):
    """Toggling a non-built-in tag should return 400."""
    response = client.post("/api/custom-game-systems/toggle-builtin", json={
        "tag": "Cairn",
        "disabled": True,
    })
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def test_persist_to_disk(client, tmp_path):
    """Custom systems should be saved to disk as JSON."""
    client.post("/api/custom-game-systems", json={
        "tag": "Cairn",
        "game_system": "Cairn",
        "keywords": ["cairn"],
    })

    config_path = tmp_path / CUSTOM_SYSTEMS_FILENAME
    assert config_path.exists()

    raw = json.loads(config_path.read_text())
    assert raw["version"] == 1
    assert len(raw["systems"]) == 1
    assert raw["systems"][0]["tag"] == "Cairn"


def test_missing_file_loads_empty(client):
    """Without a config file, known-game-systems should still work."""
    response = client.get("/api/known-game-systems")
    assert response.status_code == 200
    data = response.json()
    # Should have all built-in systems
    assert len(data["systems"]) > 0
    assert all(s["is_builtin"] for s in data["systems"])


# ---------------------------------------------------------------------------
# Detection with custom systems
# ---------------------------------------------------------------------------

def test_custom_keywords_in_detection(client, tmp_path):
    """Custom system keywords should participate in auto-detection."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    # Create a custom system
    client.post("/api/custom-game-systems", json={
        "tag": "Mothership",
        "game_system": "Mothership",
        "keywords": ["mothership", "mothership rpg"],
    })

    # Create a PDF in a "Mothership" folder
    mothership_dir = tmp_path / "Mothership"
    mothership_dir.mkdir()
    pdf_path = mothership_dir / "panic_engine.pdf"
    c = canvas.Canvas(str(pdf_path), pagesize=letter)
    c.drawString(72, 750, "Welcome to the Mothership RPG sci-fi horror experience.")
    c.save()

    # Index the file — should auto-detect "Mothership"
    client.post("/api/index-files", json={
        "paths": [str(pdf_path)]
    })

    response = client.get("/api/sources")
    data = response.json()
    assert len(data["sources"]) == 1
    assert data["sources"][0]["game_system"] == "Mothership"
