"""
Legend Lore — MCP server for TTRPG PDF library.

This is a separate process from the FastAPI sidecar. Claude Desktop
launches it via stdio, and it calls the sidecar's HTTP API to fulfill
requests.

Architecture:
    Claude Desktop ←→ mcp_server.py (stdio) ←→ FastAPI sidecar (HTTP) ←→ ChromaDB

Usage:
    python mcp_server.py --data-dir /path/to/app/data
    python mcp_server.py --sidecar-url http://localhost:8420
"""

import argparse
import re
import sys
import threading
import time
from pathlib import Path

import httpx
from mcp.server.mcpserver import MCPServer


PORT_FILENAME = "sidecar.port"
SIDECAR_URL_DISCOVERY_TIMEOUT = 30.0  # seconds; covers a slow sidecar boot

# Per-request timeout for sidecar HTTP calls. httpx defaults to 5s, but a
# warm reranked search takes 5-7s (the cross-encoder is the whole budget),
# so the default silently times out a search the sidecar answers 200 OK.
SIDECAR_REQUEST_TIMEOUT_SECONDS = 60.0


# Tag every sidecar request from this process so the sidecar can track
# MCP-originated activity separately from desktop UI calls.
MCP_HEADERS = {"X-Source": "mcp"}
HEARTBEAT_INTERVAL_SECONDS = 30


_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")

# search_library's compact default prints this much of the matched unit per
# result (roadmap 2.2): enough to judge relevance, small enough that many
# results fit an 8k context budget. get_section fetches the rest on demand.
MATCHED_SNIPPET_CHARS = 600


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
        default=None,
        help="Explicit sidecar URL. Takes precedence over --data-dir.",
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default=None,
        help="App data directory containing sidecar.port (preferred — picks up "
             "the ephemeral port the sidecar binds at launch).",
    )
    return parser.parse_args()


def current_sidecar_url(args) -> str | None:
    """Resolve the sidecar URL right now, with no retry.

    Used per-request so the MCP server follows the sidecar across Legend
    Lore restarts: ephemeral binding gives a different port every launch,
    but ``sidecar.port`` always reflects the current one. Returns ``None``
    when the file is absent (sidecar not running) so callers can show a
    "launch the app" hint.

    Precedence: ``--sidecar-url`` (explicit, frozen) > ``--data-dir``
    (live port file lookup).
    """
    if args.sidecar_url:
        return args.sidecar_url
    if args.data_dir:
        port_file = Path(args.data_dir) / PORT_FILENAME
        try:
            port = int(port_file.read_text().strip())
            return f"http://127.0.0.1:{port}"
        except (FileNotFoundError, ValueError):
            return None
    return None


def discover_sidecar_url(args) -> str:
    """Resolve the sidecar URL at startup, with a grace window for slow boots.

    Used by ``check_sidecar_health`` (one-shot diagnostic at startup).
    Falls back to the legacy default URL when discovery times out so old
    configs without ``--data-dir`` still work in dev.
    """
    url = current_sidecar_url(args)
    if url:
        return url
    if args.data_dir:
        deadline = time.monotonic() + SIDECAR_URL_DISCOVERY_TIMEOUT
        while time.monotonic() < deadline:
            time.sleep(0.5)
            url = current_sidecar_url(args)
            if url:
                return url
        print(
            f"Warning: timed out waiting for sidecar port file in {args.data_dir}. "
            f"Falling back to default URL.",
            file=sys.stderr,
        )
    return "http://localhost:8420"


# ---------------------------------------------------------------------------
# Sidecar HTTP client
# ---------------------------------------------------------------------------

_SIDECAR_DOWN_HINT = (
    "Cannot connect to Legend Lore app. Make sure the desktop app is running."
)

_SIDECAR_TIMEOUT_HINT = (
    "Legend Lore timed out waiting for the app to respond. It may be busy "
    "(a large library or a slow search) — try again, or narrow your query."
)


class SidecarClient:
    """Thin wrapper around httpx for calling the FastAPI sidecar.

    Holds the parsed CLI args and re-resolves the sidecar URL on every
    request. The MCP server outlives any single Legend Lore launch, so a
    cached URL would go stale the moment the user quit and relaunched the
    desktop app (each launch picks a fresh ephemeral port).
    """

    def __init__(self, args):
        self._args = args

    def _resolve(self) -> str | None:
        return current_sidecar_url(self._args)

    async def get(self, path: str) -> dict | str:
        url = self._resolve()
        if url is None:
            return _SIDECAR_DOWN_HINT
        try:
            async with httpx.AsyncClient(
                headers=MCP_HEADERS, timeout=SIDECAR_REQUEST_TIMEOUT_SECONDS
            ) as client:
                resp = await client.get(f"{url}{path}")
                resp.raise_for_status()
                return resp.json()
        except httpx.ConnectError:
            return _SIDECAR_DOWN_HINT
        except httpx.TimeoutException:
            return _SIDECAR_TIMEOUT_HINT
        except httpx.HTTPStatusError as e:
            return f"Sidecar error: {e.response.status_code} — {e.response.text}"

    async def post(self, path: str, json: dict) -> dict | str:
        url = self._resolve()
        if url is None:
            return _SIDECAR_DOWN_HINT
        try:
            async with httpx.AsyncClient(
                headers=MCP_HEADERS, timeout=SIDECAR_REQUEST_TIMEOUT_SECONDS
            ) as client:
                resp = await client.post(f"{url}{path}", json=json)
                resp.raise_for_status()
                return resp.json()
        except httpx.ConnectError:
            return _SIDECAR_DOWN_HINT
        except httpx.TimeoutException:
            return _SIDECAR_TIMEOUT_HINT
        except httpx.HTTPStatusError as e:
            return f"Sidecar error: {e.response.status_code} — {e.response.text}"


