"""
Tests for rename detection during index sync.

When a previously indexed PDF is renamed, the system should detect
that the content is unchanged and transfer existing chunks to the new
filename without re-embedding — saving the expensive Ollama call.
"""

import os
import shutil

from server import (
    MANIFEST_FILENAME,
    COLLECTIONS_FILENAME,
    IndexManifest,
    ManifestEntry,
    CollectionsStore,
    Collection,
    compute_diff,
    file_content_hash,
)


# ---------------------------------------------------------------------------
# file_content_hash
# ---------------------------------------------------------------------------

def test_file_content_hash_deterministic(sample_pdf_path):
    """Same file should produce the same hash on repeated calls."""
    h1 = file_content_hash(sample_pdf_path)
    h2 = file_content_hash(sample_pdf_path)
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex digest


def test_file_content_hash_differs_for_different_files(sample_pdf_path, large_text_pdf_path):
    """Different files should produce different hashes."""
    h1 = file_content_hash(sample_pdf_path)
    h2 = file_content_hash(large_text_pdf_path)
    assert h1 != h2


# ---------------------------------------------------------------------------
# compute_diff — rename detection
# ---------------------------------------------------------------------------

def test_compute_diff_detects_rename(sample_pdf_path, tmp_path):
    """A file that moved from old_path to new_path with same content
    should appear in to_rename, not to_add/to_remove."""
    content_hash = file_content_hash(sample_pdf_path)
    file_size = os.path.getsize(sample_pdf_path)

    # Simulate: old path was indexed, file now lives at a new path
    old_path = "/old/location/dragonbane_monsters.pdf"
    new_path = str(sample_pdf_path)

    manifest = IndexManifest(files={
        old_path: ManifestEntry(
            filename="dragonbane_monsters.pdf",
            mtime=1000.0,
            chunk_count=5,
            indexed_at="2026-01-01T00:00:00Z",
            content_hash=content_hash,
            file_size=file_size,
        )
    })

    diff = compute_diff([new_path], manifest)

    assert len(diff["to_rename"]) == 1
    assert len(diff["to_add"]) == 0
    assert len(diff["to_remove"]) == 0

    rename = diff["to_rename"][0]
    assert rename["old_path"] == old_path
    assert rename["new_path"] == new_path
    assert rename["content_hash"] == content_hash


def test_rename_no_match_without_hash(sample_pdf_path):
    """Legacy manifest entries (empty content_hash) should fall back
    to normal add+remove — no rename detection possible."""
    old_path = "/old/location/dragonbane_monsters.pdf"
    new_path = str(sample_pdf_path)

    manifest = IndexManifest(files={
        old_path: ManifestEntry(
            filename="dragonbane_monsters.pdf",
            mtime=1000.0,
            chunk_count=5,
            indexed_at="2026-01-01T00:00:00Z",
            # No content_hash or file_size — legacy entry
        )
    })

    diff = compute_diff([new_path], manifest)

    assert len(diff["to_rename"]) == 0
    assert len(diff["to_add"]) == 1
    assert len(diff["to_remove"]) == 1


def test_rename_with_content_change(sample_pdf_path, large_text_pdf_path):
    """If a file is renamed AND its content changed, the hash won't match.
    It should appear as separate add+remove."""
    old_hash = file_content_hash(large_text_pdf_path)
    old_size = os.path.getsize(large_text_pdf_path)
    old_path = str(large_text_pdf_path)
    new_path = str(sample_pdf_path)  # Different content

    manifest = IndexManifest(files={
        old_path: ManifestEntry(
            filename="core_rules.pdf",
            mtime=1000.0,
            chunk_count=5,
            indexed_at="2026-01-01T00:00:00Z",
            content_hash=old_hash,
            file_size=old_size,
        )
    })

    diff = compute_diff([new_path], manifest)

    assert len(diff["to_rename"]) == 0
    assert len(diff["to_add"]) == 1
    assert len(diff["to_remove"]) == 1


def test_multiple_renames_in_one_sync(sample_pdf_path, large_text_pdf_path, tmp_path):
    """Two files renamed simultaneously should both be detected."""
    hash1 = file_content_hash(sample_pdf_path)
    size1 = os.path.getsize(sample_pdf_path)
    hash2 = file_content_hash(large_text_pdf_path)
    size2 = os.path.getsize(large_text_pdf_path)

    manifest = IndexManifest(files={
        "/old/book_a.pdf": ManifestEntry(
            filename="book_a.pdf", mtime=1000.0, chunk_count=3,
            indexed_at="2026-01-01T00:00:00Z",
            content_hash=hash1, file_size=size1,
        ),
        "/old/book_b.pdf": ManifestEntry(
            filename="book_b.pdf", mtime=1000.0, chunk_count=5,
            indexed_at="2026-01-01T00:00:00Z",
            content_hash=hash2, file_size=size2,
        ),
    })

    diff = compute_diff(
        [str(sample_pdf_path), str(large_text_pdf_path)], manifest
    )

    assert len(diff["to_rename"]) == 2
    assert len(diff["to_add"]) == 0
    assert len(diff["to_remove"]) == 0


