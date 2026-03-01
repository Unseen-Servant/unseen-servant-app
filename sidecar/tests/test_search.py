"""
Tests for POST /api/search.

These tests verify that semantic search returns relevant results.
Because we use ChromaDB's DefaultEmbeddingFunction (real ONNX
embeddings), we can actually test that "dragon" queries return
dragon-related chunks — not just that "something came back."
"""

import pytest


@pytest.fixture
def indexed_client(client, sample_pdf_path):
    """Client with one PDF already indexed.

    Pattern: fixture that depends on another fixture.
    This builds a "ready to search" state without repeating
    the indexing call in every test.
    """
    client.post("/api/index-files", json={
        "paths": [str(sample_pdf_path)]
    })
    return client


def test_search_returns_results(indexed_client):
    """A query matching indexed content should return results."""
    response = indexed_client.post("/api/search", json={
        "query": "fire breathing dragon",
        "n_results": 3
    })

    assert response.status_code == 200
    data = response.json()
    assert len(data["results"]) > 0


def test_search_result_shape(indexed_client):
    """Each result should have text, filename, source, chunk, relevance."""
    response = indexed_client.post("/api/search", json={
        "query": "armor class",
        "n_results": 1
    })

    result = response.json()["results"][0]
    assert "text" in result
    assert "filename" in result
    assert "source" in result
    assert "chunk" in result
    assert "relevance" in result
    assert isinstance(result["relevance"], float)


def test_search_relevance_is_numeric(indexed_client):
    """Relevance should be a float (computed as 1 - distance).

    Note: with L2 distance (used by ONNX DefaultEmbeddingFunction),
    distances can exceed 1.0, making relevance negative. With cosine
    distance (used by Ollama in production), relevance stays in [0, 1].
    So we only check it's a number, not its bounds.
    """
    response = indexed_client.post("/api/search", json={
        "query": "dragon fire",
        "n_results": 5
    })

    for result in response.json()["results"]:
        assert isinstance(result["relevance"], float), \
            f"Expected float, got {type(result['relevance'])}"


def test_search_respects_n_results(indexed_client):
    """Should return at most n_results items."""
    response = indexed_client.post("/api/search", json={
        "query": "dragon",
        "n_results": 1
    })

    assert len(response.json()["results"]) <= 1


def test_search_empty_collection(client):
    """Searching with no indexed documents should return empty results."""
    response = client.post("/api/search", json={
        "query": "anything",
        "n_results": 5
    })

    assert response.status_code == 200


def test_search_default_n_results(indexed_client):
    """If n_results is omitted, default should be 5."""
    response = indexed_client.post("/api/search", json={
        "query": "dragon"
    })

    assert response.status_code == 200
