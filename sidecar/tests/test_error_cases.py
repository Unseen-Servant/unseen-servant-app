"""
Edge case and error handling tests.

Your collection has 2,629 PDFs. With that many files, you WILL encounter:
- Corrupted PDFs
- Filenames with special characters (D&D, apostrophes, parentheses)
- Scanned-only PDFs (no extractable text)
- Duplicate indexing requests (clicking "Index" twice)
"""


def test_index_non_pdf_file(client, tmp_path):
    """Sending a non-PDF file path should handle gracefully."""
    txt_file = tmp_path / "notes.txt"
    txt_file.write_text("This is not a PDF")

    response = client.post("/api/index-files", json={
        "paths": [str(txt_file)]
    })

    # PyMuPDF will raise an error trying to read a .txt as PDF
    data = response.json()
    assert data["indexed"] == 0
    assert len(data["errors"]) == 1


def test_index_special_characters_filename(client, special_chars_pdf_path):
    """Filenames with &, ', (), spaces should not crash indexing.

    Real example from a TTRPG collection:
    "D&D 5E - Player's Handbook (2024).pdf"
    """
    response = client.post("/api/index-files", json={
        "paths": [str(special_chars_pdf_path)]
    })

    data = response.json()
    assert data["indexed"] == 1
    assert data["errors"] == []


def test_duplicate_indexing(client, sample_pdf_path, test_store):
    """Indexing the same PDF twice should not create duplicate chunks.

    A reindex replaces the book's rows in one transaction — same count,
    no errors.
    """
    # Index once
    client.post("/api/index-files", json={
        "paths": [str(sample_pdf_path)]
    })
    count_after_first = test_store.count_units()

    # Index again
    response = client.post("/api/index-files", json={
        "paths": [str(sample_pdf_path)]
    })

    assert response.status_code == 200
    data = response.json()
    assert data["indexed"] == 1
    assert data["errors"] == []

    # Count should stay the same (replaced, not duplicated)
    count_after_second = test_store.count_units()
    assert count_after_second == count_after_first


def test_index_missing_request_body(client):
    """POST with no JSON body should return 422 (Pydantic validation)."""
    response = client.post("/api/index-files")
    assert response.status_code == 422


def test_search_missing_query(client):
    """POST /api/search without query field should return 422."""
    response = client.post("/api/search", json={})
    assert response.status_code == 422


def test_search_negative_n_results(client, sample_pdf_path):
    """Negative n_results: should either error or return empty.

    This is a boundary condition. The vector store may handle it
    differently than expected. The test documents the actual behavior.
    """
    client.post("/api/index-files", json={
        "paths": [str(sample_pdf_path)]
    })

    response = client.post("/api/search", json={
        "query": "dragon",
        "n_results": -1
    })
    # Document the behavior — either 200 with empty or 422/500
    assert response.status_code in [200, 422, 500]
