# Unseen Servant

> A desktop workstation for TTRPG Game Masters. Its first tool, Legend Lore, browses, indexes,
> and searches your local PDF collection when prepping or running a game.

---

## Installation (End Users)

1. Download the latest installer from [GitHub Releases](https://github.com/Unseen-Servant/unseen-servant-app/releases):
   - **macOS (Apple Silicon):** `.dmg`
   - **Windows:** `.msi` or `.exe`
2. Install the app:
   - **macOS:** Drag **Unseen Servant** to your Applications folder
   - **Windows:** Run the installer and follow the prompts
3. Install [Ollama](https://ollama.com), pull the embedding model, and start
   Ollama with the 8K context window the embedder needs:

   ```bash
   ollama pull bge-m3
   OLLAMA_CONTEXT_LENGTH=8192 ollama serve
   ```

   `OLLAMA_CONTEXT_LENGTH` is required — without it Ollama silently truncates
   embeddings at 2048 tokens. The app probes for this at startup and warns in
   the sidecar logs if truncation is detected.

4. Launch Unseen Servant
   - The app runs in the menu bar / system tray — click the tray icon to show the window

> **Note:** Ollama must be running for indexing and search to work. The app will still launch and
> let you browse files without it.

---

## Philosophy

Legend Lore is built around three ideas:

1. **Local-first.** Everything runs on your machine. PDFs are never uploaded anywhere. Embeddings, search, and AI integration all happen locally.

2. **No lock-in.** Your collection stays readable on disk whether or not you use the app. Indexed metadata is stored in open formats (ChromaDB/SQLite). Inspired by Obsidian's approach to notes.

3. **Built for live play.** Design takes cues from DAWs and live performance tools — fast lookup, scoped context, minimal friction. A GM mid-session is closer to a musician performing than a researcher browsing.

---

## Features

### Library browser

- Folder tree with lazy expansion, checkbox selection, and persistent state across sessions
- Two views: directory tree and game-system grouping
- Right-click actions: open, reveal in Finder, rename, reindex, delete, add to collection
- Double-click to open in system viewer

### Indexing and sync

- Indexes selected PDFs into ChromaDB via a local Python sidecar (PyMuPDF4LLM + Ollama embeddings)
- Tables are split into per-row embed units, so a lookup lands on the exact row of a spell or
  equipment table — with a coverage tripwire that flags lossy table parses
- Detects added, removed, and modified files; syncs incrementally with real-time progress
- Configurable sync behavior: background polling, disk event handling, per-event policies

### Search

- Semantic search across indexed PDFs with page citations
- Misspelled queries are corrected against your library's own vocabulary
  ("owlber" → "owlbear") before searching; results say what was corrected
- Local cross-encoder reranking (ONNX, CPU-only) sharpens the top results
- Results carry a relevance tier — **strong / good / weak** — instead of a raw "% match";
  weak matches are dimmed below a divider so noise reads as noise
- Naming a game system in the query ("fireball in 5e") soft-boosts results from that system
  without hiding the rest of the library
- Scope search to a folder, file, game system, or collection

### Collections

- Curated subsets of PDFs with name, description, color, and archived state
- Inline creation and editing; MCP tools respect active collection scope

### Game system tagging

- Tag indexed files with a game system (D&D 5e, Pathfinder, etc.)
- Filter the library view to exclude specific systems
- Group files by system in the systems view

### Status bar

- Sidecar and MCP connection health at a glance
- File/index counts, storage size, top game system, last sync timestamp
- Manual sync button

### System tray

- Runs in the menu bar; close-to-tray behavior

### MCP integration (Claude Desktop)

- `search_library` — semantic search scoped by system, source, or collection
- `list_sources` — indexed PDFs with chunk counts
- `list_collections` — curated collections with file counts and descriptions
- `list_game_systems` — game systems detected across the library
- Results report match tiers (strong/good/weak) so Claude knows when to trust them, and
  near-miss filter values (typos, partial names) resolve to the closest match instead of
  failing silently

---

## MCP Server (Claude Desktop)

The MCP server lets Claude Desktop search your indexed library during a conversation. It runs as a separate stdio process that Claude Desktop launches automatically, and calls the FastAPI sidecar over HTTP.

```text
Claude Desktop ←→ mcp_server.py (stdio) ←→ FastAPI sidecar (HTTP :8420) ←→ ChromaDB
```

**Step 1 — Install sidecar dependencies** (once): `uv sync` in `sidecar/` — installs from `pyproject.toml`, notably `mcp` and `httpx`.

**Step 2 — Start the sidecar.** It starts automatically with `npm run tauri dev`. To start it manually:

```bash
cd sidecar
uv run python server.py --port 8420
```

**Step 3 — Configure Claude Desktop.** Click **"Copy MCP Config"** in the app to copy a ready-to-paste JSON snippet with the correct absolute paths. Paste it into:

- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

Manual config:

```json
{
  "mcpServers": {
    "Unseen Servant": {
      "command": "/full/path/to/sidecar/.venv/bin/python3",
      "args": [
        "/full/path/to/legend-lore/sidecar/mcp_server.py",
        "--sidecar-url", "http://localhost:8420"
      ]
    }
  }
}
```

> Use the **full path** to your Python interpreter — Claude Desktop has a limited PATH and won't find pyenv shims or virtualenvs.

---

## Tech Stack

| Layer             | Choice                                                          | Why                                             |
|-------------------|-----------------------------------------------------------------|-------------------------------------------------|
| Desktop framework | [Tauri v2](https://tauri.app)                                   | ~3MB binary vs Electron's 150MB+. Rust backend. |
| Frontend          | [SvelteKit](https://kit.svelte.dev) + TypeScript                | Lightweight, fast, great reactivity model       |
| Backend           | Rust                                                            | Ships with Tauri; safe filesystem access        |
| Indexing sidecar  | Python + [FastAPI](https://fastapi.tiangolo.com) + PyMuPDF4LLM | Mature PDF/ML ecosystem, managed by Tauri        |
| Vector DB         | [ChromaDB](https://www.trychroma.com)                           | Semantic search for PDF content                 |
| Embeddings        | [Ollama](https://ollama.com) (bge-m3)                           | Local embeddings, no API keys needed            |
| Reranker          | [fastembed](https://github.com/qdrant/fastembed) cross-encoder | Sharper top results; ONNX on CPU, no PyTorch    |
| AI integration    | Claude via [MCP](https://modelcontextprotocol.io)               | Query your library in natural language          |

---

## Prerequisites

### All Platforms

- [Rust](https://www.rust-lang.org/tools/install)
- Node.js 18+ (via [nvm](https://github.com/nvm-sh/nvm) or your preferred manager)
- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (manages the sidecar's Python environment; installs Python 3.12 for you if missing)
- [Ollama](https://ollama.com) with the `bge-m3` model and an 8K context window:
  `ollama pull bge-m3 && OLLAMA_CONTEXT_LENGTH=8192 ollama serve`

### macOS

- [Xcode Command Line Tools](https://developer.apple.com/xcode/resources/): `xcode-select --install`

### Windows

- [Visual Studio Build Tools 2019+](https://visualstudio.microsoft.com/visual-cpp-build-tools/) with "Desktop development with C++"
- [WebView2](https://developer.microsoft.com/en-us/microsoft-edge/webview2/)

### Linux

- GTK3 dev libraries: `sudo apt install libgtk-3-dev libwebkit2gtk-4.1-dev`

See the [Tauri prerequisites guide](https://tauri.app/start/prerequisites/) for full details.

---

## Setup

```bash
# 1. Clone the repository
git clone https://github.com/Unseen-Servant/unseen-servant-app.git
cd unseen-servant-app

# 2. Install frontend dependencies
npm install

# 3. Set up the Python sidecar (one-time)
cd sidecar
uv sync                          # Creates .venv on Python 3.12 and installs deps
cd ..

# 4. Start Ollama with the embedding model
ollama pull bge-m3
OLLAMA_CONTEXT_LENGTH=8192 ollama serve

# 5. Run in development mode
npm run tauri dev
```

> Always use `npm run tauri dev`, not `npm run dev`. Plain `npm run dev` runs only the SvelteKit
> frontend in a browser — Tauri APIs (filesystem, native dialogs) won't work there.

Other useful commands:

```bash
npm run check                    # TypeScript + Svelte type checking
bash scripts/bump-version.sh 1.2.0  # Bump version across package.json, tauri.conf.json, Cargo.toml
```

### Sidecar Tests and Evals

```bash
cd sidecar
uv run pytest tests/ -v          # Unit tests (no Ollama needed)
uv run python -m evals.run_eval  # Retrieval quality eval (needs Ollama + eval corpus)
```

The eval harness runs 40 pre-registered queries against the production search
pipeline and reports MRR/nDCG per category. See [sidecar/evals/README.md](sidecar/evals/README.md)
for the corpus setup and how to record baselines.

---

## Building for Production

```bash
chmod +x scripts/build-sidecar.sh
./scripts/build-sidecar.sh   # Bundle Python sidecar into standalone binaries
npm run tauri build           # Build Tauri app (includes sidecar binaries)
```

`tauri build` stops if any sidecar source is newer than the binaries in `src-tauri/binaries/`: rerun `scripts/build-sidecar.sh` first.

Output: `src-tauri/target/release/bundle/` — `dmg/*.dmg` (macOS), `nsis/*.exe` (Windows).

---

## Project Structure

```text
unseen-servant-app/
├── src/                        # Frontend (SvelteKit + TypeScript)
│   ├── routes/
│   │   ├── +page.svelte        # Main window: one tab per tool panel
│   │   ├── panel/[id]/         # A panel popped out into its own window
│   │   └── +layout.ts          # Disables SSR (SPA mode for Tauri)
│   └── lib/
│       ├── shell/              # Workstation chrome: panel hosts (PANELS.md), header, status bar, settings, dialogs
│       ├── ui/                 # Shared primitives: buttons, confirm dialog, icons
│       ├── legend-lore/        # Legend Lore panel and components (file tree, search, collections)
│       ├── command/            # Command panel (placeholder)
│       └── servant/            # Servant panel (placeholder)
│
├── src-tauri/                  # Backend (Rust)
│   ├── src/
│   │   ├── lib.rs              # run(), sidecar lifecycle, tray, windows, health checks
│   │   ├── legend_lore.rs      # Legend Lore commands (proxy to the sidecar)
│   │   └── main.rs             # App entry point
│   ├── capabilities/
│   │   └── default.json        # Tauri permissions (dialog, store, etc.)
│   ├── tauri.conf.json         # App config (window size, bundle ID, icons)
│   └── Cargo.toml              # Rust dependencies
│
├── sidecar/                    # Python indexing sidecar
│   ├── server.py               # FastAPI app construction, lifecycle, health
│   ├── mcp_server.py           # MCP tool definitions for Claude Desktop
│   ├── legend_lore/            # Legend Lore: routes, indexing, search, retrieval modules
│   │   ├── router.py           # HTTP routes (APIRouter mounted by server.py)
│   │   ├── service.py          # Extraction, indexing, stores, search pipeline
│   │   ├── reranker.py         # Cross-encoder reranking (fastembed/ONNX)
│   │   └── linearize.py        # Table row-linearization for embed units
│   ├── evals/                  # Retrieval eval harness (queries, scorer, baselines)
│   ├── pyproject.toml          # Dependencies (runtime + dev/build groups)
│   ├── uv.lock                 # Locked dependency versions
│   └── tests/                  # Pytest suite
│
└── scripts/
    ├── build-sidecar.sh        # Bundles Python sidecar for production
    └── bump-version.sh         # Version bump across all config files
```

---

## Data Flow

```text
PDF files on disk
  → text extraction (PyMuPDF4LLM)
  → chunking (1000 chars, 200 overlap; tables linearized into per-row units)
  → embedding (Ollama bge-m3, 1024-dim)
  → storage (ChromaDB)
  → search (spell-correct query → embed → nearest neighbors → cross-encoder rerank → relevance tiers)
  → results to UI or Claude via MCP
```

---

## Recommended IDE Setup

[VS Code](https://code.visualstudio.com/) with:

- [Svelte for VS Code](https://marketplace.visualstudio.com/items?itemName=svelte.svelte-vscode)
- [Tauri](https://marketplace.visualstudio.com/items?itemName=tauri-apps.tauri-vscode)
- [rust-analyzer](https://marketplace.visualstudio.com/items?itemName=rust-lang.rust-analyzer)

---

## License

Unseen Servant is proprietary software. See [LICENSE](LICENSE) for details.