def test_duplicate_hash_files_matched_one_to_one(sample_pdf_path, tmp_path):
    """Two identical PDFs (same hash) renamed — should pair 1:1."""
    # Copy sample_pdf to create a duplicate
    copy_path = tmp_path / "copy_of_monsters.pdf"
    shutil.copy2(sample_pdf_path, copy_path)

    content_hash = file_content_hash(sample_pdf_path)
    file_size = os.path.getsize(sample_pdf_path)

    manifest = IndexManifest(files={
        "/old/dup_a.pdf": ManifestEntry(
            filename="dup_a.pdf", mtime=1000.0, chunk_count=3,
            indexed_at="2026-01-01T00:00:00Z",
            content_hash=content_hash, file_size=file_size,
        ),
        "/old/dup_b.pdf": ManifestEntry(
            filename="dup_b.pdf", mtime=1000.0, chunk_count=3,
            indexed_at="2026-01-01T00:00:00Z",
            content_hash=content_hash, file_size=file_size,
        ),
    })

    diff = compute_diff(
        [str(sample_pdf_path), str(copy_path)], manifest
    )

    assert len(diff["to_rename"]) == 2
    assert len(diff["to_add"]) == 0
    assert len(diff["to_remove"]) == 0


# ---------------------------------------------------------------------------
# ManifestEntry backward compatibility
# ---------------------------------------------------------------------------

def test_manifest_backward_compat_content_hash():
    """Old manifests without content_hash/file_size should load with defaults."""
    entry = ManifestEntry(
        filename="old_book.pdf",
        mtime=1000.0,
        chunk_count=5,
        indexed_at="2026-01-01T00:00:00Z",
    )
    assert entry.content_hash == ""
    assert entry.file_size == 0


# ---------------------------------------------------------------------------
# sync-index — rename phase (HTTP integration tests)
# ---------------------------------------------------------------------------

def test_sync_rename_preserves_chunks(client, sample_pdf_path, tmp_path):
    """Renaming a file should transfer chunks without re-indexing."""
    # Step 1: Index the file
    response = client.post("/api/sync-index", json={
        "selected_paths": [str(sample_pdf_path)]
    })
    assert response.status_code == 200
    data = response.json()
    assert data["added"] == 1
    original_total = data["total_indexed"]

    # Step 2: "Rename" — copy to new path
    new_path = tmp_path / "renamed_monsters.pdf"
    shutil.copy2(sample_pdf_path, new_path)

    # Step 3: Sync with new path only (old path deselected)
    response = client.post("/api/sync-index", json={
        "selected_paths": [str(new_path)]
    })
    assert response.status_code == 200
    data = response.json()
    assert data["renamed"] == 1
    assert data["added"] == 0
    assert data["removed"] == 0
    assert data["total_indexed"] == original_total


def test_sync_rename_updates_metadata(client, sample_pdf_path, tmp_path):
    """After rename, chunk metadata should reflect the new path/filename."""
    # Index the file
    client.post("/api/sync-index", json={
        "selected_paths": [str(sample_pdf_path)]
    })

    # Rename
    new_path = tmp_path / "renamed_dragons.pdf"
    shutil.copy2(sample_pdf_path, new_path)

    client.post("/api/sync-index", json={
        "selected_paths": [str(new_path)]
    })

    # Search for the content — results should reference the new filename
    response = client.post("/api/search", json={"query": "dragon fire"})
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) > 0
    for result in results:
        assert result["filename"] == "renamed_dragons.pdf"
        assert result["source"] == str(new_path)


def test_sync_rename_updates_manifest(client, sample_pdf_path, tmp_path):
    """After rename, manifest should have new path and content_hash."""
    # Index
    client.post("/api/sync-index", json={
        "selected_paths": [str(sample_pdf_path)]
    })

    # Rename
    new_path = tmp_path / "new_name.pdf"
    shutil.copy2(sample_pdf_path, new_path)

    client.post("/api/sync-index", json={
        "selected_paths": [str(new_path)]
    })

    # Check manifest
    import json as json_mod
    manifest_data = json_mod.loads(
        (tmp_path / MANIFEST_FILENAME).read_text()
    )
    files = manifest_data["files"]
    assert str(sample_pdf_path) not in files  # Old path gone
    assert str(new_path) in files  # New path present
    assert files[str(new_path)]["content_hash"] != ""  # Hash populated


def test_sync_rename_updates_collections(client, sample_pdf_path, tmp_path):
    """Collections referencing the old path should be updated."""
    # Index the file
    client.post("/api/sync-index", json={
        "selected_paths": [str(sample_pdf_path)]
    })

    # Create a collection referencing the old path
    client.post("/api/collections", json={
        "name": "test_coll",
        "file_paths": [str(sample_pdf_path)],
    })

    # Rename
    new_path = tmp_path / "moved_book.pdf"
    shutil.copy2(sample_pdf_path, new_path)

    client.post("/api/sync-index", json={
        "selected_paths": [str(new_path)]
    })

    # Check collection has updated path
    response = client.get("/api/collections")
    data = response.json()
    coll = data["collections"]["test_coll"]
    assert str(new_path) in coll["file_paths"]
    assert str(sample_pdf_path) not in coll["file_paths"]


def test_sync_rename_response_includes_count(client, sample_pdf_path, tmp_path):
    """Sync response should include the 'renamed' field."""
    # Index
    client.post("/api/sync-index", json={
        "selected_paths": [str(sample_pdf_path)]
    })

    # Rename
    new_path = tmp_path / "another_name.pdf"
    shutil.copy2(sample_pdf_path, new_path)

    response = client.post("/api/sync-index", json={
        "selected_paths": [str(new_path)]
    })
    data = response.json()
    assert "renamed" in data
    assert data["renamed"] == 1


def test_index_status_shows_rename(client, sample_pdf_path, tmp_path):
    """The index-status endpoint should report renames in its summary."""
    # Index
    client.post("/api/sync-index", json={
        "selected_paths": [str(sample_pdf_path)]
    })

    # Rename
    new_path = tmp_path / "status_check.pdf"
    shutil.copy2(sample_pdf_path, new_path)

    response = client.post("/api/index-status", json={
        "selected_paths": [str(new_path)]
    })
    data = response.json()
    assert data["summary"]["rename"] == 1
    assert len(data["to_rename"]) == 1
