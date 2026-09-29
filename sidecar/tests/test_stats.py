"""
Tests for GET /api/stats.
"""

from tests.test_search_scoping import twin_pdfs  # noqa: F401


def test_stats_empty_db(client):
    """Stats on empty DB should show zero counts."""
    response = client.get("/api/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["total_chunks"] == 0
    assert data["total_documents"] == 0
    assert "storage_bytes" in data
    assert isinstance(data["storage_bytes"], int)


def test_stats_after_indexing(client, sample_pdf_path):
    """Stats should reflect indexed document counts."""
    client.post("/api/index-files", json={
        "paths": [str(sample_pdf_path)]
    })

    response = client.get("/api/stats")
    data = response.json()
    assert data["total_chunks"] > 0
    assert data["total_documents"] == 1


def test_stats_multiple_documents(client, sample_pdf_path, large_text_pdf_path):
    """Stats should count unique documents, not total chunks."""
    client.post("/api/index-files", json={
        "paths": [str(sample_pdf_path), str(large_text_pdf_path)]
    })

    response = client.get("/api/stats")
    data = response.json()
    assert data["total_documents"] == 2
    # Total chunks should be more than the document count
    assert data["total_chunks"] > 2


def test_stats_counts_same_named_files_in_different_folders(client, twin_pdfs):
    """Two monsters.pdf in different folders are two documents, as they
    are everywhere else the library keys sources by path."""
    a, b = twin_pdfs
    client.post("/api/index-files", json={"paths": [str(a), str(b)]})

    assert client.get("/api/stats").json()["total_documents"] == 2
