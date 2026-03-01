# Unseen Servant Development Guide

## Product Vision

Unseen Servant is a local-first, AI-augmented toolkit for tabletop RPG Game Masters. It helps GMs browse, index, and semantically search their PDF rulebook collections, and integrates with Claude AI via MCP for mid-session lookups and homebrew creation.

### Target User

A TTRPG Game Master who:
- Owns a large PDF library (hundreds to thousands of rulebooks, supplements, and adventures)
- Needs to find specific rules, tables, or lore quickly during session prep and live play
- Wants AI assistance for homebrew content, rule comparisons, and creative prompts
- Values privacy — their library stays on their machine, not in the cloud

### Core Philosophy

1. **Local-first.** Everything runs on the GM's machine. No accounts, no cloud uploads, no data leaves the laptop. Ollama for embeddings, ChromaDB for storage, Tauri for the desktop shell.
2. **AI-augmented, not AI-dependent.** AI handles the tedious work (searching 2,000+ PDFs, comparing rules across systems, generating random encounters) so the GM can focus on storytelling. The app is fully functional without AI — search still works, files still browse.
3. **Markdown for collaboration.** Use Markdown files wherever possible for human-machine readability. Configuration, notes, and homebrew content should be easy to read and edit by both the GM and AI tools.

---

<!-- [REPO-SPECIFIC] Replace this section for each repository -->
## This Repository: `unseen-server`

The core desktop application — Tauri v2 shell with SvelteKit frontend and a Python sidecar for PDF indexing and search.

### What it does
- **Tauri + Rust:** Native desktop window, filesystem access, sidecar lifecycle management
- **SvelteKit + TypeScript:** File browser UI with recursive tree, lazy loading, persistent selection
- **Python sidecar (FastAPI):** PDF text extraction, ChromaDB indexing, semantic search API (port 8420)
- **MCP server:** 7 tools for Claude Desktop integration (search, compare, random tables, etc.)

### Quick reference
```bash
npm run tauri dev          # Development (compiles Rust + starts frontend with HMR)
npm run tauri build        # Production build
cd sidecar && pytest -v    # Run sidecar tests (39 tests)
```

### Key files
- `src/routes/+page.svelte` — Main UI page
- `src/lib/FileTree.svelte` — Recursive file tree component
- `src/lib/types.ts` — Shared TypeScript types
- `src-tauri/src/lib.rs` — Rust backend commands + sidecar lifecycle
- `sidecar/server.py` — FastAPI indexing and search server
- `sidecar/mcp_server.py` — MCP tool definitions for Claude Desktop
- `sidecar/tests/` — Pytest suite (chunking, indexing, search, MCP tools)
<!-- [END REPO-SPECIFIC] -->

---

## Ecosystem Overview

Unseen Servant spans four repositories:

| Repository | Purpose | Stack |
|---|---|---|
| `unseen-server` | Desktop app + sidecar + MCP server | Tauri v2, SvelteKit, Rust, Python, FastAPI |
| `unseen-app-desktop` | Desktop application (alternate) | Tauri, SvelteKit |
| `unseen-script` | Utility scripts | Python |

### Shared infrastructure
- **Ollama** with `nomic-embed-text` for local embeddings (no API keys)
- **ChromaDB** for vector storage and semantic search
- **MCP (Model Context Protocol)** for Claude Desktop integration
- **pypdf** for PDF text extraction

### Data flow
```
PDF files on disk
  → text extraction (pypdf)
  → chunking (1000 chars, 200 overlap)
  → embedding (Ollama nomic-embed-text)
  → storage (ChromaDB)
  → semantic search (query → embed → nearest neighbors)
  → results to UI or Claude via MCP
```

---

## Architecture Principles

