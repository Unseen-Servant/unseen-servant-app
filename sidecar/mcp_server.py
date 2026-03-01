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
import sys

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.prompts.base import UserMessage

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
# Resources
# ---------------------------------------------------------------------------

@mcp.resource("library://sources")
async def resource_sources() -> str:
    """List of all indexed TTRPG sourcebooks with chunk counts.

    Provides the complete catalog of PDFs that have been indexed
    in the library, showing how many text chunks each contains.
    """
    data = await sidecar.get("/api/sources")
    if isinstance(data, str):
        return data

    sources = data.get("sources", [])
    if not sources:
        return "No documents indexed yet."

    lines = [f"Indexed library: {data['count']} document(s)\n"]
    for s in sources:
        lines.append(f"  - {s['filename']} ({s['chunks']} chunks)")

    return "\n".join(lines)


@mcp.resource("library://source/{filename}")
async def resource_source_content(filename: str) -> str:
    """Full text content of a specific indexed sourcebook.

    Retrieves all chunks for the given PDF filename and returns
    the concatenated text content.
    """
    data = await sidecar.get(f"/api/source/{filename}/content")
    if isinstance(data, str):
        return data

    return (
        f"=== {data['filename']} ({data['chunks']} chunks) ===\n\n"
        f"{data['content']}"
    )


