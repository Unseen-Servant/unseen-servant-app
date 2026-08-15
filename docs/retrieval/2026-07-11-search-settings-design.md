# Search-pipeline settings — General tab, sidecar-wide

**Date:** 2026-07-11 · **Status:** approved
**Context:** The 2026-07-10 rerank ablation flipped the default to rerank-off on eval evidence, then reverted the same day: real-library quality visibly disagreed with the 3-book eval corpus. Instead of another silent default change, the pipeline knobs become user-visible settings.

## Goal

A **General** tab in the settings modal where the GM configures the search pipeline. Settings are the *sidecar's* defaults — every caller (desktop UI, MCP/Claude Desktop) inherits them; explicit per-request values still win.

## Knobs

| Setting | Type | Default | Notes |
|---|---|---|---|
| `rerank` | bool | `true` | Cross-encoder rerank of the candidate pool |
| `rerank_candidates` | int | `50` (env `RERANK_CANDIDATES`) | Clamped to 10–200; only meaningful when rerank is on |
| `spell_correction` | bool | `true` | Typo-tolerance section A |
| `hybrid` | bool | `false` | Experimental — BM25+RRF fusion; eval showed no aggregate gain |
| `variant_expansion` | bool | `false` | Experimental — spacing variants; eval NO-GO |

No rerank model picker (needs download-state UI; deferred). No per-search override UI.

## Architecture

**Storage (source of truth):** `search_settings.json` in the sidecar data dir, next to `collections.json`, with matching `load_search_settings` / `save_search_settings` helpers. Missing file or missing keys → defaults above (no migration). Unknown keys ignored; unparseable file → defaults + warning log. Loaded per search request (same cost class as the existing per-request `load_collections`).

**Resolution order (per knob, in the `/api/search` handler):**
explicit request field → persisted setting → built-in default.
`SearchRequest` knob fields become `Optional[...] = None`; `None` means "use settings". New field `rerank_candidates: int | None` replaces the startup-env-only pool size (env var remains the built-in default). Consequences:

- MCP inherits settings with **zero changes** to `mcp_server.py` (it doesn't send knob fields).
- The desktop UI search call is also unchanged (it doesn't send them either).
- The eval harness keeps sending explicit flags, so it stays pinned to what it claims to measure — and it runs against its own data dir regardless.

**API:** `GET /api/search-settings` returns the full effective settings. `PUT /api/search-settings` accepts a partial body, merges onto current, clamps `rerank_candidates` to 10–200, persists, returns the result.

**Tauri:** thin `get_search_settings` / `update_search_settings` commands proxying the two endpoints.

**UI:** `GeneralSettings.svelte`, self-contained (loads on mount, saves on change — the `syncPreferences` no-Save-button pattern). Tab order becomes `General | Library | Game Systems | Help`; General is the default tab. Layout: rerank toggle → pool-size number input (dimmed when rerank off) → spell-correction toggle → "Experimental" subsection (hybrid, variant expansion) with one-line descriptions noting the eval verdicts. A "Restore defaults" action resets to the table above. Styling matches existing panes.

## Error handling

- Sidecar unreachable → pane shows "sidecar not running", controls disabled.
- `PUT` failure → revert the control to its last known value, show the error inline.
- Out-of-range pool size → clamped server-side, echoed back; the control adopts the echoed value.

## Testing

- **Pytest** (`test_search_settings.py`): GET/PUT round-trip; partial update merge; clamping; resolution order (request > persisted > default) for `rerank` and `rerank_candidates`; persisted `rerank: false` actually skips the cross-encoder (monkeypatched `rerank_scores` sentinel); corrupt/missing settings file falls back to defaults.
- **Frontend:** `svelte-check` + vitest for the settings normalize/merge helper.
- **Manual:** flip knobs in the UI, confirm an MCP search honors them.

## Out of scope

Rerank model picker, per-search overrides in the search bar, growing the eval corpus (tracked separately as the fix for the eval/real-library mismatch).
