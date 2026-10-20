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

import asyncio
import pytest

from mcp_server import (
    search_library,
    get_section,
    get_pages,
    list_sources,
    list_game_systems,
    list_collections,
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


@pytest.fixture
def http_sidecar(monkeypatch):
    """The real SidecarClient, its HTTP answered by a handler the test sets.

    For error paths: the client, not a mock, has to turn a refused
    connection or an error status into the message the tool returns.
    """
    import argparse
    import httpx
    import mcp_server

    handler = {}
    real_client = httpx.AsyncClient

    def client_factory(**kwargs):
        transport = httpx.MockTransport(lambda request: handler["fn"](request))
        return real_client(transport=transport, **kwargs)

    monkeypatch.setattr(mcp_server.httpx, "AsyncClient", client_factory)
    args = argparse.Namespace(sidecar_url="http://sidecar.test", data_dir=None)
    monkeypatch.setattr(mcp_server, "sidecar", mcp_server.SidecarClient(args))
    return handler


def _refuse(request):
    import httpx
    raise httpx.ConnectError("connection refused", request=request)


# ---------------------------------------------------------------------------
# search_library tests
# ---------------------------------------------------------------------------

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
                "tier": "strong",
                "reranked": True,
            }
        ]
    })

    result = await search_library("fire drake")
    assert "Fire Drake" in result
    assert "dragonbane_monsters.pdf" in result
    assert "match: strong" in result
    assert "[Dragonbane]" in result


async def test_search_library_no_results(mock_sidecar):
    mock_sidecar.set_post("/api/search", {"results": []})

    result = await search_library("nonexistent topic")
    assert "No results found" in result


async def test_search_library_surfaces_server_message_on_empty(mock_sidecar):
    """The server explains WHY the result set is empty (bad filter value,
    empty collection) — that explanation must reach the model instead of
    being swallowed into a generic 'No results found' (issue #309)."""
    mock_sidecar.set_post("/api/search", {
        "results": [],
        "message": (
            'game_system "Shadowrun" is not in the library. '
            'Available: D&D 5E, Dragonbane.'
        ),
    })
    result = await search_library("grappling", game_system="Shadowrun")
    assert "Shadowrun" in result
    assert "Available: D&D 5E, Dragonbane" in result


async def test_search_library_surfaces_resolution_note_with_results(mock_sidecar):
    """When the server auto-resolved a near-miss filter, the note is shown
    so the model learns the exact value for follow-up calls."""
    mock_sidecar.set_post("/api/search", {
        "results": [{
            "text": "Grappling rules.",
            "filename": "phb.pdf",
            "source": "/phb.pdf",
            "game_system": "D&D 5E",
            "relevance": 0.9,
            "tier": "strong",
            "reranked": True,
        }],
        "message": 'game_system "dnd" matched "D&D 5E".',
    })
    result = await search_library("grappling", game_system="dnd")
    assert 'matched "D&D 5E"' in result
    assert "Grappling rules." in result


async def test_search_library_sidecar_down(http_sidecar):
    http_sidecar["fn"] = _refuse

    result = await search_library("anything")
    assert "Cannot connect" in result


async def test_search_library_with_game_system(mock_sidecar):
    """game_system parameter should be included in the payload."""
    captured = {}

    def capture_payload(json_data):
        captured.update(json_data)
        return {"results": []}

    mock_sidecar.set_post("/api/search", capture_payload)

    await search_library("initiative", game_system="D&D 5E")
    assert captured.get("game_system") == "D&D 5E"


# ---------------------------------------------------------------------------
# search_library — tiers instead of raw scores (issues #306/#310)
# ---------------------------------------------------------------------------

def _result(text, tier, relevance=0.5):
    return {
        "text": text,
        "filename": "book.pdf",
        "source": "/book.pdf",
        "game_system": "D&D 5E",
        "relevance": relevance,
        "tier": tier,
        "reranked": True,
    }


async def test_search_library_prints_tier_not_raw_relevance(mock_sidecar):
    """Results show the ordinal tier; the raw cross-scale number is dropped."""
    mock_sidecar.set_post("/api/search", {
        "results": [_result("Grappling rules text.", "strong", 0.999)],
    })
    result = await search_library("grappling")
    assert "match: strong" in result
    assert "relevance" not in result
    assert "0.999" not in result


