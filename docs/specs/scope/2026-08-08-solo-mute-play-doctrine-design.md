# SOLO / MUTE / PLAY — scope doctrine — design

**Date:** 2026-08-08
**Status:** Implemented 2026-08-08 on branch
claude/unseen-servant-solo-mute-play-02b695 (automated checks green;
manual QA checklist pending — see the plan's Task 13).
**Related:** `src/lib/searchScope.ts`, issue #307 (untagged bucket), commits
5ebde7a (unified solo), 4b04974 (play/stop transport), e61ace2 (filter
console).

## Problem

The scope convention grew organically and is internally inconsistent:

1. **Play composes two different ways.** Playing collections join the
   *solo side* of the collection axis, so play unions with folder/file
   solos — but axes intersect, so the same play *intersects* with system
   solos and curation solos. Soloing a folder while a collection plays
   yields "collection ∪ entire folder", which surprises: the DAW-faithful
   reading is that solo narrows what you hear *of what's playing*.
2. **Gesture availability is asymmetric.** Collections carry only ▶/⏹;
   "search everything except my Homebrew collection" is inexpressible
   unless the collection happens to be one folder.
3. **Display rules are per-surface.** The systems view dims muted and
   non-soloed groups; the collections panel dims non-playing tracks; the
   tree dims only explicit mutes and shows nothing about the playing mix.
4. **No scope state survives a restart**, despite "prep the night before,
   play at the table" being the product's core story.

## Doctrine

> **The transport arms material into the mix; S narrows within what's
> armed; M carves out of it.**

### The mix (universe layer)

Play is promoted out of the collection axis into its own layer. One rule,
no special cases:

```text
base = (any collection playing) ? union of playing collections' files
                                : all indexed files
mix  = base \ union of muted collections' files        (∩ indexed)
```

- Nothing playing, nothing muted → the mix is the whole indexed library
  (today's behavior, unchanged).
- **Mute wins over play while lit.** A playing, muted collection
  contributes nothing; unmuting restores its contribution without
  re-arming. Stopping is not muting — the armed state survives.
- Muting with an idle transport carves the collection's files out of
  whole-library search — the "everything except my Homebrew" case.
- A file reached by both a playing and a muted collection is **out**:
  mute is a carve on the mix, not a per-track fader. Predictability over
  DAW purism on this edge.

### Narrowing (three axes, unchanged internally)

Systems, folder/file S/M, and Collected/Loose keep today's algebra —
solos union within an axis, solo overrides mute within an axis, axes
intersect — but every axis now resolves **within the mix**:

```text
scope = mix ∩ systems-axis ∩ folder/file-axis ∩ curation-axis
```

Resolution to the backend is unchanged in shape: the systems axis becomes
the `game_systems` include-list; the mix becomes the *universe* the
folder/file and curation axes filter over, and the result is the
`source_paths` include-list. When those axes have no narrowing engaged,
`source_paths` is the mix itself — or `null` when the mix is the whole
library. No sidecar changes.

The scope-bar denominator and the search-results count compute against
the resolved scope. Per-channel counts (the filter console's system and
Collected/Loose counts, the status bar's indexed total) deliberately
stay whole-library: like a DAW channel meter, they describe the
channel's material — what muting carves or unmuting restores — not its
post-narrowing contribution. A muted channel showing 0 would erase the
one number that says what's behind the M.

### Empty states

Three messages, first match wins:

1. Transport armed but the mix resolves empty (unindexed collections, or
   mutes carved it to nothing) → **"Nothing indexed is playing."**
2. Any solo engaged and the intersection is empty →
   **"Nothing under the soloed items."**
3. Otherwise (mutes emptied the scope) → **"Everything is muted."**

## Gesture grammar

| Object              | Gestures        | Notes                                                        |
| ------------------- | --------------- | ------------------------------------------------------------ |
| Collection          | ▶/⏹ (P/Space), M | No solo — play *is* the focus verb here. Mute wins over play. |
| Archived collection | M only          | No transport (unarchive to play); muting a shelved collection is the "retired homebrew" carve. |
| Folder / file       | S, M            | Offered wherever the row has indexed material (see Affordance parity below). |
| Game system         | S, M            | Untagged stays mute-only (never passes under solos, #307).   |
| Collected / Loose   | S, M            | Unchanged.                                                   |

Play stays exclusive to collections: they are the session-level unit. If
a folder belongs in tonight's mix, making it a collection is the intended
gesture. Systems are metadata channels, not material you arm.

Keyboard: M toggles mute on a focused collection row (joining the
existing P/Space transport binding), matching S/M on tree and systems
view rows.

### Affordance parity (amended 2026-08-08)

Every input path offers S/M on tree rows under one predicate
(`rowHasIndexedMaterial` in `treeNav.ts`): the row has indexed material
to act on — a file in the index, or a folder with an indexed
descendant — or is already engaged, so stale chips stay toggleable
where they were set. Concretely: the inline S/M cluster renders on
indexed file rows as well as folders; the context menu pairs "Mute
this folder/file" with Solo behind the same gate; and the toggle
handlers refuse to *create* a narrowing on a row with nothing indexed
(removal always works). Dead-on-arrival solos are thus impossible from
any input path — the honest-empty-solo rule now only applies to chips
that go stale after creation.

### Hide territory (amended 2026-08-08)

Hide stays display-only (hidden files remain indexed, searched, and
counted) and splits territory with M: **hide is the visibility verb for
what scope can't speak about** — unindexed files and folders. "Hide
file" (context menu and the `.` key) is no longer offered for indexed
files; their disappearing verb is mute plus the focus lens. Unhide
always remains available, so files hidden before indexing (or indexed
while hidden) never strand. Folder hide is untouched — junk folders
are the common clutter case even when a stray indexed file sits
inside.

## Display doctrine

One rule on every surface: **out-of-scope dims — a single level, hover
restores legibility, never hidden by default; the control responsible
stays lit; every engaged narrowing materializes a scope-bar chip.**

Surfaces split into two classes: **browsing surfaces** (file tree,
systems view) show material and may hide it under the focus lens below;
**console surfaces** (filter console, collections panel, scope bar) show
channels and controls and never hide them — the mixer is the recovery
path, so nothing can disappear from it.

- **Dim predicate:** membership in the final resolved scope (mix ∩ all
  axes), applied at each surface's own granularity:
  - *Tree file rows* dim when the file is indexed but not in scope.
    Unindexed files keep their existing treatments — out-of-scope
    dimming only speaks about searchability of indexed material.
  - *Tree folder rows* dim when they contain indexed descendants and
    none are in scope; a folder with no indexed descendants says
    nothing. The path to in-scope material therefore stays bright.
  - *System groups* dim when the channel is muted, when another
    channel's solo excludes it, or when none of the group's files are
    in scope (e.g. transport armed elsewhere).
  - *Collection tracks* dim when not contributing to the mix — not
    armed while others play, or muted. A muted-while-playing row shows
    ▶ armed **and** M lit vermilion, content dimmed.
- **One dim level.** A single token pair in `app.css`
  (`--opacity-out-of-scope`: 0.45 rest, 0.7 hover — the tree's current
  values) replaces the per-surface values. No deeper tier for explicit mutes — the lit M
  carries the "why".
- **Chips:** playing collections wear the collection's color; every mute
  (collections included) wears vermilion; folder/file solos stay
  neutral. Whole-chip removal disengages that narrowing.
- **Search results never dim** — by construction they are always in
  scope.

The tree gains the two treatments it is missing today (dim outside the
playing mix, dim outside an active solo); "what's in tonight's mix" then
reads in the tree as the complement's dimming — no wash needed there.

### Focus lens: "Hide out-of-scope items"

A toggle in the filter console masthead, sibling to "Show hidden items".
For very large libraries, thousands of dimmed rows are still thousands
of rows — dimming communicates scope but doesn't shrink the surface
(DAW mixers have the same lens: hide unused tracks).

- **Engaged**, browsing surfaces hide exactly what the dim predicate
  would dim — explicit mutes and merely-out-of-scope alike. A folder
  hides when it has indexed descendants and none are in scope.
- Console surfaces are unaffected; recovery stays two-deep everywhere
  (the chip on the scope bar, the channel in the console).
- The lit toggle wears purple (`--text-active`) — a mode the user
  switched on. With no narrowing engaged the lens is a harmless no-op.
- If the scope resolves empty while the lens is on, the tree shows a
  one-line "everything is out of scope" placeholder so blank doesn't
  read as broken.

## Persistence

Full console recall through the existing store plugin: playing set,
muted collections, system S/M, folder/file S/M maps (path + kind +
label), curation S/M, and the focus-lens toggle. Saved on change, loaded
before the first search.

- Collections are keyed by name; the rename action migrates the playing
  and muted sets, and deletion clears both. Restored state loads after
  the collections themselves, so restored names are never transient
  ghosts.
- Stale state is seen rather than silently ignored — chips remain
  visible and removable — but staleness resolves per gesture:
  collection names with no matching collection resolve away entirely
  (they engage nothing, not even the mix's null decision); path *mutes*
  subtract nothing and are harmless; path *solos* keep narrowing — a
  solo covering nothing indexed narrows the scope to nothing, honestly,
  with the lit chip and the empty-state message naming the cause. A
  solo chip must never be lit while contributing nothing to the
  narrowing.
- The filter console's [clear all] remains the one-gesture reset.

## Deltas from current implementation

1. `searchScope.ts` — new `resolveMix(playing, mutedCollections,
   collections, indexed)`; `searchSourcePathsFilter` and
   `searchCurationFilter` keep their signatures but receive the mix as
   their universe; final `source_paths` falls back to the mix when the
   axes produce no narrowing.
2. `+page.svelte` — new `mutedCollections: Set<string>`; playing
   collections no longer pushed into the solo sets; count and
   empty-state logic reworked to the three messages.
3. `CollectionsPanel.svelte` — M button beside the transport (archived
   rows: M only); keyboard M; rename migrates transport/mute sets.
4. `SearchScopeBar.svelte` — vermilion chips for muted collections.
5. `FileTree.svelte` — scope-membership dimming (file + folder-subtree
   predicates) replacing the mute-only prefix dim; rows drop from the
   render under the focus lens, plus the empty-scope placeholder.
6. `SystemsView.svelte` — adds the no-files-in-scope dim condition;
   dimmed groups drop under the focus lens.
7. `FilterPanel.svelte` — "Hide out-of-scope items" toggle row in the
   masthead beside "Show hidden items".
8. `app.css` — the out-of-scope opacity token pair; surfaces adopt it.
9. New persistence module wiring the store plugin.

## Testing

Extend `src/lib/searchScope.test.ts` with the mix-layer cases: play ∩
folder-solo intersects (the Strahd/Bestiary case); mute-wins-over-play;
muted collection with idle transport; shared file in a playing and a
muted collection (carved); each empty-state branch in priority order;
stale-path tolerance; mix-as-source-paths fallback. Display predicates
(file/folder scope membership) get unit tests where they live as pure
functions — the focus lens reuses the same predicates, so hiding is
covered by them plus a component assertion where vitest patterns already
exist. Persistence: round-trip save/load unit test including the lens.

## Non-goals

- No solo on collections; no play on folders, files, or systems.
- No two-tier dim. Hiding is opt-in via the focus lens only, and only
  on browsing surfaces — console surfaces never hide their channels,
  and there are no per-surface hide toggles.
- No sidecar/backend changes — the filters API is untouched.
- No changes to what indexing checkboxes or hidden-item treatments mean.
