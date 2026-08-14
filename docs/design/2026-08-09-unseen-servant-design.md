# Unseen Servant — In-App Agentic GM Copilot — Design

**Date:** 2026-08-09
**Status:** **Paused 2026-08-14, pending retrieval quality.** Built end to end on
branch `worktree-unseen-servant` (all seven phases; Phase 1 merged to `main` as
`4940026`). The harness works — the model drives the tools reliably and answers
from real sources — but the retrieval underneath is not good enough to carry it.
See [the retrieval findings](../roadmap/2026-08-14-agent-harness-retrieval-findings.md),
which is now the input to a search-quality workstream. Resume this only once that
lands; nothing in the design below is retracted.
**Scope:** New Tauri window + SvelteKit route (`src/routes/servant/`, `src/lib/servant/`), new sidecar agent module (`sidecar/servant/`), changes to `sidecar/server.py`, `sidecar/mcp_server.py`, `src-tauri/src/lib.rs`, `src-tauri/tauri.conf.json`, new `src-tauri/capabilities/servant.json`, `scripts/build-sidecar.sh` + `.github/workflows/release.yml`.

## Problem

Legend Lore is an MCP **server** and nothing more. It exposes four stdio tools and
assumes someone else's agent — Claude Desktop — does the thinking. There is no
generative LLM anywhere in the codebase; Ollama is used only for `bge-m3`
embeddings.

That was a deliberate choice. `c5ccd5d` added MCP resources and prompts; `5828cbd`
and `7c6dd89` removed them again, along with `random_table`, the Encounter Builder
and the NPC Generator, with a stated doctrine:

> Tools are the only surface that earns its keep. […] Focus the MCP server on what
> it does well: search and retrieval.

The doctrine was right about *that* surface and stays in force: MCP prompts and
resources are buried in a host app's UI, and generation-shaped MCP endpoints are
worse than an agent that owns its own loop.

What it did not address is the GM at the table. Mid-session, the answer to "how does
grappling work" is three seconds away in a PDF the app has already indexed — but
getting it requires alt-tabbing to a cloud model, which means leaving the app,
needing a network, and sending session context off the machine. That last part is
in direct tension with the product's first principle (*no PDFs leave the GM's
machine*).

So: generation gets a home in the app, but a narrow one. **Retrieval-grounded
question answering, locally, in a window you can leave open next to the map.** Not
homebrew, not creative generation — those stay with the external agent, where the
doctrine still holds and where a frontier model is worth the alt-tab.

