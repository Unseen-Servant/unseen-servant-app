"""
Tests for index-status and sync-index endpoints.

These endpoints enable incremental indexing: instead of re-processing
every selected PDF, the sidecar compares selected paths against a
manifest of previously indexed files and only processes the diff.
"""

import json
import os
import time

from server import MANIFEST_FILENAME, IndexManifest, ManifestEntry


# ---------------------------------------------------------------------------
# POST /api/index-status
# ---------------------------------------------------------------------------

def test_index_status_new_files(client, sample_pdf_path):
    """Selected files not in the manifest should appear in to_add."""
    response = client.post("/api/index-status", json={
        "selected_paths": [str(sample_pdf_path)]
    })

    assert response.status_code == 200
    data = response.json()
    assert len(data["to_add"]) == 1
    assert data["to_add"][0]["filename"] == "dragonbane_monsters.pdf"
    assert data["summary"]["add"] == 1


def test_index_status_removed_files(client, sample_pdf_path, tmp_path):
    """Manifest entries not in selected_paths should appear in to_remove."""
    # Pre-seed manifest with a file that won't be in selected_paths
    manifest = IndexManifest(files={
        "/old/removed_book.pdf": ManifestEntry(
            filename="removed_book.pdf",
            mtime=1000.0,
            chunk_count=10,
            indexed_at="2026-01-01T00:00:00Z",
        )
    })
    (tmp_path / MANIFEST_FILENAME).write_text(manifest.model_dump_json())

    response = client.post("/api/index-status", json={
        "selected_paths": []  # Nothing selected
    })

    data = response.json()
    assert len(data["to_remove"]) == 1
    assert data["to_remove"][0]["filename"] == "removed_book.pdf"
    assert data["to_remove"][0]["chunk_count"] == 10
    assert data["summary"]["remove"] == 1


def test_index_status_modified_file(client, sample_pdf_path, tmp_path):
    """Files with a different mtime than the manifest should be in to_update."""
    # Pre-seed manifest with an old mtime
    manifest = IndexManifest(files={
        str(sample_pdf_path): ManifestEntry(
            filename="dragonbane_monsters.pdf",
            mtime=1.0,  # Clearly wrong — file was just created
            chunk_count=5,
            indexed_at="2026-01-01T00:00:00Z",
        )
    })
    (tmp_path / MANIFEST_FILENAME).write_text(manifest.model_dump_json())

    response = client.post("/api/index-status", json={
        "selected_paths": [str(sample_pdf_path)]
    })

    data = response.json()
    assert len(data["to_update"]) == 1
    assert data["to_update"][0]["filename"] == "dragonbane_monsters.pdf"
    assert data["summary"]["update"] == 1


def test_index_status_up_to_date(client, sample_pdf_path, tmp_path):
    """Files with matching mtime should appear in up_to_date."""
    current_mtime = os.path.getmtime(sample_pdf_path)
    manifest = IndexManifest(files={
        str(sample_pdf_path): ManifestEntry(
            filename="dragonbane_monsters.pdf",
            mtime=current_mtime,
            chunk_count=5,
            indexed_at="2026-01-01T00:00:00Z",
        )
    })
    (tmp_path / MANIFEST_FILENAME).write_text(manifest.model_dump_json())

    response = client.post("/api/index-status", json={
        "selected_paths": [str(sample_pdf_path)]
    })

    data = response.json()
    assert len(data["up_to_date"]) == 1
    assert data["summary"]["up_to_date"] == 1
    assert data["summary"]["add"] == 0


def test_index_status_missing_file_on_disk(client, tmp_path):
    """Selected paths that don't exist on disk should appear in errors."""
    response = client.post("/api/index-status", json={
        "selected_paths": ["/nonexistent/ghost.pdf"]
    })

    data = response.json()
    assert len(data["errors"]) == 1
    assert "File not found" in data["errors"][0]["error"]
    assert data["summary"]["errors"] == 1


def test_index_status_empty_selection(client):
    """Empty selection with empty manifest should return all zeros."""
    response = client.post("/api/index-status", json={
        "selected_paths": []
    })

    data = response.json()
    assert data["summary"] == {
        "add": 0, "remove": 0, "update": 0,
        "up_to_date": 0, "errors": 0,
    }


