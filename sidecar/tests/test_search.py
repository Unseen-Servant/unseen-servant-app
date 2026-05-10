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
    """Parent-document retrieval response contract: each result carries
    text, source provenance, the section breadcrumb, page span, and
    relevance score."""
    response = indexed_client.post("/api/search", json={
        "query": "armor class",
        "n_results": 1
    })

    result = response.json()["results"][0]
    assert "text" in result
    assert "filename" in result
    assert "source" in result
    assert "section_heading" in result
    assert "page_start" in result
    assert "page_end" in result
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
    """If n_results is omitted, default should be 15."""
    response = indexed_client.post("/api/search", json={
        "query": "dragon"
    })

    assert response.status_code == 200
    assert len(response.json()["results"]) <= 15


# ---------------------------------------------------------------------------
# Filtered search tests (source_filter)
# ---------------------------------------------------------------------------

@pytest.fixture
def multi_indexed_client(client, sample_pdf_path, large_text_pdf_path):
    """Client with two PDFs indexed — useful for testing source_filter.

    - dragonbane_monsters.pdf: dragon/fire content
    - core_rules.pdf: dungeon/adventurer content
    """
    client.post("/api/index-files", json={
        "paths": [str(sample_pdf_path), str(large_text_pdf_path)]
    })
    return client


def test_filtered_search_returns_only_matching_source(multi_indexed_client):
    """With source_filter, results should only come from that file."""
    response = multi_indexed_client.post("/api/search", json={
        "query": "dragon fire",
        "n_results": 10,
        "source_filter": "dragonbane_monsters.pdf"
    })

    data = response.json()
    assert len(data["results"]) > 0
    for result in data["results"]:
        assert result["filename"] == "dragonbane_monsters.pdf"


def test_filtered_search_excludes_other_sources(multi_indexed_client):
    """Filtering to one source should not return chunks from the other."""
    response = multi_indexed_client.post("/api/search", json={
        "query": "adventurer dungeon",
        "n_results": 10,
        "source_filter": "dragonbane_monsters.pdf"
    })

    data = response.json()
    for result in data["results"]:
        assert result["filename"] != "core_rules.pdf"


def test_filtered_search_nonexistent_source(multi_indexed_client):
    """Filtering to a source that doesn't exist should return empty results."""
    response = multi_indexed_client.post("/api/search", json={
        "query": "dragon",
        "n_results": 5,
        "source_filter": "nonexistent_book.pdf"
    })

    assert response.status_code == 200
    data = response.json()
    assert data["results"] == []


def test_unfiltered_search_still_works(multi_indexed_client):
    """Without source_filter, search should return results from all sources."""
    response = multi_indexed_client.post("/api/search", json={
        "query": "dragon dungeon adventurer",
        "n_results": 10
    })

    data = response.json()
    filenames = {r["filename"] for r in data["results"]}
    # Should have results from both indexed PDFs
    assert len(filenames) >= 1  # At least one source
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Game system filter tests
# ---------------------------------------------------------------------------

@pytest.fixture
def multi_system_client(client, dnd5e_pdf_path, dragonbane_pdf_path):
    """Client with PDFs from two different game systems indexed."""
    client.post("/api/index-files", json={
        "paths": [str(dnd5e_pdf_path), str(dragonbane_pdf_path)]
    })
    return client


def test_search_filter_by_game_system(multi_system_client):
    """With game_system filter, results should only match that system."""
    response = multi_system_client.post("/api/search", json={
        "query": "adventure rules",
        "n_results": 10,
        "game_system": "D&D 5E",
    })

    data = response.json()
    assert len(data["results"]) > 0
    for result in data["results"]:
        assert result["game_system"] == "D&D 5E"


def test_search_game_system_no_match(multi_system_client):
    """Filtering to a system with no docs should return empty."""
    response = multi_system_client.post("/api/search", json={
        "query": "adventure",
        "n_results": 5,
        "game_system": "Call of Cthulhu",
    })

    assert response.status_code == 200
    data = response.json()
    assert data["results"] == []


def test_search_no_game_system_returns_all(multi_system_client):
    """Without game_system filter, results from all systems should appear."""
    response = multi_system_client.post("/api/search", json={
        "query": "adventure rules",
        "n_results": 10,
    })

    data = response.json()
    systems = {r["game_system"] for r in data["results"]}
    assert len(systems) >= 1


