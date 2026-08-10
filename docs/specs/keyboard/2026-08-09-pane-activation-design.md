# Pane activation vs. caret placement — design

**Date:** 2026-08-09
**Status:** Implemented 2026-08-09 on main. Automated gates green; the manual
QA checklist below is pending.
**Supersedes:** the state model in
`2026-08-09-pane-focus-model-design.md`. That spec's rule — "setting one token
nulls the other two" — is no longer the whole story. Everything else in it
(row identity by stable key, the `⌘⌥` chords, the deferrals) still stands.
**Related:** `src/lib/paneFocus.ts`, `src/routes/+page.svelte`,
`src/lib/CollectionsPanel.svelte`, `src/lib/FilterPanel.svelte`,
`src/lib/SystemsView.svelte`.

## Problem

Clicking anywhere non-selectable in a pane planted the caret on row 0. The
Collections masthead, the sort button, `+ collection`, a systems-view group
header, a scope-bar chip, the empty space below the last tree row — all of them
put a parchment ring on the first row of a list the user had not pointed at.

One variable was doing two jobs. `focusedFilePath`, `focusedCollectionName` and
`focusedFilterRow` each meant both *"this pane owns the arrow keys"* and *"the
caret is on this row"*. Being the same variable, a pane could not be handed the
keyboard without also being handed a caret — so every chrome-click handler
ended in `setFocused…(rows[0])`.

Two smaller problems fell out of the same knot:

- **The Filters panel had no mouse entry point at all** — no row click handler,
  no chrome handler. `⌘⌥↓` was the only way in. The previous spec opened by
  calling that asymmetry out; it survived the change that was meant to close it.
- **The mutex had a hole.** Neither the tree-nav gate nor `SystemsView`'s key
  handler checked `focusedFilterRow`, so `↓` with the filter panel focused fired
  `stepFilterRow` *and* the file-region nav, and the file caret won the race.

## Decision

Split the two jobs into two axes.

| Axis | State | Means | Set by |
| --- | --- | --- | --- |
| Ownership | `activePane: 'files' \| 'collections' \| 'filters'` | which region answers arrows | chrome mousedown, `⌘⌥` chords, any caret placement |
| Caret | the three nullable tokens | where the ring is drawn | row click, keyboard nav, `claim()` |

This is the state-level echo of the row-state grammar
(`docs/design/2026-08-09-row-state-grammar-design.md`): *background says what a
row is, a ring says where the caret is.* Ownership and caret were already
separate ideas visually; now they are separate in the model behind them.

### Why `activePane` is not nullable

The file region is the resting owner. `handleTreeNavKey` and `SystemsView`'s key
handler already accepted arrows with a null caret and materialized on their own,
so `'files'` is simply the name for what used to be spelled "no token anywhere".
Making it explicit costs nothing and turns the two missing gate checks above
into a type.

### The invariant

> At most one caret exists, and it belongs to the active pane.

Four rules, all in `+page.svelte`:

1. **Activating clears foreign carets.** `setActivePane` is a no-op when the
   pane is already active, so re-clicking a pane's chrome preserves the caret it
   already has.
2. **Placing a caret implies activating.**
3. **Clearing a dock caret returns ownership to `'files'`.** This is why Escape
   and panel-close release for free — both already call `setFocused…(null)`.
4. **Clearing the file caret changes nothing**, since `'files'` is the resting
   state.

### Materialization

Pressing an arrow with a pane active and no caret places the caret at the
pane's last-focused row, falling back to the direction-aware first/last row when
that row is gone. It **places, it does not step** — the first `↓` lands *on* the
restored row, not one past it.

`src/lib/paneFocus.ts` holds that as a pure function, `materializeKey(keys,
last, delta)`, called from all four list panes. It is the change's only
automated coverage: `vitest.config.ts` includes `src/**/*.test.ts` with no jsdom
and no Svelte plugin, so nothing inside a `.svelte` file is reachable. Extracting
the fragile rule and testing it follows the `src/lib/filterRows.ts` precedent.

Restoring rather than landing on row 0 is a deliberate choice: a coarse "point
at the panel" gesture should not throw away the user's position, which is the
same promise `⌘⌥←/→/↑/↓` already make.

### Gates

