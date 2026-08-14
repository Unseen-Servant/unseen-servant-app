# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Changed

- The filter console's `[clear all]` is now `[reset]`, and it answers for the whole panel: every solo and mute, plus the focus lens, show-hidden and hide-unindexed switches below it, which it used to leave lit. It sits dim until something is actually engaged. Files you've hidden by hand stay hidden — the Hidden items section keeps its own Clear for those
- **Search is `⌘K`, the Filters panel is `⌘F`.** Search moves to the chord command bars everywhere use, which frees `F` for the thing it actually reads as: filtering. `⌘⇧F` no longer does anything
- **Every confirmation is the app's own.** Deleting a file or folder and re-indexing a single file raised a system dialog in the operating system's chrome; they now use the same prompt the rest of the app does, so the same `⌘⌫` looks the same in the file tree as it does in the collections panel
- Deleting a custom game system, and resetting a customized built-in to its defaults, now ask first — neither did
- **Danger red means one thing again.** Cancel and Discard no longer turn red under the pointer — hovering only brightens — so red marks the action that actually destroys something. The Danger Zone's two-step arms with a tinted wash instead of filling solid red, matching the mute button
- **Dialog actions are bracketed text** — `[Cancel]`, `[Delete]` — the affordance the app already spends on `[Compact]` and `[R]`, instead of a checkmark or cross beside the label. Icon-only buttons keep their glyph; the two are alternative markers, not a pair
- The Game Systems editor's footer is one family of buttons instead of three
- Dialogs fade and scale in rather than appearing instantly, and hold still if your system asks for reduced motion. Their close × is a lighter glyph that no longer outshines the rest of the title bar, and every dialog now draws from one set of width and padding steps
- The keyboard shortcut sheet brackets its single-key chords — `[R]`, `[X]` — the way the menus already do, so a lone letter reads as a key rather than a stray capital
- A file's Info dialog is titled with the filename, with its full path beneath it, and the game system moves out of the cramped five-column readout onto its own line where a multi-system file fits
- **Tap latches, hold is momentary.** Holding `S`, `M` or `P` engages it only while the key is down and puts it back when you let go, the way a hardware transport works — peek at one book alone mid-search without dismantling a scope you spent prep time building. Tapping still latches, exactly as before
- **`B` bypasses the whole scope console** — every indexed file back in scope, for A/B'ing a thin result against your own filters. Hold to peek or tap to latch. Nothing is cleared: the chips dim rather than disappear, so you can see what's being passed through, and a `BYPASS` lamp shows in the status bar. Not remembered across launches
- **The scope bar names itself and carries the bypass switch.** It used to render empty until something narrowed — present but blank, and nothing you could learn from. It now always shows a `Scope` nameplate, a `B` switch beside it, and, when nothing is narrowed, the number of files a search would run against. The switch sits inert until there's a scope to bypass
- Engaging a solo or mute snaps — one bright frame as the switch reaches its position

### Fixed

- **Bypass now reaches every dim it should.** While `B` is engaged the systems view no longer keeps muted and non-soloed groups dimmed (or hidden, under the focus lens), and a soloed Collected/Loose bucket no longer keeps rows out of the systems view — search already saw all of it; now the browsing surfaces agree. The S/M buttons stay lit through it, as before
- The scope bar's `hidden shown`, `indexed only` and `lens on` chips no longer dim under bypass — bypass doesn't suspend those switches, and the dim claimed it did
- Pressing `B` over an empty console no longer lights the `BYPASS` lamp for nothing — the key now refuses exactly what the scope bar's inert switch refuses
- Soloing combinations that intersect to nothing — a system solo with no file under a soloed folder, say — now say "Nothing under the soloed items." instead of a generic no-results message beside a meter reading "of 0 files"
- The hits meter no longer claims its count came from your scope while the scope is bypassed — the number was already the whole library, but the tooltip said otherwise
- Enter no longer commits a destructive prompt when Cancel is focused. Destructive prompts open on Cancel so that Enter from muscle memory is harmless, and that focus is now visible — it was being drawn without a ring whenever the prompt was raised by mouse

