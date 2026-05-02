"""
Tests for custom game system CRUD and merge logic.

- POST /api/custom-game-systems — create a custom system (or override a built-in)
- PUT /api/custom-game-systems/{tag} — update a custom system (or create built-in override)
- DELETE /api/custom-game-systems/{tag} — remove a custom system (or reset built-in override)
- POST /api/custom-game-systems/toggle-builtin — disable/enable a built-in
- GET /api/known-game-systems — merged list with is_builtin, is_customized flags
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
        "keywords": ["cairn", "cairn 2e"],
    })

    assert response.status_code == 200
    data = response.json()
    assert data["tag"] == "Cairn"
    assert data["keywords"] == ["cairn", "cairn 2e"]


def test_create_builtin_override(client):
    """Creating a system with a built-in tag should succeed (creates override)."""
    response = client.post("/api/custom-game-systems", json={
        "tag": "D&D 5E",
        "keywords": ["5e", "dnd5e", "my custom keywords"],
    })
    assert response.status_code == 200

    # Should appear as is_builtin=True, is_customized=True in the known list
    known = client.get("/api/known-game-systems").json()
    dnd = next(s for s in known["systems"] if s["tag"] == "D&D 5E")
    assert dnd["is_builtin"] is True
    assert dnd["is_customized"] is True
    assert "my custom keywords" in dnd["keywords"]


def test_create_duplicate_custom_tag_rejected(client):
    """Creating two custom systems with the same tag should fail."""
    client.post("/api/custom-game-systems", json={
        "tag": "Mothership",
        "keywords": ["mothership"],
    })

    response = client.post("/api/custom-game-systems", json={
        "tag": "Mothership",
        "keywords": ["mothership rpg"],
    })
    assert response.status_code == 409


def test_create_builtin_override_twice_rejected(client):
    """Creating a built-in override twice should fail (custom entry already exists)."""
    client.post("/api/custom-game-systems", json={
        "tag": "D&D 5E",
        "keywords": ["5e custom"],
    })
    response = client.post("/api/custom-game-systems", json={
        "tag": "D&D 5E",
        "keywords": ["5e custom again"],
    })
    assert response.status_code == 409


def test_create_empty_tag_rejected(client):
    """Tag must not be empty."""
    response = client.post("/api/custom-game-systems", json={
        "tag": "  ",
    })
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/known-game-systems — merged list
# ---------------------------------------------------------------------------

def test_custom_system_in_known_list(client):
    """Custom systems should appear in known-game-systems with is_builtin=False."""
    client.post("/api/custom-game-systems", json={
        "tag": "Cairn",
        "keywords": ["cairn"],
    })

    response = client.get("/api/known-game-systems")
    data = response.json()

    cairn = next(s for s in data["systems"] if s["tag"] == "Cairn")
    assert cairn["is_builtin"] is False
    assert cairn["is_customized"] is False
    assert "cairn" in cairn["keywords"]


def test_builtins_have_is_builtin_true(client):
    """Built-in systems should have is_builtin=True and is_customized=False."""
    response = client.get("/api/known-game-systems")
    data = response.json()

    dnd = next(s for s in data["systems"] if s["tag"] == "D&D 5E")
    assert dnd["is_builtin"] is True
    assert dnd["is_customized"] is False


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
        "keywords": ["cairn"],
    })

    response = client.put("/api/custom-game-systems/Cairn", json={
        "tag": "Cairn 2E",
        "keywords": ["cairn", "cairn 2e", "cairn second edition"],
    })

    assert response.status_code == 200
    data = response.json()
    assert data["tag"] == "Cairn 2E"
    assert "cairn 2e" in data["keywords"]


def test_edit_builtin_creates_override(client):
    """Editing a built-in should create a custom override."""
    response = client.put("/api/custom-game-systems/D%26D%205E", json={
        "tag": "D&D 5E",
        "keywords": ["dnd", "5e", "custom kw"],
    })
    assert response.status_code == 200

    known = client.get("/api/known-game-systems").json()
    dnd = next(s for s in known["systems"] if s["tag"] == "D&D 5E")
    assert dnd["is_builtin"] is True
    assert dnd["is_customized"] is True
    assert "custom kw" in dnd["keywords"]


def test_update_nonexistent_system(client):
    """Updating a non-existent system (neither custom nor built-in) should return 404."""
    response = client.put("/api/custom-game-systems/Ghost", json={
        "tag": "Ghost",
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
        "keywords": ["cairn"],
    })

    response = client.delete("/api/custom-game-systems/Cairn")
    assert response.status_code == 200
    assert response.json()["deleted"] == "Cairn"

    # Verify it's gone from the known list
    known = client.get("/api/known-game-systems").json()
    tags = [s["tag"] for s in known["systems"]]
    assert "Cairn" not in tags


def test_delete_builtin_override_resets_to_defaults(client):
    """Deleting a built-in override should restore the original built-in."""
    # Override D&D 5E keywords
    client.post("/api/custom-game-systems", json={
        "tag": "D&D 5E",
        "keywords": ["custom kw only"],
    })

    # Delete the override
    response = client.delete("/api/custom-game-systems/D%26D%205E")
    assert response.status_code == 200

    # Built-in should be restored with original keywords
    known = client.get("/api/known-game-systems").json()
    dnd = next(s for s in known["systems"] if s["tag"] == "D&D 5E")
    assert dnd["is_builtin"] is True
    assert dnd["is_customized"] is False
    assert "d&d 5e" in dnd["keywords"]  # Original keyword restored


def test_delete_unoverridden_builtin_rejected(client):
    """Deleting a built-in that has no custom override should return 404."""
    response = client.delete("/api/custom-game-systems/D%26D%205E")
    assert response.status_code == 404


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


# ---------------------------------------------------------------------------
# Color (issue #198)
# ---------------------------------------------------------------------------

def test_known_systems_include_default_colors(client):
    """Built-ins ship with a default color in /api/known-game-systems."""
    known = client.get("/api/known-game-systems").json()
    dnd = next(s for s in known["systems"] if s["tag"] == "D&D 5E")
    pf = next(s for s in known["systems"] if s["tag"] == "PF2E")
    assert dnd["color"] == "#c75450"
    assert pf["color"] == "#5fb068"


def test_create_custom_with_color(client, tmp_path):
    """Custom system stores the chosen color and surfaces it via known-systems."""
    response = client.post("/api/custom-game-systems", json={
        "tag": "Cairn",
        "keywords": ["cairn"],
        "color": "#4fa896",
    })
    assert response.status_code == 200
    assert response.json()["color"] == "#4fa896"

    known = client.get("/api/known-game-systems").json()
    cairn = next(s for s in known["systems"] if s["tag"] == "Cairn")
    assert cairn["color"] == "#4fa896"


def test_create_custom_without_color_stays_unset(client):
    """A custom system without a color reports color=None so the UI can render
    the 'no color' state explicitly."""
    client.post("/api/custom-game-systems", json={
        "tag": "Mothership",
        "keywords": ["mothership"],
    })

    known = client.get("/api/known-game-systems").json()
    moth = next(s for s in known["systems"] if s["tag"] == "Mothership")
    assert moth["color"] is None


def test_update_custom_changes_color(client):
    """Updating a custom system replaces the stored color."""
    client.post("/api/custom-game-systems", json={
        "tag": "Cairn",
        "keywords": ["cairn"],
        "color": "#4fa896",
    })
    response = client.put("/api/custom-game-systems/Cairn", json={
        "tag": "Cairn",
        "keywords": ["cairn"],
        "color": "#9b6cb6",
    })
    assert response.status_code == 200
    assert response.json()["color"] == "#9b6cb6"


def test_builtin_override_inherits_color_when_unset(client):
    """Customizing a built-in without picking a color preserves the built-in default."""
    # Built-in D&D 5E ships as red.
    client.post("/api/custom-game-systems", json={
        "tag": "D&D 5E",
        "keywords": ["dnd5e", "my own keyword"],
        # color omitted on purpose
    })

    known = client.get("/api/known-game-systems").json()
    dnd = next(s for s in known["systems"] if s["tag"] == "D&D 5E")
    assert dnd["color"] == "#c75450"
    assert dnd["is_customized"] is True
