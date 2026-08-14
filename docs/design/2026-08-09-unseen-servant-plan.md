# Unseen Servant Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A second Tauri window holding a locally-run, retrieval-grounded GM copilot
that drives Legend Lore's own MCP tools — per [the approved spec](2026-08-09-unseen-servant-design.md).

**Architecture:** Servant window → Rust `Channel` relay → sidecar SSE agent loop →
Ollama (`/api/chat`, streaming, one tool) → MCP stdio client → `legend-lore-mcp` →
`/api/search`. Citations ride a sidechannel (`app.state.servant_last_results`) rather
than being parsed out of MCP prose.

**Tech Stack:** Python 3.12 / uv (`mcp==1.28.1` and `ollama==0.6.2` are already
dependencies — no new ones), FastAPI SSE, Tauri v2 + `tauri::ipc::Channel`, Svelte 5
in **legacy mode** (`export let`, `$:`, `on:click` — the repo has zero runes),
pytest, vitest (node env, pure modules only), stylelint (`npm run lint:css`),
svelte-check (`npm run check`).

**Conventions for every task:**
- Commit after each task, on the `unseen-servant` worktree branch. **Nothing lands on
  `main` until the whole feature has been tested live** — this is a deliberate
  departure from the repo's trunk-based default because the feature is exploratory.
- CI does not run on this branch (`ci.yml` triggers on PR and push-to-`main` only), so
  run `cd sidecar && pytest -v`, `npm run check`, `npm run lint:css`, `npm test` and
  `cargo clippy` locally at every task boundary.
- `npm run check` must report zero errors **and zero "Unused CSS selector" warnings**.
- Every colour in a component must be a `var(--*)` token from `src/app.css`. Add a
  token rather than a raw value.
- Line numbers below are as of commit `ad6ecba`; they shift as tasks land — anchor on
  the quoted code, not the numbers.

---

## Task 1: Unblock the sidecar event loop (#344, #341)

Ordered first because the Servant is unusable without it, and because it is the one
piece worth keeping even if everything else is abandoned. **Keep this commit free of
any Servant code** so it can be cherry-picked onto `main` independently.

`/api/search` is `async def` but its body is entirely synchronous — including a
blocking Ollama embed with a 120s timeout inside `collection.query()`. A 5–7s search
therefore blocks the whole event loop. Today that only degrades concurrent requests;
once the Servant exists it means every tool call freezes the main window's health
pollers (3s timeouts at `lib.rs:423` and `:444`), flipping the StatusBar lamps to
"disconnected" during normal use.

**Files:**
- Modify: `sidecar/server.py`
- Modify: `sidecar/tests/test_search.py` (or a new `test_search_concurrency.py`)

- [ ] **Step 1: Confirm Chroma collection reads are thread-safe under concurrency.**
      Write the test before the refactor: two threads issuing `collection.query()`
      against the same collection, asserting both return correct results. If this
      fails, the whole approach changes — stop and reassess.
- [ ] **Step 2: Extract the body of `search()` (`server.py:3162`) into a module-level
      `_search_sync(...)`.** It currently closes over `collection`, `data_dir`,
      `_merged`, `_get_spell_corrector`, `_get_lexical_index` — pass them as
      parameters. Pure mechanical move, no behaviour change.
- [ ] **Step 3: Make the route `return await run_in_threadpool(_search_sync, ...)`.**
      Follow the existing precedent: `sync_index_stream` (`server.py:2194`) already
      avoids blocking by yielding from a *sync* generator, which Starlette threads.
- [ ] **Step 4: Add a `threading.Semaphore` bounding concurrent searches** so N of
      them don't fan out into N simultaneous Ollama embeds. Pick the bound by
      measuring against the eval corpus rather than guessing — gains flatten once
      Ollama and the ONNX reranker saturate.
- [ ] **Step 5: Add the `bge-m3` keep-warm ticker** — a daemon thread embedding a
      one-token string every ~4 minutes, mirroring the existing
      `probe_embed_truncation` thread pattern at `server.py:948`. Closes #341.
- [ ] **Step 6: Verify.** Two concurrent `curl` searches complete in ~max(t1,t2), not
      t1+t2. p50 latency for a single search is unchanged. `pytest -v` green.

## Task 2: MCP client in the sidecar (no model yet)

**Files:**
- Create: `sidecar/servant/__init__.py`, `sidecar/servant/broker.py`
- Modify: `sidecar/server.py`, `sidecar/mcp_server.py`, `src-tauri/src/lib.rs`
- Create: `sidecar/tests/test_servant_broker.py`, `sidecar/tests/test_servant_citations.py`

