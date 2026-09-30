"""
Tests for rename detection during index sync.

When a previously indexed PDF is renamed, the system should detect
that the content is unchanged and transfer existing chunks to the new
filename without re-embedding — saving the expensive Ollama call.
"""

import os
import shutil

from legend_lore.service import (
    MANIFEST_FILENAME,
    COLLECTIONS_FILENAME,
    IndexManifest,
    ManifestEntry,
    CollectionsStore,
    Collection,
    compute_diff,
    file_content_hash,
)
from tests.conftest import run_sync


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


def test_compute_diff_discovers_rename_from_stale_selection(sample_pdf_path, tmp_path):
    """When selectedPaths still references the old path (file renamed on disk),
    compute_diff should scan the parent directory and detect the rename."""
    content_hash = file_content_hash(sample_pdf_path)
    file_size = os.path.getsize(sample_pdf_path)

    # Use an isolated subdirectory so sample_pdf_path doesn't interfere
    isolated_dir = tmp_path / "rename_test"
    isolated_dir.mkdir()

    old_path = isolated_dir / "original_name.pdf"
    shutil.copy2(sample_pdf_path, old_path)
    old_path_str = str(old_path)

    # Build manifest with the old path
    manifest = IndexManifest(files={
        old_path_str: ManifestEntry(
            filename="original_name.pdf",
            mtime=os.path.getmtime(old_path),
            chunk_count=5,
            indexed_at="2026-01-01T00:00:00Z",
            content_hash=content_hash,
            file_size=file_size,
        )
    })

    # Simulate rename on disk: delete old, create new in same directory
    new_path = isolated_dir / "renamed_file.pdf"
    old_path.rename(new_path)

    # Call compute_diff with stale selection (old path that no longer exists)
    diff = compute_diff([old_path_str], manifest)

    # Should detect as rename, not error
    assert len(diff["to_rename"]) == 1
    assert len(diff["errors"]) == 0
    assert diff["to_rename"][0]["old_path"] == old_path_str
    assert diff["to_rename"][0]["new_path"] == str(new_path)


def test_deleted_file_auto_removed_when_parent_accessible(sample_pdf_path, tmp_path):
    """When a file is deleted but its parent directory is accessible,
    it should go to to_auto_remove (not errors)."""
    content_hash = file_content_hash(sample_pdf_path)
    file_size = os.path.getsize(sample_pdf_path)

    # Use a separate subdirectory so the original sample_pdf isn't a candidate
    isolated_dir = tmp_path / "isolated"
    isolated_dir.mkdir()
    old_path = isolated_dir / "vanished.pdf"
    shutil.copy2(sample_pdf_path, old_path)
    old_path_str = str(old_path)

    manifest = IndexManifest(files={
        old_path_str: ManifestEntry(
            filename="vanished.pdf",
            mtime=os.path.getmtime(old_path),
            chunk_count=5,
            indexed_at="2026-01-01T00:00:00Z",
            content_hash=content_hash,
            file_size=file_size,
        )
    })

    # Delete without creating a replacement — directory is now empty
    old_path.unlink()

    diff = compute_diff([old_path_str], manifest)

    assert len(diff["to_rename"]) == 0
    assert len(diff["to_auto_remove"]) == 1
    assert diff["to_auto_remove"][0]["path"] == old_path_str
    assert len(diff["errors"]) == 0


def test_deleted_file_errors_when_parent_inaccessible():
    """When the parent directory doesn't exist (e.g. unmounted drive),
    the missing file should stay in errors."""
    manifest = IndexManifest(files={
        "/mnt/external/rpg_books/rulebook.pdf": ManifestEntry(
            filename="rulebook.pdf",
            mtime=1000.0,
            chunk_count=5,
            indexed_at="2026-01-01T00:00:00Z",
            content_hash="abc123",
            file_size=1024,
        )
    })

    diff = compute_diff(["/mnt/external/rpg_books/rulebook.pdf"], manifest)

    assert len(diff["to_auto_remove"]) == 0
    assert len(diff["errors"]) == 1
    assert diff["errors"][0]["path"] == "/mnt/external/rpg_books/rulebook.pdf"


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
    response = run_sync(client, {
        "selected_paths": [str(sample_pdf_path)]
    })
    data = response
    assert data["added"] == 1
    original_total = data["total_indexed"]

    # Step 2: "Rename" — copy to new path
    new_path = tmp_path / "renamed_monsters.pdf"
    shutil.copy2(sample_pdf_path, new_path)

    # Step 3: Sync with new path only (old path deselected)
    response = run_sync(client, {
        "selected_paths": [str(new_path)]
    })
    data = response
    assert data["renamed"] == 1
    assert data["added"] == 0
    assert data["removed"] == 0
    assert data["total_indexed"] == original_total


