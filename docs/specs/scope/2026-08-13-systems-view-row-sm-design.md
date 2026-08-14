# Systems view row S/M — design

**Date:** 2026-08-13
**Status:** Implemented 2026-08-13 on main (automated checks green;
manual QA pending — see Testing).
**Related:** `2026-08-08-solo-mute-play-doctrine-design.md` (amended by
this design), `2026-08-13-sm-bypass-audit.md`,
`2026-08-11-momentary-transport-design.md` (hold latch),
`src/lib/SystemsView.svelte`, `src/lib/keybindings.ts`, #307.

## Problem

The systems view is the asset library: every row is indexed material by
construction (`indexedEntries` = `up_to_date` + `to_update`), grouped by
system — the natural console for deciding what search hears. Yet the
folder/file axis is reachable there only through the context menu. Tree
rows carry an inline S/M cluster; systems-view rows carry none, and
keyboard S/M on a focused row toggles the row's *group*. Hover (nothing),
keyboard (group), and right-click (file) disagree about what a row's S/M
means.

## Decision

> **The systems view is the asset library: bus-level S/M on system
> headers speaks the systems axis, channel-level S/M on file rows speaks
> the folder/file axis — two levels of one console, not two consoles.**

File rows gain the inline S/M cluster and keyboard retargets to the
row's file; group toggles lift to `⇧S`/`⇧M`. No algebra changes — row
chips are a second render of the tree's folder/file-axis state through
the same handlers.

## Row cluster

- Same markup pattern as tree rows and this view's headers, converted
  via the existing `entryToFileItem`. Four props thread from the page:
  `soloedScopePaths`, `mutedScopePaths`, `onToggleScopeSolo`,
  `onToggleScopeMute`.
- **Always offered.** Every row is indexed, so the shared gate
  (`rowHasIndexedMaterial`, `treeNav.ts`) passes trivially — no
  conditional rendering.
- **Placement:** right-aligned before the indexed-time meta, mirroring
  the header cluster's seat before its count, so engaged chips form one
  console column down the surface's right edge.
- **Reveal:** the established rule — opacity 0 at rest; row hover,
  `:focus-within`, or an engaged chip reveals.
- **Lit state is path-keyed**, so a multi-tagged file lights its chip
  under every group it appears in.
- Titles: "Solo *filename* (S)" / "Mute *filename* (M)"; header cluster
  titles gain the `⇧S` / `⇧M` hints.

## Keyboard

- Bare `S`/`M` on a focused row target the **file** — the tree's
  grammar, "act on the row you're on", now uniform across browsing
  surfaces. `⇧S`/`⇧M` lift to the focused row's **group** (systems
  axis), today's bare-letter behavior relocated.
- All four run through the shared hold latch under the existing
  `'s'`/`'m'` ids — tap latches, hold is momentary. The release path
  lowercases `event.key`, so a held `⇧S` releases the same latch; the
  closure captured at press decides the target. `event.repeat` guarded,
  as today. Hold-to-peek gains its best use here: **hold S on a row to
  peek a search scoped to one book, release to snap back.**
- **Untagged:** bare `S`/`M` work on its rows like any other — the
  first solo path untagged material has ever had (#307 keeps the
  *system* axis mute-only). `⇧S` stays inert (systems never solo
  untagged); `⇧M` mutes under the backend's untagged key.
- **Dispatch is a pure function** in `keybindings.ts` (which owns
  `ChordEvent`): chord × untagged → `{axis: file|system, kind:
  solo|mute}` or null, unit-tested beside the existing predicates.
  `SystemsView.handleWindowKey` consumes it.
- **Registry:** `systems.solo`/`systems.mute` relabel to the file; two
  new hint-only entries document `⇧S`/`⇧M` for the group.
  `eventMatchKey` deliberately can't express shift chords and doesn't
  need to — SystemsView dispatches locally, like the tree's `⇧F10`.

## Display and bypass

No new rules; the point is inheriting the amended display doctrine
exactly:

- Rows keep dimming by membership in the resolved scope (browsing
  surface); chips stay lit by channel state.
- Under master bypass, dims lift and lit chips persist — the same
  split the S/M bypass audit's finding 1 fix established for this view.
- Scope-bar chips per existing rules: file solos neutral, mutes
  vermilion.

## The cross-level solo collision (named, deliberate)

Soloing a group header and a file row in *another* group intersects two
axes and resolves empty. This is pre-existing algebra — the filter
panel + tree can express the identical collision today — but row chips
put the two solo levels on one surface, so the design owns it
explicitly:

- The cross-axis empty resolves to **"Nothing under the soloed items."**
  with the scope-bar meter reading "… of 0 files" (audit finding 5's
  fix). Manual QA pins this exact case.
- The intended gesture for "this system plus that one book" remains a
  collection played into the mix, per the doctrine ("play stays
  exclusive to collections").
- A DAW reading predicts union here (bus solo + channel solo are one
  dimension on a console); our axes intersect. The empty-state message
  is the corrective, and this paragraph is the record that the tradeoff
  was seen, not drifted into.

## Doctrine amendments

Applied to `2026-08-08-solo-mute-play-doctrine-design.md` with this
design:

1. **Gesture grammar** gains "Rows as channels in the systems view
   (amended 2026-08-13)" — the decision statement above plus the
   keyboard grammar.
2. **Affordance parity** widens from "tree rows" to "browsing-surface
   rows".
3. **Display doctrine** records the asset-library sentence in the
   surface-classes paragraph.

## Testing

- `searchScope.ts` untouched; its suite stands as-is.
- The keyboard dispatch helper gets unit tests in
  `keybindings.test.ts`: bare/shift × solo/mute × tagged/untagged,
  including the inert `⇧S`-on-Untagged row.
- Cluster rendering and latch behavior land on the rolling manual QA
  checklist: chips reveal/engage; bare vs shifted targets; hold-S peek
  snaps back; header-solo + row-solo collision shows the doctrine
  message; bypass lifts dims with chips lit; a multi-tagged file lights
  in every group; untagged rows solo while `⇧S` stays inert.

## Non-goals

- No play on rows, files, or systems; no exclusive solo (union is
  load-bearing — audit, "The solo question first").
- No keyboard focus for group headers; `⇧S`/`⇧M` are the keyboard path
  to the bus.
- No shared cluster component: four surfaces render ~15 lines each with
  their own reveal rules; extraction is a refactor to revisit only if
  the markup itself starts drifting.
- No sidecar/backend changes.