Claude Desktop is untouched by this, and in fact gets three fixes out of it: a
non-blocking search handler (#344), an embedder that stops going cold (#341), and a
parent-death watchdog on the MCP server so it stops orphaning.

## The model

A second window, "Unseen Servant", holding a chat transcript. The GM types a
question; a small local model decides whether to search, and if so calls Legend
Lore's own `search_library` tool over real MCP; the answer streams back with
citations that open the source PDF at the right page.

Three properties make it a *live-play* tool rather than a chat toy:

- **It is scoped.** It searches whatever the main window's solo/mute/play console is
  set to. "This is my Dragonbane session" already exists as app state; the Servant
  inherits it.
- **It shows its work.** Tool calls render as visible rows — the query it chose, how
  many results came back, how many were strong. When a small model gets it wrong,
  you can see *that* it got it wrong.
- **It is honest about missing content.** The system prompt inherits the tuned rule
  from `mcp_server.py:200-217` — never claim something is unavailable without
  searching, never invent rules when the search comes back empty.

## Decisions taken

1. **The agent loop lives in the Python sidecar**, as an SSE endpoint. (Chosen over
   Rust — no precedent in the repo, weakest MCP/LLM library story; and over the
   frontend — the CSP at `tauri.conf.json:23` is `connect-src 'self' ipc:`, so the
   webview cannot reach Ollama or the sidecar at all.)
2. **The sidecar is a real MCP client**, spawning the bundled `legend-lore-mcp`
   stdio binary and speaking MCP to it. This is deliberately circular — sidecar →
   MCP subprocess → HTTP → same sidecar — and that is the point: the Servant
   exercises the same surface Claude Desktop uses, so improvements land in both
   places, and the harness stays generic enough to attach a second MCP server later.
   (Chosen over calling `/api/search` directly, which is simpler and exposes more
   knobs but makes "through MCP" shape-only and stops the surface being dogfooded.)
   *Escape hatch:* the loop depends on a `ToolBroker` protocol, with `McpToolBroker`
   and `DirectToolBroker` implementations. If MCP-in-sidecar proves unworkable the
   swap is one line and nothing downstream changes.
3. **Model-driven tool calls**, not fixed always-retrieve RAG. Validated by the
   Phase 0 spike below. (Chosen over always-retrieve, which is more reliable but is
   a chat UI over search rather than an agent; and over a hybrid retrieval floor,
   which the measured numbers made unnecessary.)
4. **The Servant honors the main window's live scope**, pushed to the sidecar on
   change and snapshotted per turn. (Chosen over library-wide, which risks surfacing
   the wrong system's rules mid-session, and over a separate collection picker in
   the Servant window, which would let the two windows silently disagree.)
5. **The window is created hidden during `setup()`**, after `wait_for_sidecar`, and
   summoned on demand. (Chosen over lazy creation on first summon; costs a second
   webview's memory for every user, buys a zero-latency summon.)
6. **Conversations persist as JSONL**, one message per line, under
   `<data_dir>/conversations/<id>.jsonl`, with a Markdown export action. (Chosen
   over Markdown-as-storage, which is lossy and fragile to parse back, and over
   session-only, which loses last session's rulings. JSONL is plain text and
   greppable, so it satisfies the no-lock-in principle; Markdown is the *export*,
   not the store.)
7. **The chat model is configurable in Settings**, defaulting to `qwen3.5:2b`,
   mirroring the `search_settings.json` precedent at `server.py:2627`.

### Decisions that came out of design review

8. **Citations come from a sidechannel, not from parsing MCP output.**
   `search_library` prints `Source: {filename}` (`mcp_server.py:334`) and never the
   absolute path — and filenames are explicitly not unique, which `server.py:3315-3317`
   calls out by name (issue #308). Parsing that text would open the wrong PDF for any
   two books sharing a basename. Instead `/api/search` stashes its own structured
   results into `app.state.servant_last_results` when the request carries
   `X-Source: servant`. The model gets the prose; the UI gets objects with `source`,
   `page_start`, `page_end`, `tier`. No parsing, no MCP schema change, immune to
   format drift. Structured MCP tool output is the eventual right answer and is
   deferred to its own issue.
9. **Scope never enters the tool schema.** The model gets one tool with one required
   argument. Scope is applied server-side by `/api/search` for servant-sourced
   requests, and the harness pre-injects the game-systems list into the system
   prompt rather than spending a tool round on `list_game_systems`. Keeping the
   model's job small is the single biggest lever on small-model reliability.
10. **`X-Source: servant`, not `mcp`.** `mcp_server.py` stamps `X-Source: mcp` on
    every call (`:38`) and heartbeats every 30s (`:416`); together those drive the
    StatusBar's "MCP active — agent querying" lamp. Without gating, the in-app
    Servant would light the lamp that is supposed to mean Claude Desktop. The
    spawned instance takes a `LEGEND_LORE_MCP_SOURCE` env var, and **both** the
    header and the heartbeat are gated on it.
11. **Streaming uses `tauri::ipc::Channel`, not events.** `emit_to(label)` cannot
    reach a bare `listen()` — the JS side registers `{kind:'Any'}` and Rust's target
    matcher falls through to `false`, so the stream would silently go nowhere with no
    error. A `Channel` passed as an invoke argument is point-to-point by
    construction, needs no capability, and delivers sub-8KB payloads by direct eval.
12. **`--mcp-command` carrying a JSON argv array**, not `--mcp-binary`. Dev needs a
    program *and* arguments (`venv_python mcp_server.py …`, and note the load-bearing
    symlink comment at `lib.rs:1310-1316`); prod needs just the binary. One flag
    covers both and reuses `get_mcp_config`'s existing resolution.
13. **Greedy decoding.** See Findings — this is the difference between a flaky
    demo and a reliable tool.

## Phase 0 findings — can a 2B model drive the loop?

Spike run 2026-08-09 against `qwen3.5:2b` (2.3B params, Q8_0, 262144 context,
capabilities `completion vision tools thinking`) on Ollama 0.32.6. 24 GM-phrased
prompts derived from `sidecar/evals/queries.yaml`, plus 8 conversational prompts
that should *not* trigger a search. Bail-out bar was 80% usable tool invocation.

| Metric | Model defaults (`temp=1`, `presence_penalty=1.5`) | **Greedy (`temp=0`, `pp=0`)** |
|---|---|---|
| Tool-call recall (should search, did) | 23/24 — 96% | **24/24 — 100%** |
| Usable `query` argument | 23/24 — 96% | **24/24 — 100%** |
| Over-calling (shouldn't search, did) | 0/8 — 0% | **0/8 — 0%** |
| Grounded on tool output | 3/3 | **3/3** |
| Honest on empty results | yes | **yes** |
| Query determinism (6 repeats) | 5–6 distinct | **1 distinct** |
| Throughput | ~59 tok/s median | **~62 tok/s median** |

**Verdict: GO.** Four findings shape the implementation:

- **Decoding config is load-bearing.** Every failure in the default-config run was
  temperature variance — the same prompt would call the tool on one run and answer
  from memory on the next. At `temperature: 0` it is 6/6 across repeats with a single
  distinct query. The model's *shipped* `presence_penalty: 1.5` also pads queries
  with filler (`"skeleton statistics and lore TTRPG"`); at `presence_penalty: 0` the
  same prompt yields `"skeleton morale"`. Tighter queries are better retrieval input,
  so this is a quality lever, not just a tidiness one. **Ship `temperature: 0`,
  `presence_penalty: 0`.**
- **Tool calls arrive whole, in one chunk.** `content` is `""`, `tool_calls` is
  populated once, and `arguments` is an already-parsed `dict` — Ollama parses the
  call server-side before emitting. There are no partial argument deltas, so no
  assembly buffer is needed and the "malformed args" rail is about *semantically*
  wrong arguments, not truncated JSON.
- **`think=False` is required.** The model advertises `thinking`; left on, a 2B model
  burns hundreds of reasoning tokens before every tool call, which live play cannot
  afford.
- **No model contention on this machine.** `bge-m3` (0.66 GB) and `qwen3.5:2b`
  (2.41 GB) stay co-resident at 3.08 GB combined, and an embed immediately after a
  chat turn takes 0.21s — no reload. The earlier disappearance of `bge-m3` was its
  5-minute TTL (#341), not eviction. Risk downgraded; the keep-warm ticker is still
  worth shipping because #341 is real on its own.

Caveats on the numbers: single machine, single run, one model, and the grounding
check uses stubbed tool output with sentinel facts rather than live retrieval. The
honest claim is "the tool-calling mechanism is sound", not "the answers are good" —
answer quality is gated on real retrieval and is what Phase 3's `curl` harness is for.

## Architecture

```
Servant window (SvelteKit /servant)
  │  invoke('servant_chat', {query, conversationId, onEvent: Channel})
  ▼
Rust servant_chat ── SSE relay, framing per consume_sync_stream (lib.rs:475)
  │  POST /api/servant/chat
  ▼
Sidecar agent loop ──► Ollama /api/chat  (stream, tools, think=False, temp=0)
  │                         │ tool_calls
  │  ToolBroker.call_tool ◄─┘
  ▼
McpToolBroker ──stdio──► legend-lore-mcp ──HTTP(X-Source: servant)──► /api/search
                                                                          │
                                        app.state.servant_last_results ◄──┘
```

Scope travels separately: the main window pushes its resolved scope to
`PUT /api/servant/scope` on change; the agent snapshots it under the turn lock at
turn start; `/api/search` applies it only for `X-Source: servant`.

## Edge cases

| Case | Behaviour |
|---|---|
| Model not pulled | Health check reports it (today `check_ollama_health` only looks for `bge-m3`); Servant shows an empty state naming the `ollama pull` command. |
| Model emits no tool call for a content question | Answer streams with a visible "answered without sources" marker. Not silently presented as grounded. |
| Model emits malformed arguments | One corrective observation fed back, then give up into the same unsourced state. |
| Model emits a fenced JSON block instead of `tool_calls` | Fallback parse for that shape, then unsourced state. |
| Search returns nothing | Tool result says so; the prompt forbids inventing rules. Spike confirms the model complies. |
| Scope resolves to empty | Turn short-circuits with the existing `emptyScopeMessage` copy from `searchScope.ts:202`. |
| Scope changes mid-turn | Turn uses its start-of-turn snapshot; two tool calls in one turn can never cite two different libraries. |
| Both windows hidden | Tray gains a "Show Unseen Servant" item — otherwise the window is unreachable. |
| Sidecar dies mid-stream | `sidecar://failed` already broadcasts; Servant listens and surfaces it. |
| Two books share a basename | Citations carry absolute paths from the sidechannel, so the correct PDF opens (decision 8). |

## Alternatives rejected

- **Parsing `search_library`'s text for citations** — loses the absolute path, breaks
  on duplicate basenames (decision 8).
- **Extending `search_library`'s MCP schema with `source_paths` / `game_systems`** —
  would pollute the tool surface Claude Desktop sees with parameters it cannot
  meaningfully supply (absolute filesystem paths), and hands a 2B model filter
  arguments to reason about.
- **Tauri events for the token stream** — silently undeliverable (decision 11).
- **Markdown as the conversation store** — lossy round-trip; kept as export only.
- **A hybrid retrieval floor** (always run one search as a safety net) — designed as
  insurance against unreliable tool calling; the spike measured 24/24 and 0/8, so it
  would only add latency and unwanted context.

## Out of scope

Creative and homebrew generation — that stays with the external agent, where the
`5828cbd` doctrine still holds. Multi-server MCP attachment. Structured MCP tool
output (deferred; would let citations skip the sidechannel). A per-turn "search the
whole library" override. Voice input. Conversation search.

## Verification

Detailed per-phase steps live in the paired
[implementation plan](2026-08-09-unseen-servant-plan.md). At the top level:

- `cd sidecar && pytest -v` — agent loop, broker, citations, scope, persistence. The
  loop is fully testable with a fake Ollama iterator and no live model.
- `npm test`, `npm run check`, `npm run lint:css`, `cargo clippy`, `cargo test --lib`.
- Manual pre-tag pass on macOS and Windows: summon the Servant, ask one question,
  watch the tool row resolve, click one citation, confirm the PDF opens at the right
  page. CI is Linux-only until a release tag, so two-window behaviour, capability
  resolution, onefile-spawning-onefile and Ollama are outside CI permanently.