- **Lazy loading.** Never load everything at once. File trees load on expand. PDFs index in batches. Search returns top-N results.
- **Separation of concerns.** Rust handles filesystem and process management. Python handles ML/PDF/ChromaDB. Svelte handles UI. They communicate via HTTP (sidecar) and Tauri commands (IPC).
- **Start simple, add complexity later.** Get the feature working first. Optimize second. Add persistence third. Don't over-engineer for hypothetical requirements.
- **Prefer editing over creating.** Build on existing files and patterns rather than creating new abstractions. Three similar lines are better than a premature utility function.
- **Organized code structure.** Separate type files from implementation. Keep components focused. Use clear naming.

---

## Development Process

### Workflow
1. **Plan** — For non-trivial work, create a GitHub Issue describing the goal, approach, and acceptance criteria
2. **Branch** — Create a feature branch off `main` with a descriptive name (e.g., `add-search-ui`, `fix-chunking-overlap`)
3. **Code** — Implement incrementally. Commit logical chunks, not entire features at once
4. **Test** — Write tests for new functionality. Run existing tests before committing to catch regressions
5. **Commit** — Descriptive commit messages focused on "why," not "what." One logical change per commit
6. **PR** — Optional for solo work, but use PRs for any change that benefits from a second look or documentation trail

### Commit messages
- Start with a verb: "Add search filtering by source," "Fix chunking overlap at page boundaries"
- Keep the first line under 72 characters
- Add a body for non-obvious changes explaining the reasoning

### Testing expectations
- **Python sidecar:** pytest suite in `sidecar/tests/`. New endpoints or logic need tests. Tests use in-memory ChromaDB (no Ollama required)
- **Rust:** Compiler is your first line of defense. Add integration tests for Tauri commands when feasible
- **Svelte:** Manual testing via `npm run tauri dev` for UI changes. Consider component tests for complex logic

### When to create issues
- New features or user-facing changes
- Bugs that need investigation before fixing
- Refactors that touch multiple files
- Not needed for typo fixes, small tweaks, or documentation updates

---

## Teaching Approach

### Developer profile
Jerome is a PM/AI-ML Senior Director with a physics engineering background, based in Montreal. He's comfortable with concepts and architectural thinking, and is learning implementation details hands-on. He prefers understanding trade-offs before writing code and thinks in terms of scalability (e.g., "will this work for 18GB of PDFs?").

### How Claude should teach
- **Explain "why" before "how."** Always give the reasoning behind a decision before showing the implementation. Compare trade-offs between approaches.
- **Break down complexity.** Start with the simplest working version. Add complexity incrementally. Celebrate what works before optimizing.
- **Encourage critical thinking.** Ask leading questions ("What would happen if...?") rather than handing over solutions. Validate good reasoning.
- **Build mental models.** Show data flows and component relationships. Help Jerome see patterns he can reuse elsewhere.
- **Guide debugging, don't just fix.** Point toward the problem. Let Jerome find the solution. Validate his diagnosis.

### Tone
- Encouraging and honest — acknowledge what's correct, then point out improvements
- Concise — Jerome appreciates directness over lengthy explanations
- Socratic — ask questions that lead to discovery
- Contextual — reference the actual scale (2,629 PDFs, 18GB) and TTRPG use cases
- Present at most 2-3 options when offering choices, not 10

### What to avoid
- Providing complete solutions without explanation
- Assuming prior knowledge of implementation details
- Moving too fast through new concepts
- Over-engineering or adding features beyond what was asked

---

## Code Standards

### Rust (src-tauri)
- Use `Result<T, String>` for Tauri commands with descriptive error messages via `.map_err()`
- Snake_case for functions and variables
- Register all commands in `tauri::generate_handler![]`

### TypeScript / Svelte (src)
- Separate type definitions in dedicated files (e.g., `types.ts`)
- CamelCase for variables and functions, PascalCase for components
- Force Svelte reactivity through reassignment, not mutation
- Use `invoke<T>()` with explicit type parameters for Tauri IPC calls

### Python (sidecar)
- Type hints on all function signatures (Python 3.10+)
- Async/await for all FastAPI endpoints
- Descriptive error messages in HTTP responses
- Tests use fixtures from `conftest.py` — in-memory ChromaDB, no external dependencies
