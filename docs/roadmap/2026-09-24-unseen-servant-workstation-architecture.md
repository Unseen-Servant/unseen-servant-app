# Unseen Servant workstation — codebase architecture

**Date:** 2026-09-24
**Status:** proposed. Decisions D1–D7 agreed in discussion; sequencing (§7) not started.
**Objective:** grow this repository from one tool (Legend Lore) into the GM workstation — one app, **Unseen Servant**, hosting three tools: Legend Lore (RAG over the PDF library), Command (session manager), and the Servant (assistant) — without a rewrite, a plugin system, or a second repository.

---

## 0. TL;DR

- **One repo, one Tauri app, one sidecar process.** No multi-repo, no npm/cargo/uv workspaces, no plugin architecture. Solo dev, three tools that always ship together under one version number — every boundary those would add has nobody on the other side of it.
- **Tool folders inside each layer, not layers inside tool folders.** The build boundaries are per layer (Vite → `src/`, Cargo → `src-tauri/`, PyInstaller → `sidecar/`), so each layer gets `legend-lore/`, `command/`, `servant/` plus a `shell/` for what the workstation itself owns.
- **One window per tool.** Each tool is a `WebviewWindow` whose label is the tool id and whose title is the tool name; the app name (dock, menu bar, tray, About) is Unseen Servant. Rust owns the window registry. This is the DAW model — arrange / mixer / floating plugin windows — and it is what a GM with a laptop and a second screen at the table actually wants.
- **Every window is its own JS context.** Anything two windows must agree on has Rust or the sidecar as source of truth, with windows subscribing via Tauri events. Svelte stores are per window by definition.
- **The seam between tools is the MCP tool surface.** Legend Lore already exposes its tools; Command exposes its state the same way; the Servant is an MCP client of both — it gets exactly what Claude Desktop gets, no privileged back door.
- **The vault is the user's, indexes are caches.** Authored data (sessions, notes, NPCs) is plain Markdown/YAML in a user-chosen folder; derived data (embeddings, FTS, parents) lives per tool in app-data and is rebuildable.
- **First step is a move-only refactor** of the 90-file flat `src/lib/` and the 4 300-line `server.py` into tool folders, before Command exists — cheap now, expensive once a second tool is interleaved.

---

## 1. Where the code is today

| Layer | State | Multi-tool readiness |
|---|---|---|
| `src/lib/` | ~90 files, flat: shell chrome (Header, StatusBar, Settings*, Modal, dialogStack, keybindings, palette, paneFocus), design primitives (ActionButton, ConfirmDialog, ContextMenu, icons), and Legend Lore (FileTree, SearchResults, collections*, searchScope*, syncJob) all siblings | needs the split (§3) |
| `src/routes/` | one route, `+page.svelte` is Legend Lore | needs one route per tool |
| `src-tauri/src/lib.rs` | 2 100 lines: sidecar lifecycle, ~30 commands proxying the sidecar, tray, window hide-on-close, per-label `save_window_size` | sidecar is already app-owned (stopped on `RunEvent::Exit`, not on window close); tray already keeps the app alive with no visible window — the multi-window model extends this rather than replacing it |
| `sidecar/server.py` | 4 300 lines, 37 routes, one FastAPI app | needs `include_router` per tool package |
| `sidecar/mcp_server.py` | 570 lines, Legend Lore tools only | becomes the aggregator |
| `tauri.conf.json` | `productName` "Legend Lore", identifier `games.unseenservant.legendlore`, one implicit `main` window | rename (§2) |
| capabilities | one file, `windows: ["main"]` | one file per tool window |
| settings | `tauri-plugin-store` (Rust-side JSON), no `localStorage` use in the app | store is shared across windows by construction; live cross-window reactivity to verify (§4) |

---

## 2. Decisions

### D1 — One repository, renamed

Rename `unseen-legend-lore` → `unseen-servant` (GitHub redirects the old URL; update the local remote). `productName` → "Unseen Servant", identifier → `games.unseenservant.app`, one version number for the whole app (`scripts/bump-version.sh` already touches the three files). Legend Lore becomes the name of a tool, not of the app.

**Rejected:** a repo per tool (three CI configs, cross-repo changes for every shell tweak, version coordination — for nothing, since no tool has an independent release cadence or an external consumer); workspaces (same reason, at the package level); a plugin/extension system (no third party will ever load a plugin).

### D2 — Tool folders inside each layer

```
src/lib/
  shell/          Header, StatusBar, Settings*, Modal, dialogStack, confirmStore,
                  keybindings, palette, paneFocus, menuSlot, notificationStore, OllamaStatus
  ui/             ActionButton, ConfirmDialog, ContextMenu, CommitSwitch, icons, iconPaths
  legend-lore/    FileTree, SearchResults, SearchScopeBar, collections*, searchScope*,
                  searchTiers, syncJob, GameSystems*, SystemsView, DocumentStatsModal, …
  command/
  servant/
  tools.ts        the tool manifest (§2 D3)
src/routes/
  +layout.svelte            per-window chrome: status bar, dialog stack, keybinding scope
  legend-lore/+page.svelte
  command/+page.svelte
  servant/+page.svelte
src-tauri/src/
  lib.rs                    shell: sidecar lifecycle, tray, window registry, settings
  legend_lore.rs            the ~30 sidecar-proxy commands that live in lib.rs today
  command.rs
  servant.rs
sidecar/
  legend_lore/              chunker, lexical, reranker, spelling, parents_store, … (the
                            whole retrieval stack) + router.py
  servant/                  the paused agent harness, when it resumes
  server.py                 one FastAPI app; `include_router` per package
  mcp_server.py             one MCP server; registers each package's tools
```

