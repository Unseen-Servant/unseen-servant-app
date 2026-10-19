"""
Unseen Servant — MCP server for Legend Lore (the TTRPG PDF library) and
Command (the GM's campaign notes).

This is a separate process from the FastAPI sidecar. Claude Desktop
launches it via stdio, and it calls the sidecar's HTTP API to fulfill
requests.

Architecture:
    Claude Desktop ←→ mcp_server.py (stdio) ←→ FastAPI sidecar (HTTP) ←→ library store (SQLite)

Usage:
    python mcp_server.py --data-dir /path/to/app/data
    python mcp_server.py --sidecar-url http://localhost:8420
"""

import argparse
import asyncio
import re
import sys
import threading
import time
from pathlib import Path
from urllib.parse import quote

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
    parser = argparse.ArgumentParser(description="Unseen Servant MCP server")
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
    "Cannot connect to Unseen Servant. Make sure the desktop app is running."
)

_SIDECAR_TIMEOUT_HINT = (
    "Timed out waiting for Unseen Servant to respond. It may be busy "
    "(a large library or a slow search) — try again, or narrow your query."
)


def _refusal(response: httpx.Response) -> str:
    """Why the sidecar refused a request: its ``detail`` when that's a
    sentence (every Command refusal is), else the status and the body."""
    try:
        detail = response.json().get("detail")
    except (ValueError, AttributeError):
        detail = None
    if isinstance(detail, str) and detail:
        return detail
    return f"Sidecar error: {response.status_code} — {response.text}"


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
            return _refusal(e.response)

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
            return _refusal(e.response)

    async def put(self, path: str, json: dict) -> dict | str:
        url = self._resolve()
        if url is None:
            return _SIDECAR_DOWN_HINT
        try:
            async with httpx.AsyncClient(
                headers=MCP_HEADERS, timeout=SIDECAR_REQUEST_TIMEOUT_SECONDS
            ) as client:
                resp = await client.put(f"{url}{path}", json=json)
                resp.raise_for_status()
                return resp.json()
        except httpx.ConnectError:
            return _SIDECAR_DOWN_HINT
        except httpx.TimeoutException:
            return _SIDECAR_TIMEOUT_HINT
        except httpx.HTTPStatusError as e:
            return _refusal(e.response)


# ---------------------------------------------------------------------------
# MCP server setup
# ---------------------------------------------------------------------------

# Sidecar client is set in __main__ once CLI args are parsed. Tool handlers
# capture this global at call time, so it's safe to leave as None during
# import (e.g. when pytest collects the module).
sidecar: SidecarClient | None = None

