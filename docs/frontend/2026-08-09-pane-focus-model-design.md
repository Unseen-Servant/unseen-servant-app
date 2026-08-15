# Pane focus model — the filter panel joins the keyboard — design

**Date:** 2026-08-09
**Status:** Implemented 2026-08-09 on main — 480dd30 (row model), bb0ff52
(third token), af21ec8 (pane pattern), 4699dae (role=checkbox rows),
e6186a7 (wiring), a8c7b6a (dock chords), a442ef1 (registry).
svelte-check, vitest, stylelint and the vite build all green; the plan's
manual QA checklist is still pending.
**Partly superseded 2026-08-09** by
`2026-08-09-pane-activation-design.md`. The state model below — one token per
pane, "setting one nulls the other two" — was split in two: `activePane` now
carries keyboard ownership and the tokens carry only caret placement, so a
pane can be claimed without a caret being drawn. Row identity by stable key,
the `⌘⌥` chords and the deferrals recorded here are unaffected.
**Related:** `src/lib/FilterPanel.svelte`, `src/lib/CollectionsPanel.svelte`,
`src/routes/+page.svelte`, `src/lib/keybindings.ts`, commit 3c6ef23 (the
interim Escape fix this design supersedes).

## Problem

The filter panel's keyboard model was written when it was a dropdown
menu. It became docked furniture and the keyboard code never followed.

The app already has a coherent pane pattern, used by the file tree and
the collections panel:

- a focus token per pane (`focusedFilePath`, `focusedCollectionName`),
- mutual exclusion between tokens, so exactly one region claims the
  keyboard (`setFocusedFilePath` / `setFocusedCollectionName`),
- last-focused memory per pane, so returning lands where you left,
- a `claim(preferred)` method on the component,
- a window-level keydown handler that early-returns when the token is
  null,
- `⌘⌥←` / `⌘⌥→` to move between regions.

`FilterPanel` implements none of it. It takes real DOM focus on its
`<aside>` at mount, listens with an element-scoped handler, and tracks
an integer `focusedIdx` into a live `querySelectorAll('[data-fm]')`.
Three consequences:

1. **The panel is unreachable by keyboard.** `focusCollectionsRegion` is
   hardcoded to collections — it even force-opens that panel — so
   "Focus left pane" cannot land on Filters. The mouse and the mount-time
   auto-focus are the only ways in.
2. **There was no way out.** Escape used to close the panel, which also
   persisted `filterPanelOpen: false` — a reflex Escape silently rewrote
   the dock layout for every future launch. Commit 3c6ef23 removed that,
   which was correct but left the panel with no exit at all.
3. **The cursor is always lit.** `focusedIdx` is clamped to `≥ 0`, so a
   row wears the cursor highlight from first paint whether or not the
   panel has focus — it reads as "this row is different" rather than
   "this is where j/k will act."

The registry still encodes the origin: the scope is named `filterMenu`.

## Model

Three peer panes, one focus token each, mutually exclusive. The filter
panel becomes the third participant in machinery that already exists.

```ts
function setFocusedFilterRow(key: string | null) {
  focusedFilterRow = key;
  if (key) { focusedFilePath = null; focusedCollectionName = null; }
}
```

The two existing setters each null the new token as well. Three setters
of three lines: explicit and greppable. Not worth abstracting at N=3 —
see Follow-up.

`lastFocusedFilterRow` joins the two existing `$:` trackers so
`⌘⌥↑`/`⌘⌥↓` restore the cursor rather than resetting it to row 0.

`FilterPanel` gains what its siblings have: a `claim(preferred)` method,
a `<svelte:window on:keydown>` handler that early-returns on a null
token, and the same yield stack `CollectionsPanel` uses — inline
renames, the sort/context menus, `dialog[open]`, and
`input, textarea, [contenteditable]` targets.

## Row identity

`focusedIdx` is an integer index into a DOM query, and it is fragile:
the systems list grows as files are indexed, `showSystemFilter` flips
with view mode, `showCollectionFilter` with context, and `hasHidden`
decides whether the first row is navigable at all. Index 3 means a
different row after a re-index.

New module `src/lib/filterRows.ts`:

```ts
export type FilterRowKind = 'view' | 'curation' | 'system';
export interface FilterRow { key: string; kind: FilterRowKind; }

export function computeFilterRows(input: {
  hasHidden: boolean;
  showCollectionFilter: boolean;
  showSystemFilter: boolean;
  systems: { name: string; count: number }[];
  untaggedCount: number;
}): FilterRow[];
```

Stable keys: `curation:collected`, `curation:loose`, `system:<name>`,
`system:unknown`, `view:showHidden`, `view:hideUnindexed`,
`view:hideOutOfScope`. The token is `string | null`, matching
`focusedCollectionName`.

**Order is Curation → Systems → View**, matching the rendered DOM as of
commit c4f4f81, which moved the Hidden-items section to the bottom of
the panel. The function's output order *is* the navigation order, so it
has to track the template — the same contract `computeVisibleRows` holds
for the tree.

The panel renders its navigable set from this list rather than querying
`[data-fm]`, so the row model stops being a side effect of the DOM. The
rules the query encoded move into the function and become testable:

- Curation rows are present only when `showCollectionFilter`.
- System rows are present only when `showSystemFilter`;
  `system:unknown` additionally requires `untaggedCount > 0`.