- [ ] **Step 1: Define the `ToolBroker` protocol** with `McpToolBroker` and
      `DirectToolBroker` implementations. This is the escape hatch from design
      decision 2 — if MCP-in-sidecar proves unworkable, the swap is one line.
- [ ] **Step 2: Implement `McpToolBroker` with a single long-lived supervisor task
      owning both context managers end to end.** Entering `stdio_client` /
      `ClientSession` in one task and exiting in another raises
      `RuntimeError: Attempted to exit cancel scope in a different task` — the
      classic MCP-SDK footgun. Calling `session.call_tool()` from another task is
      fine; only the context-manager exit is task-bound.

      ```python
      async def _run(self):
          async with stdio_client(params) as (r, w):
              async with ClientSession(r, w) as s:
                  await s.initialize()
                  self._session = s
                  self._ready.set()
                  await self._stop.wait()
      ```
- [ ] **Step 3: Spawn once per app session**, not per conversation or per turn —
      `legend-lore-mcp` is a PyInstaller onefile and costs ~200–500ms of temp
      extraction per spawn.
- [ ] **Step 4: Gate `LEGEND_LORE_MCP_SOURCE` in `mcp_server.py` for BOTH
      `MCP_HEADERS` (`:38`) and `heartbeat_loop` (`:416`).** Both, or the Servant
      lights the StatusBar lamp that is supposed to mean Claude Desktop. Env passes
      safely: the MCP SDK's `get_default_environment()` merges onto a 6-var POSIX
      allowlist, so `_MEIPASS` / `DYLD_*` / `LD_LIBRARY_PATH` never reach the child.
- [ ] **Step 5: Add a `--parent-pid` watchdog to `mcp_server.py`,** mirroring
      `server.py:3609`. The MCP SDK spawns with `start_new_session=True`, which puts
      the child in its own process group and defeats the `libc::kill(-pid, …)` at
      `lib.rs:1527` — without this, every app run leaks one MCP process. Independently
      valuable for Claude Desktop.
- [ ] **Step 6: Pass `--mcp-command <json argv array>` from Rust to the sidecar** in
      `start_sidecar` (`lib.rs:1459`), reusing `get_mcp_config`'s dev/prod resolution
      (`:1294`). Read it in `parse_args` (`server.py:104`) — note `create_app`
      re-invokes `parse_args` at `:1686`, so no threading is needed. Branch any
      path logic on `getattr(sys, "frozen", False)`: when frozen,
      `Path(__file__).parent` resolves into the temp extraction dir.
- [ ] **Step 7: Add sidechannel citation capture.** When `/api/search` sees
      `X-Source: servant`, stash its structured `formatted` list into
      `app.state.servant_last_results`. Add `POST /api/servant/tools/search`
      returning `{text, citations}`.
- [ ] **Step 8: Verify.** `curl` returns citations with correct **absolute** paths;
      include a test with two indexed files sharing a basename. MCP lamp stays dark.
      No orphaned `legend-lore-mcp` process after quitting the app.

## Task 3: Agent loop + SSE endpoint (no UI)

**Files:**
- Create: `sidecar/servant/agent.py`, `sidecar/tests/test_servant_agent.py`
- Modify: `sidecar/server.py`

- [ ] **Step 1: Implement the loop against `ToolBroker`,** never against the MCP
      session directly.
- [ ] **Step 2: Call Ollama with the config the spike validated** —
      `AsyncClient.chat(model, messages, tools=[search_library], stream=True,
      think=False, options={"temperature": 0, "presence_penalty": 0},
      keep_alive="30m")`. All four matter: `think=False` because the model advertises
      `thinking` and a 2B model cannot afford it; `temperature: 0` because every
      spike failure was temperature variance; `presence_penalty: 0` because the
      model's shipped `1.5` pads queries with filler.
- [ ] **Step 3: Assemble the response.** Accumulate `content` into a buffer and
      `tool_calls` into a list across *all* chunks — don't assume one call or that it
      lands on the last chunk. `arguments` arrives as an already-parsed `dict`; there
      are no partial argument deltas.
- [ ] **Step 4: Build the tool round-trip.** Append the assistant message *with* its
      `tool_calls`, then `{"role": "tool", "content": <text>, "tool_name":
      "search_library"}`.
- [ ] **Step 5: Add the rails.** Max 3 tool rounds; per-tool-call timeout; total turn
      timeout; one corrective observation on semantically-bad arguments, then give up
      into a visible "answered without sources" state; a fallback parse for a fenced
      JSON block in `content` for models that don't populate `tool_calls`; strip a
      literal `<think>…</think>` from `content` defensively.
