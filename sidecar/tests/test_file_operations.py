"""
Tests for direct file rename and delete operations.

When a file is renamed or deleted through the UI, the sidecar directly
updates the index — transferring chunks without re-embedding (rename)
or removing them immediately (delete) — instead of waiting for the
next auto-sync poll to discover the change.
"""

import shutil

from tests.conftest import index_pdfs, read_manifest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# File rename
# ---------------------------------------------------------------------------

def test_file_rename_updates_manifest(client, sample_pdf_path, tmp_path):
    """Manifest should have the new path after rename."""
    index_pdfs(client, sample_pdf_path)

    new_path = str(tmp_path / "renamed_monsters.pdf")
    response = client.post("/api/file-rename", json={
        "old_path": str(sample_pdf_path),
        "new_path": new_path,
    })
    assert response.status_code == 200
    assert response.json()["renamed"] is True

    manifest = read_manifest(tmp_path)
    assert str(sample_pdf_path) not in manifest["files"]
    assert new_path in manifest["files"]


def test_file_rename_updates_search_metadata(client, sample_pdf_path, tmp_path):
    """Search results should reference the new path after rename."""
    index_pdfs(client, sample_pdf_path)

    new_path = str(tmp_path / "moved_dragons.pdf")
    client.post("/api/file-rename", json={
        "old_path": str(sample_pdf_path),
        "new_path": new_path,
    })

    response = client.post("/api/search", json={"query": "dragon fire"})
    results = response.json()["results"]
    assert len(results) > 0
    for result in results:
        assert result["source"] == new_path
        assert result["filename"] == "moved_dragons.pdf"


def test_file_rename_updates_collections(client, sample_pdf_path, tmp_path):
    """Collections referencing the old path should be updated."""
    index_pdfs(client, sample_pdf_path)

    client.post("/api/collections", json={
        "name": "test_coll",
        "file_paths": [str(sample_pdf_path)],
    })

    new_path = str(tmp_path / "new_name.pdf")
    response = client.post("/api/file-rename", json={
        "old_path": str(sample_pdf_path),
        "new_path": new_path,
    })
    assert response.json()["affected_collections"] == 1

    coll_resp = client.get("/api/collections")
    coll = coll_resp.json()["collections"]["test_coll"]
    assert new_path in coll["file_paths"]
    assert str(sample_pdf_path) not in coll["file_paths"]


def test_file_rename_not_indexed(client, tmp_path):
    """Renaming a file that isn't indexed should return not_indexed."""
    response = client.post("/api/file-rename", json={
        "old_path": "/fake/path.pdf",
        "new_path": "/fake/new_path.pdf",
    })
    assert response.status_code == 200
    assert response.json()["renamed"] is False
    assert response.json()["reason"] == "not_indexed"


def test_file_rename_preserves_chunk_count(client, sample_pdf_path, tmp_path):
    """Chunk count should remain the same after rename."""
    data = index_pdfs(client, sample_pdf_path)
    chunks_before = data["chunks_total"]

    new_path = str(tmp_path / "renamed.pdf")
    client.post("/api/file-rename", json={
        "old_path": str(sample_pdf_path),
        "new_path": new_path,
    })

    manifest = read_manifest(tmp_path)
    assert manifest["files"][new_path]["chunk_count"] == chunks_before


def test_file_rename_moves_the_lexical_rows(
    client, large_text_pdf_path, test_store, tmp_path
):
    """The persisted FTS rows follow the file and keep their unit ids.

    A rename is one update of the book's documents row, so the lexical
    side finds the same units under the new path and none under the old.
    """
    index_pdfs(client, large_text_pdf_path)
    old_path = str(large_text_pdf_path)
    before = test_store.fts(
        '"combat"', 50, test_store.scope_document_ids(paths=[old_path])
    )
    assert len(before) > 1  # a single-chunk file could not detect a mix-up

    new_path = str(tmp_path / "renamed_lexical.pdf")
    resp = client.post("/api/file-rename", json={
        "old_path": old_path,
        "new_path": new_path,
    })
    assert resp.json()["renamed"] is True

    assert test_store.scope_document_ids(paths=[old_path]) == []
    after = test_store.fts(
        '"combat"', 50, test_store.scope_document_ids(paths=[new_path])
    )
    assert after == before
    assert {u.source for u in test_store.hydrate(after).values()} == {new_path}


def test_file_rename_preserves_pipeline_version(client, sample_pdf_path, tmp_path):
    """Rename should copy the old entry's pipeline_version, never recompute it."""
    from legend_lore.service import load_manifest, save_manifest

    index_pdfs(client, sample_pdf_path)
    manifest = load_manifest(tmp_path)
    manifest.files[str(sample_pdf_path)].pipeline_version = "old/x"
    save_manifest(tmp_path, manifest)

    new_path = str(tmp_path / "renamed.pdf")
    client.post("/api/file-rename", json={
        "old_path": str(sample_pdf_path),
        "new_path": new_path,
    })

    manifest = load_manifest(tmp_path)
    assert manifest.files[new_path].pipeline_version == "old/x"


# ---------------------------------------------------------------------------
# File delete
# ---------------------------------------------------------------------------

def test_file_delete_removes_from_manifest(client, sample_pdf_path, tmp_path):
    """Manifest should no longer contain the file after delete."""
    index_pdfs(client, sample_pdf_path)

    response = client.post("/api/file-delete", json={
        "path": str(sample_pdf_path),
    })
    assert response.status_code == 200
    assert response.json()["deleted"] is True

    manifest = read_manifest(tmp_path)
    assert str(sample_pdf_path) not in manifest["files"]


def test_file_delete_removes_chunks(client, sample_pdf_path, tmp_path):
    """The store should have no chunks for the file after delete."""
    index_pdfs(client, sample_pdf_path)

    search_resp = client.post("/api/search", json={"query": "dragon"})
    assert len(search_resp.json()["results"]) > 0

    client.post("/api/file-delete", json={
        "path": str(sample_pdf_path),
    })

    search_resp = client.post("/api/search", json={"query": "dragon"})
    assert len(search_resp.json()["results"]) == 0


def test_file_delete_updates_collections(client, sample_pdf_path, tmp_path):
    """Collections should have the deleted file removed."""
    index_pdfs(client, sample_pdf_path)

    client.post("/api/collections", json={
        "name": "test_coll",
        "file_paths": [str(sample_pdf_path)],
    })

    response = client.post("/api/file-delete", json={
        "path": str(sample_pdf_path),
    })
    assert response.json()["affected_collections"] == 1

    coll_resp = client.get("/api/collections")
    coll = coll_resp.json()["collections"]["test_coll"]
    assert len(coll["file_paths"]) == 0


def test_file_delete_not_indexed(client, tmp_path):
    """Deleting a file that isn't indexed should return not_indexed."""
    response = client.post("/api/file-delete", json={
        "path": "/fake/path.pdf",
    })
    assert response.status_code == 200
    assert response.json()["deleted"] is False
    assert response.json()["reason"] == "not_indexed"
