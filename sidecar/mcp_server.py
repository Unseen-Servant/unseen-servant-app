"""
Legend Lore — MCP server for TTRPG PDF library.

This is a separate process from the FastAPI sidecar. Claude Desktop
launches it via stdio, and it calls the sidecar's HTTP API to fulfill
requests.

Architecture:
    Claude Desktop ←→ mcp_server.py (stdio) ←→ FastAPI sidecar (HTTP) ←→ ChromaDB

Usage:
    python mcp_server.py
    python mcp_server.py --sidecar-url http://localhost:8420
"""

import argparse
import re
import sys
import threading
import time

import httpx
from mcp.server.fastmcp import FastMCP


# Tag every sidecar request from this process so the sidecar can track
# MCP-originated activity separately from desktop UI calls.
MCP_HEADERS = {"X-Source": "mcp"}
HEARTBEAT_INTERVAL_SECONDS = 30


_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


def _strip_bold(s: str) -> str:
    """Remove **...** wrapping from breadcrumb text for display.

    pymupdf4llm captures headings as ``## **Goblin**`` so section_heading
    carries bold markup. The embed pipeline keeps it intact (matches the
    spike's measured baseline); display formatters strip it.
    """
    return _BOLD_RE.sub(r"\1", s)

# ---------------------------------------------------------------------------
# CLI arguments
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(description="Legend Lore MCP server")
    parser.add_argument(
        "--sidecar-url",
        type=str,
        default="http://localhost:8420",
        help="URL of the FastAPI sidecar (default: http://localhost:8420)",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Sidecar HTTP client
# ---------------------------------------------------------------------------

class SidecarClient:
    """Thin wrapper around httpx for calling the FastAPI sidecar.

    Why a class? So every tool doesn't repeat the base URL and
    error-handling logic. If the sidecar is down, we return a
    helpful message instead of crashing the MCP server.
    """

    def __init__(self, base_url: str):
        self.base_url = base_url

    async def get(self, path: str) -> dict | str:
        try:
            async with httpx.AsyncClient(headers=MCP_HEADERS) as client:
                resp = await client.get(f"{self.base_url}{path}")
                resp.raise_for_status()
                return resp.json()
        except httpx.ConnectError:
            return f"Cannot connect to Legend Lore app. Make sure the desktop app is running (sidecar at {self.base_url})."
        except httpx.HTTPStatusError as e:
            return f"Sidecar error: {e.response.status_code} — {e.response.text}"

    async def post(self, path: str, json: dict) -> dict | str:
        try:
            async with httpx.AsyncClient(headers=MCP_HEADERS) as client:
                resp = await client.post(f"{self.base_url}{path}", json=json)
                resp.raise_for_status()
                return resp.json()
        except httpx.ConnectError:
            return f"Cannot connect to Legend Lore app. Make sure the desktop app is running (sidecar at {self.base_url})."
        except httpx.HTTPStatusError as e:
            return f"Sidecar error: {e.response.status_code} — {e.response.text}"


# ---------------------------------------------------------------------------
# MCP server setup
# ---------------------------------------------------------------------------

args = parse_args()
sidecar = SidecarClient(args.sidecar_url)

mcp = FastMCP(
    name="Legend Lore",
    instructions=(
        "You have access to the user's indexed TTRPG PDF library via Legend Lore. "
        "Use the search and retrieval tools to find rules, lore, stat blocks, "
        "spells, monsters, and other content from their sourcebooks.\n\n"
        "IMPORTANT GUIDELINES:\n"
        "- At the start of a conversation, call list_game_systems() to see what "
        "game systems are in the library. Do not assume you know what's available "
        "from prior conversations.\n"
        "- NEVER say a game system or sourcebook is unavailable without first "
        "searching for it using search_library() or list_sources().\n"
        "- When the user asks about a specific game system, always search the "
        "library first — even if you haven't seen it mentioned before.\n"
        "- Always cite the source filename when referencing content.\n"
        "- If a search returns no results, try alternative terms or broader "
        "queries before concluding the content isn't indexed."
    ),
)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def list_collections() -> str:
    """List all document collections in the library.

    Collections are curated subsets of indexed PDFs, organized
    by the user for specific campaigns, sessions, or topics.
    Use a collection name with search_library's collection parameter
    to search only within that subset.
    """
    data = await sidecar.get("/api/collections")
    if isinstance(data, str):
        return data

    collections = data.get("collections", {})
    if not collections:
        return "No collections defined yet. Create one in the Legend Lore desktop app."

    active = data.get("active_context")
    lines = [f"Collections ({data['count']}):\n"]
    for name, c in collections.items():
        desc = f" — {c['description']}" if c.get("description") else ""
        marker = "  ★ " if name == active else "  - "
        lines.append(f"{marker}{name} ({c['file_count']} files){desc}")
    if active:
        lines.append(f"\nActive context: {active} (★)")
    return "\n".join(lines)


@mcp.tool()
async def get_active_context() -> str:
    """Show the currently active collection scope, if any.

    The active context auto-scopes search_library and list_sources to
    a single collection. The user sets this in the Legend Lore desktop
    app for session prep or live play.
    """
    data = await sidecar.get("/api/active-context")
    if isinstance(data, str):
        return data
    active = data.get("active_context")
    if not active:
        return "No active context set. Searches cover the whole library."
    return f"Active context: {active}"


@mcp.tool()
async def search_library(
    query: str,
    n_results: int = 5,
    source_filter: str | None = None,
    game_system: str | None = None,
    collection: str | None = None,
    search_all: bool = False,
) -> str:
    """Search your TTRPG PDF library for relevant content.

    This should be your FIRST action when the user asks about any rules,
    lore, or game content. Always search before telling the user something
    isn't available.

    If the user has set an active context in the desktop app, this tool
    auto-scopes to that collection unless `collection` is passed explicitly
    or `search_all=True`.

    Args:
        query: What to search for (e.g., "grappling rules",
               "fire drake stats", "healing potions")
        n_results: How many results to return (default 5)
        source_filter: Optional PDF filename to restrict search
                       to one book (e.g., "dragonbane_core.pdf")
        game_system: Optional game system to filter by
                     (e.g., "D&D 5E", "Dragonbane", "Pathfinder 2E")
        collection: Optional collection name to search within
                    (see list_collections for available collections).
                    Overrides any active context.
        search_all: Set to True to bypass the active context and
                    search the entire library.
    """
    payload = {"query": query, "n_results": n_results, "search_all": search_all}
    if source_filter:
        payload["source_filter"] = source_filter
    if game_system:
        payload["game_system"] = game_system
    if collection:
        payload["collection"] = collection

    data = await sidecar.post("/api/search", payload)
    if isinstance(data, str):
        return data  # Error message

    notice = ""
    if data.get("auto_scoped") and data.get("effective_collection"):
        notice = f"[Active context: {data['effective_collection']}]\n\n"

    results = data.get("results", [])
    if not results:
        return f"{notice}No results found for: {query}"

    lines = [f"{notice}Found {len(results)} result(s) for \"{query}\":\n"]
    for i, r in enumerate(results, 1):
        lines.append(f"--- Result {i} (relevance: {r['relevance']}) ---")
        system_tag = r.get('game_system', 'unknown')
        lines.append(f"Source: {r['filename']} [{system_tag}]")
        heading = _strip_bold(r.get("section_heading") or "") or "(no section)"
        page_start = r.get("page_start")
        page_end = r.get("page_end")
        if page_start and page_end:
            page_span = f"p.{page_start}" if page_start == page_end else f"pp.{page_start}–{page_end}"
            lines.append(f"Section: {heading} ({page_span})")
        else:
            lines.append(f"Section: {heading}")
        lines.append(r["text"])
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
async def read_document(filename: str) -> str:
    """Read the full text content of an indexed sourcebook.

    Use this when you need to read or summarize an entire document,
    or when search isn't finding what you need and you want to
    browse the full text.

    Args:
        filename: The PDF filename to read
                  (e.g., "dragonbane_monsters.pdf")
    """
    data = await sidecar.get(f"/api/source/{filename}/content")
    if isinstance(data, str):
        return data

    return (
        f"=== {data['filename']} ({data['chunks']} chunks) ===\n\n"
        f"{data['content']}"
    )


@mcp.tool()
async def list_sources(show_all: bool = False) -> str:
    """List all indexed TTRPG sourcebooks in the library.

    Shows every PDF that has been indexed, along with how many
    text chunks each one contains. Use this to see what's available
    before searching.

    If the user has set an active context, output is scoped to that
    collection's files unless `show_all=True`.

    Args:
        show_all: Set to True to bypass the active context and
                  list every indexed source.
    """
    data = await sidecar.get("/api/sources")
    if isinstance(data, str):
        return data

    sources = data.get("sources", [])
    if not sources:
        return "No documents indexed yet. Open the Legend Lore app and index some PDFs first."

    notice = ""
    if not show_all:
        cdata = await sidecar.get("/api/collections")
        if isinstance(cdata, dict):
            active = cdata.get("active_context")
            if active and active in cdata.get("collections", {}):
                allowed_paths = set(cdata["collections"][active].get("file_paths", []))
                sources = [s for s in sources if s.get("source") in allowed_paths]
                notice = f"[Active context: {active}]\n\n"

    if not sources:
        return f"{notice}No sources match the active context."

    lines = [f"{notice}Indexed library: {len(sources)} document(s)\n"]
    for s in sources:
        system_tag = f" [{s['game_system']}]" if s.get('game_system') else ""
        lines.append(f"  - {s['filename']} ({s['chunks']} chunks){system_tag}")

    return "\n".join(lines)


@mcp.tool()
async def list_game_systems() -> str:
    """List all game systems detected in your indexed library.

    Call this at the start of each conversation to see what's available.
    Do not rely on memory from prior conversations — the library may
    have changed. Use the returned values for filtering with
    search_library's game_system parameter.
    """
    data = await sidecar.get("/api/game-systems")
    if isinstance(data, str):
        return data

    systems = data.get("game_systems", [])
    if not systems:
        return "No game systems detected yet. Index some PDFs first."

    lines = [f"Game systems in library ({data['count']}):\n"]
    for s in systems:
        lines.append(f"  - {s}")
    return "\n".join(lines)


@mcp.tool()
async def compare_sources(
    query: str,
    filenames: list[str],
    n_results: int = 3,
) -> str:
    """Compare how different sourcebooks cover the same topic.

    Searches for the same query in each specified book and returns
    results side by side. Great for comparing rules across game
    systems or checking different supplements.

    Args:
        query: What to compare (e.g., "grappling rules",
               "character creation")
        filenames: List of PDF filenames to compare
                   (e.g., ["dragonbane_core.pdf", "dnd_5e_phb.pdf"])
        n_results: Results per book (default 3)
    """
    if len(filenames) < 2:
        return "Please provide at least 2 filenames to compare."

    sections = []
    for fname in filenames:
        payload = {
            "query": query,
            "n_results": n_results,
            "source_filter": fname,
        }
        data = await sidecar.post("/api/search", payload)
        if isinstance(data, str):
            sections.append(f"=== {fname} ===\n{data}\n")
            continue

        results = data.get("results", [])
        if not results:
            sections.append(f"=== {fname} ===\nNo results found.\n")
            continue

        lines = [f"=== {fname} ==="]
        for r in results:
            lines.append(f"[relevance: {r['relevance']}]")
            lines.append(r["text"])
            lines.append("")
        sections.append("\n".join(lines))

    header = f"Comparing \"{query}\" across {len(filenames)} sources:\n\n"
    return header + "\n".join(sections)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def check_sidecar_health(url: str) -> None:
    """Log whether the FastAPI sidecar is reachable. Non-blocking — the
    MCP server starts regardless, since the sidecar may launch later."""
    try:
        resp = httpx.get(f"{url}/health", timeout=2.0)
        resp.raise_for_status()
        print(f"Sidecar is running at {url}", file=sys.stderr)
    except (httpx.ConnectError, httpx.TimeoutException):
        print(
            f"Warning: Sidecar not reachable at {url}. "
            f"Make sure the Legend Lore app is running.",
            file=sys.stderr,
        )


def heartbeat_loop(url: str) -> None:
    """Tell the sidecar we're alive every HEARTBEAT_INTERVAL_SECONDS so the
    desktop UI can show an "MCP connected" indicator. Failures are silently
    ignored — the sidecar may be unreachable temporarily."""
    while True:
        try:
            httpx.post(f"{url}/api/mcp-heartbeat", timeout=2.0)
        except Exception:
            pass
        time.sleep(HEARTBEAT_INTERVAL_SECONDS)


if __name__ == "__main__":
    check_sidecar_health(args.sidecar_url)
    threading.Thread(
        target=heartbeat_loop,
        args=(args.sidecar_url,),
        daemon=True,
    ).start()
    mcp.run(transport="stdio")