Rules:

- **Tools never import each other's UI.** `src/lib/command/` may not import from `src/lib/legend-lore/`. Shared components go to `ui/`; shared workstation state goes to `shell/`.
- **Tool → tool inside the sidecar is a plain Python import**, one process. Tool → tool across the Rust/JS boundary is a Tauri command or an event, never a shared Svelte store (§4).
- **Command probably has no Python.** The sidecar exists for the ML stack. A session manager is CRUD over Markdown — Rust + Svelte covers it. Only the Servant (inference orchestration, where the paused Phase 1 harness already lives in Python) joins Legend Lore in the sidecar. Put Command in the sidecar only if it grows a need that is actually Python-shaped.

### D3 — One window per tool, Rust owns the registry

Each tool is a `WebviewWindow` opening a route of the same SvelteKit bundle:

```rust
WebviewWindowBuilder::new(app, "legend-lore", WebviewUrl::App("legend-lore".into()))
    .title("Legend Lore")
    .inner_size(1280.0, 800.0).min_inner_size(940.0, 600.0)
    .build()?;
```

- **Window label = tool id.** Titles are tool names ("Legend Lore", "Command", "Servant"); the app identity lives in the dock / menu bar / tray / About as Unseen Servant. No "Legend Lore — Unseen Servant" suffix.
- **One Rust command, `open_tool(id)`:** focus the window if it exists, create it otherwise — single instance per tool. Creation stays in Rust so the frontend never needs `core:webview:allow-create-webview-window`, and so Rust is the only place that knows which windows exist.
- **Reachable from:** the native **Window** menu (Legend Lore / Command / Servant), the tray menu (which already exists), the command palette in every window, and optionally a global shortcut that summons the Servant from anywhere (`tauri-plugin-global-shortcut`).
- **The manifest** (`src/lib/tools.ts`) is a typed object, not a plugin loader:

  ```ts
  export const tools = {
    'legend-lore': { label: 'Legend Lore', route: '/legend-lore', keybindings: …, paletteCommands: … },
    command:       { … },
    servant:       { … },
  } as const;
  ```

  The layout reads it for the palette and keybinding scopes; Rust carries its own copy of the window defaults (title, size) because window creation happens there.
- **Close = hide** stays as it is today (`CloseRequested` → `prevent_close` + hide, app alive in the tray). What changes: `Reopen` on macOS shows the last-focused window, not `main`; the tray Quit path saves every window's geometry, not `main`'s.
- **Startup restores the layout.** The existing per-label `save_window_size` already keys on the label; extend the same store entry with the *set* of windows visible at quit, and reopen that set on launch. First launch: Legend Lore only. If this grows past a screen of code, swap for `tauri-plugin-window-state`.
- **One capability file per window.** `legend-lore.json` keeps the current `opener`/`dialog`/`clipboard`/`store` grants; `servant.json` gets `core:default` and `store:default` only. Free least-privilege.

**Rejected:** a single window with a tool rail / tabs. It works, but it puts the tools in competition for one viewport, which is the opposite of what live play needs (rulebook search on the second screen while the session view stays up), and it would have shipped a one-item rail until Command exists.

### D4 — Every window is its own JS context

Svelte stores do not cross windows. Rule: **if two windows must agree on it, Rust or the sidecar is the source of truth and windows subscribe.**

| State | Today | Under multi-window |
|---|---|---|
| `dialogStack`, `confirmStore`, `paneFocus`, `notificationStore`, `keybindings`, `menuSlot`, `dragPayload` | Svelte store | **per window — correct as is.** A confirm in Command must not block Legend Lore. |
| settings (`searchSettings`, library folder, game systems, general) | `tauri-plugin-store`, read into stores | persistence is already shared. Verify plugin-store's change events reach every window; if they do, settings are solved by subscribing. If not, `emit("settings-changed")` from the writer. |
| Ollama status, sidecar health | polled from the one webview | Rust polls once, `emit`s to all windows; windows render. |
| sync-job / reindex progress (`syncJob.ts`, SSE streams) | one webview owns the stream | the stream stays owned by whichever window started it, but progress is mirrored through Rust state + `emit` so a second window's status bar shows it too. |

Cross-window drag-and-drop **does not work** — HTML5 DnD cannot cross webviews. "Drag a search hit into the current scene" becomes an explicit **Send to Command** context-menu / palette action routed through a Rust command. `dragPayload.ts` stays for in-window drops. This is the keyboard-reachable form of the gesture anyway.