# ---------------------------------------------------------------------------
# POST /api/sync-index
# ---------------------------------------------------------------------------

def test_sync_adds_new_files(
    client, sample_pdf_path, test_collection, tmp_path
):
    """Sync should index new files and write them to the manifest."""
    response = client.post("/api/sync-index", json={
        "selected_paths": [str(sample_pdf_path)]
    })

    assert response.status_code == 200
    data = response.json()
    assert data["added"] == 1
    assert data["removed"] == 0
    assert data["updated"] == 0
    assert data["total_indexed"] == 1

    # Verify chunks in ChromaDB
    assert test_collection.count() > 0

    # Verify manifest was written
    manifest_raw = json.loads((tmp_path / MANIFEST_FILENAME).read_text())
    assert str(sample_pdf_path) in manifest_raw["files"]


def test_sync_removes_files(
    client, sample_pdf_path, test_collection, tmp_path
):
    """Sync should delete chunks for files no longer selected."""
    # First, index a file
    client.post("/api/sync-index", json={
        "selected_paths": [str(sample_pdf_path)]
    })
    assert test_collection.count() > 0

    # Now sync with empty selection — should remove it
    response = client.post("/api/sync-index", json={
        "selected_paths": []
    })

    data = response.json()
    assert data["removed"] == 1
    assert data["total_indexed"] == 0

    # Verify chunks deleted from ChromaDB
    assert test_collection.count() == 0

    # Verify manifest entry removed
    manifest_raw = json.loads((tmp_path / MANIFEST_FILENAME).read_text())
    assert str(sample_pdf_path) not in manifest_raw["files"]


def test_sync_updates_modified_files(
    client, sample_pdf_path, test_collection, tmp_path
):
    """Sync should re-index files whose mtime has changed."""
    # Index the file first
    client.post("/api/sync-index", json={
        "selected_paths": [str(sample_pdf_path)]
    })
    count_before = test_collection.count()

    # Simulate modification by changing the manifest mtime
    manifest_raw = json.loads((tmp_path / MANIFEST_FILENAME).read_text())
    path_key = str(sample_pdf_path)
    manifest_raw["files"][path_key]["mtime"] = 1.0  # Force mismatch
    (tmp_path / MANIFEST_FILENAME).write_text(json.dumps(manifest_raw))

    # Sync again — should detect the "modification" and re-index
    response = client.post("/api/sync-index", json={
        "selected_paths": [str(sample_pdf_path)]
    })

    data = response.json()
    assert data["updated"] == 1
    assert data["added"] == 0

    # Chunk count should be the same (same content, upsert overwrites)
    assert test_collection.count() == count_before


def test_sync_mixed_operations(
    client, sample_pdf_path, large_text_pdf_path, test_collection, tmp_path
):
    """Sync with a mix of adds and removes in one call."""
    # Index sample_pdf first
    client.post("/api/sync-index", json={
        "selected_paths": [str(sample_pdf_path)]
    })

    # Now sync with large_text_pdf selected instead (swap)
    response = client.post("/api/sync-index", json={
        "selected_paths": [str(large_text_pdf_path)]
    })

    data = response.json()
    assert data["added"] == 1       # large_text_pdf
    assert data["removed"] == 1     # sample_pdf
    assert data["total_indexed"] == 1

    # Verify only large_text_pdf remains in manifest
    manifest_raw = json.loads((tmp_path / MANIFEST_FILENAME).read_text())
    assert str(large_text_pdf_path) in manifest_raw["files"]
    assert str(sample_pdf_path) not in manifest_raw["files"]


def test_manifest_persists_after_sync(client, sample_pdf_path, tmp_path):
    """The manifest file should survive a reload after sync."""
    client.post("/api/sync-index", json={
        "selected_paths": [str(sample_pdf_path)]
    })

    # Read the manifest directly
    manifest_path = tmp_path / MANIFEST_FILENAME
    assert manifest_path.exists()

    manifest_raw = json.loads(manifest_path.read_text())
    assert manifest_raw["version"] == 1

    entry = manifest_raw["files"][str(sample_pdf_path)]
    assert entry["filename"] == "dragonbane_monsters.pdf"
    assert entry["chunk_count"] > 0
    assert "indexed_at" in entry
    assert entry["mtime"] > 0