mcp = MCPServer(
    name="Unseen Servant",
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
        "(e.g. a table of contents or a map) when search doesn't surface it.\n\n"
        "You also have the GM's campaign notes via Command: Markdown notes in "
        "tracks (NPCs, Locations, Secrets, …), a shelf of gathered material not "
        "filed on a track yet, beats (scenes, each a set of notes) and sessions "
        "(a plan of beats). Tools act on the campaign open in the app unless "
        "you pass campaign=.\n"
        "- Start with campaign_overview(): the campaigns, then the open one's "
        "tracks, notes, beats and sessions by name.\n"
        "- Call current_session() to see what's planned, and live_set() for "
        "what's in play at the table right now.\n"
        "- Read notes with read_note() and find them with find_notes() before "
        "describing them — never invent what a note says.\n"
        "- create_note() writes new material into a track, or onto the shelf "
        "when it isn't clear where it belongs, and edit_note() corrects a "
        "note's text with the hash read_note() shows.\n"
        "- To prep a session: create_session() starts the next one and opens "
        "it in the app, or set_active_session() opens one that exists. Then "
        "create_beat(session=) makes each scene from notes already written, "
        "one at a time in play order, since a plan takes beats as the calls "
        "arrive. add_to_beat() and plan_beat() fix a beat or the plan.\n"
        "- Renaming and deleting are the GM's: say what should change.\n"
        "- add_to_live_set() and spend() follow the table during play."
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
        return "No collections defined yet. Create one in Legend Lore, in Unseen Servant."

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
                           assembly (default 8000). Applies to full_text
                           mode only — compact results are already bounded
                           by their snippet length.
        full_text: Print each result's full section instead of the
                   compact matched snippet (default False).
    """
    payload = {
        "query": query,
        "n_results": n_results,
        # Compact mode prints at most MATCHED_SNIPPET_CHARS per result, so
        # the payload is bounded by n_results already. Sending a budget
        # anyway makes the server bill whole sections against it and drop
        # results we were never going to print in full — asking for eight
        # and receiving two. The budget belongs to full_text mode, where
        # the sections really are what gets printed.
        "max_context_chars": max_context_chars if full_text else None,
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

    # The divider opens the trailing run of weak results: the system-boost
    # partition and the straggler scoring can leave a strong result after
    # a weak one, and it must not sit below a "scored poorly" line.
    weak_tail = len(results)
    while weak_tail > 0 and results[weak_tail - 1].get("tier") == "weak":
        weak_tail -= 1
    for i, r in enumerate(results, 1):
        tier = r.get("tier")
        if i == weak_tail + 1 and not all_weak:
            lines.append(
                "--- Results below this line scored poorly (weak matches; "
                "likely not relevant) ---\n"
            )
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
        if full_text or not section_id:
            # No section_id means a legacy row with nothing to drill into:
            # a snippet would strand the rest of the text unreachable.
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
    data = await sidecar.get(f"/api/section/{quote(section_id, safe='')}")
    if isinstance(data, str):
        return data  # Error message

    heading = _strip_bold(data.get("section_heading") or "") or "(no section)"
    page_span = _page_span(data)
    lines = [f"Section: {heading}"]
    if data.get("windowed"):
        # The store returned a window grown around the match, not the whole
        # subtree — say so, or a truncated rule reads as a complete one.
        lines.append(
            "(partial: this section exceeds the cap; showing its first part)"
        )
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
        end: Last page to fetch, 1-based inclusive (the span is at most 20 pages).
    """
    data = await sidecar.get(
        f"/api/source/{quote(filename, safe='')}/pages?start={start}&end={end}"
    )
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
        return "No documents indexed yet. Open Unseen Servant and index some PDFs in Legend Lore first."

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
# Command (docs/roadmap/2026-10-11-command-design.md §8)
# ---------------------------------------------------------------------------

_NO_CAMPAIGN = (
    "No campaign is open in Command. Open one in the app, or pass campaign= "
    "(campaign_overview() lists them)."
)


def _q(**params: str | None) -> str:
    return "&".join(f"{k}={quote(v, safe='')}" for k, v in params.items() if v is not None)


async def _context() -> dict:
    """The campaign and session open in the app; empty when it can't say."""
    ctx = await sidecar.get("/api/command/context")
    return ctx if isinstance(ctx, dict) else {}


async def _campaign_index(campaign: str | None) -> tuple[dict | None, dict, str | None]:
    """The campaign to act on — ``campaign``, else the one open in the app —
    its index, and the app's context; or the message saying why not."""
    reply = await sidecar.get("/api/command/context")
    if isinstance(reply, str) and not campaign:
        return None, {}, reply  # the app isn't answering: say that, not "nothing open"
    ctx = reply if isinstance(reply, dict) else {}
    name = campaign or ctx.get("campaign")
    if not name:
        return None, ctx, _NO_CAMPAIGN
    index = await sidecar.get(f"/api/command/campaign?{_q(name=name)}")
    if isinstance(index, str):
        return None, ctx, index
    return index, ctx, None


def _kind(note: dict) -> str:
    """What a note is, by its first folder: a beat, a session, or a note."""
    return {"beats": "beat", "sessions": "session"}.get((note["track"] or "").casefold(), "note")


def _note(index: dict, name: str, kind: str | None = None) -> tuple[dict | None, str | None]:
    """The note ``name`` means: a name, or a path ending in it
    (``NPCs/Ismark``), as a wikilink resolves it, and of one ``kind`` when
    given, since a beat may share a note's name; or the message saying why
    not."""
    wanted = name.strip().removesuffix(".md").casefold()
    parts = [p for p in wanted.split("/") if p]
    pool = [n for n in index["notes"] if kind is None or _kind(n) == kind]
    exact = [n for n in pool if n["path"].removesuffix(".md").casefold() == wanted]
    hits = exact or [n for n in pool if n["path"].removesuffix(".md").casefold().split("/")[-len(parts):] == parts]
    if len(hits) == 1:
        return hits[0], None
    if not hits and kind == "beat":
        return None, f'No beat named "{name}" in {index["name"]}. campaign_overview() lists the beats.'
    if not hits:
        return None, f'No note named "{name}" in {index["name"]}. Try find_notes("{name}").'
    paths = ", ".join(n["path"] for n in hits)
    return None, f'"{name}" names more than one note in {index["name"]} ({paths}) — pass the path.'


def _session(index: dict, ctx: dict) -> dict | None:
    """The session open in the app if it's this campaign's, else the latest."""
    sessions = index["sessions"]
    if ctx.get("campaign") == index["name"]:
        open_one = next((s for s in sessions if s["name"] == ctx.get("session")), None)
        if open_one:
            return open_one
    return sessions[-1] if sessions else None


def _session_named(index: dict, name: str) -> tuple[dict | None, str | None]:
    """The session ``name`` means, by name or path; or the message saying
    why not."""
    wanted = name.strip().removesuffix(".md").casefold()
    for s in index["sessions"]:
        if wanted in (s["name"].casefold(), s["path"].removesuffix(".md").casefold()):
            return s, None
    known = ", ".join(s["name"] for s in index["sessions"]) or "none yet"
    return None, f'{index["name"]} has no session named "{name}". Its sessions: {known}.'


def _taken(index: dict, name: str, kind: str) -> str | None:
    """The message for a name another of ``kind`` has: a beat may share a
    note's name, never another beat's. A retried create meets what it made."""
    clash = next((
        n for n in index["notes"] if _kind(n) == kind and n["name"].casefold() == name.strip().casefold()
    ), None)
    if clash is None:
        return None
    return (
        f'A {kind} named "{clash["name"]}" already exists ({clash["path"]}). If you just made it, '
        f'it\'s there: read_note("{clash["path"]}"). Otherwise pick another name.'
    )


def _label(index: dict, ref: dict) -> str:
    """A beat's note as a plan line names it: name and track, or missing."""
    note = next((n for n in index["notes"] if n["path"] == ref.get("path")), None)
    if note is None:
        return f"{ref['link']} (not written yet)"
    spent = ", spent" if note.get("spent") else ""
    return f"{note['name']} ({note['track'] or 'loose'}{spent})"


def _in_folder_order(index: dict, notes: list[dict], track: str) -> list[dict]:
    """A track's notes as its Prep column lists them: those directly in it,
    then each subfolder's, every folder in the GM's order, then by name."""
    def key(n: dict):
        folder = f"{track}/{n['group']}" if n["group"] else track
        saved = [s.casefold() for s in index["note_order"].get(folder, [])]
        name = n["name"].casefold()
        rank = saved.index(name) if name in saved else len(saved)
        return (n["group"] is not None, (n["group"] or "").casefold(), rank, name)
    return sorted(notes, key=key)


def _names(notes: list[dict]) -> str:
    return ", ".join(n["name"] + (" (spent)" if n.get("spent") else "") for n in notes) or "(empty)"


@mcp.tool()
async def campaign_overview(campaign: str | None = None) -> str:
    """Start here. The campaigns in Command, the GM's campaign notes, with
    the one open in the app marked (the one the other Command tools act on);
    then that campaign's shape: its tracks with their notes, the shelf,
    beats with their notes, and sessions. Names only: read_note() reads one.

    Args:
        campaign: A campaign name; defaults to the one open in the app.
    """
    data = await sidecar.get("/api/command/campaigns")
    if isinstance(data, str):
        return data
    campaigns = data.get("campaigns", [])
    if not campaigns:
        return "No campaigns yet. Create one in Command."
    ctx = await _context()
    lines = ["Campaigns:"]
    for name in campaigns:
        mark = ""
        if name == ctx.get("campaign"):
            mark = f" (open, session: {ctx['session']})" if ctx.get("session") else " (open)"
        lines.append(f"  - {name}{mark}")
    name = campaign or ctx.get("campaign")
    if not name:
        return "\n".join(lines + ["", "None is open in the app: pass campaign= to see one."])
    index = await sidecar.get(f"/api/command/campaign?{_q(name=name)}")
    if isinstance(index, str):
        return "\n".join(lines + ["", index])

    notes = index["notes"]
    lines += ["", f"Tracks in {index['name']}:"]
    for track in index["tracks"]:
        mine = _in_folder_order(index, [n for n in notes if n["track"] == track], track)
        lines.append(f"  {track}: {_names(mine)}")
    shelf = [n for n in notes if (n["track"] or "").casefold() == "shelf"]
    if shelf:
        shelf = _in_folder_order(index, shelf, shelf[0]["track"])  # the folder as it is on disk
    lines += ["", f"Shelf: {_names(shelf)}"]
    loose = sorted((n for n in notes if n["track"] is None), key=lambda n: n["name"].casefold())
    if loose:
        lines.append(f"Loose, outside any track: {_names(loose)}")

    planning: dict[str, list[str]] = {}
    for s in index["sessions"]:
        for ref in s["beats"]:
            if ref.get("path"):
                planning.setdefault(ref["path"], []).append(s["name"])
    names = {n["path"]: n["name"] for n in notes}
    lines += ["", "Beats:"]
    if not index["beats"]:
        lines.append("  (none yet)")
    for b in index["beats"]:
        held = ", ".join(
            names[r["path"]] if r.get("path") else f"{r['link']} (not written yet)" for r in b["notes"]
        ) or "(no notes)"
        spent = " (spent)" if b.get("spent") else ""
        planned = f" — planned in {', '.join(planning[b['path']])}" if b["path"] in planning else ""
        lines.append(f"  {b['name']}{spent}: {held}{planned}")

    lines += ["", "Sessions:"]
    if not index["sessions"]:
        lines.append("  (none yet)")
    for s in index["sessions"]:
        when = f" ({s['date']})" if s.get("date") else ""
        missing = sum(1 for r in s["beats"] if not r.get("path"))
        count = f"{len(s['beats'])} beat(s) planned" if s["beats"] else "nothing planned"
        lines.append(f"  {s['name']}{when}: {count}" + (f", {missing} not written yet" if missing else ""))

    if index["ambiguous"]:
        lines += ["", "Names more than one note answers to (pass the path):"]
        shared: dict[tuple[str, str], list[dict]] = {}
        for n in notes:
            if n["path"] in index["ambiguous"]:
                shared.setdefault((_kind(n), n["name"].casefold()), []).append(n)
        for hits in shared.values():
            lines.append(f"  {hits[0]['name']}: {', '.join(n['path'] for n in hits)}")
    return "\n".join(lines)


@mcp.tool()
async def current_session(campaign: str | None = None, session: str | None = None) -> str:
    """The session at the table, or any other: its plan of beats (scenes)
    with the notes each holds, and what's live.

    Args:
        campaign: A campaign name; defaults to the one open in the app.
        session: A session's name ("Session 3"); defaults to the one open
                 in the app, else the latest.
    """
    index, ctx, error = await _campaign_index(campaign)
    if error:
        return error
    if session:
        session, error = _session_named(index, session)
        if error:
            return error
    else:
        session = _session(index, ctx)
    if session is None:
        return f"{index['name']} has no session yet. create_session() starts one."
    live = await sidecar.get(f"/api/command/live?{_q(campaign=index['name'])}")
    live = live if isinstance(live, dict) else {}
    beats = {b["path"]: b for b in index["beats"]}

    when = f" ({session['date']})" if session.get("date") else ""
    lines = [f"{session['name']}{when} — {index['name']}", "", "Plan:"]
    if not session["beats"]:
        lines.append("  (nothing planned)")
    for i, ref in enumerate(session["beats"], 1):
        beat = beats.get(ref.get("path"))
        if beat is None:
            lines.append(f"  {i}. {ref['link']} — not written yet")
            continue
        marks = [f"spent {beat['spent']}"] if beat.get("spent") else []
        if beat["path"] == live.get("beat"):
            marks.append("live")
        lines.append(f"  {i}. {beat['name']}" + (f" — {', '.join(marks)}" if marks else ""))
        if beat["notes"]:
            lines.append("     " + ", ".join(_label(index, r) for r in beat["notes"]))

    playing = live.get("notes") or []
    lines.append("")
    if playing:
        source = beats.get(live.get("beat"))
        origin = f" from {source['name']}" if source else ""
        lines.append(f"Live{origin}: {len(playing)} note(s) — live_set() has their text.")
    else:
        lines.append("Nothing is live.")
    return "\n".join(lines)


@mcp.tool()
async def live_set(campaign: str | None = None) -> str:
    """The notes in play at the table right now, each with its full text.

    Args:
        campaign: A campaign name; defaults to the one open in the app.
    """
    index, _ctx, error = await _campaign_index(campaign)
    if error:
        return error
    live = await sidecar.get(f"/api/command/live?{_q(campaign=index['name'])}")
    if isinstance(live, str):
        return live
    if not live.get("notes"):
        return f"Nothing is live in {index['name']}."
    beat = next((b for b in index["beats"] if b["path"] == live.get("beat")), None)
    lines = [f"Live in {index['name']}" + (f", launched from {beat['name']}" if beat else "") + ":"]
    for path in live["notes"]:
        note = await sidecar.get(f"/api/command/note?{_q(campaign=index['name'], path=path)}")
        if isinstance(note, str):
            lines += ["", f"## {path}", "(can't be read right now)"]
            continue
        lines += ["", f"## {note['name']} ({path})", note["content"].strip()]
    return "\n".join(lines)


@mcp.tool()
async def read_note(name: str, campaign: str | None = None) -> str:
    """Read one of the GM's notes in full: an NPC, a location, a beat, a
    session — anything in the campaign. Its hash is what edit_note() needs.

    Args:
        name: The note's name ("Ismark"), or its path ("NPCs/Ismark") when
              the name is shared.
        campaign: A campaign name; defaults to the one open in the app.
    """
    index, _ctx, error = await _campaign_index(campaign)
    if error:
        return error
    entry, error = _note(index, name)
    if error:
        return error
    note = await sidecar.get(f"/api/command/note?{_q(campaign=index['name'], path=entry['path'])}")
    if isinstance(note, str):
        return note
    return f"{note['name']} ({note['path']})\nhash: {note['hash']}\n\n{note['content']}"


@mcp.tool()
async def edit_note(name: str, content: str, hash: str, campaign: str | None = None) -> str:
    """Replace the text of one of the GM's notes, any note: fill a stub, fix
    a line. The note's frontmatter stays as it is, so content is the text
    below it, or the whole note as read_note() showed it with the
    frontmatter unchanged. Keys keep their own writers: spend() marks a note
    spent, add_to_beat() changes a beat's notes, plan_beat() a session's
    plan, and the rest are the GM's, in the app.

    Args:
        name: The note's name, or its path when the name is shared.
        content: Its whole new Markdown text. Link other notes as [[Name]].
        hash: The hash read_note() showed, or the last edit_note() replied
              with, so an edit never overwrites a change made since.
        campaign: A campaign name; defaults to the one open in the app.
    """
    index, _ctx, error = await _campaign_index(campaign)
    if error:
        return error
    entry, error = _note(index, name)
    if error:
        return error
    where = _q(campaign=index["name"], path=entry["path"])
    note = await sidecar.get(f"/api/command/note?{where}")
    if isinstance(note, str):
        return note
    if note["hash"] != hash.strip():
        return f'{entry["name"]} changed since you read it. read_note("{entry["path"]}") again.'
    saved = await sidecar.put("/api/command/note", {
        "campaign": index["name"], "path": entry["path"], "content": content,
        "base_hash": note["hash"], "keep_frontmatter": True,
    })
    if isinstance(saved, str):
        return saved
    return f"Saved {entry['path']} in {index['name']}.\nhash: {saved['hash']}"


@mcp.tool()
async def find_notes(query: str, campaign: str | None = None, track: str | None = None) -> str:
    """Find the GM's notes whose name or text mentions something.

    Args:
        query: Words to look for, matched case-insensitively.
        campaign: A campaign name; defaults to the one open in the app.
        track: Only notes in this track (e.g. "NPCs").
    """
    index, _ctx, error = await _campaign_index(campaign)
    if error:
        return error
    data = await sidecar.get(f"/api/command/find?{_q(campaign=index['name'], query=query, track=track)}")
    if isinstance(data, str):
        return data
    notes = data.get("notes", [])
    if not notes:
        return f'No note in {index["name"]} mentions "{query}".'
    lines = [f'Notes in {index["name"]} mentioning "{query}":']
    for n in notes:
        snippet = f" — {n['snippet']}" if n.get("snippet") else ""
        lines.append(f"  - {n['name']} ({n['path']}){snippet}")
    return "\n".join(lines)


@mcp.tool()
async def create_note(track: str, name: str, content: str = "", campaign: str | None = None) -> str:
    """Write a new note into one of the campaign's tracks, or onto its shelf.

    Args:
        track: The track (folder) it belongs to, e.g. "NPCs" or "Secrets";
               "Shelf" for material not filed on a track yet.
        name: The note's name, which links reach it by; no other note's
              (a beat's may be the same).
        content: Its Markdown text. Link other notes as [[Name]].
        campaign: A campaign name; defaults to the one open in the app.
    """
    index, _ctx, error = await _campaign_index(campaign)
    if error:
        return error
    if track not in index["tracks"] and track.casefold() != "shelf":
        return (
            f'{index["name"]} has no track named "{track}". '
            f'Its tracks: {", ".join(index["tracks"])}, or "Shelf".'
        )
    if taken := _taken(index, name, "note"):
        return taken
    made = await sidecar.post("/api/command/notes", {
        "campaign": index["name"], "folder": track, "name": name, "content": content,
    })
    if isinstance(made, str):
        return made
    return f"Created {made['path']} in {index['name']}."


@mcp.tool()
async def create_beat(
    name: str,
    notes: list[str] | None = None,
    content: str = "",
    session: str | None = None,
    campaign: str | None = None,
) -> str:
    """Make a beat: a scene, holding the notes it needs, with the scene
    itself in its text. Write the notes first; a beat holds only notes that
    exist. Given a session, the beat joins the end of its plan, so make a
    session's beats one at a time, in play order; plan_beat() reorders.

    Args:
        name: The beat's name; no other beat's, though it may be a note's,
              as a scene named after its place.
        notes: The notes it holds, by name, or by path when a name is shared.
        content: The scene in Markdown: what happens, what the players
                 face. Link notes as [[Name]].
        session: A session to add it to the end of ("Session 4").
        campaign: A campaign name; defaults to the one open in the app.
    """
    index, _ctx, error = await _campaign_index(campaign)
    if error:
        return error
    if taken := _taken(index, name, "beat"):
        return taken
    members = []
    for n in notes or []:
        entry, error = _note(index, n, "note")
        if error:
            return error
        members.append(entry)
    planned = None
    if session:
        # Resolved first: the route makes the beat before it plans it.
        planned, error = _session_named(index, session)
        if error:
            return error
    made = await sidecar.post("/api/command/beats", {
        "campaign": index["name"], "name": name, "notes": [m["path"] for m in members],
        "content": content, "session": planned["path"] if planned else None,
    })
    if isinstance(made, str):
        return made
    held = ", ".join(m["name"] for m in members) or "no notes yet"
    reply = f"Created {made['path']} in {index['name']}, holding {held}."
    if planned:
        reply += f" It's beat {len(planned['beats']) + 1} of {planned['name']}'s plan."
    return reply


@mcp.tool()
async def add_to_beat(name: str, beat: str, member: bool = True, campaign: str | None = None) -> str:
    """Put a note in a beat, or take it out.

    Args:
        name: The note's name, or its path when the name is shared.
        beat: The beat's name.
        member: False to take the note out of the beat.
        campaign: A campaign name; defaults to the one open in the app.
    """
    index, _ctx, error = await _campaign_index(campaign)
    if error:
        return error
    entry, error = _note(index, name, "note")
    if error:
        return error
    scene, error = _note(index, beat, "beat")
    if error:
        return error
    data = await sidecar.post("/api/command/beats/members", {
        "campaign": index["name"], "beat": scene["path"], "note": entry["path"], "member": member,
    })
    if isinstance(data, str):
        return data
    where = "in" if member else "out of"
    return f"{entry['name']} is {where} {scene['name']}, which holds {', '.join(data['notes']) or 'no notes'}."


# How long set_active_session waits for the app to report the switch.
OPEN_SESSION_WAIT_SECONDS = 3.0


async def _open_in_app(campaign: str, path: str, name: str) -> str:
    """Ask the app to open a session, and wait until its context says so, so
    the reply is true. The open campaign's sessions only."""
    ctx = await _context()
    if ctx.get("campaign") != campaign:
        return f"The app has {ctx.get('campaign') or 'no campaign'} open, not {campaign}, so {name} isn't open there."
    if ctx.get("session") == name:
        return f"{name} is open in the app."
    asked = await sidecar.post("/api/command/context/session", {"campaign": campaign, "session": path})
    if isinstance(asked, str):
        return asked
    if not asked["sent"]:
        return f"The app isn't listening, so {name} isn't open there."
    deadline = time.monotonic() + OPEN_SESSION_WAIT_SECONDS
    while time.monotonic() < deadline:
        await asyncio.sleep(0.1)
        if (await _context()).get("session") == name:
            return f"{name} is open in the app."
    return f"Asked the app to open {name}, but it hasn't said it has."


@mcp.tool()
async def set_active_session(session: str) -> str:
    """Open a session in the app, as the GM picking it there would, so the
    session tools (and the GM) are on it. Sessions of the campaign open in
    the app only.

    Args:
        session: The session's name ("Session 4").
    """
    index, _ctx, error = await _campaign_index(None)
    if error:
        return error
    entry, error = _session_named(index, session)
    if error:
        return error
    return await _open_in_app(index["name"], entry["path"], entry["name"])


@mcp.tool()
async def create_session(campaign: str | None = None) -> str:
    """Start the next session, Session N, dated today with nothing planned,
    and open it in the app, as its New session does. Each call makes
    another, so check campaign_overview() for one not played yet first.

    Args:
        campaign: A campaign name; defaults to the one open in the app.
    """
    index, _ctx, error = await _campaign_index(campaign)
    if error:
        return error
    made = await sidecar.post("/api/command/sessions", {"campaign": index["name"]})
    if isinstance(made, str):
        return made
    opened = await _open_in_app(index["name"], made["path"], made["name"])
    return f"Created {made['name']} ({made['path']}) in {index['name']}, with nothing planned. {opened}"


@mcp.tool()
async def plan_beat(
    name: str,
    planned: bool = True,
    position: int | None = None,
    session: str | None = None,
    campaign: str | None = None,
) -> str:
    """Put a beat in a session's plan, move it, or take it out.

    Args:
        name: The beat's name. Taking out also finds an entry whose beat
              no longer exists.
        planned: False to take it out of the plan.
        position: Where it goes, 1 first, as current_session() numbers the
                  plan; a beat already planned moves there. Without one, a
                  new beat goes at the end.
        session: The session's name; defaults to the one open in the app,
                 else the latest.
        campaign: A campaign name; defaults to the one open in the app.
    """
    index, ctx, error = await _campaign_index(campaign)
    if error:
        return error
    if session:
        target, error = _session_named(index, session)
        if error:
            return error
    else:
        target = _session(index, ctx)
        if target is None:
            return f"{index['name']} has no session yet. create_session() starts one."
    beat, missing = _note(index, name, "beat")
    wanted = name.strip().removesuffix(".md").casefold()
    refs = target["beats"]
    at = next((
        i for i, r in enumerate(refs)
        if (beat and r.get("path") == beat["path"]) or r["link"].casefold() == wanted
    ), None)
    if position is not None and position < 1:
        return "position counts from 1, the plan's first beat."

    edit = None
    if not planned:
        if at is None:
            return f"{name} isn't in {target['name']}'s plan."
        edit = {"op": "remove", "at": at, "expect": refs[at]["link"]}
    elif beat is None:
        return missing
    elif at is None:
        edit = {"op": "add", "beat": beat["path"], "to": None if position is None else position - 1}
    elif position is not None and position - 1 != at:
        edit = {"op": "move", "at": at, "to": position - 1, "expect": refs[at]["link"]}

    plan = [r["link"] for r in refs]
    if edit:
        data = await sidecar.post("/api/command/sessions/plan", {
            "campaign": index["name"], "session": target["path"], **edit,
        })
        if isinstance(data, str):
            return data
        plan = data["beats"]
    lines = [f"{target['name']}'s plan:"] + [f"  {i}. {b}" for i, b in enumerate(plan, 1)]
    return "\n".join(lines if plan else [f"{target['name']}'s plan: nothing planned."])


@mcp.tool()
async def add_to_live_set(name: str, campaign: str | None = None) -> str:
    """Put a note in play at the table, beside whatever is live already.

    Args:
        name: The note's name, or its path when the name is shared.
        campaign: A campaign name; defaults to the one open in the app.
    """
    index, _ctx, error = await _campaign_index(campaign)
    if error:
        return error
    entry, error = _note(index, name, "note")
    if error:
        return error
    live = await sidecar.post("/api/command/live/note", {
        "campaign": index["name"], "note": entry["path"], "live": True,
    })
    if isinstance(live, str):
        return live
    return f"{entry['name']} is live: {len(live['notes'])} note(s) in play."


@mcp.tool()
async def spend(name: str, spent: bool = True, campaign: str | None = None) -> str:
    """Mark a note spent (a secret revealed, a treasure given, an NPC dead, a
    beat played) or unspent again.

    Args:
        name: The note's name, or its path when the name is shared.
        spent: False to mark it unspent.
        campaign: A campaign name; defaults to the one open in the app.
    """
    index, _ctx, error = await _campaign_index(campaign)
    if error:
        return error
    entry, error = _note(index, name)
    if error:
        return error
    data = await sidecar.post("/api/command/spent", {
        "campaign": index["name"], "path": entry["path"], "spent": spent,
    })
    if isinstance(data, str):
        return data
    state = f"spent ({data['spent']})" if data.get("spent") else "unspent"
    return f"{entry['name']} is {state}."


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
            f"Make sure Unseen Servant is running.",
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
