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
    """Selected paths that don't exist and aren't indexed should be stale."""
    response = client.post("/api/index-status", json={
        "selected_paths": ["/nonexistent/ghost.pdf"]
    })

    data = response.json()
    # /nonexistent parent doesn't exist, so this is an error (not stale)
    assert data["summary"]["errors"] == 0
    # Non-indexed file with missing parent → stale path
    assert data["summary"]["stale"] == 1
    assert "/nonexistent/ghost.pdf" in data["stale_paths"]


def test_index_status_empty_selection(client):
    """Empty selection with empty manifest should return all zeros."""
    response = client.post("/api/index-status", json={
        "selected_paths": []
    })

    data = response.json()
    assert data["summary"] == {
        "add": 0, "remove": 0, "auto_remove": 0, "rename": 0, "update": 0,
        "up_to_date": 0, "errors": 0, "stale": 0,
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

    # Create a PDF with lots of text (many chunks).
    # Multiple paragraphs separated by vertical gaps so pymupdf4llm emits
    # `\n\n` blank lines and the structure-aware chunker can split there.
    pdf_path = tmp_path / "shrinking_book.pdf"
    c = canvas.Canvas(str(pdf_path), pagesize=letter)
    paragraphs = [
        "The adventurer explores the dungeon corridors. " * 25,
        "Spell components hide in the wizard's bottomless pouch. " * 25,
        "The thief picks the lock with practiced fingers. " * 25,
        "Dragons hoard their treasure for centuries on end. " * 25,
    ]
    y = 750
    for paragraph in paragraphs:
        for i in range(0, len(paragraph), 80):
            c.drawString(72, y, paragraph[i:i + 80])
            y -= 12
            if y < 72:
                c.showPage()
                y = 750
        y -= 24
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


# ---------------------------------------------------------------------------
# Force reindex — end-to-end coverage via /api/reindex-all-stream
# ---------------------------------------------------------------------------

def test_reindex_all_stream_reprocesses_up_to_date_files(
    client, sample_pdf_path, test_collection, tmp_path
):
    """POST /api/reindex-all-stream should force-update every manifest file."""
    # Prime the index so the manifest has one up-to-date entry.
    client.post("/api/sync-index", json={
        "selected_paths": [str(sample_pdf_path)]
    })
    count_before = test_collection.count()
    assert count_before > 0

    # A plain sync with the same selection should be a no-op (nothing changed).
    noop = client.post("/api/sync-index", json={
        "selected_paths": [str(sample_pdf_path)]
    }).json()
    assert noop["updated"] == 0

    # Force-reindex via the new endpoint. StreamingResponse → parse SSE.
    response = client.post("/api/reindex-all-stream")
    assert response.status_code == 200

    complete = None
    for line in response.text.splitlines():
        if not line.startswith("data: "):
            continue
        event = json.loads(line[len("data: "):])
        if event["event"] == "complete":
            complete = event

    assert complete is not None
    assert complete["updated"] == 1
    assert complete["added"] == 0
    assert complete["total_indexed"] == 1

    # Chunk count is stable (same content, upsert overwrites).
    assert test_collection.count() == count_before


# ---------------------------------------------------------------------------
# POST /api/delete-index
# ---------------------------------------------------------------------------

def test_delete_index_clears_manifest_and_chunks(
    client, sample_pdf_path, test_collection, test_chroma_client, tmp_path
):
    """POST /api/delete-index should purge chunks and empty the manifest.

    Note: delete-index drops and recreates the underlying collection (so
    the dim binding resets after an embedding-model swap), which means the
    original ``test_collection`` reference is dead after the call. Refetch
    via the client.
    """
    client.post("/api/sync-index", json={
        "selected_paths": [str(sample_pdf_path)]
    })
    collection_name = test_collection.name
    chunks_before = test_collection.count()
    assert chunks_before > 0

    manifest_path = tmp_path / MANIFEST_FILENAME
    assert json.loads(manifest_path.read_text())["files"]

    response = client.post("/api/delete-index")
    assert response.status_code == 200
    data = response.json()
    assert data["removed_files"] == 1
    assert data["removed_chunks"] == chunks_before

    fresh_collection = test_chroma_client.get_collection(name=collection_name)
    assert fresh_collection.count() == 0
    assert json.loads(manifest_path.read_text())["files"] == {}


def test_delete_index_empty_manifest(client, test_collection):
    """Deleting when nothing is indexed should succeed with zero counts."""
    assert test_collection.count() == 0

    response = client.post("/api/delete-index")
    assert response.status_code == 200
    data = response.json()
    assert data["removed_files"] == 0
    assert data["removed_chunks"] == 0


def test_delete_index_resets_collection_dim_binding(
    client, sample_pdf_path, test_collection, test_chroma_client
):
    """After delete-index, the recreated collection should accept embeddings
    of a different dim than the original.

    Chroma locks a collection's vector dim to the first inserted embedding;
    a row-only delete preserves that lock, which is exactly the failure mode
    that broke search after the bge-m3 swap. This test would fail under the
    old "delete rows only" implementation.
    """
    import chromadb

    collection_name = test_collection.name
    client.post("/api/sync-index", json={
        "selected_paths": [str(sample_pdf_path)]
    })
    assert test_collection.count() > 0

    client.post("/api/delete-index")

    # The original handle is dead; the recreated collection must accept
    # vectors of a different dim. Add a manual embedding with a dim the
    # original ONNX model does NOT produce — this would raise on the
    # original collection.
    fresh = test_chroma_client.get_collection(
        name=collection_name,
        embedding_function=chromadb.utils.embedding_functions.DefaultEmbeddingFunction(),
    )
    assert fresh.count() == 0
    fresh.add(
        ids=["dim-probe-0"],
        documents=["any document"],
        embeddings=[[0.0] * 4242],  # arbitrary dim, would be rejected if dim was locked
    )
    assert fresh.count() == 1


def test_delete_index_preserves_collections(
    client, sample_pdf_path, test_collection, tmp_path
):
    """Delete keeps collections fully intact — names AND file paths.

    Collections store file paths, not chunk IDs. Those paths are still
    valid on disk after the index is cleared, and will resolve again
    once the next sync re-creates their chunks.
    """
    client.post("/api/sync-index", json={
        "selected_paths": [str(sample_pdf_path)]
    })

    create_resp = client.post("/api/collections", json={
        "name": "My Books",
        "file_paths": [str(sample_pdf_path)],
    })
    assert create_resp.status_code == 200

    client.post("/api/delete-index")

    list_resp = client.get("/api/collections")
    assert list_resp.status_code == 200
    collections = list_resp.json()["collections"]
    assert "My Books" in collections, "Collection should be preserved"
    assert collections["My Books"]["file_paths"] == [str(sample_pdf_path)], \
        "Collection file paths should be preserved across index deletion"
