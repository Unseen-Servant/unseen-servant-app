# Search view ↔ filter / collection panels — interaction audit

**Date:** 2026-08-13
**Status:** All eight recommendations implemented 2026-08-14. Finding 2
was resolved toward the console: the dock panes stay keyboard-live
during search (arbitrated by `activePane` — entering search or clicking
the search side points it at `'files'`, the search key block yields
whenever a dock pane holds it, and `⌘⌥←/→` cross between the sides),
which also made finding 3's Escape comment true instead of dead. The
armed-collection bridge kept click-as-select on result rows (the
inspector is how a book is judged before filing); the checkbox and `X`
are the filing gestures. Finding 7 took the full form — child rows
joined the panel's row model via `collectionsNav.ts` — with `⌘⌫`
remove, `⌘O` open, and `←` to the head row. Findings ordered by
severity within each section. Scope semantics (solo/mute/bypass resolution) were audited
separately in `docs/frontend/2026-08-13-sm-bypass-audit.md` and are
not re-covered here — this audit is about the *interaction layer*:
reachability, affordances, and mouse/keyboard symmetry between the
search view, the two dock panels, and the two browsing views.
**Baseline:** commit 8a87f1a. Key files: `src/routes/+page.svelte`,
`src/lib/SearchResults.svelte`, `src/lib/SearchScopeBar.svelte`,
`src/lib/SearchInspector.svelte`, `src/lib/FilterPanel.svelte`,
`src/lib/CollectionsPanel.svelte`, `src/lib/FileTree.svelte`,
`src/lib/SystemsView.svelte`.

## Model recap (what the design promises)

- **Pane model** (`2026-08-09-pane-activation-design.md`): `activePane`
  carries keyboard ownership, three nullable carets carry ring
  placement; `⌘⌥←/→/↑/↓` jump between regions; `materializeKey`
  restores position. Search is deliberately *outside* the model — the
  results list arbitrates by real DOM focus.
- **Console doctrine**: FilterPanel + CollectionsPanel + SearchScopeBar
  are the console/readout; tree + systems are browsing surfaces. Every
  scope mutator re-runs the committed search (`runSearch` call in each
  toggle), so the console genuinely mixes results live.
- **DAW grammar**: S/M/P/B tap-latch or hold-momentary through one
  `holdLatch`; the stated GM case is *"peek at one book alone
  mid-search without dismantling a scope that took prep time to build"*
  (`holdLatch.ts:10-12`).

## Findings

### 1. Search results are a dead end for curation and scope actions

The search view is the app's primary discovery surface, yet a result
row supports exactly three gestures: click (select), double-click /
Enter (open), ⌘1–9 (jump). Everything both browsing views offer on a
row is absent:

| On a row | Tree | Systems | Search result |
|---|---|---|---|
| Drag to a collection | yes (`FileTree.svelte:302`) | yes (`SystemsView.svelte:599`) | **no** |
| Context menu | yes | yes | **no** |
| Checkbox while a collection is armed | yes (checkbox re-targets) | yes (row click re-targets) | **no** |
| S / M (hover buttons + keys) | yes | yes (systems axis) | **no** |
| `.` hide, `R` rename, `C` collection menu, `⌘I` info, `⌘O` open, `⌘⌥R` reveal | yes | yes | **no** |

The gates are structural: `handleFocusedFileActionKey` and the tree-nav
block both require `!searchViewOpen` (`+page.svelte:2426-2437`), `⌘I`
keys off `focusedFilePath` (`+page.svelte:2333`), and
`SearchResults.svelte` rows carry no `draggable`, no `on:contextmenu`,
no membership affordance (`SearchResults.svelte:152-163`).

Concrete GM cost: **the armed-collection workflow stops at search.**
The arm tooltip says "then click books in the tree to file them"
(`CollectionsPanel.svelte:768-769`) — but search is where you *find*
the book. Filing a hit means memorizing the filename, exiting search,
and hunting it down in the tree. Meanwhile the collections panel is on
screen the whole time, accepting drops from surfaces that are not
rendered.

Everything needed for a bridge already exists: `result.source` is the
absolute path, `beginPathDrag` resolves any path to a payload
(`+page.svelte:2880`), `handleContextMenu` takes a `FileItem`
(`+page.svelte:2488`), and the toggles are path-keyed. Wiring a
result row to `{ name: result.filename, path: result.source, is_dir:
false }` unlocks drag, the context menu, and the whole action-key
vocabulary in one move.

### 2. The dock is keyboard-unreachable exactly when the mix is audible

All four region-jump chords are gated `!searchViewOpen`
(`+page.svelte:2279-2302`), and both dock panes get
`active={… && !searchViewOpen}` (`:3569`, `:3603`). So while results
are on screen — the one moment the console's effect is visible — the
console is mouse-only. A keyboard user must Esc out of search, adjust,
and re-enter; hold-to-peek S/M (the flagship "mid-search" case) cannot
be performed mid-search from the keyboard at all.

