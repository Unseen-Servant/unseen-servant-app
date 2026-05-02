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
    read_document,
    list_sources,
    list_game_systems,
    list_collections,
    get_active_context,
    compare_sources,
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
                "game_system": "Dragonbane",
                "relevance": 0.85,
            }
        ]
    })

    result = await search_library("fire drake")
    assert "Fire Drake" in result
    assert "dragonbane_monsters.pdf" in result
    assert "0.85" in result
    assert "[Dragonbane]" in result


@pytest.mark.asyncio
async def test_search_library_no_results(mock_sidecar):
    mock_sidecar.set_post("/api/search", {"results": []})

    result = await search_library("nonexistent topic")
    assert "No results found" in result


@pytest.mark.asyncio
async def test_search_library_sidecar_down(mock_sidecar):
    mock_sidecar.set_post("/api/search", "Cannot connect to Legend Lore app.")

    result = await search_library("anything")
    assert "Cannot connect" in result


@pytest.mark.asyncio
async def test_search_library_with_game_system(mock_sidecar):
    """game_system parameter should be included in the payload."""
    captured = {}

    def capture_payload(json_data):
        captured.update(json_data)
        return {"results": []}

    mock_sidecar.set_post("/api/search", capture_payload)

    await search_library("initiative", game_system="D&D 5E")
    assert captured.get("game_system") == "D&D 5E"


@pytest.mark.asyncio
async def test_search_library_prepends_notice_when_auto_scoped(mock_sidecar):
    """When sidecar reports auto_scoped=true, the result starts with the notice."""
    mock_sidecar.set_post("/api/search", {
        "results": [{
            "text": "Strahd is a vampire lord.",
            "filename": "cos.pdf",
            "source": "/cos.pdf",
            "game_system": "D&D 5E",
            "relevance": 0.9,
        }],
        "effective_collection": "Curse of Strahd",
        "auto_scoped": True,
    })
    result = await search_library("strahd")
    assert result.startswith("[Active context: Curse of Strahd]")


@pytest.mark.asyncio
async def test_search_library_no_notice_when_explicit_collection(mock_sidecar):
    """No notice when the caller passed an explicit collection."""
    mock_sidecar.set_post("/api/search", {
        "results": [{
            "text": "x",
            "filename": "x.pdf",
            "source": "/x.pdf",
            "game_system": "D&D 5E",
            "relevance": 0.5,
        }],
        "effective_collection": "Strahd",
        "auto_scoped": False,
    })
    result = await search_library("anything", collection="Strahd")
    assert "Active context" not in result


@pytest.mark.asyncio
async def test_search_library_passes_search_all(mock_sidecar):
    """search_all=True is forwarded to the sidecar."""
    captured = {}

    def capture_payload(json_data):
        captured.update(json_data)
        return {"results": []}

    mock_sidecar.set_post("/api/search", capture_payload)
    await search_library("anything", search_all=True)
    assert captured.get("search_all") is True


# ---------------------------------------------------------------------------
# get_active_context tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_active_context_when_set(mock_sidecar):
    mock_sidecar.set_get("/api/active-context", {"active_context": "Strahd"})
    result = await get_active_context()
    assert "Strahd" in result


@pytest.mark.asyncio
async def test_get_active_context_when_unset(mock_sidecar):
    mock_sidecar.set_get("/api/active-context", {"active_context": None})
    result = await get_active_context()
    assert "No active context" in result


# ---------------------------------------------------------------------------
# list_collections — active context marker
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_collections_marks_active(mock_sidecar):
    mock_sidecar.set_get("/api/collections", {
        "collections": {
            "Strahd": {"name": "Strahd", "file_count": 3, "description": ""},
            "Pathfinder": {"name": "Pathfinder", "file_count": 5, "description": ""},
        },
        "count": 2,
        "active_context": "Strahd",
    })
    result = await list_collections()
    assert "★" in result
    assert "Active context: Strahd" in result


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
            {"filename": "core_rules.pdf", "source": "/path/core_rules.pdf", "chunks": 12, "game_system": "D&D 5E"},
            {"filename": "monsters.pdf", "source": "/path/monsters.pdf", "chunks": 8, "game_system": "D&D 5E"},
        ],
        "count": 2,
    })

    result = await list_sources()
    assert "2 document(s)" in result
    assert "core_rules.pdf" in result
    assert "monsters.pdf" in result
    assert "12 chunks" in result
    assert "[D&D 5E]" in result


@pytest.mark.asyncio
async def test_list_sources_empty(mock_sidecar):
    mock_sidecar.set_get("/api/sources", {"sources": [], "count": 0})

    result = await list_sources()
    assert "No documents indexed" in result


# ---------------------------------------------------------------------------
# list_game_systems tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_game_systems_shows_systems(mock_sidecar):
    mock_sidecar.set_get("/api/game-systems", {
        "game_systems": ["D&D 5E", "Dragonbane", "unknown"],
        "count": 3,
    })

    result = await list_game_systems()
    assert "3" in result
    assert "D&D 5E" in result
    assert "Dragonbane" in result


@pytest.mark.asyncio
async def test_list_game_systems_empty(mock_sidecar):
    mock_sidecar.set_get("/api/game-systems", {
        "game_systems": [],
        "count": 0,
    })

    result = await list_game_systems()
    assert "No game systems detected" in result


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
# list_collections tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_collections_shows_collections(mock_sidecar):
    mock_sidecar.set_get("/api/collections", {
        "collections": {
            "Curse of Strahd": {
                "name": "Curse of Strahd",
                "file_paths": ["/a.pdf", "/b.pdf"],
                "file_count": 2,
                "created_at": "2026-03-02T00:00:00+00:00",
                "description": "Campaign prep",
            },
        },
        "count": 1,
    })

    result = await list_collections()
    assert "Curse of Strahd" in result
    assert "2 files" in result
    assert "Campaign prep" in result


@pytest.mark.asyncio
async def test_list_collections_empty(mock_sidecar):
    mock_sidecar.set_get("/api/collections", {"collections": {}, "count": 0})

    result = await list_collections()
    assert "No collections" in result


@pytest.mark.asyncio
async def test_list_collections_no_description(mock_sidecar):
    mock_sidecar.set_get("/api/collections", {
        "collections": {
            "Quick Ref": {
                "name": "Quick Ref",
                "file_paths": ["/a.pdf"],
                "file_count": 1,
                "created_at": "2026-03-02T00:00:00+00:00",
                "description": "",
            },
        },
        "count": 1,
    })

    result = await list_collections()
    assert "Quick Ref" in result
    assert "1 files" in result
    # No description suffix
    assert " — " not in result


# ---------------------------------------------------------------------------
# search_library with collection parameter
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_library_with_collection(mock_sidecar):
    """collection parameter should be included in the payload."""
    captured = {}

    def capture_payload(json_data):
        captured.update(json_data)
        return {"results": []}

    mock_sidecar.set_post("/api/search", capture_payload)

    await search_library("fire drake", collection="Monsters Only")
    assert captured.get("collection") == "Monsters Only"


@pytest.mark.asyncio
async def test_search_library_without_collection(mock_sidecar):
    """Without collection, the payload should not include the key."""
    captured = {}

    def capture_payload(json_data):
        captured.update(json_data)
        return {"results": []}

    mock_sidecar.set_post("/api/search", capture_payload)

    await search_library("fire drake")
    assert "collection" not in captured


