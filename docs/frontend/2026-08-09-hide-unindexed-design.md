# Hide unindexed items — design

**Date:** 2026-08-09
**Status:** Implemented 2026-08-09 on main — c15e2ff (predicate), e6cb6d4
(nav rows), b324831 (FileTree), 3a01743 (console row), c78bb4e (chip),
a709a2a (persistence), ec6435e (wiring). svelte-check, vitest, stylelint
and the vite build all green; the plan's manual QA checklist is still
pending.
**Related:** `docs/frontend/2026-08-08-solo-mute-play-doctrine-design.md`
(the focus lens and the hide/mute territory split this amends),
`src/lib/treeNav.ts`, `src/lib/FileTree.svelte`, `src/lib/FilterPanel.svelte`.

## Problem

The focus lens exists because "thousands of dimmed rows are still
thousands of rows" — dimming communicates scope but doesn't shrink the
surface. It only shrinks the *indexed* slice, though. A GM with 2000
PDFs and 300 indexed turns the lens on and still scrolls 2000 rows: the
1700 unindexed ones were never in scope's vocabulary, so the lens has
nothing to say about them.

The existing verb for unindexed clutter is per-item hide (context menu,
the `.` key). It persists and it recovers cleanly, but it doesn't scale
— nobody hides 1700 files one gesture at a time.

## Why not extend the lens

Folding unindexed material into `hideOutOfScope` was considered and
rejected on three counts:

1. **It collapses a deliberate territory split.** The doctrine assigns
   hide as the visibility verb for what scope can't speak about, and
   mute + lens as the disappearing verb for indexed material. An
   unindexed file isn't out of scope; it isn't in the conversation. The
   recovery gestures differ too — unmute versus go index it.
2. **The tree is the indexing surface.** Tree checkboxes feed
   `selectedPaths` into the index run. A lens that hid unindexed rows
   would hide exactly the rows needed to grow the library, and the lens
   persists across launches — a user who left it on last week would find
   they simply cannot add books, with a small "lens on" chip as the only
   evidence.
3. **It destroys the lens's no-op guarantee at the worst moment.** The
   doctrine promises that with no narrowing engaged the lens is a
   harmless no-op. Merged, a fresh library with nothing indexed and a
   persisted lens shows an empty tree — maximally destructive precisely
   at onboarding.

A separate switch keeps all three properties and still delivers the
300-row tree.

## Behavior

A third masthead row in the filter console, **Hide unindexed items**,
sibling to "Show hidden items" and "Hide out-of-scope items". Three
orthogonal switches, each naming one reason a row is absent: manually
hidden, never ingested, out of scope.

**Hide only, never dim.** Toggle off reproduces today's tree exactly.
The doctrine's rule that unindexed files keep their existing treatments
stays true of the default view; this adds a hide tier without adding a
dim tier, and without a second dim level to reconcile against
`--opacity-out-of-scope`.

**The predicate.** A row hides when the library knows nothing about it:

- *File* — not in `indexedPaths` and not in `selectedPaths`.
- *Folder* — no indexed descendants and no selected descendants.

Selection is part of the predicate, not just the index. `indexedPaths`
is built from `up_to_date + to_update + to_remove` and deliberately
excludes `to_add`, so keying on the index alone would make a row vanish
the moment its box was checked, and keep every queued file invisible
until the run finished. Including selection means:

- Checking a box keeps the row on screen.
- Queued files stay visible through the index run.
- Deselected-but-still-indexed files (`to_remove`) stay visible — you
  need to see what is about to leave.

**Tree only.** `SystemsView` renders `indexStatus` entries, so it holds
nothing unindexed to hide; the prop is not threaded there. This is a
deliberate asymmetry with the lens, which applies to both browsing
surfaces.

