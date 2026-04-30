"""
Tests for GET /api/sources and DELETE /api/source/{filename}.
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


def test_delete_source(client, sample_pdf_path, test_collection):
    """Deleting a source should remove all its chunks."""
    client.post("/api/index-files", json={
        "paths": [str(sample_pdf_path)]
    })

    # Verify it exists
    assert test_collection.count() > 0

    # Delete it
    response = client.delete("/api/source/dragonbane_monsters.pdf")
    assert response.status_code == 200
    assert "Deleted" in response.json()["message"]

    # Verify it's gone
    assert test_collection.count() == 0


def test_delete_nonexistent_source(client):
    """Deleting a source that doesn't exist should return 404."""
    response = client.delete("/api/source/nonexistent.pdf")
    assert response.status_code == 404


def test_delete_one_preserves_others(
    client, sample_pdf_path, large_text_pdf_path, test_collection
):
    """Deleting one source should not affect other sources."""
    client.post("/api/index-files", json={
        "paths": [str(sample_pdf_path), str(large_text_pdf_path)]
    })

    count_before = test_collection.count()

    client.delete("/api/source/dragonbane_monsters.pdf")

    count_after = test_collection.count()
    assert count_after > 0
    assert count_after < count_before

    # The other source should still be listed
    response = client.get("/api/sources")
    filenames = [s["filename"] for s in response.json()["sources"]]
    assert "core_rules.pdf" in filenames
    assert "dragonbane_monsters.pdf" not in filenames


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