`localStorage` is shared across windows of one Tauri app (same origin) but must not be used as a bus — no reliable cross-webview `storage` event. The app uses none today; keep it that way.

### D5 — The seam between tools is the MCP tool surface

Legend Lore already exposes `search`, `compare`, random tables, … as MCP tools. **Command exposes its state the same way** — `current_session`, `active_scene`, `npc_roster`, `add_note`, … — and **the Servant is an MCP client of both**.

What this buys:

- The Servant is testable as a sequence of tool calls, with no hidden coupling to window state.
- Anything the in-app assistant can do, an external agent (Claude Desktop, a CLI) can do too. This is "no lock-in" applied to the AI layer.
- Cross-tool coupling exists in exactly one place. UI → own tool is Tauri commands / FastAPI routes as today; the Servant → any tool is MCP; nothing else.

### D6 — The vault is the user's; indexes are caches

Command's data — sessions, scenes, notes, NPCs — is Markdown/YAML in a user-chosen vault folder (the Obsidian model), not rows in ChromaDB or SQLite. **Authored data lives in the vault as plain text; derived data lives per tool in app-data and is rebuildable.**

A consequence to keep in mind, not a requirement: Legend Lore can grow a Markdown ingestion path and index the vault, so the Servant searches session notes with the same tools it uses for rulebooks.

### D7 — CI is unchanged in shape

Still Linux-only on push to main, still cross-platform only on `v*` tags. Path gates gain per-tool globs (`src/lib/command/**` → frontend-checks; `sidecar/servant/**` → sidecar-tests). No new billable-minute exposure.

---

## 3. What has to move (step 1 in detail)

A move-only refactor — no behaviour change, tests green before and after.

- `src/lib/` → `shell/`, `ui/`, `legend-lore/` per the table in D2. Tests move with their modules. `+page.svelte` becomes `routes/legend-lore/+page.svelte`; the root route redirects there until D3 lands.
- `sidecar/server.py` → `sidecar/legend_lore/router.py` (the 37 routes, as an `APIRouter`) + the module files it imports; `server.py` keeps app construction, lifespan, health, and `include_router`. Imports in `tests/` and the PyInstaller `.spec` files follow.
- `src-tauri/src/lib.rs` → `legend_lore.rs` gets the sidecar-proxy commands (`check_sidecar_health` … `compact`, roughly lines 532–850 today); `lib.rs` keeps `run()`, sidecar lifecycle, tray, window handling, settings.

---

## 4. Open questions

1. **plugin-store cross-window reactivity** — does `store.onChange` fire in window B when window A writes? Decides whether settings need any new code at all (D4).
2. **macOS `Reopen` target** — last-focused window, or every window that was visible before the app lost all of them? Decide when D3 lands; either is a few lines.
3. **Servant window shape** — floating always-on-top palette vs. ordinary window. Defer to the Servant's own design pass; the registry does not care.
4. **Where "current session" lives** — Rust state fed from the vault, or the sidecar? Affects whether Command's MCP tools are served by the Python MCP server or need a Rust-side bridge. Decide with the Command design doc.

---

## 5. Explicitly not doing

- Plugin / extension system, third-party tool loading.
- Workspaces (npm, cargo, uv).
- Per-tool versioning or per-tool release cadence.
- A launcher / hub window with nothing on it — the tray already is the hub.
- Micro-frontends, iframes, or separate bundles per tool.
- Cross-window drag-and-drop (D4).

---

## 6. Sequencing

Each step is independently shippable; the tree is releasable after every one.

| # | Step | Verify |
|---|---|---|
| 1 | Move-only split of `src/lib/`, `server.py`, `lib.rs` into tool folders (§3) | vitest, pytest, svelte-check, clippy green; `npm run tauri dev` behaves identically |
| 2 | Rename repo + product + identifier; Rust window registry (`open_tool`), per-window capabilities, layout restore, with Legend Lore as the sole window at label `legend-lore` | `npm run tauri build` locally; relaunch restores geometry; tray Quit saves it |
| 3 | Lift Ollama status, sidecar health, sync progress (and settings if §4 Q1 says so) to Rust source of truth + events | dev-only: open two windows on the same route, change a setting / start a sync, both windows reflect it |
| 4 | Command as second window — Rust + Svelte, Markdown vault, its MCP tools registered in `mcp_server.py` | Claude Desktop lists Command tools alongside Legend Lore's; Send-to-Command action round-trips a search hit |
| 5 | Servant as a window, MCP client over both | a scripted tool-call transcript reproduces a session-prep task end to end |

Step 3 is the one that is easy to skip and expensive to retrofit: do it **before** Command exists so the second tool lands on a shell that already assumes multiple windows.

---

## 7. Related

- [2026-08-14-agent-harness-retrieval-findings.md](2026-08-14-agent-harness-retrieval-findings.md) — the Servant's Phase 1 state and why it is paused.
- `CLAUDE.md` — product vision, CI budget rules, design conventions (the tokens in `src/app.css` apply to every window).
