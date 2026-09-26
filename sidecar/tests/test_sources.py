"""
Tests for GET /api/sources.
"""


def test_sources_empty(client):
    """No indexed docs means empty sources list."""
    response = client.get("/api/sources")
    assert response.status_code == 200
    data = response.json()
    assert data["sources"] == []
    assert data["count"] == 0


def test_sources_lists_indexed_files(client, sample_pdf_path):
    """After indexing, the source should appear in the list."""
    client.post("/api/index-files", json={
        "paths": [str(sample_pdf_path)]
    })

    response = client.get("/api/sources")
    data = response.json()
    assert data["count"] == 1
    assert data["sources"][0]["filename"] == "dragonbane_monsters.pdf"
    assert data["sources"][0]["chunks"] > 0


def test_sources_sorted_alphabetically(client, sample_pdf_path, large_text_pdf_path):
    """Sources should be sorted by filename."""
    client.post("/api/index-files", json={
        "paths": [str(sample_pdf_path), str(large_text_pdf_path)]
    })

    response = client.get("/api/sources")
    filenames = [s["filename"] for s in response.json()["sources"]]
    assert filenames == sorted(filenames)


def test_sources_includes_per_file_stats(client, sample_pdf_path):
    """/api/sources should expose pages, indexed_at, and file_size_bytes."""
    client.post("/api/index-files", json={
        "paths": [str(sample_pdf_path)]
    })

    response = client.get("/api/sources")
    source = response.json()["sources"][0]

    assert source["pages"] >= 1
    assert source["indexed_at"] is not None
    # ISO 8601 with timezone — sanity check, full parse not needed
    assert "T" in source["indexed_at"]
    assert source["file_size_bytes"] is not None
    assert source["file_size_bytes"] > 0
    # Pre-existing fields stay
    assert source["chunks"] > 0
    assert source["filename"] == "dragonbane_monsters.pdf"