The inconsistency shows in the letters the search view *does* answer:
bare `B` bypasses from the results list (`+page.svelte:2400-2410`,
gated only on `!inAnyInput`) and `?` opens help — but `s`/`m` are dead.
The console answers some transport letters and not the narrowing ones.

Arbitration is solvable: the results list already claims arrows by DOM
focus (`target.closest('.search-results')`, `:2445`), so dock handlers
could stay live during search and simply yield when DOM focus sits in
the results/input — the same shape as their existing input-target
yields. Alternatively, keep the dock inert but make `⌘⌥←` an explicit
"reach the console from search" entry that moves DOM focus out of the
list first. Either is better than a console that goes deaf whenever
the music plays.

### 3. Escape dead-ends in search when a dock pane holds `activePane` (bug)

The ladder's search branch funnels to the bar only when `activePane ===
'files'` (`+page.svelte:2214`). The comment below it claims "an active
dock pane keeps its own Esc semantics" (`:2218-2220`) — but both dock
panes bail on `!active`, and their `active` prop is ANDed with
`!searchViewOpen`. Nobody handles it.

Reachable in two clicks: while searching, click a collection row (to
peek at its contents), then press Esc → nothing happens, because the
row click ran `setFocusedCollectionName` (`+page.svelte:129-133`),
which set `activePane = 'collections'` with no search gate. The ↑-to-
input path still works, but Esc — the app's universal "step back" — is
silently dead.

Related ring lie: that same click draws the `kb-focused` ring on the
collection row (`CollectionsPanel.svelte:712-713`) while the arrows
stay with the results — the ring's one meaning ("this is where j/k
act") is false. Entering search also leaves any pre-existing dock ring
lit and inert; nothing clears carets on `handleSearchFocus`
(`+page.svelte:609-611`).

Minimal fix regardless of what finding 2 decides: clear dock carets
(or `pointAtEmpty('files')`) when the search view opens, and make the
ladder's else-branch funnel to the bar unconditionally — or actually
implement what the comment promises.

### 4. Opening a result resolves by filename, ignoring the path in hand

`handleOpenResult` → `resolvePathForFilename` does a case-insensitive
**filename** scan over `indexStatus` (`+page.svelte:613-651`), while
the result already carries `result.source` — the absolute path the
same view uses for ribbon colors (`collectionColorByPath.get(
result.source)`). Two same-named PDFs in different folders open the
wrong one; a hit whose entry isn't in `up_to_date`/`to_update` at that
moment fails with "Could not locate…". Both call sites
(`SearchResults` dblclick/Enter, `SearchInspector` Open) pass only
`filename`. Passing `source` through ends the ambiguity for free.

### 5. Filter rows are the only rows in the app a click does nothing to

Clicking a collections row places the caret (`CollectionsPanel.svelte:712`);
clicking a tree or systems row places the caret; clicking a filter
row's body does *nothing* — not caret, not pane activation (the panel
mousedown skips `[data-fm-key]` rows, `FilterPanel.svelte:121-125`,
and rows have no click handler). The pane-activation spec's stated
outcome — "clicking anywhere in the Filters panel now gives it the
arrows" — is not true of the row bodies, which are most of the panel.

The skip exists so mousing an S/M button doesn't drop a caret parked
elsewhere (QA item 7d), but that only requires the *buttons* to keep
`stopPropagation` (they already do). A click handler on the row body
that places the caret would restore parity with all three sibling
panes at no cost to 7d.

### 6. Search results' keyboard vocabulary is thinner than every sibling pane

- **No `j`/`k`.** Every other list pane accepts them alongside arrows;
  in the results list (focus on a row, not an input) they are simply
  unbound (`+page.svelte:2464-2480` handles arrows only).
- **No Home/End** — present in all four other panes.
- **`⌘O` is a no-op** on a focused result; Enter is the only keyboard
  open. Muscle memory from the other views ("⌘O opens the focused
  thing") silently fails.
- Exiting search *to a specific view* has no chord: `⌘1`/`⌘2` are
  correctly repurposed as result-jump digits, so keyboard exits are
  Esc-Esc (to the previous view) only, while the header picker offers
  both targets to the mouse. Acceptable trade, worth recording.

### 7. A collection's contents are enumerated in one place the keyboard can't enter

`→`/`L` expands a collection (`CollectionsPanel.svelte:490-494`), but
`j`/`k` step over the child file rows — they are not part of the row
model — and the per-file remove × is hover-revealed, mouse-only
(`CollectionsPanel.svelte:821-832`). Net: removing a file from a
collection from the panel that displays its contents requires a mouse;
the only keyboard path is the long way round through the tree row's
`C` submenu. Child rows also offer no open/reveal, and are not drag
sources (can't move a file from one collection to another).

### 8. Exit-by-picker skips the focus restoration exit-by-Esc performs

Esc from the bar closes the view and calls `focusFileRegion()`
(`+page.svelte:2213`); `setViewMode` — the picker-click exit — closes
the view, blurs, and restores nothing (`+page.svelte:921-936`). Mouse
exits imply mouse continuation, so this is minor, but the two exits
were written to different standards, and `setViewMode` also leaves
`focusedFilePath` unvalidated against the target view's visible rows
(only `focusFileRegion`/`claim` do the "still visible?" check).

### 9. Hover-reveal grammar: one panel latches, three trust CSS `:hover`

CollectionsPanel latches hover on real `pointerenter` because CSS
`:hover` re-lights whatever lands under the pointer after a menu close
or drag end (a5fb0c4, comment `CollectionsPanel.svelte:89-96`). The
identical reveal grammar in FilterPanel (`.row:hover .sm`), FileTree
(`.row-container:hover .sm`), and SystemsView (`.group-head-row:hover
.sm`) still runs on CSS `:hover` and carries the same bug class — close
the tree's context menu and the row under the resting pointer lights
its S/M. The dock siblings render the divergence side by side.

### 10. Small consistency notes

- **Four divergent popover-yield stacks**: `+page.svelte:2199` checks
  `.sort-menu, .dropdown, .context-menu`; `:2420` drops
  `.context-menu`; `FilterPanel.svelte:150` and
  `CollectionsPanel.svelte:418` carry their own lists;
  `SystemsView.svelte:347-350` mixes a state check with a DOM query and
  its comment calls the DOM path racy. The page comment (`:2415-2419`)
  already proposes an open-menus store — the menuSlot module is most of
  the way there.
- **`SystemsView`'s `active` prop** (`+page.svelte:3696`) lacks the
  `&& !searchViewOpen` guard its two dock siblings have. Harmless only
  because the component unmounts during search; it is the odd one out.
- **`s`/`m` mean the path axis in tree mode and the systems axis in
  systems mode**, enforced by convention split across two files
  (`+page.svelte:2094,2101` excluding systems mode so
  `SystemsView.svelte:396-409` can claim the letters). Deliberate, but
  nothing but comments keeps the two halves agreeing.
- **Scope-bar chips** are clear-affordances only; there is no gesture
  from a chip to its source row (e.g. jump to that system's channel or
  that collection). Tab reaches them (native buttons) but no chip has
  a visible focus style of its own.

## Verified consistent (checked, no action)

- **The console mixes live.** Every scope mutator re-runs the committed
  search; the scope bar renders in all three modes and its meter,
  empty-scope messages, and chips agree with resolution (post
  sm-bypass-audit fixes).
- **The pane model holds across its three members**: shared
  `materializeKey`, clamp-don't-wrap stepping, Home/End, last-focused
  restoration, `claim()`, chrome-click-activates / empty-click-
  deselects, ring-not-fill carets. The mutex hole the 08-09 spec closed
  stays closed.
- **One hold latch** serves S, M, P/Space, and B, released by a single
  window keyup/blur pair (`+page.svelte:2159-2161, 3499-3501`).
- **The drag contract is clean and shared** between tree and systems
  views (private MIME + page-stashed payload, `dragPayload.ts`), and
  the collections panel discriminates its own reorder drag from path
  drops correctly, including the drop-latch hover clears.
- **The search combobox flow** (↓ into list at current selection, ↑
  from row 0 back to the input, Esc ladder, stale-result dimming,
  weak-tier demotion, scroll-to-load) is coherent and matches its
  design doc.
- **Search-view entry/exit semantics** (focus = enter, × clears but
  never exits, query survives exits) match
  `2026-08-08-search-view-behavior-design.md`.

## Recommendations (in order)

1. **Bridge results to file actions** (finding 1): make result rows
   drag sources via `beginPathDrag(result.source, …)`, give them the
   shared context menu via a `FileItem` built from `source`, and honor
   the armed collection (checkbox or click-to-file, mirroring
   SystemsView's curating rewrite). This one change collapses most of
   the table in finding 1.
2. **Fix the Esc dead-end and stale rings** (finding 3): clear dock
   carets on search entry; funnel Esc to the bar from anywhere
   non-input in the search view. Small, purely corrective.
3. **Open results by `source`** (finding 4). One-line-per-call-site
   correctness fix.
4. **Decide the dock's keyboard status during search** (finding 2):
   either let the panes stay `active` with a results-focus yield, or
   keep them inert and say so (then also stop row clicks from ringing
   them during search). The current half-state is the worst of both.
5. **Row-body click places the caret in the filter panel** (finding 5).
6. **`j`/`k` + Home/End + `⌘O` in the results list** (finding 6).
7. **Keyboard access to collection children** (finding 7) — fold child
   rows into the panel's row model, or at minimum give the focused
   collection a keyboard remove path.
8. **Adopt the pointerenter latch (or a shared primitive) on the other
   three hover-reveal surfaces** (finding 9), and fold the four popover
   yield stacks into the existing menu-slot module (finding 10).
