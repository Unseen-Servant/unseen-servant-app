"""
Tests for MCP server tools.

These tests mock the HTTP calls to the sidecar, so we're testing
that each tool correctly transforms sidecar responses into
human-readable text — NOT that the sidecar itself works (those
tests live in test_search.py, test_sources.py, etc.).

Why mock? The MCP server is a separate process from the sidecar.
In production, it calls the sidecar over HTTP. In tests, we
simulate those HTTP responses to verify formatting and error handling.
"""

import sys
import pytest

# Prevent argparse from reading pytest's arguments
sys.argv = ["mcp_server.py"]

from mcp_server import (
    search_library,
    search_in_document,
    read_document,
    list_sources,
    library_stats,
    compare_sources,
    random_table,
    sidecar,
)


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

class MockSidecarClient:
    """Drop-in replacement for SidecarClient that returns canned responses.

    We swap out the real sidecar's get/post methods with lambdas
    that return test data, so no HTTP calls are made.
    """

    def __init__(self):
        self._get_responses = {}
        self._post_responses = {}

    def set_get(self, path: str, response):
        self._get_responses[path] = response

    def set_post(self, path: str, response):
        self._post_responses[path] = response

    async def get(self, path: str) -> dict | str:
        if path in self._get_responses:
            resp = self._get_responses[path]
            if isinstance(resp, Exception):
                raise resp
            return resp
        return f"No mock configured for GET {path}"

    async def post(self, path: str, json: dict) -> dict | str:
        if path in self._post_responses:
            resp = self._post_responses[path]
            if callable(resp):
                return resp(json)
            if isinstance(resp, Exception):
                raise resp
            return resp
        return f"No mock configured for POST {path}"


@pytest.fixture
def mock_sidecar(monkeypatch):
    """Replace the global sidecar client with a mock."""
    import mcp_server
    mock = MockSidecarClient()
    monkeypatch.setattr(mcp_server, "sidecar", mock)
    return mock


# ---------------------------------------------------------------------------
# search_library tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_library_returns_formatted_results(mock_sidecar):
    mock_sidecar.set_post("/api/search", {
        "results": [
            {
                "text": "Fire Drake breathes fire in a 30-foot cone.",
                "filename": "dragonbane_monsters.pdf",
                "source": "/path/to/dragonbane_monsters.pdf",
                "chunk": 0,
                "relevance": 0.85,
            }
        ]
    })

    result = await search_library("fire drake")
    assert "Fire Drake" in result
    assert "dragonbane_monsters.pdf" in result
    assert "0.85" in result


@pytest.mark.asyncio
async def test_search_library_no_results(mock_sidecar):
    mock_sidecar.set_post("/api/search", {"results": []})

    result = await search_library("nonexistent topic")
    assert "No results found" in result


@pytest.mark.asyncio
async def test_search_library_sidecar_down(mock_sidecar):
    mock_sidecar.set_post("/api/search", "Cannot connect to Unseen Servant app.")

    result = await search_library("anything")
    assert "Cannot connect" in result


# ---------------------------------------------------------------------------
# search_in_document tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_in_document_delegates_to_search_library(mock_sidecar):
    """search_in_document is a convenience wrapper around search_library."""
    mock_sidecar.set_post("/api/search", {
        "results": [
            {
                "text": "Grappling rules text here.",
                "filename": "dragonbane_core.pdf",
                "source": "/path/to/dragonbane_core.pdf",
                "chunk": 5,
                "relevance": 0.9,
            }
        ]
    })

    result = await search_in_document("dragonbane_core.pdf", "grappling")
    assert "Grappling" in result
    assert "dragonbane_core.pdf" in result


# ---------------------------------------------------------------------------
# read_document tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_read_document_returns_content(mock_sidecar):
    mock_sidecar.set_get("/api/source/dragonbane_monsters.pdf/content", {
        "filename": "dragonbane_monsters.pdf",
        "chunks": 3,
        "content": "Fire Drake\nArmor Class: 14\nHit Points: 45",
    })

    result = await read_document("dragonbane_monsters.pdf")
    assert "dragonbane_monsters.pdf" in result
    assert "3 chunks" in result
    assert "Fire Drake" in result


@pytest.mark.asyncio
async def test_read_document_not_found(mock_sidecar):
    mock_sidecar.set_get(
        "/api/source/nonexistent.pdf/content",
        "Sidecar error: 404 — Source not found: nonexistent.pdf",
    )

    result = await read_document("nonexistent.pdf")
    assert "404" in result


# ---------------------------------------------------------------------------
# list_sources tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_sources_shows_documents(mock_sidecar):
    mock_sidecar.set_get("/api/sources", {
        "sources": [
            {"filename": "core_rules.pdf", "source": "/path/core_rules.pdf", "chunks": 12},
            {"filename": "monsters.pdf", "source": "/path/monsters.pdf", "chunks": 8},
        ],
        "count": 2,
    })

    result = await list_sources()
    assert "2 document(s)" in result
    assert "core_rules.pdf" in result
    assert "monsters.pdf" in result
    assert "12 chunks" in result


@pytest.mark.asyncio
async def test_list_sources_empty(mock_sidecar):
    mock_sidecar.set_get("/api/sources", {"sources": [], "count": 0})

    result = await list_sources()
    assert "No documents indexed" in result


# ---------------------------------------------------------------------------
# library_stats tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_library_stats_returns_overview(mock_sidecar):
    mock_sidecar.set_get("/api/stats", {
        "total_chunks": 150,
        "total_documents": 5,
        "collection_name": "ttrpg_docs",
    })

    result = await library_stats()
    assert "150" in result
    assert "5" in result
    assert "ttrpg_docs" in result


# ---------------------------------------------------------------------------
# compare_sources tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_compare_sources_shows_side_by_side(mock_sidecar):
    def mock_search(json_data):
        fname = json_data.get("source_filter", "unknown")
        return {
            "results": [
                {
                    "text": f"Grappling rules from {fname}",
                    "filename": fname,
                    "source": f"/path/{fname}",
                    "chunk": 0,
                    "relevance": 0.8,
                }
            ]
        }

    mock_sidecar.set_post("/api/search", mock_search)

    result = await compare_sources(
        "grappling", ["dragonbane.pdf", "dnd_5e.pdf"]
    )
    assert "dragonbane.pdf" in result
    assert "dnd_5e.pdf" in result
    assert "Comparing" in result


@pytest.mark.asyncio
async def test_compare_sources_needs_two_files(mock_sidecar):
    result = await compare_sources("grappling", ["only_one.pdf"])
    assert "at least 2" in result


# ---------------------------------------------------------------------------
# random_table tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_random_table_finds_table(mock_sidecar):
    mock_sidecar.set_post("/api/search", {
        "results": [
            {
                "text": "1. Goblin ambush\n2. Wandering merchant\n3. Storm",
                "filename": "random_encounters.pdf",
                "source": "/path/random_encounters.pdf",
                "chunk": 0,
                "relevance": 0.75,
            }
        ]
    })

    result = await random_table("forest encounters")
    assert "random_encounters.pdf" in result
    # Should pick a random entry
    assert "Random roll" in result


@pytest.mark.asyncio
async def test_random_table_no_results(mock_sidecar):
    mock_sidecar.set_post("/api/search", {"results": []})

    result = await random_table("something obscure")
    assert "No tables found" in result
