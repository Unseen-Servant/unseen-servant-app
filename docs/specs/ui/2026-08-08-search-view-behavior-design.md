# Search View Behavior — Design

**Date:** 2026-08-08
**Status:** Approved
**Scope:** Frontend only (`src/routes/+page.svelte`, `src/lib/Header.svelte`, `src/lib/SearchResults.svelte`, `src/lib/keybindings.ts`). No sidecar or Rust changes.

## Problem

The search view is derived state: `searchActive = committedQuery.trim() !== ''`. It appears only once a query is committed and vanishes the instant the query empties. Consequences:

- Clicking or focusing an empty search bar does nothing view-wise.
- Escape with text in the bar clears the query, which destroys the search view in one keystroke — results, selection, and scroll position are all lost.
- The tree/systems view switch is hidden during search and Cmd+J / Cmd+T are disabled, so clearing the query is the *only* exit.

## New model

Search becomes a stateful view you enter by focusing the search bar and leave only explicitly.

- **Enter:** focusing the search input (click, Tab, Cmd+F — all funnel through the input's `focus` event).
- **Leave:** selecting tree or systems in the view switch (or Cmd+J / Cmd+T), or the Escape ladder: search results → search bar → previous view.
- **Escape never clears the query.** The ✕ button is the only clear, and clearing is not an exit.
- Query text and results survive leaving the view; refocusing the bar restores them instantly.

### Decisions taken

1. **Empty search view shows an empty-state hint.** Focusing the bar always brings up the search view, even with no query; the results pane shows a quiet "Type to search your library" message. (Chosen over "swap only when there's a query" and "recent searches".)
2. **View switch: neither segment current during search.** Both segments render idle; clicking either — including the one matching the stored `viewMode` — exits search into that view. (Chosen over "previous view stays raised" and "third search segment".)

## State

`+page.svelte` gains:

```ts
let searchViewOpen = false;
```

- Not persisted — the app always launches into the browse view (`viewMode` from the store).
- `viewMode: 'tree' | 'systems'` is untouched and remains the "previous view" that exits return to; its persistence already exists.
- `searchActive` (committed query non-empty) keeps its meaning for result-dependent wiring: the scope bar hits meter, stale-results logic, pagination.

Rejected alternatives: making `'search'` a third `viewMode` (touches store persistence, every `viewMode` comparison, and the picker contract, and still needs a shadow "last browse mode"); patching the derived state (cannot represent "search view open with empty query").

## Entry

- `Header.svelte`: new `onFocus` prop, wired to the input's `on:focus`. Page handler sets `searchViewOpen = true`.
- Cmd+F already calls `headerComponent.focus()`; the focus event covers it. Typing, debounce (300 ms), and Enter-submit are unchanged.

## Rendering

- File area: `{#if searchViewOpen}` renders the search split (results + inspector), `{:else if viewMode === 'systems'}` / `{:else}` as today.
- `SearchResults.svelte`: new state branch — empty query, no error → "Type to search your library" hint, following the existing `state-msg` pattern.
- Gates that switch from `searchActive` to `searchViewOpen` (they mean "search view on screen"):
  - `.search-mode` class on `.file-tree-area`
  - `systemsFilterRelevant` / `curationFilterRelevant` (`viewMode === 'systems' || searchViewOpen`)
  - `fileActionGate`, tree-nav gate, Cmd+Alt+←/→ region-jump gate (tree/systems rows aren't on screen during search view)
- Gates that keep `searchActive` (they mean "a query has results"): scope bar hits meter wiring, `stale` computation, `loadMoreResults`, Cmd+1–9 / results-list handlers (already guarded by `searchResults.length`).

## View switch

- `viewToggleVisible` becomes `!!selectedFolder` (no longer hidden during search).
- Header receives `searchViewOpen`; while true, neither segment gets `.current`, and both segments' click handlers call `onSetViewMode(mode)` unconditionally. The tree segment's collapse-all repeat action fires only when the tree is actually on screen (`!searchViewOpen && viewMode === 'tree'`).
- `setViewMode()` sets `searchViewOpen = false` and blurs the search input if it holds focus (it is the exit path for picker clicks and chords; without the blur, Cmd+J/Cmd+T from inside the bar would leave a focused input feeding a hidden search — typing wouldn't re-fire `focus`, so the view would never reopen).
- Cmd+J / Cmd+T drop their `!searchActive` gates: during search view they exit into systems/tree, matching the visible control. Cmd+T's collapse-all repeat keeps its current meaning only when already in the tree view with search closed.

## Escape ladder (revised)

Closing precedence, top-most first. Steps 1–3 and modal handling are unchanged.

1. Open context menu → close (ContextMenu's own handler)
2. Inline rename in flight → cancel
3. Competing popover (sort menu / dropdown / collections context menu) → its own handler
4. Focus in search results list → focus the search bar *(exists today)*
5. **New:** search view open, focus anywhere else outside the bar (e.g. after clicking a scope chip) → focus the search bar
6. **New:** focus in the search bar (search view open) → `searchViewOpen = false`, blur, keyboard focus lands in the restored view via `focusFileRegion()` (last-focused row if visible, else first). Query text, results, and selection survive.
7. Focused tree row → clear focus

Removed behaviors superseded by the new model:

- `Header.svelte` Escape-clears-text branch — deleted; Escape bubbles to the global handler.
- "Empty search input Escape → blur + focus first tree row" branch in `+page.svelte`.
- "ArrowDown from empty search input → first tree row" branch — the tree is never on screen while the input is focused. ArrowDown from the input still moves into the results list when results exist; with none, it does nothing.
- `search.intoTree` keybinding entry in `keybindings.ts` (rendered by the help overlay and reference pane).

## Edge cases

- **Collection edit mode** disables the search input. Entering edit mode while the search view is open also closes the search view (one line in the edit-mode entry path); otherwise a disabled bar would strand the user in an un-leavable view. Query text still survives.
- **✕ clear button:** clears query and results, refocuses the input — user stays in the (now empty) search view. Unchanged behavior, new framing: clearing ≠ exiting.
- **App launch:** search view never open at start, regardless of persisted `viewMode`.

## Verification

Repo convention is vitest on pure modules only; the keyboard glue in `+page.svelte` stays untested (no new abstraction for single-use, DOM-entangled logic). The implementation plan carries:

- `npm run check` (svelte-check), `npm run lint:css`, existing vitest suite green.
- Manual walkthrough: enter via click / Tab / Cmd+F; exit via each picker segment, Cmd+J, Cmd+T; triple-Escape ladder from a focused result; Escape preserves query text; ✕ clears but stays in search view; ArrowDown input↔results round-trip; collection edit mode closes search view; relaunch starts in browse view.
