"""
Tests for document collections — CRUD and search filtering.

Collections are named subsets of indexed files that let users scope
their searches to a specific campaign or session prep context.
"""

import pytest


# ---------------------------------------------------------------------------
# CRUD tests
# ---------------------------------------------------------------------------

def test_list_collections_empty(client):
    """With no collections, the list should be empty."""
    response = client.get("/api/collections")
    assert response.status_code == 200
    data = response.json()
    assert data["collections"] == {}
    assert data["count"] == 0


def test_create_collection(client):
    """Creating a collection returns its name and file count."""
    response = client.post("/api/collections", json={
        "name": "Curse of Strahd",
        "file_paths": ["/path/to/strahd.pdf", "/path/to/vgm.pdf"],
        "description": "Campaign prep for CoS",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Curse of Strahd"
    assert data["file_count"] == 2


def test_create_collection_no_description(client):
    """Description is optional and defaults to empty string."""
    response = client.post("/api/collections", json={
        "name": "Quick Ref",
        "file_paths": ["/path/to/rules.pdf"],
    })
    assert response.status_code == 200

    # Verify the default description
    list_resp = client.get("/api/collections")
    col = list_resp.json()["collections"]["Quick Ref"]
    assert col["description"] == ""


def test_create_duplicate_collection(client):
    """Creating a collection with an existing name returns 409."""
    client.post("/api/collections", json={
        "name": "My Campaign",
        "file_paths": ["/path/to/file.pdf"],
    })
    response = client.post("/api/collections", json={
        "name": "My Campaign",
        "file_paths": ["/path/to/other.pdf"],
    })
    assert response.status_code == 409


def test_list_collections_after_create(client):
    """Created collections appear in the list with correct metadata."""
    client.post("/api/collections", json={
        "name": "Session 5 Prep",
        "file_paths": ["/a.pdf", "/b.pdf", "/c.pdf"],
        "description": "Three books for tonight",
    })

    response = client.get("/api/collections")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1

    col = data["collections"]["Session 5 Prep"]
    assert col["name"] == "Session 5 Prep"
    assert col["file_count"] == 3
    assert col["description"] == "Three books for tonight"
    assert len(col["file_paths"]) == 3
    assert "created_at" in col


def test_update_collection(client):
    """Updating a collection changes its file list."""
    client.post("/api/collections", json={
        "name": "Evolving Set",
        "file_paths": ["/a.pdf"],
    })

    response = client.put("/api/collections/Evolving Set", json={
        "file_paths": ["/a.pdf", "/b.pdf", "/c.pdf"],
    })
    assert response.status_code == 200
    assert response.json()["file_count"] == 3

    # Verify the change persisted
    col = client.get("/api/collections").json()["collections"]["Evolving Set"]
    assert len(col["file_paths"]) == 3


def test_update_collection_description(client):
    """Updating description changes it; omitting it keeps the old value."""
    client.post("/api/collections", json={
        "name": "Described",
        "file_paths": ["/a.pdf"],
        "description": "Original description",
    })

    # Update with new description
    client.put("/api/collections/Described", json={
        "file_paths": ["/a.pdf"],
        "description": "Updated description",
    })
    col = client.get("/api/collections").json()["collections"]["Described"]
    assert col["description"] == "Updated description"

    # Update without description field — should keep existing
    client.put("/api/collections/Described", json={
        "file_paths": ["/a.pdf", "/b.pdf"],
    })
    col = client.get("/api/collections").json()["collections"]["Described"]
    assert col["description"] == "Updated description"
    assert col["file_count"] == 2


def test_update_nonexistent_collection(client):
    """Updating a collection that doesn't exist returns 404."""
    response = client.put("/api/collections/Ghost Collection", json={
        "file_paths": ["/a.pdf"],
    })
    assert response.status_code == 404


def test_delete_collection(client):
    """Deleting a collection removes it from the store."""
    client.post("/api/collections", json={
        "name": "Doomed",
        "file_paths": ["/a.pdf"],
    })
    response = client.delete("/api/collections/Doomed")
    assert response.status_code == 200

    # Verify it's gone
    data = client.get("/api/collections").json()
    assert "Doomed" not in data["collections"]
    assert data["count"] == 0


def test_delete_nonexistent_collection(client):
    """Deleting a collection that doesn't exist returns 404."""
    response = client.delete("/api/collections/Nope")
    assert response.status_code == 404


def test_multiple_collections(client):
    """Multiple collections can coexist."""
    client.post("/api/collections", json={
        "name": "Campaign A",
        "file_paths": ["/a.pdf"],
    })
    client.post("/api/collections", json={
        "name": "Campaign B",
        "file_paths": ["/b.pdf", "/c.pdf"],
    })

    data = client.get("/api/collections").json()
    assert data["count"] == 2
    assert "Campaign A" in data["collections"]
    assert "Campaign B" in data["collections"]


def test_collections_persist_across_restart(test_collection, tmp_path):
    """Collections created in one server session are available after restart."""
    from server import create_app
    from fastapi.testclient import TestClient

    # Session 1: create a collection
    app1 = create_app(collection=test_collection, data_dir=tmp_path)
    client1 = TestClient(app1)

    client1.post("/api/collections", json={
        "name": "Curse of Strahd",
        "file_paths": ["/books/cos.pdf", "/books/vgm.pdf"],
        "description": "Barovia campaign prep",
    })

    # Session 2: fresh app, same data_dir
    app2 = create_app(collection=test_collection, data_dir=tmp_path)
    client2 = TestClient(app2)

    data = client2.get("/api/collections").json()
    assert data["count"] == 1
    col = data["collections"]["Curse of Strahd"]
    assert col["name"] == "Curse of Strahd"
    assert col["file_count"] == 2
    assert col["description"] == "Barovia campaign prep"
    assert set(col["file_paths"]) == {"/books/cos.pdf", "/books/vgm.pdf"}
    assert "created_at" in col


def test_collections_loaded_from_preexisting_json(test_collection, tmp_path):
    """A hand-written collections.json is loaded correctly by a fresh server."""
    import json
    from server import create_app
    from fastapi.testclient import TestClient

    collections_data = {
        "version": 1,
        "collections": {
            "Session Zero": {
                "name": "Session Zero",
                "file_paths": ["/prep/setting.pdf", "/prep/npcs.pdf", "/prep/maps.pdf"],
                "created_at": "2025-01-15T12:00:00+00:00",
                "description": "World-building references",
            }
        },
    }
    (tmp_path / "collections.json").write_text(json.dumps(collections_data, indent=2))

    app = create_app(collection=test_collection, data_dir=tmp_path)
    client = TestClient(app)

    data = client.get("/api/collections").json()
    assert data["count"] == 1

    col = data["collections"]["Session Zero"]
    assert col["name"] == "Session Zero"
    assert col["file_count"] == 3
    assert col["description"] == "World-building references"
    assert col["created_at"] == "2025-01-15T12:00:00+00:00"
    assert "/prep/setting.pdf" in col["file_paths"]


# ---------------------------------------------------------------------------
# Metadata schema (id, updated_at, last_used_at, color, archived)
# ---------------------------------------------------------------------------

def test_create_returns_metadata_fields(client):
    """A newly created collection exposes the full v2 metadata shape."""
    client.post("/api/collections", json={
        "name": "Strahd",
        "file_paths": ["/cos.pdf"],
        "description": "Barovia",
        "color": "#8B0000",
    })
    col = client.get("/api/collections").json()["collections"]["Strahd"]
    assert col["id"]
    assert col["name"] == "Strahd"
    assert col["created_at"]
    assert col["updated_at"] == col["created_at"]
    assert col["last_used_at"] is None
    assert col["color"] == "#8B0000"
    assert col["archived"] is False


def test_create_without_color_defaults_to_null(client):
    """color is optional and serializes as null when omitted."""
    client.post("/api/collections", json={
        "name": "Plain",
        "file_paths": ["/a.pdf"],
    })
    col = client.get("/api/collections").json()["collections"]["Plain"]
    assert col["color"] is None


def test_collection_ids_are_unique(client):
    """Each create gets a fresh id."""
    client.post("/api/collections", json={"name": "A", "file_paths": []})
    client.post("/api/collections", json={"name": "B", "file_paths": []})
    cols = client.get("/api/collections").json()["collections"]
    assert cols["A"]["id"] != cols["B"]["id"]


def test_update_bumps_updated_at(client):
    """Any successful mutation moves updated_at forward."""
    import time
    client.post("/api/collections", json={"name": "Stamps", "file_paths": ["/a.pdf"]})
    before = client.get("/api/collections").json()["collections"]["Stamps"]["updated_at"]

    time.sleep(0.01)
    client.put("/api/collections/Stamps", json={"description": "now with notes"})
    after = client.get("/api/collections").json()["collections"]["Stamps"]["updated_at"]

    assert after > before


def test_update_writes_archived(client):
    """archived flag persists across a PUT."""
    client.post("/api/collections", json={"name": "Old Campaign", "file_paths": []})
    client.put("/api/collections/Old Campaign", json={"archived": True})
    col = client.get("/api/collections").json()["collections"]["Old Campaign"]
    assert col["archived"] is True


def test_update_writes_color(client):
    """color is settable via PUT."""
    client.post("/api/collections", json={"name": "Tinted", "file_paths": []})
    client.put("/api/collections/Tinted", json={"color": "#336699"})
    col = client.get("/api/collections").json()["collections"]["Tinted"]
    assert col["color"] == "#336699"


def test_update_writes_last_used_at(client):
    """last_used_at can be written through the existing update endpoint."""
    client.post("/api/collections", json={"name": "Touched", "file_paths": []})
    stamp = "2026-04-30T12:34:56+00:00"
    client.put("/api/collections/Touched", json={"last_used_at": stamp})
    col = client.get("/api/collections").json()["collections"]["Touched"]
    assert col["last_used_at"] == stamp


def test_update_without_file_paths_keeps_existing(client):
    """Omitting file_paths in a PUT leaves the file list untouched."""
    client.post("/api/collections", json={
        "name": "Sticky",
        "file_paths": ["/a.pdf", "/b.pdf"],
    })
    client.put("/api/collections/Sticky", json={"description": "metadata only"})
    col = client.get("/api/collections").json()["collections"]["Sticky"]
    assert col["file_count"] == 2
    assert col["description"] == "metadata only"


def test_v1_collections_migrate_on_load(test_collection, tmp_path):
    """Legacy v1 records gain v2 fields with sensible defaults."""
    import json
    from server import create_app
    from fastapi.testclient import TestClient

    legacy = {
        "version": 1,
        "collections": {
            "Old": {
                "name": "Old",
                "file_paths": ["/old.pdf"],
                "created_at": "2025-01-15T12:00:00+00:00",
                "description": "from v1",
            }
        },
    }
    (tmp_path / "collections.json").write_text(json.dumps(legacy))

    app = create_app(collection=test_collection, data_dir=tmp_path)
    client = TestClient(app)

    col = client.get("/api/collections").json()["collections"]["Old"]
    assert col["id"]  # generated
    assert col["created_at"] == "2025-01-15T12:00:00+00:00"
    assert col["updated_at"] == "2025-01-15T12:00:00+00:00"
    assert col["last_used_at"] is None
    assert col["color"] is None
    assert col["archived"] is False


# ---------------------------------------------------------------------------
# Active context — unified scope for tree filter + MCP
# ---------------------------------------------------------------------------

def test_get_active_context_default_null(client):
    """A fresh store has no active context."""
    resp = client.get("/api/active-context")
    assert resp.status_code == 200
    assert resp.json() == {"active_context": None}


def test_set_active_context(client):
    """Setting a context records it on disk and exposes it via GET."""
    client.post("/api/collections", json={"name": "Strahd", "file_paths": []})
    resp = client.post("/api/active-context", json={"name": "Strahd"})
    assert resp.status_code == 200
    assert resp.json() == {"active_context": "Strahd"}
    assert client.get("/api/active-context").json()["active_context"] == "Strahd"


def test_set_active_context_updates_last_used_at(client):
    """Setting the active context bumps last_used_at on the collection."""
    client.post("/api/collections", json={"name": "Touched", "file_paths": []})
    before = client.get("/api/collections").json()["collections"]["Touched"]
    assert before["last_used_at"] is None

    client.post("/api/active-context", json={"name": "Touched"})
    after = client.get("/api/collections").json()["collections"]["Touched"]
    assert after["last_used_at"] is not None


def test_set_active_context_unknown_collection_returns_404(client):
    resp = client.post("/api/active-context", json={"name": "Nope"})
    assert resp.status_code == 404


def test_clear_active_context(client):
    """DELETE /api/active-context unsets it."""
    client.post("/api/collections", json={"name": "Strahd", "file_paths": []})
    client.post("/api/active-context", json={"name": "Strahd"})
    client.delete("/api/active-context")
    assert client.get("/api/active-context").json()["active_context"] is None


def test_set_replaces_previous_context(client):
    """Setting a different collection replaces the previous active context."""
    client.post("/api/collections", json={"name": "A", "file_paths": []})
    client.post("/api/collections", json={"name": "B", "file_paths": []})
    client.post("/api/active-context", json={"name": "A"})
    client.post("/api/active-context", json={"name": "B"})
    assert client.get("/api/active-context").json()["active_context"] == "B"


def test_deleting_active_collection_clears_context(client):
    """Deleting the collection that's currently active clears the context."""
    client.post("/api/collections", json={"name": "Doomed", "file_paths": []})
    client.post("/api/active-context", json={"name": "Doomed"})
    client.delete("/api/collections/Doomed")
    assert client.get("/api/active-context").json()["active_context"] is None


def test_deleting_other_collection_keeps_context(client):
    """Deleting an unrelated collection does not affect the active context."""
    client.post("/api/collections", json={"name": "Keep", "file_paths": []})
    client.post("/api/collections", json={"name": "Drop", "file_paths": []})
    client.post("/api/active-context", json={"name": "Keep"})
    client.delete("/api/collections/Drop")
    assert client.get("/api/active-context").json()["active_context"] == "Keep"


def test_list_collections_includes_active_context(client):
    """GET /api/collections exposes the active context for hydration."""
    client.post("/api/collections", json={"name": "X", "file_paths": []})
    client.post("/api/active-context", json={"name": "X"})
    data = client.get("/api/collections").json()
    assert data["active_context"] == "X"


def test_active_context_persists_across_restart(test_collection, tmp_path):
    """Active context survives a sidecar restart."""
    from server import create_app
    from fastapi.testclient import TestClient

    app1 = create_app(collection=test_collection, data_dir=tmp_path)
    c1 = TestClient(app1)
    c1.post("/api/collections", json={"name": "Sticky", "file_paths": []})
    c1.post("/api/active-context", json={"name": "Sticky"})

    app2 = create_app(collection=test_collection, data_dir=tmp_path)
    c2 = TestClient(app2)
    assert c2.get("/api/active-context").json()["active_context"] == "Sticky"


def test_search_auto_scopes_to_active_context(
    multi_indexed_client, sample_pdf_path
):
    """Without an explicit collection, search uses the active context."""
    multi_indexed_client.post("/api/collections", json={
        "name": "Monsters",
        "file_paths": [str(sample_pdf_path)],
    })
    multi_indexed_client.post("/api/active-context", json={"name": "Monsters"})

    response = multi_indexed_client.post("/api/search", json={
        "query": "adventurer dungeon perception",
        "n_results": 10,
    })

    data = response.json()
    assert data.get("auto_scoped") is True
    assert data.get("effective_collection") == "Monsters"
    for r in data["results"]:
        assert r["filename"] == "dragonbane_monsters.pdf"


def test_explicit_collection_overrides_active_context(
    multi_indexed_client, sample_pdf_path, large_text_pdf_path
):
    """Passing collection explicitly takes precedence over the active context."""
    multi_indexed_client.post("/api/collections", json={
        "name": "Monsters",
        "file_paths": [str(sample_pdf_path)],
    })
    multi_indexed_client.post("/api/collections", json={
        "name": "Core",
        "file_paths": [str(large_text_pdf_path)],
    })
    multi_indexed_client.post("/api/active-context", json={"name": "Monsters"})

    response = multi_indexed_client.post("/api/search", json={
        "query": "dungeon adventurer perception",
        "n_results": 10,
        "collection": "Core",
    })

    data = response.json()
    assert data.get("auto_scoped") is False
    assert data.get("effective_collection") == "Core"
    for r in data["results"]:
        assert r["filename"] == "core_rules.pdf"


def test_search_all_bypasses_active_context(
    multi_indexed_client, sample_pdf_path
):
    """search_all=True ignores the active context entirely."""
    multi_indexed_client.post("/api/collections", json={
        "name": "Monsters",
        "file_paths": [str(sample_pdf_path)],
    })
    multi_indexed_client.post("/api/active-context", json={"name": "Monsters"})

    response = multi_indexed_client.post("/api/search", json={
        "query": "dragon dungeon adventurer",
        "n_results": 10,
        "search_all": True,
    })

    data = response.json()
    assert data.get("auto_scoped") is False
    assert data.get("effective_collection") is None
    filenames = {r["filename"] for r in data["results"]}
    assert len(filenames) >= 1


# ---------------------------------------------------------------------------
# Atomic rename — POST /api/collections/{name}/rename
# ---------------------------------------------------------------------------

def test_rename_collection_basic(client):
    """Renaming a collection moves it under the new name and preserves metadata."""
    client.post("/api/collections", json={
        "name": "Old Name",
        "file_paths": ["/a.pdf", "/b.pdf"],
        "description": "kept",
        "color": "#123456",
    })
    before = client.get("/api/collections").json()["collections"]["Old Name"]

    resp = client.post("/api/collections/Old Name/rename", json={"new_name": "New Name"})
    assert resp.status_code == 200
    assert resp.json() == {"name": "New Name", "file_count": 2}

    cols = client.get("/api/collections").json()["collections"]
    assert "Old Name" not in cols
    assert "New Name" in cols
    after = cols["New Name"]
    assert after["id"] == before["id"]
    assert after["created_at"] == before["created_at"]
    assert after["file_paths"] == before["file_paths"]
    assert after["description"] == "kept"
    assert after["color"] == "#123456"
    assert after["archived"] is False
    assert after["updated_at"] >= before["updated_at"]


def test_rename_collection_preserves_active_context(client):
    """Renaming the active collection moves the active_context pointer."""
    client.post("/api/collections", json={"name": "Active", "file_paths": []})
    client.post("/api/active-context", json={"name": "Active"})

    resp = client.post("/api/collections/Active/rename", json={"new_name": "Renamed"})
    assert resp.status_code == 200

    assert client.get("/api/active-context").json()["active_context"] == "Renamed"


def test_rename_collection_does_not_touch_unrelated_active_context(client):
    """Renaming a non-active collection leaves the active_context alone."""
    client.post("/api/collections", json={"name": "Active", "file_paths": []})
    client.post("/api/collections", json={"name": "Other", "file_paths": []})
    client.post("/api/active-context", json={"name": "Active"})

    resp = client.post("/api/collections/Other/rename", json={"new_name": "OtherRenamed"})
    assert resp.status_code == 200

    assert client.get("/api/active-context").json()["active_context"] == "Active"


def test_rename_collection_to_existing_name_returns_409(client):
    """Renaming onto an existing collection name fails with 409 and is non-destructive."""
    client.post("/api/collections", json={"name": "A", "file_paths": ["/a.pdf"]})
    client.post("/api/collections", json={"name": "B", "file_paths": ["/b.pdf"]})

    resp = client.post("/api/collections/A/rename", json={"new_name": "B"})
    assert resp.status_code == 409

    cols = client.get("/api/collections").json()["collections"]
    assert "A" in cols and "B" in cols
    assert cols["A"]["file_paths"] == ["/a.pdf"]
    assert cols["B"]["file_paths"] == ["/b.pdf"]


def test_rename_collection_missing_returns_404(client):
    resp = client.post("/api/collections/Ghost/rename", json={"new_name": "Whatever"})
    assert resp.status_code == 404


def test_rename_collection_to_same_name_is_noop(client):
    """Renaming to the same name returns success without touching updated_at."""
    client.post("/api/collections", json={"name": "Same", "file_paths": ["/a.pdf"]})
    before = client.get("/api/collections").json()["collections"]["Same"]

    resp = client.post("/api/collections/Same/rename", json={"new_name": "Same"})
    assert resp.status_code == 200
    assert resp.json() == {"name": "Same", "file_count": 1}

    after = client.get("/api/collections").json()["collections"]["Same"]
    assert after["updated_at"] == before["updated_at"]


def test_rename_collection_empty_name_returns_400(client):
    client.post("/api/collections", json={"name": "Real", "file_paths": []})
    resp = client.post("/api/collections/Real/rename", json={"new_name": "   "})
    assert resp.status_code == 400


def test_rename_collection_persists_to_disk(test_collection, tmp_path):
    """Renamed collections survive a server restart."""
    from server import create_app
    from fastapi.testclient import TestClient

    app1 = create_app(collection=test_collection, data_dir=tmp_path)
    c1 = TestClient(app1)
    c1.post("/api/collections", json={"name": "First", "file_paths": ["/a.pdf"]})
    c1.post("/api/collections/First/rename", json={"new_name": "Second"})

    app2 = create_app(collection=test_collection, data_dir=tmp_path)
    c2 = TestClient(app2)
    cols = c2.get("/api/collections").json()["collections"]
    assert "First" not in cols
    assert "Second" in cols
    assert cols["Second"]["file_paths"] == ["/a.pdf"]


def test_v1_disk_migrates_to_v2_on_save(test_collection, tmp_path):
    """After a write, the on-disk file is in v2 shape."""
    import json
    from server import create_app
    from fastapi.testclient import TestClient

    legacy = {
        "version": 1,
        "collections": {
            "Old": {
                "name": "Old",
                "file_paths": [],
                "created_at": "2025-01-15T12:00:00+00:00",
                "description": "",
            }
        },
    }
    (tmp_path / "collections.json").write_text(json.dumps(legacy))

    app = create_app(collection=test_collection, data_dir=tmp_path)
    client = TestClient(app)
    client.post("/api/collections", json={"name": "New", "file_paths": []})

    on_disk = json.loads((tmp_path / "collections.json").read_text())
    assert on_disk["version"] == 2
    old = on_disk["collections"]["Old"]
    assert "id" in old and old["id"]
    assert old["updated_at"] == "2025-01-15T12:00:00+00:00"
    assert old["archived"] is False
    new = on_disk["collections"]["New"]
    assert new["id"] != old["id"]


# ---------------------------------------------------------------------------
# Search with collection filter
# ---------------------------------------------------------------------------

@pytest.fixture
def multi_indexed_client(client, sample_pdf_path, large_text_pdf_path):
    """Client with two PDFs indexed — for testing collection filtering.

    - dragonbane_monsters.pdf: dragon/fire content
    - core_rules.pdf: dungeon/adventurer content
    """
    client.post("/api/index-files", json={
        "paths": [str(sample_pdf_path), str(large_text_pdf_path)]
    })
    return client


def test_search_with_collection_filter(
    multi_indexed_client, sample_pdf_path
):
    """Search with a collection filter returns only files in that collection."""
    # Create a collection containing only the monsters PDF
    multi_indexed_client.post("/api/collections", json={
        "name": "Monsters Only",
        "file_paths": [str(sample_pdf_path)],
    })

    response = multi_indexed_client.post("/api/search", json={
        "query": "adventurer dungeon perception",
        "n_results": 10,
        "collection": "Monsters Only",
    })

    data = response.json()
    for result in data["results"]:
        assert result["filename"] == "dragonbane_monsters.pdf"


def test_search_without_collection_returns_all(
    multi_indexed_client, sample_pdf_path
):
    """Without collection filter, results from all files should appear."""
    # Create a collection but don't use it in the search
    multi_indexed_client.post("/api/collections", json={
        "name": "Unused",
        "file_paths": [str(sample_pdf_path)],
    })

    response = multi_indexed_client.post("/api/search", json={
        "query": "dragon dungeon adventurer",
        "n_results": 10,
    })

    data = response.json()
    filenames = {r["filename"] for r in data["results"]}
    assert len(filenames) >= 1


def test_search_collection_not_found(multi_indexed_client):
    """Searching with a nonexistent collection returns 404."""
    response = multi_indexed_client.post("/api/search", json={
        "query": "anything",
        "n_results": 5,
        "collection": "Does Not Exist",
    })
    assert response.status_code == 404


def test_search_collection_empty_after_deindex(
    multi_indexed_client, sample_pdf_path
):
    """A collection pointing to non-indexed files returns empty results."""
    # Create a collection with a path that won't be in the manifest
    multi_indexed_client.post("/api/collections", json={
        "name": "Stale Refs",
        "file_paths": ["/nonexistent/path/to/deleted.pdf"],
    })

    response = multi_indexed_client.post("/api/search", json={
        "query": "anything",
        "n_results": 5,
        "collection": "Stale Refs",
    })

    assert response.status_code == 200
    data = response.json()
    assert data["results"] == []
    assert "no indexed files" in data.get("message", "").lower()
