# Unseen Servant workstation — codebase architecture

**Date:** 2026-09-24
**Status:** decisions D1–D7 agreed 2026-09-24 and the six open questions in §4 resolved the same day. D1 shipped: product + identifier rename in v3.0.0 (published), repository renamed to `unseen-servant-app`. Step 1 (move-only split) done 2026-09-25; next is Phase 5 runtime (§6 order table).
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
| `tauri.conf.json` | `productName` "Unseen Servant", identifier `games.unseenservant.app` (renamed in v3.0.0 with a one-time data-dir migration in `lib.rs`), one implicit `main` window | window label + capabilities still to do (§2 D3) |
| capabilities | one file, `windows: ["main"]` | one file per tool window |
| settings | `tauri-plugin-store` (Rust-side JSON), no `localStorage` use in the app | store is shared across windows by construction; live cross-window reactivity to verify (§4) |

---

## 2. Decisions

### D1 — One repository, renamed

Repository renamed `unseen-legend-lore` → `unseen-servant-app`, paired with `unseen-servant-site` (GitHub redirects the old URLs; historical issue links in docs keep the old name). `productName` → "Unseen Servant", identifier → `games.unseenservant.app` — both shipped in v3.0.0, with `migrate_legacy_data_dir` moving the old app-data directory once. One version number for the whole app (`scripts/bump-version.sh` already touches the three files). Legend Lore becomes the name of a tool, not of the app. The MCP server key in the generated Claude Desktop config stays `"Legend Lore"` until the MCP server aggregates more than one tool; renaming it needs a config migration so users don't keep a dead entry.

**Rejected:** a repo per tool (three CI configs, cross-repo changes for every shell tweak, version coordination — for nothing, since no tool has an independent release cadence or an external consumer); workspaces (same reason, at the package level); a plugin/extension system (no third party will ever load a plugin).

### D2 — Tool folders inside each layer

```
src/lib/
  shell/          Header, StatusBar, SettingsModal, help/, Modal, dialogStack, confirmStore,
                  keybindings, KeyboardHelpOverlay, LaunchSplash, paneFocus, menuSlot,
                  notificationStore, OllamaStatus, storeParsers, tauriInvoke
  ui/             ActionButton, ConfirmDialog, CommitSwitch, confirmKeys, inputModality,
                  holdLatch, menuGeometry, icons, iconPaths
  legend-lore/    FileTree, SearchResults, SearchScopeBar, ContextMenu, collections*,
                  searchScope*, searchTiers, syncJob, GameSystems*, SystemsView,
                  DocumentStatsModal, palette (collection pigments), General/Library
                  settings panes, GettingStarted*, types, …
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
                            whole retrieval stack) + service.py (extraction, indexing,
                            stores, search pipeline) + router.py (the routes)
  command/                  vault read/write, current-session state + router.py (§4 Q4)
  servant/                  the paused agent harness, when it resumes
  server.py                 one FastAPI app; `include_router` per package
  mcp_server.py             one MCP server; registers each package's tools
```

Rules:

- **Tools never import each other's UI.** `src/lib/command/` may not import from `src/lib/legend-lore/`. Shared components go to `ui/`; shared workstation state goes to `shell/`.
- **Tool → tool inside the sidecar is a plain Python import**, one process. Tool → tool across the Rust/JS boundary is a Tauri command or an event, never a shared Svelte store (§4).
- **Command's state and vault I/O live in the sidecar** (`sidecar/command/`, decided §4 Q4). Not because CRUD over Markdown needs Python, but because the MCP server is an HTTP adapter over the sidecar (D5): putting Command there gives its MCP tools away for free, keeps one seam, and lets Legend Lore index the vault with an import. Rust stays the shell — window registry, sidecar lifecycle, tray, proxy commands — and Svelte calls Command through Tauri commands exactly as it calls Legend Lore.

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

## 4. Open questions — all resolved 2026-09-24