## [2.2.0] - 2026-08-11

### Added

- **Arm a collection** — a record-arm (●) beside play and mute on every collection row. Arming points the file tree at that collection: click a book to file or unfile it on the spot, tick a folder to enrol everything indexed beneath it. No Save, no Cancel, and no view switch. `E` arms and disarms, `Esc` leaves
- **Drag books and folders onto a collection** — from the file tree or the systems view, onto a collection row, its expanded file list, or "+ New collection…" to seed a fresh one named after what you dragged. Folders drag as a unit and their count is named before and after the drop
- Collection membership shows in the tree and systems view as a pigment ribbon strip on file rows — up to two, plus a `+N` that accounts for the rest
- A hover × on the panel's expanded file rows removes that book from the collection
- Every collection row reads out its file count, in the same inverted LED box the filter console uses per channel
- Play and Mute join the collection's context menu, which now leads with the transport — Arm, Play, Mute — before the track's properties
- `⌘⌫` (`Del` off mac) deletes the focused row in both the file tree and the collections panel

### Changed

- **Naming a new collection happens in the "+ New collection…" box** — the box becomes the name field in place, and committing promotes it to a row in the list, created, focused and armed. `⌘N`, the box itself, a folder's context menu and a drop onto it all land there, the last two pre-filling the field with the folder's name. No draft row, no Save, no Cancel, and nothing exists until you commit, so Esc costs nothing. The box also shows its `⌘N` chord
- Editing a collection's files no longer goes through the context menu, and curating is not modal: search, scope chips, out-of-scope dimming, and disk-change detection all stay live throughout
- Membership writes are coalesced and strictly serialized, so a long curation sweep is a handful of writes rather than one per click, and a failed write reverts to the last saved state instead of half-applying
- **Row keys are consistent across the panes.** `R` renames in every pane that has something to rename (new in the collections panel), and `X` ticks the row's checkbox wherever a row has one
- **A file-tree row has one checkbox, and arming changes what it means.** Unarmed it marks the file for indexing, in parchment — the colour this app reserves for content and data. Armed it files the file into the collection being curated, in purple — the colour reserved for a mode you switched on, and the same box the systems view has always shown. Rows with nothing indexed under them show the box disabled while armed, since a collection can't hold them. Shift-click extends a range, as it already did for indexing
- **Search no longer blocks the sidecar.** Each query runs on a worker thread, at most four at once, so health checks, MCP heartbeats and everything else answer in milliseconds while a search is in flight instead of waiting it out
- The embedding model is kept warm — one token re-embedded every four minutes, so an idle bge-m3 isn't unloaded and the first search after a lull doesn't pay a full model load. `OLLAMA_KEEPALIVE_INTERVAL_SECONDS=0` turns it off
- The window opens at 940×600 — the width where all three panes just fit — and remembers its size across launches in logical pixels, so a size saved on one display comes back right on another
- The status bar moved onto the header plate and the search bar is recessed into the panel surface, so the two bars bracketing the workspace match and the header's two inlays share one depth
- The search bar shows its focus chord while empty, and the view switch keeps a dimmed mark on the view you'd return to while search is up
- The Loose curation row draws a dashed ribbon where it used to hold an empty spacer
- MCP server migrated to mcp 2.0 (`FastMCP` → `MCPServer`) — the same four tools with the same arguments
- Refreshed Rust, npm, and sidecar dependencies

### Removed

- `Space` and `Enter` as row actions in the file tree, systems view and filter panel, and `Enter` in the collections panel. `Space` still runs a collection's play/stop transport, and `Enter` still submits a search, opens a search result, activates a context-menu item, and commits any text field. Use `R` to rename, `X` to tick a checkbox, `⌘O` to open a file, and `→`/`←` to walk folders
- `⌘↵` (Save in-progress collection) — there is nothing left to save
- `F2` as a second spelling of rename — `R` renames in every pane

### Fixed

