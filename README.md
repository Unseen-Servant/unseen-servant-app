# Unseen Servant

> A desktop app for TTRPG Game Masters to browse, index, and search their PDF collection using AI
> when prepping or running a game.

Named after the classic D&D spell, **Unseen Servant** does the behind-the-scenes work so you can
focus on running your game — silently indexing your rulebooks, supplements, and homebrew PDFs so
you can ask a question during a session and get an answer instantly.

---

## Installation (End Users)

1. Download the latest `.dmg` from [GitHub Releases](https://github.com/Unseen-Servant/unseen-server/releases)
2. Drag **Unseen Server** to your Applications folder
3. Install [Ollama](https://ollama.com) and pull the embedding model:

   ```bash
   ollama pull nomic-embed-text
   ```

4. Launch Unseen Server
   - **First launch:** Right-click the app → Open (to bypass macOS Gatekeeper for unsigned apps)
   - The app runs in the menu bar — click the tray icon to show the window

> **Note:** Ollama must be running for indexing and search to work. The app will still launch and
> let you browse files without it.

---

## Philosophy

Most TTRPG GMs have enormous digital libraries — hundreds of PDFs scattered across folders, from
core rulebooks to obscure third-party supplements. Finding a specific rule, creature stat block,
or random table during a live session often means interrupting the game to dig through files
manually.

Unseen Servant is built around three ideas:

1. **Your collection, your machine.** Everything runs locally. Your PDFs are never uploaded
   anywhere. The app talks to an AI assistant via MCP (Model Context Protocol), but your files
   stay on your disk.

2. **Efficiency at scale.** Designed for large collections (tested with 2,600+ PDFs, ~18GB). The
   app uses lazy loading and batch processing so it never tries to swallow your whole library at
   once.

3. **GM-first UX.** Quick, focused answers during play. Not a general document viewer — a session
   tool.

---

## Current Features

- **Folder Browser** — Select your TTRPG folder and explore it as a sorted tree (folders first,
  then files alphabetically), with lazy expansion on demand
- **PDF Detection** — Automatically filters to only show `.pdf` files and subdirectories
- **Checkbox Selection** — Select individual PDFs or entire folders (with recursive toggle)
- **Ancestor Awareness** — Parent folders visually indicate when nested files are selected, even
  before expanding
- **Persistent Selections** — Folder and file selections are saved across sessions
- **PDF Indexing** — Index selected PDFs into ChromaDB for semantic search via a Python sidecar
  (uses Ollama embeddings locally)
- **Double-click to Open** — Double-click any file in the tree to open it in your system's
  default viewer
- **Game System Tagging** — Tag indexed files with their game system (D&D 5e, Pathfinder, etc.)
  via clickable badges in the file tree
- **Copy MCP Config** — One-click button to copy the Claude Desktop MCP configuration to your
  clipboard

### Roadmap

| Status | Feature                                           |
|--------|---------------------------------------------------|
| ✅     | Select TTRPG folder, display path                 |
| ✅     | List files in folder                              |
| ✅     | Recursive tree structure with expand/collapse     |
| ✅     | Checkbox selection (individual + recursive)       |
| ✅     | Persist folder selections across sessions         |
| ✅     | ChromaDB integration — index PDFs semantically    |
| ✅     | Game system tagging for indexed files             |
| 🔜     | Search UI — query indexed content during sessions |
| ✅     | Claude AI via MCP — answer questions from library |

---

## MCP Server (Claude Desktop)

The MCP server lets Claude Desktop search your indexed PDF library during a conversation. It runs
as a separate stdio process that Claude Desktop launches automatically, and calls the FastAPI
sidecar over HTTP to fulfill requests.

```text
Claude Desktop ←→ mcp_server.py (stdio) ←→ FastAPI sidecar (HTTP :8420) ←→ ChromaDB
```

### Connecting to Claude Desktop

**Step 1 — Start the sidecar**, either via `npm run tauri dev` (starts it automatically) or
manually:

```bash
cd sidecar
source .venv/bin/activate
python server.py --port 8420
```

**Step 2 — Configure Claude Desktop.** Add the MCP config snippet to your Claude Desktop
config file:

- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

**Easiest way:** Run the app with `npm run tauri dev` and click the **"Copy MCP Config"** button
in the UI. This copies a ready-to-paste JSON snippet with the correct absolute paths for your
machine. Paste it into your Claude Desktop config file.

**Manual setup:** If you prefer to build the config yourself:

```json
{
  "mcpServers": {
    "unseen-servant": {
      "command": "/full/path/to/sidecar/.venv/bin/python3",
      "args": [
        "/full/path/to/unseen-server/sidecar/mcp_server.py",
        "--sidecar-url", "http://localhost:8420"
      ]
    }
  }
}
```

> **Important:** Use the **full path** to your Python interpreter, not bare `python` or
> `python3`. Claude Desktop has a limited PATH and won't find pyenv shims or virtualenvs.

**Step 3 — Make sure the Python environment has the dependencies** from
`sidecar/requirements.txt` installed (notably `mcp` and `httpx`).

### Available tools

| Tool                 | Description                                           |
|----------------------|-------------------------------------------------------|
| `search_library`     | Semantic search across all indexed PDFs               |
| `search_in_document` | Search within a specific sourcebook                   |
| `read_document`      | Read the full text of an indexed PDF                  |
| `list_sources`       | List all indexed documents                            |
| `library_stats`      | Overview of indexed library size                      |
| `compare_sources`    | Compare how different books cover the same topic      |
| `random_table`       | Find and roll on a random table from your sourcebooks |

---

## Tech Stack

| Layer                   | Choice                                             | Why                                              |
|-------------------------|----------------------------------------------------|--------------------------------------------------|
| Desktop framework       | [Tauri v2](https://tauri.app)                      | ~3MB binary vs Electron's 150MB+. Rust backend.  |
| Frontend                | [SvelteKit](https://kit.svelte.dev) + TypeScript   | Lightweight, fast, great reactivity model        |
| Backend                 | Rust                                               | Ships with Tauri; safe filesystem access         |
| Indexing sidecar        | Python + [FastAPI](https://fastapi.tiangolo.com)   | Mature PDF/ML ecosystem, managed by Tauri        |
| Vector DB               | [ChromaDB](https://www.trychroma.com)              | Semantic search for PDF content                  |
| Embeddings              | [Ollama](https://ollama.com) (nomic-embed-text)    | Local embeddings, no API keys needed             |
| AI integration          | Claude via [MCP](https://modelcontextprotocol.io)  | Query your library in natural language           |

---

## Prerequisites

### All Platforms

- [Rust](https://www.rust-lang.org/tools/install)
- Node.js 18+ (via [nvm](https://github.com/nvm-sh/nvm) or your preferred manager)
- Python 3.10+ (via [pyenv](https://github.com/pyenv/pyenv) or system install)
- [Ollama](https://ollama.com) with the `nomic-embed-text` model:
  `ollama pull nomic-embed-text`

### macOS

- [Xcode Command Line Tools](https://developer.apple.com/xcode/resources/):
  `xcode-select --install`

### Windows

- [Visual Studio Build Tools 2019+](https://visualstudio.microsoft.com/visual-cpp-build-tools/)
  with "Desktop development with C++"
- [WebView2](https://developer.microsoft.com/en-us/microsoft-edge/webview2/) (pre-installed on
  Windows 11)

### Linux

- GTK3 dev libraries: `sudo apt install libgtk-3-dev libwebkit2gtk-4.1-dev`

See the [Tauri prerequisites guide](https://tauri.app/start/prerequisites/) for full details.

---

## Setup

```bash
# 1. Clone the repository
git clone https://github.com/Unseen-Servant/unseen-server.git
cd unseen-server

# 2. Install frontend dependencies
npm install

# 3. Set up the Python sidecar (one-time)
cd sidecar
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cd ..

# 4. Make sure Ollama is running with the embedding model
ollama pull nomic-embed-text

# 5. Run in development mode (compiles Rust + starts frontend with HMR)
npm run tauri dev
```

> **Important:** Always use `npm run tauri dev`, not `npm run dev`.
> Plain `npm run dev` starts only the SvelteKit frontend in a browser — Tauri APIs
> (file system access, native dialogs) won't work there.
>
> The Tauri app automatically starts and stops the Python sidecar — you don't need
> to run it manually.

---

## Building for Production

```bash
# 1. Build the Python sidecar into standalone binaries
chmod +x scripts/build-sidecar.sh
./scripts/build-sidecar.sh

# 2. Build the Tauri app (includes the sidecar binaries in the bundle)
npm run tauri build
```

The `.dmg` (macOS) is output to `src-tauri/target/release/bundle/dmg/`.

---

## Other Scripts

```bash
npm run check         # TypeScript + Svelte type checking
npm run check:watch   # Type checking in watch mode
npm run preview       # Preview the production frontend build in browser
```

### Sidecar Tests

```bash
cd sidecar
source .venv/bin/activate
pip install -r requirements-test.txt   # One-time: adds pytest, reportlab, etc.
python -m pytest tests/ -v             # Run all 39 tests (no Ollama needed)
```

---

## Project Structure

```text
unseen-server/
├── src/                        # Frontend (SvelteKit + TypeScript)
│   ├── routes/
│   │   ├── +page.svelte        # Main UI: folder picker, file tree, indexing
│   │   └── +layout.ts          # Disables SSR (SPA mode for Tauri)
│   └── lib/
│       ├── FileTree.svelte     # Recursive file tree component
│       └── types.ts            # Shared TypeScript types (FileItem)
│
├── src-tauri/                  # Backend (Rust)
│   ├── src/
│   │   ├── lib.rs              # Tauri commands + sidecar lifecycle
│   │   └── main.rs             # App entry point
│   ├── capabilities/
│   │   └── default.json        # Tauri permissions (dialog, store, etc.)
│   ├── tauri.conf.json         # App config (window size, bundle ID, icons)
│   └── Cargo.toml              # Rust dependencies
│
├── sidecar/                    # Python indexing sidecar
│   ├── server.py               # FastAPI server (ChromaDB + PDF extraction)
│   ├── requirements.txt        # Production dependencies
│   ├── requirements-test.txt   # Test dependencies (pytest, reportlab)
│   ├── pytest.ini              # Test configuration
│   └── tests/                  # 39 tests across 7 files
│       ├── conftest.py         # Shared fixtures (test DB, PDF generators)
│       ├── test_chunking.py    # Text chunking unit tests
│       ├── test_health.py      # Health endpoint
│       ├── test_indexing.py    # PDF indexing tests
│       ├── test_search.py      # Semantic search tests
│       ├── test_stats.py       # Database statistics
│       ├── test_sources.py     # Source listing + deletion
│       └── test_error_cases.py # Edge cases and robustness
│
├── static/                     # Static assets (favicon, etc.)
├── package.json
└── svelte.config.js
```

---

## Architecture

### How Svelte Talks to Rust

Tauri uses a command pattern to bridge the frontend and backend:

```text
User action in Svelte
        ↓
  invoke('command_name', { params })   ← Tauri IPC call
        ↓
  Rust function tagged with #[tauri::command]
        ↓
  Returns Result<T, String> as JSON
        ↓
  Svelte receives typed response
```

**Current commands:**

| Command                  | Description                                                   |
|--------------------------|---------------------------------------------------------------|
| `select_folder`          | Opens a native OS folder picker dialog, returns chosen path   |
| `list_files`             | Reads a directory, returns `FileItem[]` (PDFs + subfolders)   |
| `index_files`            | Sends selected PDF paths to the sidecar for indexing          |
| `get_index_status`       | Queries sidecar for what needs adding, removing, or updating  |
| `sync_index`             | Synchronizes the index — adds, removes, and updates as needed |
| `get_game_systems`       | Retrieves game system tags from indexed files                 |
| `get_known_game_systems` | Lists all predefined game system options                      |
| `set_game_system`        | Tags a file with a game system and updates its index chunks   |
| `get_mcp_config`         | Returns ready-to-paste MCP config JSON with absolute paths    |

### How Indexing Works

The Tauri app manages a Python sidecar process for PDF indexing:

```text
Tauri app launches
        ↓
  Spawns Python sidecar (FastAPI on port 8420)
        ↓
  User selects PDFs and clicks "Index"
        ↓
  Rust sends HTTP POST to sidecar with file paths
        ↓
  Sidecar extracts text (pypdf) → chunks (1000 chars, 200 overlap)
        ↓
  Embeds via Ollama (nomic-embed-text) → stores in ChromaDB
        ↓
  Returns { indexed, total, errors } to Rust → Svelte
        ↓
  Tauri app closes → kills sidecar process
```

---

## Recommended IDE Setup

[VS Code](https://code.visualstudio.com/) with these extensions:

- [Svelte for VS Code](https://marketplace.visualstudio.com/items?itemName=svelte.svelte-vscode)
- [Tauri](https://marketplace.visualstudio.com/items?itemName=tauri-apps.tauri-vscode)
- [rust-analyzer](https://marketplace.visualstudio.com/items?itemName=rust-lang.rust-analyzer)

---

## License

MIT