def test_sync_rename_preserves_pipeline_version(client, sample_pdf_path, tmp_path):
    """Rename should copy the old entry's pipeline_version, never recompute it."""
    from legend_lore.service import load_manifest, save_manifest

    run_sync(client, {
        "selected_paths": [str(sample_pdf_path)]
    })
    manifest = load_manifest(tmp_path)
    manifest.files[str(sample_pdf_path)].pipeline_version = "old/x"
    save_manifest(tmp_path, manifest)

    new_path = tmp_path / "renamed_monsters.pdf"
    shutil.copy2(sample_pdf_path, new_path)

    response = run_sync(client, {
        "selected_paths": [str(new_path)]
    })
    assert response["renamed"] == 1

    manifest = load_manifest(tmp_path)
    assert manifest.files[str(new_path)].pipeline_version == "old/x"


def test_sync_rename_updates_metadata(client, sample_pdf_path, tmp_path):
    """After rename, chunk metadata should reflect the new path/filename."""
    # Index the file
    run_sync(client, {
        "selected_paths": [str(sample_pdf_path)]
    })

    # Rename
    new_path = tmp_path / "renamed_dragons.pdf"
    shutil.copy2(sample_pdf_path, new_path)

    run_sync(client, {
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
    run_sync(client, {
        "selected_paths": [str(sample_pdf_path)]
    })

    # Rename
    new_path = tmp_path / "new_name.pdf"
    shutil.copy2(sample_pdf_path, new_path)

    run_sync(client, {
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
    run_sync(client, {
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

    run_sync(client, {
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
    run_sync(client, {
        "selected_paths": [str(sample_pdf_path)]
    })

    # Rename
    new_path = tmp_path / "another_name.pdf"
    shutil.copy2(sample_pdf_path, new_path)

    response = run_sync(client, {
        "selected_paths": [str(new_path)]
    })
    data = response
    assert "renamed" in data
    assert data["renamed"] == 1


def test_sync_rename_from_stale_selection(client, sample_pdf_path, tmp_path):
    """Full integration: index a file, rename on disk, sync with stale path.
    The sync should detect the rename and return renames list."""
    # Step 1: Index
    response = run_sync(client, {
        "selected_paths": [str(sample_pdf_path)]
    })
    assert response["added"] == 1

    # Step 2: "Rename" — copy to new path in same directory
    new_path = sample_pdf_path.parent / "renamed_bestiary.pdf"
    shutil.copy2(sample_pdf_path, new_path)
    sample_pdf_path.unlink()

    # Step 3: Sync with STALE path (the old path that no longer exists)
    response = run_sync(client, {
        "selected_paths": [str(sample_pdf_path)]
    })
    data = response
    assert data["renamed"] == 1
    assert data["added"] == 0
    assert len(data["renames"]) == 1
    assert data["renames"][0]["old_path"] == str(sample_pdf_path)
    assert data["renames"][0]["new_path"] == str(new_path)

    # Cleanup: restore the original file for other tests
    new_path.rename(sample_pdf_path)


def test_index_status_shows_rename(client, sample_pdf_path, tmp_path):
    """The index-status endpoint should report renames in its summary."""
    # Index
    run_sync(client, {
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


# ---------------------------------------------------------------------------
# Auto-remove — files deleted from disk
# ---------------------------------------------------------------------------

def test_sync_auto_removes_deleted_file(client, sample_pdf_path, tmp_path):
    """A file deleted from disk should be auto-removed from the index."""
    # Index
    response = run_sync(client, {
        "selected_paths": [str(sample_pdf_path)]
    })
    assert response["added"] == 1

    # Delete the file
    sample_pdf_path.unlink()

    # Sync with stale path (file no longer exists)
    response = run_sync(client, {
        "selected_paths": [str(sample_pdf_path)]
    })
    data = response
    assert data["auto_removed"] == 1
    assert str(sample_pdf_path) in data["auto_removed_paths"]
    assert data["total_indexed"] == 0


def test_auto_remove_updates_collections(client, sample_pdf_path, tmp_path):
    """Collections referencing a deleted file should have the path removed."""
    # Index
    run_sync(client, {
        "selected_paths": [str(sample_pdf_path)]
    })

    # Create collection
    client.post("/api/collections", json={
        "name": "test_coll",
        "file_paths": [str(sample_pdf_path)],
    })

    # Delete file
    sample_pdf_path.unlink()

    # Sync
    run_sync(client, {
        "selected_paths": [str(sample_pdf_path)]
    })

    # Check collection no longer has the path
    response = client.get("/api/collections")
    data = response.json()
    coll = data["collections"]["test_coll"]
    assert str(sample_pdf_path) not in coll["file_paths"]


def test_index_status_shows_auto_remove(client, sample_pdf_path, tmp_path):
    """The index-status endpoint should report auto_remove in its summary."""
    # Index
    run_sync(client, {
        "selected_paths": [str(sample_pdf_path)]
    })

    # Delete file
    sample_pdf_path.unlink()

    # Check status with stale path
    response = client.post("/api/index-status", json={
        "selected_paths": [str(sample_pdf_path)]
    })
    data = response.json()
    assert data["summary"]["auto_remove"] == 1
    assert len(data["to_auto_remove"]) == 1