async def test_search_library_inserts_weak_divider(mock_sidecar):
    """A divider warns the model before the first weak result."""
    mock_sidecar.set_post("/api/search", {
        "results": [
            _result("Good grappling text.", "strong"),
            _result("Marginal text.", "weak"),
        ],
    })
    result = await search_library("grappling")
    divider = result.find("scored poorly")
    assert divider != -1
    assert result.find("Good grappling text.") < divider < result.find("Marginal text.")


async def test_search_library_divider_opens_the_trailing_weak_run(mock_sidecar):
    """A weak result followed by a strong one (system-boost partition,
    straggler scoring) must not put the strong one below the line."""
    mock_sidecar.set_post("/api/search", {
        "results": [
            _result("Named-system text.", "weak"),
            _result("Strong other-system text.", "strong"),
            _result("Marginal text.", "weak"),
        ],
    })
    result = await search_library("grappling in osric")
    divider = result.find("scored poorly")
    assert result.find("Strong other-system text.") < divider < result.find("Marginal text.")
    assert result.count("scored poorly") == 1


async def test_search_library_all_weak_prefaces_warning(mock_sidecar):
    """When every result is weak, say so up front so the model doesn't
    synthesize a confident answer from noise."""
    mock_sidecar.set_post("/api/search", {
        "results": [
            _result("Unrelated text A.", "weak"),
            _result("Unrelated text B.", "weak"),
        ],
    })
    result = await search_library("eldritch blast")
    head = result[:250]
    assert "No strong matches" in head
    assert "without filters" in result


async def test_search_library_no_divider_when_all_strong(mock_sidecar):
    mock_sidecar.set_post("/api/search", {
        "results": [
            _result("Text A.", "strong"),
            _result("Text B.", "good"),
        ],
    })
    result = await search_library("grappling")
    assert "scored poorly" not in result
    assert "No strong matches" not in result


# ---------------------------------------------------------------------------
# search_library — compact output under an 8k budget (roadmap 2.2)
# ---------------------------------------------------------------------------

def _section_result(section_id="s_abc123", matched="Short match.", text=None,
                     tier="strong"):
    return {
        "text": text if text is not None else matched,
        "matched_text": matched,
        "filename": "book.pdf",
        "source": "/book.pdf",
        "section_id": section_id,
        "section_heading": "Monsters > Kraken",
        "page_start": 10,
        "page_end": 10,
        "game_system": "D&D 5E",
        "relevance": 0.9,
        "tier": tier,
        "reranked": True,
        "truncated": False,
    }


async def test_search_library_compact_shows_id_and_snippet(mock_sidecar):
    mock_sidecar.set_post("/api/search", {
        "results": [_section_result(matched="The kraken makes three tentacle attacks.")],
    })
    result = await search_library("kraken attacks")
    assert "id=s_abc123" in result
    assert "The kraken makes three tentacle attacks." in result
    assert 'Full section: get_section("s_abc123")' in result


async def test_search_library_compact_trims_long_matches(mock_sidecar):
    """A per-result block stays small even when the full section is huge —
    the compact default is what makes an 8k budget hold many results."""
    long_match = "x" * 900
    mock_sidecar.set_post("/api/search", {
        "results": [_section_result(matched=long_match, text=long_match * 5)],
    })
    result = await search_library("anything")
    assert long_match not in result
    assert "…" in result  # trailing ellipsis marks the cut
    block = result.split("--- Result 1")[1]
    assert len(block) < 800  # snippet cap + a few header lines, nowhere near 4500


async def test_search_library_prints_whole_text_when_there_is_no_section_id(mock_sidecar):
    """A legacy row has no section to drill into, so the compact snippet
    would strand the rest of its text with no way to ask for it — print
    the whole thing and omit the (useless) get_section pointer."""
    body = "Legacy body. " * 80          # well past MATCHED_SNIPPET_CHARS
    mock_sidecar.set_post("/api/search", {
        "results": [_section_result(section_id="", matched="Legacy body.",
                                    text=body)],
    })
    result = await search_library("anything")
    assert body in result
    assert "Full section:" not in result


async def test_search_library_full_text_prints_whole_text(mock_sidecar):
    full_text = "Kraken. AC 18, HP 472. " * 10
    mock_sidecar.set_post("/api/search", {
        "results": [_section_result(matched="Short match.", text=full_text)],
    })
    result = await search_library("kraken", full_text=True)
    assert full_text in result
    # Not truncated and full_text=True: the printed text already is the
    # whole section, so there's nothing more for get_section to add.
    assert "Full section:" not in result