- `view:showHidden` is present only when `hasHidden` — a disabled row
  never takes the cursor (today's `data-fm={hasHidden ? …}`). The other
  two view rows are unconditional.

## Navigation

| Chord | Meaning |
|---|---|
| `⌘⌥←` / `⌘⌥→` | Left dock ↔ file region (meaning unchanged) |
| `⌘⌥↑` / `⌘⌥↓` | Collections ↔ Filters, within the dock |
| `Esc` | Release the filter pane's token |
| `j`/`k`, `↑`/`↓`, `Home`/`End`, `S`, `M`, `Space` | Unchanged vocabulary |

`⌘⌥↑`/`⌘⌥↓` were chosen over cycling `⌘⌥←` so the arrow stays literal:
the dock stacks vertically, so vertical chords move within it. A pane
that is closed is skipped; if neither dock panel is open, the chord is a
no-op rather than opening one.

`⌘⌥←` currently force-opens the collections panel. It becomes "focus the
dock's last-focused panel," preferring collections when there is no
memory, and still opening the dock when it is closed.

**Escape composes for free.** The global ladder's Escape branch only
acts `if (focusedFilePath)`, and mutual exclusion guarantees that token
is null whenever the filter pane holds focus. So releasing the filter
token cannot also wipe the tree highlight — no ordering dependency
between the two window handlers is introduced.

**Cursor scrolling.** The panel body is `overflow-y: auto`, and today
the cursor stays visible only because DOM focus scrolls it into view.
Dropping DOM focus means the cursor move must call
`scrollIntoView({ block: 'nearest' })` explicitly. Easy to omit; called
out here because its absence only shows up in a long systems list.

## The three view rows become `role="checkbox"`

The Hidden-items section's rows are `<label><input type="checkbox">`.
Under a window-level handler that is a hazard, not a style preference:
Space has two competing activation paths (our handler's synthetic click
and the label's native activation), and the `input, textarea` yield
guard becomes ambiguous when the target is one of the panel's own rows.

Converting them to `role="checkbox"` with `aria-checked` gives the row
sole control of activation. This is the path the codebase already took
elsewhere — `app.css` says so at the `.app-checkbox` recipe: *"Both a
native input and a `role="checkbox"` button drive this recipe — the tree
and systems views use buttons so their rows keep control of focus and
click handling."* The recipe already styles `aria-checked="true"` and
`"mixed"`, so the conversion costs no CSS.

Tab behavior is explicitly **not** in scope. The panel's `S`/`M` buttons
and `clear all` are real buttons and stay in the tab order exactly as
they are; the same is true across the tree and collections. Roving
tabindex was considered and rejected — the sibling panes do not use it,
and matching the siblings is the point of this change.

## Deletions

All popover machinery with no remaining job:

- `panelEl.focus()` in `onMount`
- `previouslyFocused` and the entire `onDestroy` focus-restore
- the `querySelectorAll('[data-fm]')` inside `refreshRowsAndFocus`
- `focusedIdx`
- the `data-fm` attributes themselves, once the row model is data-driven

## Registry and help overlay

`keybindings.ts` is the declared single source of truth, and `?` renders
from it, so this change must land there too:

1. Rename the `KeyScope` member `filterMenu` → `filterPanel` and the
   five `filterMenu.*` binding ids. The scope string also appears in
   `KeyboardHelpOverlay.svelte` and `help/ReferencePane.svelte`, each
   with its own `SCOPE_ORDER` array and `SCOPE_LABELS` map — three files
   total. This is a code-clarity rename only: both display labels
   already read "Filters panel" / "Filter console", so nothing
   user-visible changes.
2. Add `focus.dockUp` / `focus.dockDown` for `⌘⌥↑` / `⌘⌥↓`.
3. Correct `focus.collections`'s label — "Focus left pane" is no longer
   what it does now that the dock holds two panes.
4. Add an Escape entry under the filter-panel scope: "Release focus /
   leave the panel."

## Testing

`src/lib/filterRows.test.ts` — the row model, which is the first
unit-testable piece the panel has had:

- a row's key is unchanged after a system is added to the list — the
  case the integer index got wrong,
- `view:showHidden` is absent when `hasHidden` is false,
- curation rows absent when `showCollectionFilter` is false; system rows
  absent when `showSystemFilter` is false,
- `system:unknown` absent when `untaggedCount` is 0, present when it is
  positive and `showSystemFilter` is true,
- order is Curation → Systems → View, so `j`/`k` walk visually adjacent
  rows.

Pane arbitration (the three setters) gets a unit test only if it moves
into a module; inline in `+page.svelte` it stays manual.

Everything else is manual QA, since the repo has no component test
harness:

1. `⌘⌥↓` from collections lands on Filters at the remembered row.
2. `⌘⌥↑` returns to collections at *its* remembered row.
3. The cursor is invisible until the pane is claimed, and disappears
   again on Escape.
4. Escape in the filter pane leaves the tree highlight untouched.
5. `j`/`k` past the visible area scrolls the cursor into view.
6. `S`/`M`/`Space` act on the cursor row, including the converted
   `role="checkbox"` rows.
7. Claiming any pane visibly releases the other two.
8. Closing the Filters panel while it holds focus does not strand the
   keyboard.
9. `?` lists the new chords under a "Filters panel" heading.

## Follow-up (not this change)

The pane pattern is now triplicated by convention with no shared code —
three tokens, three last-focused trackers, three near-identical yield
stacks. Extracting a shared pane-focus module is the right end state and
is deliberately deferred: doing it now would refactor two working
surfaces and put the whole app's keyboard at regression risk for a
problem that has not yet bitten. Revisit when a fourth pane appears or
when the three copies first drift.
