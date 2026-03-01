"""
Tests for POST /api/index-files.

This is the most important endpoint — it's the whole reason
the sidecar exists. These tests verify:
1. PDF text extraction works
2. Chunks are stored in ChromaDB with correct metadata
3. Error handling for bad files
"""


def test_index_single_pdf(client, sample_pdf_path, test_collection):
    """Indexing a valid PDF should return indexed=1 and store chunks."""
    response = client.post("/api/index-files", json={
        "paths": [str(sample_pdf_path)]
    })

    assert response.status_code == 200
    data = response.json()
    assert data["indexed"] == 1
    assert data["total"] == 1
    assert data["errors"] == []

    # Verify chunks were actually stored in ChromaDB
    count = test_collection.count()
    assert count > 0, "Expected chunks to be stored in ChromaDB"


def test_index_stores_correct_metadata(client, sample_pdf_path, test_collection):
    """Each chunk should have source, filename, and chunk index metadata."""
    client.post("/api/index-files", json={
        "paths": [str(sample_pdf_path)]
    })

    results = test_collection.get(include=["metadatas"])
    for metadata in results["metadatas"]:
        assert "source" in metadata
        assert "filename" in metadata
        assert "chunk" in metadata
        assert metadata["filename"] == "dragonbane_monsters.pdf"


def test_index_chunk_ids_follow_pattern(client, sample_pdf_path, test_collection):
    """Chunk IDs should follow the pattern: {pdf_stem}_{chunk_idx}.

    Why does the ID format matter? When re-indexing a PDF,
    ChromaDB uses IDs to detect duplicates. If the format changes,
    you'd get duplicate chunks instead of updates.
    """
    client.post("/api/index-files", json={
        "paths": [str(sample_pdf_path)]
    })

    results = test_collection.get()
    for id in results["ids"]:
        assert id.startswith("dragonbane_monsters_"), f"Unexpected ID format: {id}"


def test_index_missing_file(client):
    """Indexing a file that doesn't exist should report an error, not crash."""
    response = client.post("/api/index-files", json={
        "paths": ["/nonexistent/fake_module.pdf"]
    })

    assert response.status_code == 200  # The endpoint itself succeeds
    data = response.json()
    assert data["indexed"] == 0
    assert data["total"] == 1
    assert len(data["errors"]) == 1
    assert "File not found" in data["errors"][0]


def test_index_empty_pdf(client, empty_pdf_path):
    """A PDF with no extractable text should be reported as an error."""
    response = client.post("/api/index-files", json={
        "paths": [str(empty_pdf_path)]
    })

    data = response.json()
    assert data["indexed"] == 0
    assert len(data["errors"]) == 1
    assert "Empty or scanned PDF" in data["errors"][0]


def test_index_multiple_pdfs(client, sample_pdf_path, large_text_pdf_path):
    """Indexing multiple files in one request."""
    response = client.post("/api/index-files", json={
        "paths": [str(sample_pdf_path), str(large_text_pdf_path)]
    })

    data = response.json()
    assert data["indexed"] == 2
    assert data["total"] == 2
    assert data["errors"] == []


def test_index_mixed_valid_and_invalid(client, sample_pdf_path):
    """Mix of valid and invalid paths: valid ones should still be indexed."""
    response = client.post("/api/index-files", json={
        "paths": [str(sample_pdf_path), "/nonexistent/nope.pdf"]
    })

    data = response.json()
    assert data["indexed"] == 1
    assert data["total"] == 2
    assert len(data["errors"]) == 1


def test_index_large_pdf_creates_multiple_chunks(
    client, large_text_pdf_path, test_collection
):
    """A PDF with > 1000 chars should produce multiple chunks.

    For your 18GB collection, some PDFs will have thousands of chunks.
    This verifies the batching logic works correctly.
    """
    client.post("/api/index-files", json={
        "paths": [str(large_text_pdf_path)]
    })

    count = test_collection.count()
    assert count > 1, f"Expected multiple chunks, got {count}"


def test_index_empty_paths_list(client):
    """Sending an empty list should return indexed=0 with no errors."""
    response = client.post("/api/index-files", json={
        "paths": []
    })

    data = response.json()
    assert data["indexed"] == 0
    assert data["total"] == 0
    assert data["errors"] == []


# ---------------------------------------------------------------------------
# Game system metadata
# ---------------------------------------------------------------------------

def test_index_stores_game_system_metadata(
    client, dnd5e_pdf_path, test_collection
):
    """Chunks from a D&D 5E folder should have game_system in metadata."""
    client.post("/api/index-files", json={
        "paths": [str(dnd5e_pdf_path)]
    })

    results = test_collection.get(include=["metadatas"])
    for metadata in results["metadatas"]:
        assert metadata["game_system"] == "D&D 5E"


def test_index_unknown_game_system(client, untagged_pdf_path, test_collection):
    """PDF with no system hints should get game_system='unknown'."""
    client.post("/api/index-files", json={
        "paths": [str(untagged_pdf_path)]
    })

    results = test_collection.get(include=["metadatas"])
    for metadata in results["metadatas"]:
        assert metadata["game_system"] == "unknown"


def test_index_with_game_system_override(
    client, untagged_pdf_path, test_collection
):
    """Manual game_system override should take priority over detection."""
    client.post("/api/index-files", json={
        "paths": [str(untagged_pdf_path)],
        "game_system": "Savage Worlds",
    })

    results = test_collection.get(include=["metadatas"])
    for metadata in results["metadatas"]:
        assert metadata["game_system"] == "Savage Worlds"