async def test_search_library_full_text_still_offers_get_section_when_truncated(
    mock_sidecar
):
    """Even with full_text=True, a result the server's own budget truncated
    shows only its matched unit (pack_results swaps text -> matched_text) —
    the pointer to the real full section still belongs on screen."""
    result_data = _section_result(matched="Short match.")
    result_data["truncated"] = True
    result_data["text"] = result_data["matched_text"]  # what pack_results does
    mock_sidecar.set_post("/api/search", {"results": [result_data]})
    result = await search_library("kraken", full_text=True)
    assert 'Full section: get_section("s_abc123")' in result


async def test_search_library_compact_sends_no_context_budget(mock_sidecar):
    """Compact mode prints at most MATCHED_SNIPPET_CHARS per result, so the
    payload is already bounded by n_results. Billing the full sections
    against an 8k budget instead starves the list down to two or three
    results — the server packs whole sections, we print snippets."""
    captured = {}

    def capture_payload(json_data):
        captured.update(json_data)
        return {"results": []}

    mock_sidecar.set_post("/api/search", capture_payload)

    await search_library("anything")
    assert "max_context_chars" in captured
    assert captured["max_context_chars"] is None


async def test_search_library_full_text_sends_the_budget(mock_sidecar):
    captured = {}

    def capture_payload(json_data):
        captured.update(json_data)
        return {"results": []}

    mock_sidecar.set_post("/api/search", capture_payload)

    await search_library("anything", full_text=True)
    assert captured.get("max_context_chars") == 8000


async def test_search_library_max_context_chars_override(mock_sidecar):
    """The budget is a full_text-mode knob: it caps what the server
    assembles for the sections we are about to print in full."""
    captured = {}

    def capture_payload(json_data):
        captured.update(json_data)
        return {"results": []}

    mock_sidecar.set_post("/api/search", capture_payload)

    await search_library("anything", max_context_chars=2000, full_text=True)
    assert captured.get("max_context_chars") == 2000


# ---------------------------------------------------------------------------
# get_section
# ---------------------------------------------------------------------------

async def test_get_section_formats_heading_and_text(mock_sidecar):
    mock_sidecar.set_get("/api/section/s_k", {
        "section_id": "s_k",
        "section_heading": "Monsters > Kraken",
        "text": "Kraken. AC 18, HP 472. A gargantuan monstrosity.",
        "filename": "monsters.pdf",
        "source": "/corpus/monsters.pdf",
        "page_start": 10,
        "page_end": 11,
    })
    result = await get_section("s_k")
    assert "Section: Monsters > Kraken" in result
    assert "monsters.pdf" in result
    assert "Kraken. AC 18, HP 472. A gargantuan monstrosity." in result


async def test_get_section_flags_a_windowed_section(mock_sidecar):
    """A section bigger than the assembly cap comes back as a window, not
    the whole thing — say so, or the model reads a truncated rule as
    complete."""
    mock_sidecar.set_get("/api/section/s_big", {
        "section_id": "s_big",
        "section_heading": "Combat",
        "text": "Combat rules, part one.",
        "filename": "core.pdf",
        "source": "/corpus/core.pdf",
        "page_start": 10,
        "page_end": 14,
        "windowed": True,
    })
    result = await get_section("s_big")
    assert "(partial: this section exceeds the cap; showing its first part)" in result


async def test_get_section_does_not_flag_a_whole_section(mock_sidecar):
    mock_sidecar.set_get("/api/section/s_k", {
        "section_id": "s_k",
        "section_heading": "Monsters > Kraken",
        "text": "Kraken. AC 18, HP 472.",
        "filename": "monsters.pdf",
        "source": "/corpus/monsters.pdf",
        "page_start": 10,
        "page_end": 11,
        "windowed": False,
    })
    result = await get_section("s_k")
    assert "partial:" not in result


async def test_get_section_not_found(http_sidecar):
    import httpx
    seen = {}

    def not_found(request):
        seen["path"] = request.url.path
        seen["source"] = request.headers.get("x-source")
        return httpx.Response(404, json={"detail": "Section not found: nope"})

    http_sidecar["fn"] = not_found
    result = await get_section("nope")
    assert result == "Section not found: nope"
    assert seen == {"path": "/api/section/nope", "source": "mcp"}


async def test_get_section_sidecar_down(http_sidecar):
    http_sidecar["fn"] = _refuse
    result = await get_section("s_k")
    assert "Cannot connect" in result


# ---------------------------------------------------------------------------
# get_pages
# ---------------------------------------------------------------------------

