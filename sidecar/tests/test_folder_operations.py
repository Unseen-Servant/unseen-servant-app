"""
Tests for folder rename and delete operations.

When a folder is renamed or deleted through the UI, the sidecar batch-updates
all indexed PDFs under that folder — transferring chunks without re-embedding
(rename) or removing them entirely (delete).
"""

import json

from legend_lore.service import MANIFEST_FILENAME, COLLECTIONS_FILENAME
from tests.conftest import run_sync


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def index_pdfs(client, *pdf_paths):
    """Index one or more PDFs via sync-index and assert success."""
    response = run_sync(client, {
        "selected_paths": [str(p) for p in pdf_paths]
    })
    return response


def read_manifest(tmp_path):
    """Load the manifest from disk."""
    return json.loads((tmp_path / MANIFEST_FILENAME).read_text())


# ---------------------------------------------------------------------------
# Folder rename
# ---------------------------------------------------------------------------

def test_folder_rename_updates_manifest(client, sample_pdf_path, large_text_pdf_path, tmp_path):
    """All manifest entries under the old prefix should move to the new prefix."""
    index_pdfs(client, sample_pdf_path, large_text_pdf_path)

    old_prefix = str(tmp_path)
    new_prefix = str(tmp_path).rstrip("/") + "_renamed"

    response = client.post("/api/folder-rename", json={
        "old_prefix": old_prefix,
        "new_prefix": new_prefix,
    })
    assert response.status_code == 200
    data = response.json()
    assert data["renamed_files"] == 2

    manifest = read_manifest(tmp_path)
    for path in manifest["files"]:
        assert path.startswith(new_prefix + "/")
        assert not path.startswith(old_prefix + "/")


def test_folder_rename_updates_search_metadata(client, sample_pdf_path, tmp_path):
    """After folder rename, search results should reference the new path."""
    index_pdfs(client, sample_pdf_path)

    old_prefix = str(tmp_path)
    new_prefix = str(tmp_path).rstrip("/") + "_moved"

    client.post("/api/folder-rename", json={
        "old_prefix": old_prefix,
        "new_prefix": new_prefix,
    })

    response = client.post("/api/search", json={"query": "dragon fire"})
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) > 0
    for result in results:
        assert result["source"].startswith(new_prefix + "/")
        assert not result["source"].startswith(old_prefix + "/")


def test_folder_rename_updates_collections(client, sample_pdf_path, tmp_path):
    """Collections referencing files under the old prefix should be updated."""
    index_pdfs(client, sample_pdf_path)

    client.post("/api/collections", json={
        "name": "test_coll",
        "file_paths": [str(sample_pdf_path)],
    })

    old_prefix = str(tmp_path)
    new_prefix = str(tmp_path).rstrip("/") + "_renamed"

    response = client.post("/api/folder-rename", json={
        "old_prefix": old_prefix,
        "new_prefix": new_prefix,
    })
    assert response.status_code == 200
    assert response.json()["affected_collections"] == 1

    coll_resp = client.get("/api/collections")
    coll = coll_resp.json()["collections"]["test_coll"]
    for p in coll["file_paths"]:
        assert p.startswith(new_prefix + "/")


def test_folder_rename_preserves_chunk_count(client, sample_pdf_path, tmp_path):
    """Chunk count should remain the same after rename (no re-embedding)."""
    data = index_pdfs(client, sample_pdf_path)
    chunks_before = data["chunks_total"]

    old_prefix = str(tmp_path)
    new_prefix = str(tmp_path).rstrip("/") + "_moved"

    client.post("/api/folder-rename", json={
        "old_prefix": old_prefix,
        "new_prefix": new_prefix,
    })

    manifest = read_manifest(tmp_path)
    total_chunks = sum(e["chunk_count"] for e in manifest["files"].values())
    assert total_chunks == chunks_before


