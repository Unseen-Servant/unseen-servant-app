"""
Unseen Servant — MCP server for TTRPG PDF library.

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
import random

import httpx
from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# CLI arguments
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(description="Unseen Servant MCP server")
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
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{self.base_url}{path}")
                resp.raise_for_status()
                return resp.json()
        except httpx.ConnectError:
            return f"Cannot connect to Unseen Servant app. Make sure the desktop app is running (sidecar at {self.base_url})."
        except httpx.HTTPStatusError as e:
            return f"Sidecar error: {e.response.status_code} — {e.response.text}"

    async def post(self, path: str, json: dict) -> dict | str:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(f"{self.base_url}{path}", json=json)
                resp.raise_for_status()
                return resp.json()
        except httpx.ConnectError:
            return f"Cannot connect to Unseen Servant app. Make sure the desktop app is running (sidecar at {self.base_url})."
        except httpx.HTTPStatusError as e:
            return f"Sidecar error: {e.response.status_code} — {e.response.text}"


# ---------------------------------------------------------------------------
# MCP server setup
# ---------------------------------------------------------------------------

args = parse_args()
sidecar = SidecarClient(args.sidecar_url)

mcp = FastMCP(
    name="Unseen Servant",
    instructions=(
        "You have access to the user's indexed TTRPG PDF library. "
        "Use the search and retrieval tools to find rules, lore, "
        "stat blocks, and other content from their sourcebooks. "
        "Always cite the source filename when referencing content."
    ),
)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def search_library(
    query: str,
    n_results: int = 5,
    source_filter: str | None = None,
) -> str:
    """Search your TTRPG PDF library for relevant content.

    Use this to find rules, lore, stat blocks, spells, monsters,
    or any content across your indexed sourcebooks.

    Args:
        query: What to search for (e.g., "grappling rules",
               "fire drake stats", "healing potions")
        n_results: How many results to return (default 5)
        source_filter: Optional PDF filename to restrict search
                       to one book (e.g., "dragonbane_core.pdf")
    """
    payload = {"query": query, "n_results": n_results}
    if source_filter:
        payload["source_filter"] = source_filter

    data = await sidecar.post("/api/search", payload)
    if isinstance(data, str):
        return data  # Error message

    results = data.get("results", [])
    if not results:
        return f"No results found for: {query}"

    lines = [f"Found {len(results)} result(s) for \"{query}\":\n"]
    for i, r in enumerate(results, 1):
        lines.append(f"--- Result {i} (relevance: {r['relevance']}) ---")
        lines.append(f"Source: {r['filename']}")
        lines.append(f"Chunk: {r['chunk']}")
        lines.append(r["text"])
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
async def search_in_document(
    filename: str,
    query: str,
    n_results: int = 5,
) -> str:
    """Search within a specific sourcebook.

    Use this when the user wants to find something in a particular
    book, e.g., "find the spell list in the Player's Handbook."

    Args:
        filename: The PDF filename to search within
                  (e.g., "dragonbane_core.pdf")
        query: What to search for within that book
        n_results: How many results to return (default 5)
    """
    return await search_library(query, n_results, source_filter=filename)


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
        return "No documents indexed yet. Open the Unseen Servant app and index some PDFs first."

    lines = [f"Indexed library: {data['count']} document(s)\n"]
    for s in sources:
        lines.append(f"  - {s['filename']} ({s['chunks']} chunks)")

    return "\n".join(lines)


@mcp.tool()
async def library_stats() -> str:
    """Get an overview of your indexed TTRPG library.

    Returns total chunks, total documents, and collection info.
    Useful for understanding how much content is available for search.
    """
    data = await sidecar.get("/api/stats")
    if isinstance(data, str):
        return data

    return (
        f"Library statistics:\n"
        f"  Total documents: {data['total_documents']}\n"
        f"  Total chunks: {data['total_chunks']}\n"
        f"  Collection: {data['collection_name']}"
    )


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


@mcp.tool()
async def random_table(query: str, n_results: int = 3) -> str:
    """Find and roll on a random table from your sourcebooks.

    Searches for table-like content (random encounters, loot,
    NPC traits, weather, etc.) and picks a random entry.

    Args:
        query: What kind of table to find (e.g., "random encounter
               forest", "loot table", "NPC personality traits")
        n_results: How many table candidates to search for (default 3)
    """
    payload = {"query": f"table {query}", "n_results": n_results}
    data = await sidecar.post("/api/search", payload)
    if isinstance(data, str):
        return data

    results = data.get("results", [])
    if not results:
        return f"No tables found for: {query}"

    # Pick the most relevant result as the table
    best = results[0]

    # Try to extract numbered/bulleted lines as table entries
    lines = best["text"].strip().split("\n")
    entries = [
        line.strip() for line in lines
        if line.strip() and any(
            line.strip().startswith(prefix)
            for prefix in ("1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-", "•", "*")
        )
    ]

    output = [
        f"Table found in: {best['filename']}",
        f"(relevance: {best['relevance']})\n",
        best["text"],
    ]

    if entries:
        roll = random.choice(entries)
        output.append(f"\n🎲 Random roll: {roll}")
    else:
        output.append(
            "\n(No numbered/bulleted entries detected — "
            "showing the raw text above for you to roll manually.)"
        )

    return "\n".join(output)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")
