# Legend Lore Development Guide

## Product Vision

Legend Lore is a local-first, AI-augmented toolkit for tabletop RPG Gamemasters. It helps GMs browse, index, and semantically search their PDF rulebook collections, and integrates with Claude AI via MCP for mid-session lookups and homebrew creation.

### Target User

A TTRPG Gamemaster who:

- Owns a large PDF library (hundreds to thousands of rulebooks, supplements, and adventures)
- Needs to find specific rules, tables, or lore quickly during session prep and live play
- Wants AI assistance for homebrew content, rule comparisons, and creative prompts
- Values privacy — their library stays on their machine, not in the cloud

### Core Philosophy

1. **Local-first.** No accounts, no cloud, no data leaves the machine.
2. **AI-augmented, not AI-dependent.** The app is fully functional without AI — search still works, files still browse.
3. **Markdown for collaboration.** Configuration, notes, and homebrew content should be readable and editable by both humans and AI tools.

---

## This Repository: `unseen-legend-lore`

The core desktop application — Tauri v2 shell with SvelteKit frontend and a Python sidecar for PDF indexing and search.

### What it does

- **Tauri + Rust:** Native desktop window, filesystem access, sidecar lifecycle management
- **SvelteKit + TypeScript:** File browser UI with recursive tree, lazy loading, persistent selection
- **Python sidecar (FastAPI):** PDF text extraction, ChromaDB indexing, semantic search API (port 8420)
- **MCP server:** 7 tools for Claude Desktop integration (search, compare, random tables, etc.)

### Quick reference

```bash
npm run tauri dev          # Development (compiles Rust + starts frontend with HMR)
npm run tauri build        # Production build
cd sidecar && pytest -v    # Run sidecar tests
bash scripts/bump-version.sh 1.2.0  # Bump version in package.json, tauri.conf.json, Cargo.toml
```

### Key files

- `src/routes/+page.svelte` — Main UI page
- `src/lib/FileTree.svelte` — Recursive file tree component
- `src/lib/types.ts` — Shared TypeScript types
- `src-tauri/src/lib.rs` — Rust backend commands + sidecar lifecycle
- `sidecar/server.py` — FastAPI indexing and search server
- `sidecar/mcp_server.py` — MCP tool definitions for Claude Desktop
- `sidecar/tests/` — Pytest suite (chunking, indexing, search, MCP tools)

---

## Infrastructure

- **Ollama** with `nomic-embed-text` for local embeddings (no API keys)
- **ChromaDB** for vector storage and semantic search
- **MCP (Model Context Protocol)** for Claude Desktop integration
- **pypdf** for PDF text extraction

### Data flow

```text
PDF files on disk
  → text extraction (pypdf)
  → chunking (1000 chars, 200 overlap)
  → embedding (Ollama nomic-embed-text)
  → storage (ChromaDB)
  → semantic search (query → embed → nearest neighbors)
  → results to UI or Claude via MCP
```

---

## Testing

Python sidecar tests use in-memory ChromaDB and do not require Ollama.