def test_folder_rename_nested_subfolders(client, tmp_path):
    """Files in nested subfolders should all be updated."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    # Create nested structure: parent/sub1/a.pdf, parent/sub2/b.pdf
    parent = tmp_path / "library"
    sub1 = parent / "sub1"
    sub2 = parent / "sub2"
    sub1.mkdir(parents=True)
    sub2.mkdir(parents=True)

    pdf_a = sub1 / "book_a.pdf"
    c = canvas.Canvas(str(pdf_a), pagesize=letter)
    c.drawString(72, 750, "Content for book A about elves and forests.")
    c.save()

    pdf_b = sub2 / "book_b.pdf"
    c = canvas.Canvas(str(pdf_b), pagesize=letter)
    c.drawString(72, 750, "Content for book B about dwarves and mines.")
    c.save()

    index_pdfs(client, pdf_a, pdf_b)

    old_prefix = str(parent)
    new_prefix = str(tmp_path / "library_v2")

    response = client.post("/api/folder-rename", json={
        "old_prefix": old_prefix,
        "new_prefix": new_prefix,
    })
    assert response.status_code == 200
    assert response.json()["renamed_files"] == 2

    manifest = read_manifest(tmp_path)
    paths = list(manifest["files"].keys())
    assert any("sub1/book_a.pdf" in p for p in paths)
    assert any("sub2/book_b.pdf" in p for p in paths)
    for p in paths:
        assert p.startswith(new_prefix + "/")


def test_folder_rename_empty_folder(client, tmp_path):
    """Renaming a folder with no indexed files should be a no-op."""
    response = client.post("/api/folder-rename", json={
        "old_prefix": str(tmp_path / "nonexistent"),
        "new_prefix": str(tmp_path / "also_nonexistent"),
    })
    assert response.status_code == 200
    assert response.json()["renamed_files"] == 0
    assert response.json()["affected_collections"] == 0


# ---------------------------------------------------------------------------
# Folder delete
# ---------------------------------------------------------------------------

def test_folder_delete_removes_from_manifest(client, sample_pdf_path, large_text_pdf_path, tmp_path):
    """All manifest entries under the folder prefix should be removed."""
    index_pdfs(client, sample_pdf_path, large_text_pdf_path)

    response = client.post("/api/folder-delete", json={
        "folder_prefix": str(tmp_path),
    })
    assert response.status_code == 200
    assert response.json()["deleted_files"] == 2

    manifest = read_manifest(tmp_path)
    assert len(manifest["files"]) == 0


def test_folder_delete_removes_chunks(client, sample_pdf_path, tmp_path):
    """ChromaDB should have zero chunks after folder delete."""
    index_pdfs(client, sample_pdf_path)

    # Verify chunks exist before delete
    search_resp = client.post("/api/search", json={"query": "dragon"})
    assert len(search_resp.json()["results"]) > 0

    client.post("/api/folder-delete", json={
        "folder_prefix": str(tmp_path),
    })

    # Verify chunks are gone
    search_resp = client.post("/api/search", json={"query": "dragon"})
    assert len(search_resp.json()["results"]) == 0


def test_folder_delete_updates_collections(client, sample_pdf_path, tmp_path):
    """Collections should have files under the deleted prefix removed."""
    index_pdfs(client, sample_pdf_path)

    client.post("/api/collections", json={
        "name": "test_coll",
        "file_paths": [str(sample_pdf_path)],
    })

    response = client.post("/api/folder-delete", json={
        "folder_prefix": str(tmp_path),
    })
    assert response.status_code == 200
    assert response.json()["affected_collections"] == 1

    coll_resp = client.get("/api/collections")
    coll = coll_resp.json()["collections"]["test_coll"]
    assert len(coll["file_paths"]) == 0


def test_folder_delete_empty_folder(client, tmp_path):
    """Deleting a folder with no indexed files should be a no-op."""
    response = client.post("/api/folder-delete", json={
        "folder_prefix": str(tmp_path / "nonexistent"),
    })
    assert response.status_code == 200
    assert response.json()["deleted_files"] == 0
    assert response.json()["affected_collections"] == 0