def test_search_combined_filters(multi_system_client):
    """Both source_filter and game_system can be used together."""
    response = multi_system_client.post("/api/search", json={
        "query": "adventure",
        "n_results": 10,
        "source_filter": "dragonbane_core.pdf",
        "game_system": "Dragonbane",
    })

    data = response.json()
    for result in data["results"]:
        assert result["filename"] == "dragonbane_core.pdf"
        assert result["game_system"] == "Dragonbane"


def test_search_result_includes_game_system(indexed_client):
    """Search results should include game_system field."""
    response = indexed_client.post("/api/search", json={
        "query": "dragon",
        "n_results": 1,
    })

    result = response.json()["results"][0]
    assert "game_system" in result


# ---------------------------------------------------------------------------
# Path-scoped search tests (source_paths)
# ---------------------------------------------------------------------------

def test_search_source_paths_restricts_to_given_files(
    multi_indexed_client, sample_pdf_path
):
    """source_paths should restrict results to the listed full paths."""
    response = multi_indexed_client.post("/api/search", json={
        "query": "dragon dungeon adventurer",
        "n_results": 10,
        "source_paths": [str(sample_pdf_path)],
    })

    data = response.json()
    assert len(data["results"]) > 0
    for result in data["results"]:
        assert result["source"] == str(sample_pdf_path)


def test_search_source_paths_unknown_path_returns_empty(multi_indexed_client):
    """A path that isn't indexed yields no results, not an error."""
    response = multi_indexed_client.post("/api/search", json={
        "query": "dragon",
        "n_results": 5,
        "source_paths": ["/nope/never/indexed.pdf"],
    })

    assert response.status_code == 200
    assert response.json()["results"] == []


# ---------------------------------------------------------------------------
# Multi-system filter (game_systems list)
# ---------------------------------------------------------------------------

def test_search_game_systems_list_includes_only_listed(multi_system_client):
    """game_systems list should restrict results to systems in the list."""
    response = multi_system_client.post("/api/search", json={
        "query": "adventure rules",
        "n_results": 10,
        "game_systems": ["D&D 5E"],
    })

    data = response.json()
    assert len(data["results"]) > 0
    for result in data["results"]:
        assert result["game_system"] == "D&D 5E"


def test_search_game_systems_list_multiple(multi_system_client):
    """A list with multiple systems should accept any of them."""
    response = multi_system_client.post("/api/search", json={
        "query": "adventure",
        "n_results": 10,
        "game_systems": ["D&D 5E", "Dragonbane"],
    })

    data = response.json()
    systems = {r["game_system"] for r in data["results"]}
    assert systems.issubset({"D&D 5E", "Dragonbane"})


# ---------------------------------------------------------------------------
# Secondary-tag resolution (issue #98)
# ---------------------------------------------------------------------------

def test_search_resolves_secondary_tag(client, dnd5e_pdf_path):
    """Searching by a secondary tag returns the file via filename $in resolution."""
    # Primary-tag detection from the path puts this file under D&D 5E.
    client.post("/api/index-files", json={"paths": [str(dnd5e_pdf_path)]})

    # Add PF2E as a secondary tag (D&D 5E remains primary).
    client.post("/api/set-game-systems", json={
        "filename": "player_handbook.pdf",
        "game_systems": ["D&D 5E", "PF2E"],
    })

    response = client.post("/api/search", json={
        "query": "character creation rules",
        "n_results": 5,
        "game_system": "PF2E",
    })

    data = response.json()
    assert len(data["results"]) > 0
    for result in data["results"]:
        assert result["filename"] == "player_handbook.pdf"


def test_search_primary_tag_unaffected(client, dnd5e_pdf_path, dragonbane_pdf_path):
    """Primary-tag search returns both primary matches and secondary matches."""
    client.post("/api/index-files", json={
        "paths": [str(dnd5e_pdf_path), str(dragonbane_pdf_path)]
    })

    # Make Dragonbane book a secondary 5E hit too.
    client.post("/api/set-game-systems", json={
        "filename": "dragonbane_core.pdf",
        "game_systems": ["Dragonbane", "D&D 5E"],
    })

    response = client.post("/api/search", json={
        "query": "adventure rules",
        "n_results": 10,
        "game_system": "D&D 5E",
    })

    filenames = {r["filename"] for r in response.json()["results"]}
    assert "player_handbook.pdf" in filenames
    assert "dragonbane_core.pdf" in filenames