**Empty state.** When the toggle hides every row, the tree shows the
one-line placeholder **"Nothing in the library yet."** rather than
reading as broken — same `.scope-empty` treatment as "Everything is out
of scope." The exact condition is
`hideUnindexed && indexedPaths.size === 0 && selectedPaths.size === 0`:
if the library knows nothing, every row hides, and nothing else
produces a fully empty tree.

**Chip.** The scope bar gains an `indexed only` chip sharing the purple
`.chip.lens-on` treatment — purple marks a mode the user switched on,
and whole-chip click disengages it. Recovery stays two-deep: the chip on
the bar, the checkbox in the console.

## Accepted cost

With the toggle on, adding a book that is neither indexed nor selected
requires turning it off first. This is accepted rather than designed
away: the selected-aware predicate confines the friction to genuinely
new material — nothing already in the index or in flight disappears —
and recovery is two-deep as doctrine requires. No mode-suppression rule
(of the kind `SystemsView` uses for the lens in collection-edit mode) is
added, because unindexed files are irrelevant to collection editing
anyway; there the toggle is a help, not a hazard.

## Implementation deltas

1. **`src/lib/treeNav.ts`** — a `LibraryKnowledge` interface
   (`indexedPaths`, `indexedFolderPaths`, `selectedPaths`,
   `foldersWithSelections`) and one pure predicate composed from the
   existing one:

   ```ts
   export function rowHasLibraryMaterial(path, isDir, known: LibraryKnowledge): boolean {
     return rowHasIndexedMaterial(path, isDir, known.indexedPaths, known.indexedFolderPaths)
         || rowHasIndexedMaterial(path, isDir, known.selectedPaths, known.foldersWithSelections);
   }
   ```

   Composition, not a unioned set: unioning would rebuild a
   multi-thousand-path `Set` on every selection click, which the
   `reuseIfSame` pattern in `+page.svelte` exists to avoid. Two O(1)
   lookups instead.

2. **`computeVisibleRows`** — a defaulted `library: LibraryKnowledge |
   null = null` parameter, applied immediately after the hidden-paths
   rule. Keyboard nav and render share the predicate so the two can
   never drift, the same discipline the lens follows through
   `isRowOutOfScope`.

3. **`src/lib/FileTree.svelte`** — one new prop, `hideUnindexed:
   boolean`, ORed into the existing `$: hidden`. `selectedPaths` and
   `foldersWithSelections` are already props, so nothing else threads.

4. **`src/lib/FilterPanel.svelte`** — the third masthead row, always
   enabled (unlike "Show hidden items", which disables when nothing is
   hidden — the equivalent check here would need a whole-tree scan for
   no real benefit).

5. **`src/lib/SearchScopeBar.svelte`** — the `indexed only` chip; the
   `.chip.lens-on` rule grows a second selector rather than being
   duplicated.

6. **`src/routes/+page.svelte`** — state, toggle handler, prop
   threading, and the empty-state placeholder beside the existing
   `.scope-empty`.

7. **Doctrine amendment** — the "Hide stays display-only" section of the
   2026-08-08 design doc states that hide is *the* visibility verb for
   unindexed material. That becomes two verbs: per-item hide, plus this
   bulk switch. Amend rather than leave the spec contradicting the code.

## Persistence

Its own store key, parallel to `showHidden` — not the scope-console
blob. It is a view mode, not a narrowing, so it stays out of the console
schema, out of `parseScopeConsoleState`, and out of `[clear all]`,
matching the existing rule that the focus lens survives a clear.

## Testing

`src/lib/treeNav.test.ts` covers the new predicate and the new
`computeVisibleRows` behavior:

- A folder whose descendants are all unindexed and unselected is skipped
  with its subtree.
- A folder with one selected-but-unindexed descendant is kept, and so is
  that descendant — the queued-file case.
- An indexed-but-deselected file (`to_remove`) stays visible.
- The toggle off reproduces the current row list exactly.
- The predicate and the lens compose: a row hidden by either is absent,
  and neither disables the other.

Persistence is a plain boolean through the existing `parseBoolean` path,
already covered by that pattern's tests.