Every pane's window-keydown gate becomes the same line, `if (!active) return;`.
The two dock gates **loosen** — they now run with a null caret so the first
arrow can materialize — which is the whole mechanism. `FilterPanel` gains a
`focusedRow === null` guard ahead of its Space/Enter/S/M branches, since those
call `rowElByKey` and are newly reachable with no caret; `CollectionsPanel`'s
existing `idx < 0` guard already covered it. Escape stays above both so it can
release a pane that never grew a caret.

### Search

Both dock panes stay mounted while the search view is open, so `active` is
ANDed with `!searchViewOpen` at the call site. Without it, a pane left active
from browse mode steps its caret alongside the result selection — a
pre-existing double-fire (opening search never released the dock), now closed.
`SystemsView` needs no equivalent: it is unmounted under search.

`selectedResultIndex` stays outside the model and non-nullable. It is a
selection with a downstream consumer — it drives `SearchInspector` — not a
caret; the search view arbitrates arrows by real DOM focus rather than by a
token; and no gesture lands it on row 0 unintentionally.

## Decided non-changes

- **Row clicks still draw the caret.** Only chrome and non-selectable space are
  silent. The ring marks the row that `S`/`M`/`P`/`Space`/`R`/`A`/`X`/`.`/`⌘O`
  act on, so a mouse user needs to see it after clicking a row.
- **No input-modality tracking** — no `lastInputWasKeyboard`, no
  `:focus-visible` polyfill. The caret is virtual (a class, not DOM focus), so
  we already control exactly when it is drawn; a modality heuristic would be a
  second mechanism guessing at what `activePane` states outright.
- **Still no shared pane-focus component module.** The old spec deferred it
  until "a fourth pane appears or the three copies first drift". Neither
  happened, and this change moves the other way: three differently-shaped gates
  (`focusedName === null`, `focusedRow === null`, `focusedCollectionName !==
  null`) converge on one identical `if (!active) return`.
- **Tab is still out of scope**, as in the superseded spec.

## Behaviour changes to expect

1. **`Esc` then `↓` returns to your last row** instead of landing on row 0.
   Materialization is one rule regardless of what cleared the caret; two rules
   for the same visible state (pane active, no caret) would mean remembering
   *why* it is null.
2. **`↓` with the Filters pane focused no longer moves the tree.** That is the
   mutex hole closing.
3. **Clicking anywhere in the Filters panel now gives it the arrows** — its
   first mouse entry point.

## Verification

`npm run test` (including `src/lib/paneFocus.test.ts`), `npm run check`,
`npm run lint:css` — all green.

Manual QA, none of it reachable by an automated gate:

1. Click the empty area below the last tree row → no caret; `↓` restores the
   last row you were on.
2. Click a scope-bar chip → no caret; the chip still clears its narrowing.
3. Systems mode: click a group header → no caret; it still expands.
4. Click the Collections masthead / sort button / `+ collection` → no caret;
   `↓` restores your last collection row.
5. Click the Filters masthead / `clear all` / a section label → the pane takes
   the arrows; `↓` restores your last filter row.
6. Caret on collections row 3 → click the collections masthead → caret stays on
   row 3.
7. Caret on a tree row → click the collections masthead → tree caret
   disappears, no collections caret appears.
8. Filters focused → `↓` must not move the tree, in both tree and systems mode.
9. `Esc` from each dock pane → caret gone *and* the next `↓` moves the tree.
10. Chrome-click Collections, then `⌘B` to close it → `↓` moves the tree.
11. Chrome-click Filters, then `⌘E` to close it → `↓` moves the tree; `⌘⌥←`
    still works. (This is the superseded spec's still-pending QA item 8, now
    actually testable.)
12. Chrome-click Filters → `⌘⌥↑` reaches Collections.
13. `⌘N` draft row → chrome-click the panel → `↓` lands on the draft; Esc
    discards it.
14. Empty collections list → chrome-click → `↓` does nothing; one Esc restores
    tree arrows.
15. Search open: click dock chrome, then `↑`/`↓` → the results list navigates
    and nothing in the dock moves.
16. `⌘⌥←/→/↑/↓` still restore the last-focused row in each pane.
17. `S`/`M`/`Space`/`P`/`A`/`X`/`.`/`⌘O` are inert while a pane is active with
    no caret, and act on the row once one materializes.
18. Long tree: chrome-click, then `↓` — the restored row scrolls into view
    without a jarring snap (`focusTreeRow` calls `scrollIntoView`).

## Outcomes

Recorded on completion.
