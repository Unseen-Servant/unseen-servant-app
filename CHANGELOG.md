# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

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
