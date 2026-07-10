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

1. **Local-first**: All content and inference work are done locally on a machine, which means dealing with all the limitation and tradeoffs that it brings. No PDFs leave the GM's machine.
2. **No platform or format lock-in**: All the content that GMs are building remains accessible and readable on their machines after they are done using Unseen Servant. Obsidian is the obvious inspiration here.
3. **Enabler for improvisation**: Many design elements take inspiration from DAWs and other tool used by musicians for live session. I see many similarity with a GM's role and responsibilities during prep and live play.

---

## This Repository: `unseen-legend-lore`

The core desktop application — Tauri v2 shell with SvelteKit frontend and a Python sidecar for PDF indexing and search.

### What it does

- **Tauri + Rust:** Native desktop window, filesystem access, sidecar lifecycle management
- **SvelteKit + TypeScript:** File browser UI with recursive tree, lazy loading, persistent selection
- **Python sidecar (FastAPI):** PDF text extraction, ChromaDB indexing, semantic search API (port 8420)
- **MCP server:** Tools for agentic integration (search, compare, random tables, etc.)

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

- **Ollama** with `bge-m3` for local embeddings (no API keys; needs `OLLAMA_CONTEXT_LENGTH=8192`)
- **ChromaDB** for vector storage and semantic search
- **MCP (Model Context Protocol)** for Claude Desktop integration
- **PyMuPDF4LLM** for PDF text extraction

### Data flow

```text
PDF files on disk
  → text extraction (PyMuPDF4LLM)
  → chunking (1000 chars, 200 overlap; tables linearized into per-row units)
  → embedding (Ollama bge-m3, 1024-dim)
  → storage (ChromaDB)
  → search (query embed → nearest neighbors → cross-encoder rerank → relevance tiers)
  → results to UI or Claude via MCP
```

### Related repositories

- **unseen-legend-lore-experiments** ('~/code/unseen-legend-lore-experiments') - Research spikes for Legend Lore. *Relationship:* FINDINGS inform key architectural decision in Legend Lore
- **unseen-servant-site** ('~/code/unseen-servant-site') - Landing page of Unseen Servant. *Relationship:* legend lore is distribution through the landing page. Product description needs to match actual code and features.

---

## Continuous Integration

Solo dev project on the GitHub Pro tier: **3000 billable minutes/month**. macOS jobs bill at 10×, Windows at 2×, Linux at 1× — macOS dominates any budget. CI is structured around this constraint.

### What runs when

- **PR + push to `main` (`ci.yml`):** Linux-only — `sidecar-tests` (pytest), `rust-checks` (fmt + clippy + cargo test), `frontend-checks` (svelte-check + vitest + vite build). All path-gated on PR; everything runs on push. Effective cost: ~free under the included minutes.
- **Tag push `v*` (`release.yml`):** Full cross-platform build on macOS + Windows, sidecar PyInstaller bundle, codesign, draft GitHub Release. This *is* the cross-platform validation — there is no separate "tauri-build-smoke" on main.

### Rules for changing CI

1. **No macOS/Windows jobs on PR or push-to-main.** If you're tempted to add one, the question is "what will this catch that Linux + the next release tag won't?" — and the answer needs to justify the billable-min cost.
2. **Estimate billable minutes before adding any job.** Include the multiplier. Note it in the commit message.
3. **Release-time regressions are acceptable.** If a cross-platform bug only surfaces at tag push, fix forward and bump the patch version. Re-tagging an unpublished draft once is fine; if a second fix lands, bump the patch.
4. **Local validation is the dev's responsibility.** Before tagging a release that touches build config, `src-tauri/`, sidecar deps, or the build scripts, run `npm run tauri build` and `bash scripts/build-sidecar.sh` locally.

### Commit workflow

Solo dev, trunk-based without PRs (since 2026-07-03): commit directly to `main` and push. CI runs the full Linux suite on every push to main — check that it's green before tagging a release. Releases are `v*` tags cut from main whenever the tree is in a good state.

PRs are the exception, not the rule — reserve them for changes that benefit from a review pass or CI-before-merge (e.g. risky CI or build-config changes). When a PR is used, keep it single-purpose and don't stack it on another open PR.

---

## Guidelines

### 1. Think Before Coding

Don't assume. Don't hide confusion. Surface tradeoffs.

Before implementing:

- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First

Minimum code that solves the problem. Nothing speculative.

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 3. Surgical Changes

Touch only what you must. Clean up only your own mess.

When editing existing code:

- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:

- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

### 4. Goal-Driven Execution

Define success criteria. Loop until verified.

Transform tasks into verifiable goals:

- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:

```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.