async def test_get_pages_formats_range_and_text(mock_sidecar):
    mock_sidecar.set_get("/api/source/X.pdf/pages?start=3&end=4", {
        "filename": "X.pdf",
        "start": 3,
        "end": 4,
        "text": "Page three text.\n\nPage four text.",
    })
    result = await get_pages("X.pdf", 3, 4)
    assert "Pages 3–4 of X.pdf" in result
    assert "Page three text." in result


async def test_get_pages_sidecar_down(http_sidecar):
    http_sidecar["fn"] = _refuse
    result = await get_pages("X.pdf", 1, 1)
    assert "Cannot connect" in result


async def test_get_pages_url_encodes_special_characters_in_filename(mock_sidecar):
    """A raw '#' in the filename would otherwise be read as a URL fragment
    delimiter (truncating the path, dropping the query) and a raw '?' as
    the start of the query string — both must be percent-encoded."""
    mock_sidecar.set_get(
        "/api/source/Dragon%20Magazine%20%23237.pdf/pages?start=1&end=1",
        {
            "filename": "Dragon Magazine #237.pdf",
            "start": 1,
            "end": 1,
            "text": "Editorial.",
        },
    )
    result = await get_pages("Dragon Magazine #237.pdf", 1, 1)
    assert "Editorial." in result


# ---------------------------------------------------------------------------
# list_collections
# ---------------------------------------------------------------------------

async def test_list_collections_plain_listing(mock_sidecar):
    mock_sidecar.set_get("/api/collections", {
        "collections": {
            "Strahd": {"name": "Strahd", "file_count": 3, "description": ""},
            "Pathfinder": {"name": "Pathfinder", "file_count": 5, "description": "PF2e books"},
        },
        "count": 2,
    })
    result = await list_collections()
    assert "Strahd (3 files)" in result
    assert "Pathfinder (5 files) — PF2e books" in result
    assert "★" not in result


# ---------------------------------------------------------------------------
# list_sources tests
# ---------------------------------------------------------------------------

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


async def test_list_sources_empty(mock_sidecar):
    mock_sidecar.set_get("/api/sources", {"sources": [], "count": 0})

    result = await list_sources()
    assert "No documents indexed" in result


# ---------------------------------------------------------------------------
# list_game_systems tests
# ---------------------------------------------------------------------------

async def test_list_game_systems_shows_systems(mock_sidecar):
    mock_sidecar.set_get("/api/game-systems", {
        "game_systems": ["D&D 5E", "Dragonbane", "unknown"],
        "count": 3,
    })

    result = await list_game_systems()
    assert "3" in result
    assert "D&D 5E" in result
    assert "Dragonbane" in result


async def test_list_game_systems_empty(mock_sidecar):
    mock_sidecar.set_get("/api/game-systems", {
        "game_systems": [],
        "count": 0,
    })

    result = await list_game_systems()
    assert "No game systems detected" in result


# ---------------------------------------------------------------------------
# list_collections tests
# ---------------------------------------------------------------------------

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


async def test_list_collections_empty(mock_sidecar):
    mock_sidecar.set_get("/api/collections", {"collections": {}, "count": 0})

    result = await list_collections()
    assert "No collections" in result


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

async def test_search_library_with_collection(mock_sidecar):
    """collection parameter should be included in the payload."""
    captured = {}

    def capture_payload(json_data):
        captured.update(json_data)
        return {"results": []}

    mock_sidecar.set_post("/api/search", capture_payload)

    await search_library("fire drake", collection="Monsters Only")
    assert captured.get("collection") == "Monsters Only"


async def test_search_library_without_collection(mock_sidecar):
    """Without collection, the payload should not include the key."""
    captured = {}

    def capture_payload(json_data):
        captured.update(json_data)
        return {"results": []}

    mock_sidecar.set_post("/api/search", capture_payload)

    await search_library("fire drake")
    assert "collection" not in captured


def test_registered_tools_are_the_public_surface():
    from mcp_server import mcp
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert names == {
        "search_library", "get_section", "get_pages",
        "list_sources", "list_game_systems", "list_collections",
        # Command's (test_mcp_command.py)
        "campaign_overview", "current_session", "live_set", "read_note",
        "find_notes", "create_note", "edit_note", "create_beat", "add_to_beat",
        "set_active_session", "create_session", "plan_beat", "add_to_live_set", "spend",
        "connect_cards", "frame_cards", "add_text", "arrange_board",
    }