# ---------------------------------------------------------------------------
# MCP server setup
# ---------------------------------------------------------------------------

# Sidecar client is set in __main__ once CLI args are parsed. Tool handlers
# capture this global at call time, so it's safe to leave as None during
# import (e.g. when pytest collects the module).
sidecar: SidecarClient | None = None

mcp = MCPServer(
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
        "queries before concluding the content isn't indexed.\n"
        "- search_library's results are compact by default (a short matched "
        "snippet per result) — call get_section() with a result's id to read "
        "its full section, or pass search_library's full_text=True to get "
        "full sections for every result up front.\n"
        "- Use get_pages() to read a specific page range straight from a PDF "
        "(e.g. a table of contents or a map) when search doesn't surface it."
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

    lines = [f"Collections ({data['count']}):\n"]
    for name, c in collections.items():
        desc = f" — {c['description']}" if c.get("description") else ""
        lines.append(f"  - {name} ({c['file_count']} files){desc}")
    return "\n".join(lines)


def _page_span(result: dict) -> str:
    """Cite the page a reader can actually turn to.

    TTRPG PDFs carry covers, front matter and ads, so a book's printed page
    numbers commonly sit 20-40 short of the PDF's own index. When the printed
    label is known it leads, and the physical page follows for PDF viewers.
    Returns "" when the result carries no usable page span.
    """
    start, end = result.get("page_start"), result.get("page_end")
    if not (start and end):
        return ""
    physical = f"p.{start}" if start == end else f"pp.{start}\u2013{end}"
    label_start = result.get("page_label_start") or ""
    label_end = result.get("page_label_end") or ""
    if not (label_start and label_end):
        return physical
    printed = (f"p.{label_start}" if label_start == label_end
               else f"pp.{label_start}\u2013{label_end}")
    return f"{printed} (PDF {physical})"


@mcp.tool()
async def search_library(
    query: str,
    n_results: int = 8,
    source_filter: str | None = None,
    game_system: str | None = None,
    collection: str | None = None,
    max_context_chars: int = 8000,
    full_text: bool = False,
) -> str:
    """Search your TTRPG PDF library for relevant content.

    This should be your FIRST action when the user asks about any rules,
    lore, or game content. Always search before telling the user something
    isn't available.

    Results are compact by default: each shows a short matched snippet plus
    an `id=` you can pass to get_section() to read that result's full
    section. Pass full_text=True to get full sections for every result
    up front instead — useful for a small n_results, costly for a large one.

    Args:
        query: What to search for (e.g., "grappling rules",
               "fire drake stats", "healing potions")
        n_results: How many results to return (default 8)
        source_filter: Optional PDF filename to restrict search
                       to one book (e.g., "dragonbane_core.pdf").
                       Matched case/accent-insensitively; an unambiguous
                       near-miss resolves automatically (noted in the
                       output), otherwise the closest indexed filenames
                       are suggested.
        game_system: Optional game system to filter by
                     (e.g., "D&D 5E", "Dragonbane", "Pathfinder 2E").
                     Matched case/accent-insensitively like
                     source_filter; unknown values return the list of
                     available systems.
        collection: Optional collection name to search within
                    (see list_collections for available collections).
        max_context_chars: Character budget for the sidecar's own section
                           assembly (default 8000).
        full_text: Print each result's full section instead of the
                   compact matched snippet (default False).
    """
    payload = {
        "query": query,
        "n_results": n_results,
        "max_context_chars": max_context_chars,
    }
    if source_filter:
        payload["source_filter"] = source_filter
    if game_system:
        payload["game_system"] = game_system
    if collection:
        payload["collection"] = collection

    data = await sidecar.post("/api/search", payload)
    if isinstance(data, str):
        return data  # Error message

    # The server's `message` explains empty results (bad filter value,
    # empty collection) and carries filter-resolution notes — surface it
    # instead of swallowing it into a generic line (issue #309).
    server_note = data.get("message")

    results = data.get("results", [])
    if not results:
        if server_note:
            return server_note
        return f"No results found for: {query}"

    # Ordinal tiers, not raw scores (issues #306/#310): the underlying
    # numbers come from two different scales (cross-encoder sigmoid vs
    # cosine similarity) and neither is a calibrated probability — printing
    # them invites over-reading. Weak results are still included (recall),
    # but flagged so the model doesn't synthesize an answer from noise.
    all_weak = all(r.get("tier") == "weak" for r in results)

    lines = [f"Found {len(results)} result(s) for \"{query}\":\n"]
    if server_note:
        lines.insert(1, f"[{server_note}]\n")
    if all_weak:
        lines.insert(0, (
            "No strong matches — every result below scored poorly. The "
            "content may not be indexed, or may be outside the current "
            "scope (collection, game_system, or source filters). "
            "Consider retrying without filters.\n"
        ))

    weak_divider_emitted = False
    for i, r in enumerate(results, 1):
        tier = r.get("tier")
        if tier == "weak" and not all_weak and not weak_divider_emitted:
            lines.append(
                "--- Results below this line scored poorly (weak matches; "
                "likely not relevant) ---\n"
            )
            weak_divider_emitted = True
        match_tag = f" (match: {tier})" if tier else ""
        lines.append(f"--- Result {i}{match_tag} ---")
        system_tag = r.get('game_system', 'unknown')
        lines.append(f"Source: {r['filename']} [{system_tag}]")
        heading = _strip_bold(r.get("section_heading") or "") or "(no section)"
        page_span = _page_span(r)
        section_id = r.get("section_id") or ""
        section_line = (f"Section: {heading} ({page_span})" if page_span
                        else f"Section: {heading}")
        lines.append(f"{section_line}  id={section_id}")
        if full_text:
            lines.append(r.get("text", ""))
        else:
            matched = r.get("matched_text") or r.get("text", "")
            if len(matched) > MATCHED_SNIPPET_CHARS:
                matched = matched[:MATCHED_SNIPPET_CHARS] + "…"
            lines.append(matched)
        # Shown whenever what's printed above isn't the whole section: always
        # in compact mode, and in full_text mode too when the server's own
        # budget (max_context_chars) truncated this result down to its
        # matched unit (pack_results swaps `text` for `matched_text` then).
        if section_id and (not full_text or r.get("truncated")):
            lines.append(f'Full section: get_section("{section_id}")')
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
async def get_section(section_id: str) -> str:
    """Fetch the full text of one section from search_library's compact output.

    Use the `id=` value printed under a search_library result to read its
    complete section instead of the short matched snippet.

    Args:
        section_id: The id from a search_library result's Section line.
    """
    data = await sidecar.get(f"/api/section/{section_id}")
    if isinstance(data, str):
        return data  # Error message

    heading = _strip_bold(data.get("section_heading") or "") or "(no section)"
    page_span = _page_span(data)
    lines = [f"Section: {heading}"]
    source_line = f"Source: {data.get('filename', '')}"
    if page_span:
        source_line += f" ({page_span})"
    lines.append(source_line)
    lines.append("")
    lines.append(data.get("text", ""))
    return "\n".join(lines)


@mcp.tool()
async def get_pages(filename: str, start: int, end: int) -> str:
    """Fetch the raw text of a page range directly from an indexed PDF.

    Use this for content search_library doesn't surface well, like a table
    of contents, a map key, or an appendix — a page span of at most 20 pages.

    Args:
        filename: Indexed PDF filename (e.g., "dragonbane_core.pdf").
        start: First page to fetch, 1-based inclusive.
        end: Last page to fetch, 1-based inclusive (at most 20 pages from start).
    """
    data = await sidecar.get(f"/api/source/{filename}/pages?start={start}&end={end}")
    if isinstance(data, str):
        return data  # Error message

    lines = [
        f"Pages {data['start']}–{data['end']} of {data['filename']}",
        "",
        data.get("text", ""),
    ]
    return "\n".join(lines)


@mcp.tool()
async def list_sources() -> str:
    """List all indexed TTRPG sourcebooks in the library.

    Shows every PDF that has been indexed, along with how many
    text chunks each one contains. Use this to see what's available
    before searching.
    """
    data = await sidecar.get("/api/sources")
    if isinstance(data, str):
        return data

    sources = data.get("sources", [])
    if not sources:
        return "No documents indexed yet. Open the Legend Lore app and index some PDFs first."

    lines = [f"Indexed library: {len(sources)} document(s)\n"]
    for s in sources:
        systems = s.get("game_systems") or ([s["game_system"]] if s.get("game_system") else [])
        system_tag = f" [{', '.join(systems)}]" if systems else ""
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


def heartbeat_loop(args) -> None:
    """Tell the sidecar we're alive every HEARTBEAT_INTERVAL_SECONDS so the
    desktop UI can show an "MCP connected" indicator. Re-resolves the URL
    on each tick so heartbeats follow the sidecar across Legend Lore
    restarts. Silently skips when the sidecar is down."""
    while True:
        url = current_sidecar_url(args)
        if url:
            try:
                httpx.post(f"{url}/api/mcp-heartbeat", timeout=2.0)
            except Exception:
                pass
        time.sleep(HEARTBEAT_INTERVAL_SECONDS)


if __name__ == "__main__":
    args = parse_args()
    sidecar = SidecarClient(args)
    check_sidecar_health(discover_sidecar_url(args))
    threading.Thread(
        target=heartbeat_loop,
        args=(args,),
        daemon=True,
    ).start()
    mcp.run(transport="stdio")
