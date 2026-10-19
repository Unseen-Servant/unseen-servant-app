# Contributing to Unseen Servant

Thank you for helping. Unseen Servant is open so you can read it, fix it, run it
on your machine and build on it, but it has one designer, and its direction
stays with its maintainer. That decides which help goes furthest.

## What helps most

- **Bug reports:** crashes, wrong results, anything that broke after an update.
- **Stability fixes:** hangs, failed launches, state that doesn't survive a
  restart.
- **Portability:** Windows, Intel Macs, Linux, odd PDFs, network shares, slow
  disks. The maintainer works on an Apple Silicon Mac, CI runs on Linux, and
  macOS and Windows builds happen only at release, so your platform catches
  what nothing else does.
- **Performance** on large libraries, from hundreds to thousands of PDFs.

## What needs a conversation first

New features, interface or design changes, and new dependencies. Open an issue
that describes the problem before writing code. Most feature ideas will be
declined to keep the tool small, and a pull request that arrives unannounced
may be closed without review. That's no judgement on the work.

Two rules aren't up for discussion:

- **Local-first.** Indexing and search run on the user's machine. No change may
  make them depend on a remote service; downloading a model once is the only
  exception.
- **Plain files.** Campaigns stay Markdown and JSON Canvas that other tools can
  open.

The building blocks for your own tools are the MCP server (Help → Reference
lists its tools) and the campaign folder itself.

## Reporting a bug

Open an issue with the bug report template. It asks for the app version
(Help → About), your OS, your Ollama version and the size of your library. For
search or indexing problems, attach `sidecar.log`: **reveal** next to the data
directory in Help → About opens its folder. Copy the log before reopening the
app, because every launch starts a new one.

Found a security problem? Email guild@unseenservant.games instead of opening an
issue.

## Contributor License Agreement

Before your first pull request can merge, you sign the
[Contributor License Agreement](CLA.md). The CLA Assistant bot asks for it on
the pull request, and once covers every later contribution. You keep the
copyright in your work; the agreement lets Unseen Servant Games license it,
including under terms other than the AGPL.

## Build from source

You need:

- [Rust](https://www.rust-lang.org/tools/install) (stable) and Node.js 20
- [uv](https://docs.astral.sh/uv/), which installs Python 3.12 for the sidecar
- [Ollama](https://ollama.com) with `bge-m3` pulled, running with an 8K context:
  the Ollama app's **Context length** setting, or
  `OLLAMA_CONTEXT_LENGTH=8192 ollama serve` in its own terminal
- **macOS:** Xcode Command Line Tools (`xcode-select --install`)
- **Windows:** [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)
  with "Desktop development with C++", and WebView2 (built into Windows 11)
- **Linux:** builds and runs from source but isn't a release target. CI
  installs `libwebkit2gtk-4.1-dev libgtk-3-dev libayatana-appindicator3-dev librsvg2-dev`.

The [Tauri prerequisites](https://tauri.app/start/prerequisites/) have the
details. Then:

```bash
git clone https://github.com/Unseen-Servant/unseen-servant-app.git
cd unseen-servant-app
npm ci
(cd sidecar && uv sync)
npm run tauri dev
```

Use `npm run tauri dev`, not `npm run dev`: plain `npm run dev` serves only the
interface in a browser, where the app's native side doesn't exist. In dev, the
sidecar runs from `sidecar/.venv`; its first start compiles bytecode and can
outlast the app's wait, so an "Indexer failed to start" on the very first
launch only needs a relaunch.

### How it fits together

```text
Svelte interface ⇄ Rust (Tauri) ⇄ Python sidecar (FastAPI on a local port)
                                    ├─ SQLite + sqlite-vec: the library index
                                    ├─ Ollama (bge-m3): embeddings
                                    └─ campaign folders: Markdown + JSON Canvas
AI agent ⇄ MCP server (stdio) ⇄ Python sidecar
```

- `src/`: the interface, one folder per tool under `src/lib/` (`legend-lore/`,
  `command/`, `servant/`) plus the shared `shell/` and `ui/`.
- `src-tauri/`: the native app, which starts the sidecar and proxies to it.
- `sidecar/`: indexing and search (`legend_lore/`), campaign files
  (`command/`), and `mcp_server.py`, which an AI agent launches and which finds
  the running sidecar through the port file in the app's data folder.
- `evals/`: the retrieval eval harness.

### Checks

CI runs these on Linux for the parts a change touches. Run them before opening
a pull request:

```bash
npm run check && npm run lint:css && npm test               # interface
(cd src-tauri && cargo fmt --all -- --check \
  && cargo clippy --all-targets -- -D warnings && cargo test --lib)   # Rust
(cd sidecar && uv run pytest)                               # sidecar
uv run --project sidecar pytest evals/tests                 # eval harness
```

Changes to indexing or ranking are judged on the retrieval harness
([evals/README.md](evals/README.md); its corpus isn't in the repo) and on real
libraries, so include before and after numbers.

### Build an installer

On macOS:

```bash
bash scripts/build-sidecar.sh   # bundles the sidecar with PyInstaller
npm run tauri build
```

`tauri build` stops if any sidecar source is newer than the binaries in
`src-tauri/binaries/`: rerun `scripts/build-sidecar.sh` first.

The `.dmg` lands in `src-tauri/target/release/bundle/dmg/`. On Windows, follow
the `build-windows` job in [.github/workflows/release.yml](.github/workflows/release.yml),
which runs the same PyInstaller steps in PowerShell and leaves the `.exe` in
`src-tauri\target\release\bundle\nsis\`.

### Dependencies and acknowledgements

A new dependency needs a licence compatible with the AGPL-3.0: no GPL-2.0-only,
non-commercial or source-available terms, and that includes model weights.
After adding or updating one, regenerate the acknowledgements that ship in the
app:

```bash
uv run --frozen --project sidecar --group build python scripts/acknowledgements.py
```

## Pull requests

- One fix per pull request, kept small. Say what was broken, how you tested the
  fix, and on which OS.
- Match the code around your change. Interface changes follow the design
  conventions in [CLAUDE.md](CLAUDE.md).
- Commit messages follow the history's style: `fix(sidecar): …`,
  `feat(command): …`.