def test_index_files_writes_manifest(client, sample_pdf_path, tmp_path):
    """The old POST /api/index-files endpoint should also update the manifest."""
    client.post("/api/index-files", json={
        "paths": [str(sample_pdf_path)]
    })

    manifest_path = tmp_path / MANIFEST_FILENAME
    assert manifest_path.exists()

    manifest_raw = json.loads(manifest_path.read_text())
    assert str(sample_pdf_path) in manifest_raw["files"]


# ---------------------------------------------------------------------------
# Game system in manifest
# ---------------------------------------------------------------------------

def test_sync_stores_game_system_in_manifest(
    client, dnd5e_pdf_path, tmp_path
):
    """Sync should store detected game_system in the manifest."""
    client.post("/api/sync-index", json={
        "selected_paths": [str(dnd5e_pdf_path)]
    })

    manifest_raw = json.loads((tmp_path / MANIFEST_FILENAME).read_text())
    entry = manifest_raw["files"][str(dnd5e_pdf_path)]
    assert entry["game_system"] == "D&D 5E"


def test_sync_with_game_system_override(
    client, untagged_pdf_path, tmp_path
):
    """Game system overrides should be stored in the manifest."""
    client.post("/api/sync-index", json={
        "selected_paths": [str(untagged_pdf_path)],
        "game_system_overrides": {
            str(untagged_pdf_path): "Call of Cthulhu",
        },
    })

    manifest_raw = json.loads((tmp_path / MANIFEST_FILENAME).read_text())
    entry = manifest_raw["files"][str(untagged_pdf_path)]
    assert entry["game_system"] == "Call of Cthulhu"


def test_sync_update_with_fewer_chunks_removes_orphans(
    client, test_collection, tmp_path
):
    """Re-indexing a file that now produces fewer chunks should not leave orphans."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    # Create a PDF with lots of text (many chunks)
    pdf_path = tmp_path / "shrinking_book.pdf"
    c = canvas.Canvas(str(pdf_path), pagesize=letter)
    long_text = "The adventurer explores the dungeon corridors. " * 100
    y = 750
    for i in range(0, len(long_text), 80):
        c.drawString(72, y, long_text[i:i + 80])
        y -= 12
        if y < 72:
            c.showPage()
            y = 750
    c.save()

    # Index it
    client.post("/api/sync-index", json={
        "selected_paths": [str(pdf_path)]
    })
    count_before = test_collection.count()
    assert count_before > 2  # Should have multiple chunks

    # Rewrite the PDF with much less text (fewer chunks)
    c = canvas.Canvas(str(pdf_path), pagesize=letter)
    c.drawString(72, 750, "Short book now.")
    c.save()

    # Force mtime mismatch so sync detects a modification
    manifest_raw = json.loads((tmp_path / MANIFEST_FILENAME).read_text())
    manifest_raw["files"][str(pdf_path)]["mtime"] = 1.0
    (tmp_path / MANIFEST_FILENAME).write_text(json.dumps(manifest_raw))

    # Sync again — should re-index with fewer chunks
    response = client.post("/api/sync-index", json={
        "selected_paths": [str(pdf_path)]
    })
    data = response.json()
    assert data["updated"] == 1

    # The key assertion: collection count should match the new (smaller) chunk count,
    # not retain orphaned chunks from the old version
    count_after = test_collection.count()
    assert count_after < count_before
    assert count_after == 1  # "Short book now." = 1 chunk


def test_manifest_backward_compat_missing_game_system(tmp_path):
    """Old manifests without game_system should load with 'unknown' default."""
    old_manifest = {
        "version": 1,
        "files": {
            "/old/book.pdf": {
                "filename": "book.pdf",
                "mtime": 1000.0,
                "chunk_count": 5,
                "indexed_at": "2026-01-01T00:00:00Z",
            }
        }
    }
    (tmp_path / MANIFEST_FILENAME).write_text(json.dumps(old_manifest))

    from server import load_manifest
    manifest = load_manifest(tmp_path)
    assert manifest.files["/old/book.pdf"].game_system == "unknown"