- Systems view: a game system's "select all" checkbox no longer latches. Unticking the last file in a system left its header still showing selected
- Creating a collection no longer switches the main pane to the systems view and leaves it there permanently — a bug that persisted across restarts for anyone who worked in tree view
- A trackpad flick no longer rubber-bands the whole app and uncovers a dark band at the window edge
- The filter panel's lens checkboxes light purple again instead of parchment — purple is the colour this app reserves for a mode you switched on
- The search bar's clear button draws as × in the app's own face, instead of falling through to a system font

## [2.1.0] - 2026-08-09

### Added

- Relevance tiers — results read as **strong / good / weak** instead of a raw "% match", with weak matches dimmed below a floor so noise reads as noise
- Table row-linearization: tables are split into per-row embed units, so a lookup lands on the exact row of a spell or equipment table, with a coverage-ratio tripwire that flags lossy table parses
- Spell correction: misspelled query tokens are rewritten against your library's own vocabulary ("owlber" → "owlbear") before searching, and results say what was corrected
- Game-system soft-boost — naming a system in the query ("fireball in 5e") lifts that system's results without hiding the rest of the library
- Startup probe that detects silent Ollama embed truncation and warns in the sidecar logs
- General settings tab with sidecar-wide search-pipeline knobs, including a candidate pool preset from Fastest (10) to Exhaustive (200)
- Solo/mute/play scope doctrine: a mixer-style filter console, a play/stop transport on collections, archive as shelving, and a focus lens that hides out-of-scope items
- Scope bar with system and collection chips, pinned above the scrolling tree and systems views
- Full console recall — solo, mute, play, and lens state persist across launches
- Stateful search view: focusing the search bar opens it, and Escape, a view switch, or ⌘J / ⌘T step back out
- Pane focus model for keyboard navigation, with keyboard chords shown on menu rows
- Space as the primary action on a focused row, X to toggle the indexing checkbox, ⌘⇧F for the Filters panel, and ⌘⌥↑/↓ to move within the left dock
- "Hide unindexed items" switch with a matching indexed-only scope chip
- Window opens at 1280×800 and remembers its geometry across launches
- Retrieval eval harness with answer-chunk grading, per-query latency, and a recorded baseline
- Experimental, default-off search flags: `hybrid` (BM25) and `variant_expansion`

### Changed

- Shared header voice classes, an LED pip in place of the menu checkmark, and menu geometry driven by tokens and real measurements
- Game systems go monochrome — color is now reserved for collections — over a manuscript-pigment palette
- Amethyst re-grounded as the active hue and vermilion as danger, with a brighter tertiary text token for WCAG contrast on the app background
- Mono font, radii, and modal shadow moved onto tokens; stylelint now forbids raw colors in component styles
- Filter console and collections became docked sibling panels, with a view-switch picker in the header
- MCP: near-miss filter values (typos, partial names) resolve to the closest match instead of failing silently; `list_collections` reports file counts and descriptions; results carry match tiers
- Sidecar hard-cap splitter cuts on row boundaries instead of mid-row
- Tag metadata updates are batched past ChromaDB's write cap
- Accessibility: menu roles and `aria-checked`, chords exposed via `aria-keyshortcuts` rather than the accessible name, and view rows as `role=checkbox` buttons

### Fixed

- Untagged-mute drop and same-named-file scoping leaks
- A saved tag no longer rolls back when the status refresh fails
- Tauri errors now include the sidecar response body
- File renames migrate path solos and mutes like every other path set
- Only one menu stays open at a time, and Escape no longer closes the docked filter panel
- Archived collections stay off both collection submenus
- Context-menu actions no longer fire against a nulled menu state
- Empty-state messaging is centralized and truthful on every surface

## [2.0.2] - 2026-07-02

### Changed

- Migrate the sidecar to uv and Python 3.12
- Drop cross-platform smoke jobs from CI and document the billable-minutes budget policy
- Refresh Rust, npm, and sidecar dependencies

### Fixed

- Raise the MCP client timeout
- Skip the English-only reranker on non-ASCII queries

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