1. **plugin-store cross-window reactivity — yes, it broadcasts.** Verified in `tauri-plugin-store` 2.4.4 source: `Store::set` calls `app.emit("store://change", …)` (global, every window), and a second window loading the same path gets the same resource id, which is what the JS `onChange`/`onKeyChange` filter keys on. Settings need no new bus: the funnel (step 2a) subscribes with `onKeyChange` and every window follows.
2. **macOS `Reopen` when no window is visible → the last-focused window only.** Deliberate closes stay closed; when some window is visible, `has_visible_windows` is true and macOS just brings the app forward.
3. **Servant window shape → an ordinary window**, same class as the tools. Always-on-top can be added later if live play asks for it.
4. **Command's state lives in the sidecar, `sidecar/command/`.** `mcp_server.py` is a pure `httpx` adapter over the FastAPI routes, so MCP exposure needs an HTTP surface; the sidecar already is one. Rejected: Rust state plus a second local HTTP server (two servers, new dependency), and moving the MCP server into Rust (rewrites a working server before Command exists). D2 amended accordingly.
5. **The `games.unseenservant.command` data dir is from a throwaway spike.** Nothing to port; Command is greenfield. The directory is orphaned and can be deleted.
6. **MCP is kept for the user's own harness**, not for Claude Desktop (config removed 2026-09-24). D5 stands: the Servant consumes the same tool surface; the Claude Desktop installer in Getting Started is just one client of it.

---

## 5. Explicitly not doing

- Plugin / extension system, third-party tool loading.
- Workspaces (npm, cargo, uv).
- Per-tool versioning or per-tool release cadence.
- A launcher / hub window with nothing on it — the tray already is the hub.
- Micro-frontends, iframes, or separate bundles per tool.
- Cross-window drag-and-drop (D4).

---

## 6. Next steps

Each step is independently shippable; the tree is releasable after every one. Steps 1–3 are Legend-Lore-only work and ship as v3.x; nothing in them is user-visible except 2c. Steps 4–5 are the new tools.

### Order across workstreams (decided 2026-09-24: Phase 5 before Command)

The retrieval roadmap's Phase 5 (`2026-09-02-v2-retrieval-improvement-roadmap.md` §4, decision in §8) was ruled GO for both swaps on the v3.0.0 numbers. It interleaves with the steps below like this:

| # | Work | Track | Why here |
|---|---|---|---|
| 1 | Step 1 — move-only split (1a/1b/1c) | shell | Days, zero behaviour change. Precedes Phase 5 so the store/embedder rewrite lands inside `sidecar/legend_lore/` instead of a 4 300-line file that then moves a second time. |
| 2 | Phase 5 runtime — Ollama → in-process bge-m3 ONNX | retrieval | Biggest user-visible win left (no prerequisite, no `OLLAMA_CONTEXT_LENGTH` foot-gun, no cold cliffs) and a prerequisite for both new tools, which embed vault notes and prompts on the fly. Drops "Ollama status" from step 3's list. Ships as **v3.1.0**. |
| 3 | #330 — filename-addressed mutations hit twins | retrieval | Small correctness bug in the routes 1b just moved; fix while that code is fresh. |
| 4 | Command design doc | shell | No code; written alongside 2–3. Decides what the vault looks like, which is what steps 2–3's shell has to serve — building the shell first is scaffolding for a guess. |
| 5 | Phase 5 store — Chroma → sqlite-vec | retrieval | One-shot vector migration, no reindex. Closes #170, retires Compact and the orphan GC, gives Command's vault index a transactional home in the same SQLite. Ships as **v3.2.0**. |
| 6 | Steps 2–3 — settings funnel, window label, registry, cross-window state | shell | Invisible; done right before the thing that needs it. |
| 7 | Step 4 — Command | shell | **v4.0.0**, the second tool. |
| 8 | Step 5 — Servant | shell | Needs 2 (local embedding) and 7 (something to command). |
| — | #329 — two-column reading order | retrieval | Parked explicitly: PDFium was a NO-GO and no cheap fix is known. Pick up when a book used at the table is wrong. |