- [ ] **Step 6: Build the system prompt.** Shorten `mcp_server.py:200-217`, keeping
      the load-bearing "never say unavailable without searching" and "don't invent
      rules" rules. Pre-inject the game-systems list at conversation start rather than
      spending a tool round on `list_game_systems`.
- [ ] **Step 7: Add `POST /api/servant/chat`** streaming `data: {json}\n\n` frames
      typed `token | tool_start | tool_end | citation | done | error`, matching the
      framing at `server.py:2212`. Add `: ping\n\n` keepalives every ~10s. Add
      `POST /api/servant/cancel/{id}`.
- [ ] **Step 8: Test with a `FakeOllama` async iterator** yielding canned chunk dicts
      — 0-tool, 1-tool, 2-tool, malformed-args → retry → give-up, max-rounds cutoff,
      tool timeout, fenced-JSON fallback. No live model needed; this is where the bugs
      will be.
- [ ] **Step 9: Verify with `curl -N`.** The result is a usable terminal GM copilot,
      and the cleanest bail-out point in the plan.

## Task 4: Persistence, scope, settings

**Files:**
- Create: `sidecar/servant/persistence.py`, `sidecar/servant/settings.py`
- Create: `sidecar/tests/test_servant_persistence.py`, `sidecar/tests/test_servant_scope.py`
- Modify: `sidecar/server.py`, `src/routes/+page.svelte`

- [ ] **Step 1: JSONL persistence** at `<data_dir>/conversations/<id>.jsonl`, one
      message per line, appended as the turn completes. Tolerate corrupt trailing
      lines on read (crash mid-write). Add `GET /api/servant/conversations`,
      `GET|DELETE /api/servant/conversations/{id}`, and a Markdown export.
- [ ] **Step 2: `PUT /api/servant/scope` taking `{game_systems, source_paths}`.**
      No `collection` field — the main window never sends one; `runSearch`
      (`+page.svelte:392-443`) invokes with exactly `{query, nResults, sourcePaths,
      gameSystems}`.
- [ ] **Step 3: Snapshot the scope into a turn-local slot under the turn lock** at
      turn start. Without this, a mid-turn solo toggle lets two tool calls in one turn
      cite two different libraries.
- [ ] **Step 4: Apply the stored scope in `/api/search` only for `X-Source: servant`.**
      Test that `mcp` and unheadered requests are provably unaffected —
      `tests/test_search_scoping.py` is the precedent.
- [ ] **Step 5: Push scope from the main window.** Wire it as an explicit call
      alongside `runSearch(committedQuery)`, **not** as a `$:` reactive statement —
      the toggles call `runSearch` synchronously before deriveds flush (see the
      comment at `+page.svelte:322-325`), and a `$:` containing an `await` is an
      infinite-loop hazard in legacy mode.
- [ ] **Step 6: `GET|PUT /api/servant-settings`** (model, max tool rounds), mirroring
      the `search_settings.json` precedent at `server.py:2627`.

## Task 5: Rust plumbing (no window yet)

**Files:**
- Modify: `src-tauri/src/lib.rs`

- [ ] **Step 1: Add `servant_chat(query, conversationId, onEvent: Channel<ServantEvent>)`,**
      reusing the `"\n\n"` framing loop at `lib.rs:481-491` verbatim. Use
      `tauri::ipc::Channel`, **not** events — `emit_to(label)` cannot reach a bare
      `listen()` and fails silently.
- [ ] **Step 2: Add `servant_cancel`, `servant_show`** (`show()` + `unminimize()` +
      `set_focus()`, the same triple as `lib.rs:1685-1687`), and the conversation
      list/load/delete commands.
- [ ] **Step 3: Extend `check_ollama_health` (`:391`)** — it matches only
      `starts_with("bge-m3")`, so a user missing the chat model gets a green lamp and
      a 404 on first message. Report the configured chat model too.
- [ ] **Step 4: Add a `#[test]` for `ServantEvent` serde shape** alongside the
      existing unit tests at `lib.rs:1756`.
- [ ] **Step 5: Verify by invoking from the *main* window's devtools.** This
      deliberately separates "does IPC streaming work" from "does a second window
      work".

## Task 6: The window

**Files:**
- Modify: `src-tauri/tauri.conf.json`, `src-tauri/src/lib.rs`
- Create: `src-tauri/capabilities/servant.json`, `src/routes/servant/+page.svelte`

- [ ] **Step 1: Add a second `windows` entry** with `"label": "servant"`,
      `"create": false`, `"visible": false`, **`"focus": false`** (it defaults to
      `true`; omitting it causes launch focus flicker), and `"url": "/servant"`.
