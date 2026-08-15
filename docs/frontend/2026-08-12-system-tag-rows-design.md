# System Tag Rows — Design

**Date:** 2026-08-12
**Status:** Designed. Implemented same day.

## Problem

The game-system picker is implemented twice with no shared source of
truth.

`ContextMenu`'s "Game system" submenu and the standalone `SystemTagMenu`
render the same thing: a `.menu-pip`, the Font Awesome dice-d6 path, an
ellipsizing tag label, a divider, and a "Clear tags" row in danger ink.
The dice path is 400 characters of SVG copied byte-for-byte. Their CSS
matches too — `.context-item` and `.dropdown-item` declare the same
eleven properties, `.submenu-tag` and `.dropdown-tag` the same four.

Nothing keeps them that way. The prose matches today because it was
hand-matched.

Two smaller things surfaced while surveying:

1. **The trigger gates disagree.** `ContextMenu` offers "Game system"
   only under `canTag` — `!item.is_dir && isIndexed && knownSystems.length > 0`.
   `FileTree`'s `+ tag` button calls `tagMenu?.toggle(e)` for any indexed
   file, so with no systems known it opens a menu with nothing in it and
   no copy explaining why. This is reachable three ways: a fresh profile
   before the first `fetchIndexStatus` fills `knownSystems`
   (`+page.svelte:1184`), a sidecar that hasn't come up, and a library
   where every built-in has been disabled and every custom deleted.

2. **A leading divider in the tagged-but-unknown state.**
   `SystemTagMenu` renders its `<hr>` on `tags.length > 0` regardless of
   whether any rows precede it. Tag a file, then disable that system in
   Settings: the menu opens on a divider with "Clear tags" under it.

## Decision

### `SystemTagRows.svelte` — the block, not the row

One component owning the whole repeated stretch: the system rows, the
divider, and "Clear tags". Extracting only the row would leave the
divider condition and the danger-ink clear row duplicated, which is
where two of the three defects above live.

```
knownSystems, tags → rows
onToggle(tag), onClear()
```

The callbacks keep the shapes each surface already had. `onToggle`
emits a single tag, so `ContextMenu` keeps merging it into the array it
hands `onSetGameSystems` and `SystemTagMenu` keeps delegating upward.
`onClear` fires and returns, so `SystemTagMenu` keeps closing itself
after. Neither surface changes behavior.

Rows always carry `data-mi="item"`. It is what `ContextMenu`'s keyboard
nav queries, and it is inert in `SystemTagMenu` until the
[shared menu machinery](2026-08-11-shared-menu-machinery-design.md)
lands, at which point `menuKeys.ts` reads the same attribute. A prop to
switch it off would be configurability nobody asked for.

The divider renders only when it has two things to separate —
`knownSystems.length > 0 && tags.length > 0`. That is defect 2.

### `.menu-row` and `.menu-divider` — global vocabulary

`app.css`'s `--- Menu Vocabulary ---` section already hosts `.menu-pip`
and `.menu-chord` as anatomy shared across menus. The row base joins
them, along with its `:hover` / `.kb-focused` fill and its `.danger`
ink, and the divider rule.

`ContextMenu` and `SystemTagMenu` both convert. This is what keeps the
extraction from making things worse: a `SystemTagRows` carrying its own
scoped row CSS would be a *fifth* copy of that property set, and it
would render tag rows under a different rule than the Collection rows
directly above them in the same menu. Trading cross-surface drift for
within-menu drift is not a fix.

`SystemTagMenu` is left with `.dropdown` alone — the class the
page-level Escape ladder queries for, so it stays.

### Trigger gating, both directions

The empty menu is gated, not captioned. `FileTree`'s `+ tag` renders
under `isIndexed && knownSystems.length > 0`, mirroring `canTag`.

The two already-tagged triggers — `FileTree`'s badge cluster and
`SearchInspector`'s system badge — stay ungated. In that state the menu
is not empty: "Clear tags" is there, and it is the only way to un-tag a
file whose system has since been disabled.

`canTag` widens for the same reason: `knownSystems.length > 0 ||
currentTags.length > 0`. Without it the tree's context menu hides
"Game system" on exactly the file that needs clearing, while the row's
own badge still offers it — the mirror image of defect 1.

## Decided non-changes

- **No empty-state row.** No menu in the app has empty-state prose, and
  the Collections submenu never needs it because `+ New collection…` is
  always present. The tag menu has no in-menu creation action, so an
  empty menu is a dead end to close rather than a state to caption. A
  "No game systems yet" row would also be false during the startup
  window, when the true answer is "not loaded yet".
- **`CollectionsPanel` keeps its two copies.** `.context-item:1354` and
  `.sort-item:979` are the same property set again. Converting them is
  the right cleanup and it is not this change; it belongs with the
  menu-machinery adoption pass, which is already editing those rows.
- **`.submenu-icon` stays in `ContextMenu`.** It sizes the collection
  ribbon, which is not shared with anything. `SystemTagRows` sizes its
  die itself.
- **The dice-d6 path stays inlined per surface.** Found while checking
  the extraction: the same 400-character path is also drawn by
  `SystemBadge`, `FilterPanel`, `SystemsView`, `SearchScopeBar` and
  `GameSystemsSettings`. Those are badges and panel rows rather than menu
  rows, so they are not the drift this change is about, and folding six
  surfaces into one icon component is its own decision — they disagree on
  size and on fill (`currentColor` where the die inherits a row's state,
  `--text-secondary` where it does not), which is the question that
  decision would have to answer.
- **No `<Menu>` wrapper.** Unchanged from
  [shared menu machinery](2026-08-11-shared-menu-machinery-design.md);
  the containers differ by positioning strategy and that is #279's
  settled territory.

## Verification

1. `npm run lint:css`, `npm run check`, `npm run test`, `vite build`.
2. Grep: no component declares the row property set
   (`padding: 0.2rem 0.6rem` on a menu row) except `CollectionsPanel`,
   and neither game-system picker renders a row of its own.
3. Manual, both surfaces: toggling a system from the tree context menu
   and from the row badge; "Clear tags" appearing only with tags
   present, with no divider above it when it is the only row; `+ tag`
   absent with no systems known; a tagged file with its system disabled
   still offering "Game system" → "Clear tags" in the context menu.

## Outcomes

To be recorded if anything surprises.
