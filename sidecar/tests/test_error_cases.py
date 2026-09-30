"""
Edge case and error handling tests.

Your collection has 2,629 PDFs. With that many files, you WILL encounter:
- Corrupted PDFs
- Filenames with special characters (D&D, apostrophes, parentheses)
- Scanned-only PDFs (no extractable text)
- Duplicate indexing requests (clicking "Index" twice)
"""

import httpx
import pytest
from fastapi.testclient import TestClient

from legend_lore import embedder
from legend_lore.granularity import EmbedUnit
from legend_lore.service import load_manifest
from server import create_app
from tests.conftest import seed_book


def test_index_non_pdf_file(client, tmp_path):
    """Sending a non-PDF file path should handle gracefully."""
    txt_file = tmp_path / "notes.txt"
    txt_file.write_text("This is not a PDF")

    response = client.post("/api/index-files", json={
        "paths": [str(txt_file)]
    })

    # Refused by the extension check before PyMuPDF sees it.
    data = response.json()
    assert data["indexed"] == 0
    assert data["errors"] == ["notes.txt: Not a PDF: notes.txt"]


@pytest.mark.parametrize("damage", ["garbage", "truncated"])
def test_index_corrupt_pdf(client, sample_pdf_path, test_store, tmp_path, damage):
    """A .pdf PyMuPDF can't read is reported against its name and leaves
    nothing behind: no manifest entry, no document in the store."""
    bad = tmp_path / "broken.pdf"
    if damage == "garbage":
        bad.write_bytes(b"this is not a pdf at all")
    else:
        data = sample_pdf_path.read_bytes()
        bad.write_bytes(data[: len(data) // 3])

    response = client.post("/api/index-files", json={"paths": [str(bad)]})

    data = response.json()
    assert data["indexed"] == 0
    assert len(data["errors"]) == 1
    assert data["errors"][0].startswith("broken.pdf: ")
    assert str(bad) not in load_manifest(tmp_path).files
    assert all(d.path != str(bad) for d in test_store.documents())


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


@pytest.mark.parametrize("n_results", [-1, 0])
def test_search_rejects_non_positive_n_results(client, sample_pdf_path, n_results):
    """A request for no results is a malformed request: 422, not a 500
    carrying the vector store's knn error."""
    client.post("/api/index-files", json={
        "paths": [str(sample_pdf_path)]
    })

    response = client.post("/api/search", json={
        "query": "dragon",
        "n_results": n_results,
    })
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Query-time embedding failure: Ollama down, or bge-m3 not pulled. Search
# must answer with an error that says so, not hang or return empty.
# ---------------------------------------------------------------------------


@pytest.fixture
def production_embed_client(test_store, test_embed_fn, tmp_path):
    """Search over an indexed book, with queries embedded by the real
    Ollama client (embedder.embed) instead of the test model."""
    seed_book(test_store, test_embed_fn, "/lib/bestiary.pdf", [EmbedUnit(
        chunk_id="c0", text="The fire drake breathes flame.", parent_id="p0",
        chunk_type="prose", section_heading="Fire Drake",
        source_pdf="/lib/bestiary.pdf", page_start=1, page_end=1, ordinal=0,
    )])
    app = create_app(store=test_store, data_dir=tmp_path, embed_fn=embedder.embed)
    return TestClient(app)


def test_search_reports_ollama_unreachable(production_embed_client, monkeypatch):
    # Port 1 on loopback: nothing listens, the connection is refused.
    monkeypatch.setattr(embedder, "EMBED_BASE_URL", "http://127.0.0.1:1")

    response = production_embed_client.post("/api/search", json={"query": "dragon"})

    assert response.status_code == 500
    assert response.json()["detail"].startswith("Embedder not running — ")


def test_search_reports_the_model_missing(production_embed_client, monkeypatch):
    def not_pulled(url, json, timeout):
        return httpx.Response(
            404, json={"error": 'model "bge-m3" not found, try pulling it first'},
        )

    monkeypatch.setattr(httpx, "post", not_pulled)

    response = production_embed_client.post("/api/search", json={"query": "dragon"})

    assert response.status_code == 500
    assert response.json()["detail"] == (
        'embed failed (404): model "bge-m3" not found, try pulling it first'
    )