- [ ] **Step 2: Build it in `setup()` via `WebviewWindowBuilder::from_config`,
      after `wait_for_sidecar`** so it doesn't compound the up-to-15s prod launch wait.
- [ ] **Step 3: Create `src-tauri/capabilities/servant.json`** — auto-discovered by
      `build.rs`. **Do not** add `"servant"` to `default.json`'s `windows` array; that
      would grant dialog, store, clipboard and `opener:allow-open-path $HOME/**`
      access it doesn't need. Minimum: `core:default`, plus
      `opener:allow-open-url {file://**}` and `opener:allow-open-path {$HOME/**}` for
      citations. Note the existing `#[tauri::command]`s need no capability entry —
      with no `src-tauri/permissions/` dir, non-plugin commands skip the ACL.
- [ ] **Step 4: Add a tray "Show Unseen Servant" `MenuItem`.** Both `Show` paths and
      macOS `Reopen` hardcode `"main"` and correctly stay that way; without a new item,
      hiding both windows makes the Servant unreachable. `CloseRequested` (`:1718`) is
      already label-generic and needs no change.
- [ ] **Step 5: Verify** `npm run tauri dev`, summon the window, confirm `/servant`
      loads. SPA fallback already works in both dev (vite :1420) and prod (Tauri's
      asset resolver falls back to `index.html`).

## Task 7: The UI

**Files:**
- Create: `src/lib/servant/*.svelte`, `src/lib/servant/*.ts` (+ `.test.ts`)
- Modify: `src/lib/keybindings.ts`, `scripts/build-sidecar.sh`, `.github/workflows/release.yml`

- [ ] **Step 1: Keep `src/routes/servant/+page.svelte` thin; put all real UI in
      `src/lib/servant/*.svelte`.** `npm run lint:css` globs `src/lib/**` only — UI
      placed in `routes/` escapes the raw-colour rule entirely.
- [ ] **Step 2: Extract logic into pure `src/lib/servant/*.ts` modules** — frame
      parsing, the token-stream → message-list reducer, citation → `pdfFileUrl`
      mapping, scope → payload shaping. vitest here is node-env with no jsdom, no
      svelte plugin and no `$lib`/`$app` aliases; anything importing `@tauri-apps/api`
      transitively will fail. Follow `searchScope.ts` / `searchTiers.ts`.
- [ ] **Step 3: Build the transcript** with visible tool-call rows (`searching
      «grappling rules»` → `12 results · 3 strong`). The instrumentation is the point
      of an agentic harness — when a small model goes wrong you should see it.
- [ ] **Step 4: Wire citations** to `pdfFileUrl(path, page)` → `openUrl`, the same
      path as `+page.svelte:542-546`, with `openPath` as the no-page fallback. Render
      in `--text-accent` (parchment = content).
- [ ] **Step 5: Add the chrome** — scope readout so the GM knows why answers are
      bounded, model lamp in `--text-connected` (amber = connectivity), stop button in
      `--text-danger`, composer with Enter to send / Shift+Enter for a newline.
- [ ] **Step 6: Register the summon keybinding in `src/lib/keybindings.ts`** — the
      declared single source of truth for all ~55 bindings.
- [ ] **Step 7: Add a Servant section to Settings → General** for the chat model,
      following `GeneralSettings.svelte`'s use of `get/update_search_settings`.
- [ ] **Step 8: Update the PyInstaller build.** `scripts/build-sidecar.sh` has zero
      `mcp`/`ollama` hints because `server.py` imports neither today. Add
      `--collect-all mcp`, `--collect-all ollama`, `--hidden-import
      anyio._backends._asyncio`. **Mirror the change in `.github/workflows/release.yml`**
      — the script's header says it is kept in sync, and this is only ever validated
      at tag push.

## Final verification

- [ ] `cd sidecar && pytest -v` — green, including the new `test_servant_*.py` suites.
      The one live-Ollama smoke test is marked `@pytest.mark.ollama` and deselected by
      default (CI is Linux with no Ollama).
- [ ] `npm run check` — zero errors, zero unused-CSS warnings.
- [ ] `npm run lint:css`, `npm test`, `cargo clippy`, `cargo test --lib`.
- [ ] `bash scripts/build-sidecar.sh` and `npm run tauri build` locally — the only
      validation the onefile-spawns-onefile path ever gets before a release tag.
- [ ] **Manual pass:** summon the Servant, ask a rules question, watch the tool row
      resolve, click a citation, confirm the correct PDF opens at the right page.
      Confirm the StatusBar MCP lamp stays dark throughout. Quit and confirm no
      orphaned `legend-lore-mcp` process survives.
- [ ] Only then decide whether to merge to `main`.