@mcp.resource("library://stats")
async def resource_stats() -> str:
    """Collection statistics for the indexed TTRPG library.

    Returns total chunks, total documents, and collection name.
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


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

@mcp.prompt(name="Session Prep")
def session_prep(session_topic: str, sources: str | None = None) -> list[UserMessage]:
    """Structured session preparation for a TTRPG game session.

    Helps GMs prepare for an upcoming session by searching the library
    for relevant content and organizing it into a prep document.

    Args:
        session_topic: What the session will cover (e.g., "players enter
                       the Haunted Mine", "first session of Dragonbane campaign")
        sources: Optional comma-separated list of sourcebook filenames
                 to focus on (e.g., "dragonbane_core.pdf,dragonbane_monsters.pdf")
    """
    source_instruction = ""
    if sources:
        source_names = [s.strip() for s in sources.split(",")]
        source_instruction = (
            f"\n\nFocus your search on these sourcebooks: {', '.join(source_names)}. "
            f"Use the search_in_document tool for each one."
        )

    return [
        UserMessage(
            f"I need to prepare for a TTRPG session about: {session_topic}\n\n"
            f"Please help me create a structured session prep document. "
            f"Use the search_library tool to find relevant rules, monsters, "
            f"NPCs, locations, and lore from my indexed sourcebooks. "
            f"Use read_document if you need the full text of a specific book."
            f"{source_instruction}\n\n"
            f"Organize the prep into these sections:\n"
            f"1. **Key Rules** — relevant mechanics the session might need\n"
            f"2. **NPCs & Monsters** — stat blocks and descriptions\n"
            f"3. **Locations & Lore** — setting details and background\n"
            f"4. **Random Tables** — encounter tables or other rollable content\n"
            f"5. **Session Notes** — key plot points and reminders\n\n"
            f"Cite the source filename for every piece of content you reference."
        ),
    ]


@mcp.prompt(name="Rule Lookup")
def rule_lookup(question: str, game_system: str | None = None) -> list[UserMessage]:
    """Quick rule reference with citations from indexed sourcebooks.

    Finds the answer to a specific rules question by searching
    the library and citing the exact source.

    Args:
        question: The rules question to answer (e.g., "how does grappling work",
                  "what are the conditions for surprise")
        game_system: Optional game system to focus on (e.g., "Dragonbane", "D&D 5E")
    """
    system_filter = ""
    if game_system:
        system_filter = (
            f" Focus specifically on {game_system} rules. "
            f"If possible, use the search_library tool with source_filter "
            f"to limit results to {game_system} sourcebooks."
        )

    return [
        UserMessage(
            f"Rules question: {question}\n\n"
            f"Search my TTRPG library using the search_library tool to find "
            f"the official rules that answer this question.{system_filter}\n\n"
            f"Provide:\n"
            f"1. **The Rule** — the exact text from the sourcebook\n"
            f"2. **Source** — which book and section it comes from\n"
            f"3. **Summary** — a plain-language explanation\n"
            f"4. **Related Rules** — any connected mechanics worth knowing\n\n"
            f"If the rule is ambiguous or differs between sources, "
            f"use compare_sources to show the differences."
        ),
    ]


@mcp.prompt(name="Encounter Builder")
def encounter_builder(
    party_level: str,
    theme: str | None = None,
    game_system: str | None = None,
) -> list[UserMessage]:
    """Build a combat or social encounter from indexed sourcebooks.

    Searches the library for appropriate monsters, NPCs, and
    encounter setups based on party level and theme.

    Args:
        party_level: Party level or power tier (e.g., "level 3",
                     "4 players level 5", "beginning adventurers")
        theme: Optional encounter theme (e.g., "undead ambush",
               "forest exploration", "tavern brawl")
        game_system: Optional game system (e.g., "Dragonbane", "D&D 5E")
    """
    theme_instruction = ""
    if theme:
        theme_instruction = f" The encounter theme is: {theme}."

    system_instruction = ""
    if game_system:
        system_instruction = f" Use {game_system} rules and sourcebooks."

    return [
        UserMessage(
            f"Build an encounter for: {party_level}.{theme_instruction}{system_instruction}\n\n"
            f"Use the search_library tool to find appropriate monsters, "
            f"NPCs, and encounter elements from my indexed sourcebooks. "
            f"Use random_table to find relevant random encounter tables.\n\n"
            f"Provide:\n"
            f"1. **Encounter Setup** — the scene description and hook\n"
            f"2. **Enemies/NPCs** — stat blocks or references with source citations\n"
            f"3. **Tactics** — how the enemies behave in combat\n"
            f"4. **Treasure/Rewards** — loot or story rewards\n"
            f"5. **Scaling Notes** — how to adjust difficulty up or down\n\n"
            f"Cite the source filename for every stat block or rule referenced."
        ),
    ]


@mcp.prompt(name="NPC Generator")
def npc_generator(
    role: str,
    game_system: str | None = None,
    npc_context: str | None = None,
) -> list[UserMessage]:
    """Generate an NPC using content from indexed sourcebooks.

    Creates a detailed NPC by pulling relevant material from the
    library — stat blocks, personality traits, backgrounds, and lore.

    Args:
        role: The NPC's role (e.g., "blacksmith", "tavern keeper",
              "villain's lieutenant", "quest giver")
        game_system: Optional game system (e.g., "Dragonbane", "D&D 5E")
        npc_context: Optional story context (e.g., "in a mining town
                     under siege", "works for the thieves' guild")
    """
    system_instruction = ""
    if game_system:
        system_instruction = f" Use {game_system} rules for any stat blocks."

    context_instruction = ""
    if npc_context:
        context_instruction = f" Story context: {npc_context}."

    return [
        UserMessage(
            f"Create an NPC with the role: {role}.{system_instruction}{context_instruction}\n\n"
            f"Use the search_library tool to find relevant NPC templates, "
            f"stat blocks, personality traits, and background tables from my "
            f"indexed sourcebooks. Use random_table to roll on any trait or "
            f"background tables you find.\n\n"
            f"Provide:\n"
            f"1. **Name & Appearance** — a fitting name and physical description\n"
            f"2. **Personality** — traits, mannerisms, and motivations\n"
            f"3. **Background** — how they got to where they are\n"
            f"4. **Stats** — relevant game statistics (if applicable)\n"
            f"5. **Hooks** — plot hooks or quest ideas connected to this NPC\n\n"
            f"Ground the NPC in source material — cite which books inspired each element."
        ),
    ]


@mcp.prompt(name="Lore Researcher")
def lore_researcher(topic: str, sources: str | None = None) -> list[UserMessage]:
    """Deep lore cross-referencing across indexed sourcebooks.

    Researches a lore topic across multiple sourcebooks, comparing
    and synthesizing information from different sources.

    Args:
        topic: The lore topic to research (e.g., "elven history",
               "the Underdark", "dragon types and their habits")
        sources: Optional comma-separated list of sourcebook filenames
                 to focus on (e.g., "forgotten_realms.pdf,monster_manual.pdf")
    """
    source_instruction = ""
    if sources:
        source_names = [s.strip() for s in sources.split(",")]
        source_instruction = (
            f"\n\nFocus your research on these sourcebooks: {', '.join(source_names)}. "
            f"Use compare_sources to see how they cover the topic differently."
        )

    return [
        UserMessage(
            f"Research this lore topic across my TTRPG library: {topic}\n\n"
            f"Use the search_library tool to find all references to this topic "
            f"across my indexed sourcebooks. Use read_document to get full context "
            f"when needed. Use compare_sources if the topic appears in multiple books."
            f"{source_instruction}\n\n"
            f"Provide:\n"
            f"1. **Overview** — a comprehensive summary of the topic\n"
            f"2. **Source Breakdown** — what each sourcebook says, with citations\n"
            f"3. **Contradictions** — any conflicts between sources\n"
            f"4. **GM Notes** — how to use this lore in play\n"
            f"5. **Further Reading** — which indexed books have more on this topic\n\n"
            f"Cite the source filename for every claim."
        ),
    ]


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
            f"Make sure the Unseen Servant app is running.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    check_sidecar_health(args.sidecar_url)
    mcp.run(transport="stdio")
