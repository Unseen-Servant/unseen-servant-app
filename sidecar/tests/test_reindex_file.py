"""
Tests for POST /api/reindex-file (single-file force rebuild).
"""

import time


def test_reindex_file_rebuilds_chunks(client, sample_pdf_path, test_store):
    """Re-indexing a file should keep chunk count > 0 and not duplicate."""
    client.post("/api/index-files", json={"paths": [str(sample_pdf_path)]})
    chunks_before = test_store.count_units()
    assert chunks_before > 0

    response = client.post("/api/reindex-file", json={"path": str(sample_pdf_path)})
    assert response.status_code == 200
    data = response.json()
    assert data["error"] is None
    assert data["chunks"] > 0

    # Same chunk count after — the book's rows are replaced, not duplicated.
    assert test_store.count_units() == chunks_before


def test_reindex_file_advances_indexed_at(client, sample_pdf_path):
    """The indexed_at timestamp should move forward after a re-index."""
    client.post("/api/index-files", json={"paths": [str(sample_pdf_path)]})
    first = client.get("/api/sources").json()["sources"][0]["indexed_at"]
    assert first is not None

    # Sleep so the ISO timestamp advances at second precision.
    time.sleep(1.1)

    client.post("/api/reindex-file", json={"path": str(sample_pdf_path)})
    second = client.get("/api/sources").json()["sources"][0]["indexed_at"]

    assert second > first


def test_reindex_file_missing_path(client, tmp_path):
    """Re-indexing a non-existent file returns 404."""
    response = client.post(
        "/api/reindex-file", json={"path": str(tmp_path / "nope.pdf")}
    )
    assert response.status_code == 404


def test_reindex_file_preserves_other_sources(
    client, sample_pdf_path, large_text_pdf_path, test_store
):
    """Re-indexing one file leaves other indexed files alone."""
    client.post("/api/index-files", json={
        "paths": [str(sample_pdf_path), str(large_text_pdf_path)]
    })
    total_before = test_store.count_units()

    client.post("/api/reindex-file", json={"path": str(sample_pdf_path)})

    assert test_store.count_units() == total_before
    filenames = {
        s["filename"] for s in client.get("/api/sources").json()["sources"]
    }
    assert "dragonbane_monsters.pdf" in filenames
    assert "core_rules.pdf" in filenames