Harness growth (#368, #369) and the Phase 2 residuals are pulled in only when a retrieval change needs them as a gate.

### Done (2026-09-24)

- D1: product name, bundle identifier + data-dir migration (v3.0.0, published); repository → `unseen-servant-app`.
- `scripts/build-sidecar.sh` forces `+x` on the staged sidecar binaries — the local validation build silently shipped non-executable sidecars before.

### Step 1 — move-only split (no behaviour change)

Three slices, each its own commit, each verified by the full Linux suite plus `npm run tauri dev` behaving identically:

| | Slice | Verify |
|---|---|---|
| 1a | `src/lib/` → `shell/`, `ui/`, `legend-lore/` per D2; tests move with their modules; `+page.svelte` → `routes/legend-lore/+page.svelte` with the root route redirecting there | vitest 462 green, svelte-check 0 errors, stylelint green |
| 1b | `sidecar/server.py` → `sidecar/legend_lore/router.py` (`APIRouter`, the 37 routes) + the retrieval modules; `server.py` keeps app construction, lifespan, health, `include_router`; `tests/` imports and both PyInstaller `.spec` files follow | pytest green; `bash scripts/build-sidecar.sh` produces working binaries |
| 1c | `src-tauri/src/lib.rs` → `legend_lore.rs` gets the sidecar-proxy commands (`check_sidecar_health` … `update_search_settings`); `lib.rs` keeps `run()`, sidecar lifecycle, tray, window handling | `cargo fmt --check`, clippy `-D warnings`, `cargo test` green |

**1a done 2026-09-25.** Placement follows D2 as amended above; three files moved against the first sketch because of what they contain: `ContextMenu` is the file-tree menu (collections, systems, solo/mute) and `palette` is the collection pigments, so both are Legend Lore; the General and Library settings panes are Legend Lore panes hosted by the shell's `SettingsModal`. That hosting is the one shell → tool import left (`SettingsModal`, `help/GuidesPane` → `GettingStartedSteps`); it goes away when the D3 manifest carries each tool's settings panes.

**1b done 2026-09-25.** `server.py` (285 lines) keeps CLI/port file, `create_app`, CORS, `/health` and the MCP heartbeat/status routes (workstation-level: the MCP server will aggregate every tool), the watchdog and `__main__`. The 34 Legend Lore routes are `legend_lore/router.py`'s `build_router(app, collection, data_dir, …)`, a factory whose closures are the old `create_app` body verbatim. The ~2 400 lines of module-level helpers the routes call became `legend_lore/service.py` — they could not stay in `server.py` without a circular import. The twelve retrieval modules moved into the package with relative imports. Tests patch where the call now happens (`service.rerank_scores`, `router.index_single_pdf`, …). Frozen binary serves the same 37 operations. Further splitting of `service.py` is left to Phase 5, which rewrites its embedder and store halves anyway.

**1c done 2026-09-25.** `legend_lore.rs` holds the 30 Legend Lore commands (library file system, index/sync, stats, game systems, collections, search, search settings), their response types and the rename-validation tests. Commands and the types in their signatures became `pub`, which Tauri needs for commands in a submodule. `lib.rs` keeps `run()`, sidecar lifecycle, port and `sidecar_url()`, the sidecar/Ollama/MCP health checks (shell state, lifted to Rust in step 3, so they stay beside it rather than following the doc's `check_sidecar_health …` range), `get_data_dir`, `get_mcp_config`, tray and window handling.

### Step 2 — the shell assumes many windows (still one window)

| | Slice | Verify |
|---|---|---|
| 2a | Settings funnel: one `shell/settings.ts` owns every `tauri-plugin-store` read/write (today `+page.svelte` and `storeParsers.ts` call it directly) and subscribes with `onKeyChange`, which the plugin already broadcasts to every window (§4 Q1) | vitest; a setting changed in Settings is read back through the funnel only |
| 2b | Window label `main` → `legend-lore`: `tauri.conf.json`, capability file, `Reopen`, `save_window_size`. Resets saved geometry once | relaunch restores geometry after the second launch |
| 2c | Rust window registry: `open_tool(id)` (focus-or-create), `tools.ts` manifest, **Window** menu + tray entries, remembered set of open windows; per-window capability files | `npm run tauri build` locally (with the exec-bit fix); tray Quit saves every window; relaunch reopens the same set |

### Step 3 — cross-window state

Lift Ollama status, sidecar health and sync/reindex progress to Rust source of truth with `emit` to all windows (settings are already covered — §4 Q1). **Verify:** dev-only, open two windows on the same route, start a sync — both status bars reflect it. Do this **before** Command exists so the second tool lands on a shell that already assumes multiple windows.

### Step 4 — Command

Greenfield (§4 Q5). Second window; Svelte UI over Tauri proxy commands; state and vault I/O in `sidecar/command/` (§4 Q4, D6); its MCP tools registered in `mcp_server.py`. Needs its own design doc before code. **Verify:** an MCP client lists Command tools beside Legend Lore's; Send-to-Command round-trips a search hit.

### Step 5 — Servant

An ordinary window (§4 Q3), MCP client over both tools (D5). **Verify:** a scripted tool-call transcript reproduces a session-prep task end to end.

### Outside this repository

- `unseen-servant-site`: product copy and download links → `Unseen-Servant_<ver>_aarch64.dmg` / `Unseen-Servant_<ver>_x64-setup.exe`.

---

## 7. Related

- [2026-08-14-agent-harness-retrieval-findings.md](2026-08-14-agent-harness-retrieval-findings.md) — the Servant's Phase 1 state and why it is paused.
- `CLAUDE.md` — product vision, CI budget rules, design conventions (the tokens in `src/app.css` apply to every window).
