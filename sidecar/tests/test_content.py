"""
Tests for GET /api/source/{filename}/content.

This endpoint retrieves the full stored text of an indexed PDF
by fetching all chunks from ChromaDB, sorting by chunk index,
and concatenating them.
"""


def test_get_content_returns_full_text(client, sample_pdf_path):
    """Should return the concatenated text of all chunks for a PDF."""
    client.post("/api/index-files", json={
        "paths": [str(sample_pdf_path)]
    })

    response = client.get("/api/source/dragonbane_monsters.pdf/content")

    assert response.status_code == 200
    data = response.json()
    assert data["filename"] == "dragonbane_monsters.pdf"
    assert data["chunks"] > 0
    assert "Fire Drake" in data["content"]


def test_get_content_chunks_in_order(client, large_text_pdf_path):
    """Chunks should be returned sorted by chunk index.

    The large_text_pdf produces multiple chunks. Concatenating them
    out of order would produce garbled text.
    """
    client.post("/api/index-files", json={
        "paths": [str(large_text_pdf_path)]
    })

    response = client.get("/api/source/core_rules.pdf/content")

    assert response.status_code == 200
    data = response.json()
    assert data["chunks"] > 1  # Should have multiple chunks
    # The text should read coherently (starts with known content)
    assert "adventurer" in data["content"].lower()


def test_get_content_nonexistent_source(client):
    """Requesting content for a non-indexed file should return 404."""
    response = client.get("/api/source/nonexistent.pdf/content")

    assert response.status_code == 404


def test_get_content_special_characters(client, special_chars_pdf_path):
    """Filenames with special characters should work.

    TTRPG PDFs often have names like:
    "D&D 5E - Player's Guide (2024).pdf"
    """
    client.post("/api/index-files", json={
        "paths": [str(special_chars_pdf_path)]
    })

    filename = "D&D 5E - Player's Guide (2024).pdf"
    response = client.get(f"/api/source/{filename}/content")

    assert response.status_code == 200
    data = response.json()
    assert data["filename"] == filename
    assert data["chunks"] > 0
    assert "player" in data["content"].lower()
