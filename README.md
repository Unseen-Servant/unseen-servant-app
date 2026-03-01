# Unseen Servant

> A desktop app for TTRPG Game Masters to browse, index, and search their PDF collection using AI
> when prepping or running a game.

Named after the classic D&D spell, **Unseen Servant** does the behind-the-scenes work so you can
focus on running your game — silently indexing your rulebooks, supplements, and homebrew PDFs so
you can ask a question during a session and get an answer instantly.

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

- **Folder Browser** — Select your TTRPG folder and explore it as a tree, with lazy expansion on
  demand
- **PDF Detection** — Automatically filters to only show `.pdf` files and subdirectories
- **Checkbox Selection** — Select individual PDFs or entire folders (with recursive toggle)
- **Indeterminate State** — Folder checkbox shows a mixed state when only some children are
  selected

### Roadmap

| Status | Feature                                           |
|--------|---------------------------------------------------|
| ✅     | Select TTRPG folder, display path                 |
| ✅     | List files in folder                              |
| ✅     | Recursive tree structure with expand/collapse     |
| ✅     | Checkbox selection (individual + recursive)       |
| 🔜     | Persist folder selections across sessions         |
| 🔜     | ChromaDB integration — index PDFs semantically    |
| 🔜     | Claude AI via MCP — answer questions from library |
| 🔜     | Search UI — query indexed content during sessions |

---

## Tech Stack

| Layer                    | Choice                                             | Why                                              |
|--------------------------|----------------------------------------------------|--------------------------------------------------|
| Desktop framework        | [Tauri v2](https://tauri.app)                      | ~3MB binary vs Electron's 150MB+. Rust backend.  |
| Frontend                 | [SvelteKit](https://kit.svelte.dev) + TypeScript   | Lightweight, fast, great reactivity model        |
| Backend                  | Rust                                               | Ships with Tauri; safe filesystem access         |
| Vector DB *(upcoming)*   | [ChromaDB](https://www.trychroma.com)              | Semantic search for PDF content                  |
| AI integration *(soon)*  | Claude via [MCP](https://modelcontextprotocol.io)  | Query your library in natural language           |

---

## Prerequisites

### macOS

- [Xcode Command Line Tools](https://developer.apple.com/xcode/resources/):
  `xcode-select --install`
- [Rust](https://www.rust-lang.org/tools/install):
  `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh`
- Node.js 18+ (via [nvm](https://github.com/nvm-sh/nvm) or [Homebrew](https://brew.sh))

### Windows

- [Visual Studio Build Tools 2019+](https://visualstudio.microsoft.com/visual-cpp-build-tools/)
  with "Desktop development with C++"
- [WebView2](https://developer.microsoft.com/en-us/microsoft-edge/webview2/) (pre-installed on
  Windows 11)
- [Rust](https://www.rust-lang.org/tools/install)
- Node.js 18+

### Linux

- GTK3 dev libraries: `sudo apt install libgtk-3-dev libwebkit2gtk-4.1-dev`
- [Rust](https://www.rust-lang.org/tools/install)
- Node.js 18+

See the [Tauri prerequisites guide](https://tauri.app/start/prerequisites/) for full details.

---

## Setup

```bash
# 1. Clone the repository
git clone https://github.com/Unseen-Servant/unseen-server.git
cd unseen-server

# 2. Install frontend dependencies
npm install

# 3. Run in development mode (compiles Rust + starts frontend with HMR)
npm run tauri dev
```

> **Important:** Always use `npm run tauri dev`, not `npm run dev`.
> Plain `npm run dev` starts only the SvelteKit frontend in a browser — Tauri APIs
> (file system access, native dialogs) won't work there.

---

## Building for Production

```bash
npm run tauri build
```

This compiles the SvelteKit frontend, bundles it into the Rust binary, and produces a native
installer in `src-tauri/target/release/bundle/`.

---

## Other Scripts

```bash
npm run check         # TypeScript + Svelte type checking
npm run check:watch   # Type checking in watch mode
npm run preview       # Preview the production frontend build in browser
```

---

## Project Structure

```text
unseen-server/
├── src/                        # Frontend (SvelteKit + TypeScript)
│   ├── routes/
│   │   ├── +page.svelte        # Main UI: folder picker, file tree, selection state
│   │   └── +layout.ts          # Disables SSR (SPA mode for Tauri)
│   └── lib/
│       ├── FileTree.svelte     # Recursive file tree component
│       └── types.ts            # Shared TypeScript types (FileItem)
│
├── src-tauri/                  # Backend (Rust)
│   ├── src/
│   │   ├── lib.rs              # Tauri commands: select_folder, list_files
│   │   └── main.rs             # App entry point
│   ├── tauri.conf.json         # App config (window size, bundle ID, icons)
│   └── Cargo.toml              # Rust dependencies
│
├── static/                     # Static assets (favicon, etc.)
├── package.json
└── svelte.config.js
```

---

## Architecture: How Svelte Talks to Rust

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

| Command         | Description                                                 |
|-----------------|-------------------------------------------------------------|
| `select_folder` | Opens a native OS folder picker dialog, returns chosen path |
| `list_files`    | Reads a directory, returns `FileItem[]` (PDFs + subfolders) |

---

## Recommended IDE Setup

[VS Code](https://code.visualstudio.com/) with these extensions:

- [Svelte for VS Code](https://marketplace.visualstudio.com/items?itemName=svelte.svelte-vscode)
- [Tauri](https://marketplace.visualstudio.com/items?itemName=tauri-apps.tauri-vscode)
- [rust-analyzer](https://marketplace.visualstudio.com/items?itemName=rust-lang.rust-analyzer)

---

## License

MIT
