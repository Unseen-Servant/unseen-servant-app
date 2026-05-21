# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [2.0.1] - 2026-05-11

### Changed

- Upload release assets to R2 via a new publish-release workflow
- Include the version in R2 download filenames

### Fixed

- Add `--collect-all pymupdf`/`pymupdf4llm` to the release build, fixing a sidecar crash on import
- Apply sidecar entitlements at bundle time
- Bundle sidecars via externalBin instead of a resources glob
- Use the cargo `TARGET` in build.rs instead of `TAURI_ENV_TARGET_TRIPLE`

## [2.0.0] - 2026-05-10

### Security

- Enable a Content-Security-Policy for the app window
- Scope sidecar CORS to known Tauri origins

### Added

- Cross-encoder re-ranking of search candidates for sharper relevance (fastembed ONNX)
- Section-aware result expansion in search
- DAW-style solo and mute filters for game systems (per session, not persisted)
- Game system submenu in the right-click menu for tagging PDFs
- Keyboard `?` overlay listing all shortcuts
- Action keys (R/F/./M/C) on focused entries in the systems view
- Launch splash screen
- Ollama-down state surfaced in the results pane
- Deselect folder action in library settings
- Settings store schema validation, with a missing-folder toast at startup

### Changed

- Bump default search results from 5 to 15
- Include section headings in re-ranking input
- Pin cosine distance and clamp relevance scores to [0, 1]
- Clearer in-flight UX while a fresh search runs
- Filter menu: solo with the `S` key, keep keystrokes inside the menu, and hide curation and narrowing in tree view
- Migrate Modal and ConfirmDialog to the native `<dialog>` element and shrink-wrap height by default
- Plain Enter from a text input now saves in edit dialogs
- Bigger "+ tag" chip and viewport-clamped context-menu submenus that flip upward when there's more room above
- Streamline onboarding to folder + Ollama setup in a framed control-panel layout
- Restructure the Setup tab into a Help center
- Surface the Unseen Servant homepage in About
- Status bar polish: drop the license and guide icons, add a divider
- Sidecar now binds an ephemeral port behind a readiness gate, with reliable Windows process cleanup, and MCP re-resolves the port per request
- Cap the Ollama embed timeout and tighten streaming lock release
- Atomic re-index that drains embeddings on failure
- Validate rename inputs and make collection rename atomic
- Path-gated CI jobs (sidecar/rust/frontend) that cancel superseded runs
- Bundle PyMuPDF data files in the PyInstaller sidecar binary

### Fixed

- Coerce null section heading and game system to strings in search results
- Drop a brittle sidecar-connected pre-check that blocked searches
- Bind filter-menu label clicks to the checkbox instead of the solo button
- Focus the dialog element instead of the first focusable child when a modal opens
- Stop stranding keyboard focus on a hover-opened submenu trigger
- Preserve scroll position and row focus during rename (on open, save, and Esc)
- Show an actionable error when a file's cached path is stale on rename
- Stash the sidecar failure payload so a late-mounting UI still sees the error
- Clear the missing-folder toast once settings load successfully

## [1.1.5] - 2026-03-15

### Changed

- Remove stale MSI references from the release workflow and docs
- Update app identifier

### Fixed

- Fix pre-release version builds by dropping the MSI bundle target

## [1.1.4] - 2026-03-14

### Security

- Bump pypdf to 6.8.0 — limits allowed `/Length` value of streams, improves ASCIIHexDecode filter performance

### Added

- Dependabot config for automated dependency updates
- CI workflow for sidecar tests

### Changed

- Bump FastAPI from 0.134.0 to 0.135.1
- Bump ChromaDB from 1.5.2 to 1.5.5
- Bump GitHub Actions: checkout v6, setup-python v6, setup-node v6
- Updated license modal and sync metadata

### Fixed

- Fix flaky rename detection test using isolated subdirectory

## [1.1.3] - 2026-03-14

### Added

- Getting Started onboarding guide with Ollama health check
- Folder rename and delete with child propagation
- Direct sidecar calls for file rename and delete

### Fixed

- Fix release artifact rename to match Tauri output filenames
- Fix Getting Started modal title font to match License modal
- Restore mcpServers wrapper in MCP config copy output
- Coach MCP agent to search before assuming game systems are unavailable

## [1.1.2] - 2026-03-13

### Fixed

- Fix sidecar crash in production builds by adding codesign entitlements

## [1.1.1] - 2026-03-13

### Fixed

- Add timeouts to release workflow to prevent runaway builds

## [1.1.0] - 2026-03-12

### Added

- File selection highlight and right-click context menu
- Auto-sync renames, deleted files, and stale paths without user intervention
- Renamed PDF detection to avoid redundant re-indexing
- Reclaimable space tooltip and one-click database compaction
- Auto-sync interval and manual sync button in status bar
- Apple code signing and Windows build support

### Changed

- Redesigned status bar: consolidated actions, added icons and tooltips
- Shrunk header and made UI labels non-selectable
- Lifted expand state to page level to preserve tree across reloads
- Random batch sizes in sync progress for organic UI feel

### Fixed

- Fix chunk ID collisions with atomic writes
- Fix MCP binary not executable
- Fix WebKit accent-color rendering quirk with custom CSS checkbox
- Prevent text selection on right-click in file tree

## [1.0.1] - 2026-03-07

### Added

- License viewer accessible from the status bar
- LICENSE file bundled in the app distribution

### Fixed

- Corrected package.json license field from MIT to proprietary

## [1.0.0] - Unreleased

### Added

- Folder browser with recursive PDF tree, lazy loading, and persistent selection
- PDF indexing via ChromaDB with Ollama local embeddings (nomic-embed-text)
- Semantic search across indexed PDF library
- Game system tagging (D&D 5e, Pathfinder, etc.) with clickable badges
- Real-time sync progress with SSE streaming
- Double-click to open PDFs in system viewer
- MCP server with 7 tools for Claude Desktop integration
- One-click MCP config copy to clipboard
- System tray with background operation
- macOS .dmg distribution via GitHub Releases
