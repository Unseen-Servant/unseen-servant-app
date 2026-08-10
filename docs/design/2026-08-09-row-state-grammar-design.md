# Row State Grammar — Design

**Date:** 2026-08-09
**Status:** Implemented 2026-08-09 on main. Automated gates green; the
keyboard, pointer, visual and drag passes need the running app and are
outstanding — see Outcomes.

## Problem

Every scrollable list in the app — the file tree, the collections panel,
the filter panel, the systems view, the search results — paints hover,
keyboard focus and engagement into the same CSS property, using tokens
whose names no longer match what they do.

1. **Two different hover values for the same gesture.** All five lists
   rest on `--bg-app` `rgb(25, 25, 25)`. Four of them hover to
   `--bg-focused` `rgb(50, 50, 50)`; the filter panel hovers to
   `--bg-container` `rgb(35, 35, 35)`. In OKLCH lightness that is a
   +0.099 step against a +0.043 step — the filter panel's hover is
   2.3× weaker than every other row in the app.

   The split arrived with `994c6b1`, which applied the filter-console
   design handoff. The handoff carried its own row-hover value; the
   collections panel, rebuilt in the same commit, took the tree's. The
   two were never reconciled against each other.

2. **`--bg-focused` means four things.** A raised surface (context
   menus, dropdowns, the modal header); an inset well (form selects,
   `kbd` and inline-code chips); a row hover fill; and keyboard
   focus. A hovered tree row is therefore the exact same value as an
   unhovered context menu.

3. **`--bg-container` means two opposite things.** Inside a menu it is
   the *hover* fill against the menu's 50 surface — a darkening
   (`ContextMenu.svelte:522`, `CollectionsPanel.svelte:1150`). In the
   filter panel it is the *hover* fill against the 25 dock — a
   lightening. Same token, opposite direction.

4. **The keyboard caret is invisible on exactly the rows that matter.**
   Focus and hover share one declaration, so focus also competes with
   the engaged wash for `background` — and loses. `.row.soloed`
   (`FilterPanel.svelte:460`) is declared after `.row.kb-focused`
   (`:436`), and `.row-container.playing`
   (`CollectionsPanel.svelte:878`) after `.row-container.kb-focused`
   (`:872`). Arrow onto a soloed channel or a playing collection today
   and nothing moves. This is a live bug, not a consequence of the fix.

5. **Hover and keyboard focus are indistinguishable.** Every list paints
   them identically, so with the pointer parked anywhere over a list
   there is no way to tell where the caret is.

## Decision

Split the two axes. **Background says what a row *is*. A ring says where
the caret *is*.** They stop competing for one property, and each token
goes back to one meaning.

### The background ramp

Three values on the `--bg-app` dock, and no more:

| State | Fill | OKLCH L |
| --- | --- | --- |
| Rest | `--bg-app` `rgb(25, 25, 25)` | 0.213 |
| Hover | `--bg-container` `rgb(35, 35, 35)` | 0.256 |
| Engaged (solo / playing) | `color-mix(in srgb, var(--text-accent) 8%, transparent)` + `border-left-color: var(--text-active)` | 0.261 |

The filter panel's value wins. Two reasons beyond preference:

- **It is the only one that reads as hover rather than as state.**
  Engaged rows land at L 0.261, hover at 0.256 — the same lightness,
  separated by hue. Hover stays neutral, engagement carries parchment.
  That is the split CLAUDE.md already asks for ("hover never glows and
  never introduces new hues — it brightens or fills with a grey step"),
  and it makes the two axes readable independently. At `--bg-focused`
  the hover step is brighter than the engaged wash, so a passing mouse
  outshouts a state the user deliberately set.
- **It improves contrast.** `docs/design/2026-08-09-header-voices-design.md`
  measured `--text-tertiary` `#7d8590` at 3.44:1 on `--bg-focused` and
  4.21:1 on `--bg-container`. Row counts, badges and secondary labels
  are tertiary text; today they get *less* legible under the pointer.

`--bg-focused` keeps only its surface meanings — raised (menus, modal
header) and inset (wells, `kbd` chips). Nothing on the dock uses it.

### The focus ring

```css
/* Roving keyboard focus on list rows. Drawn inset because rows in a
   dense list have no room for the global :focus-visible outline's
   2px offset — same parchment, adapted to the list. */
--ring-focus: inset 0 0 0 1px var(--text-accent);
```

Applied as `box-shadow: var(--ring-focus)` on `.kb-focused` /
`.focused`.

**Parchment, not a neutral.** The app already has exactly one focus
vocabulary: `:focus-visible { outline: 2px solid var(--text-accent) }`
at `app.css:176`, repeated at `.sm-btn:focus-visible` (`:294`),
`.app-checkbox:focus-visible` (`:344`) and
`SearchInspector.svelte:379`. The row lists use *roving virtual* focus —
a class, because DOM focus stays on the container — so the row indicator
must look like the real one or it reads as a second, unrelated idea.

**A ring, not a brighter fill.** A fill cannot coexist with the engaged
wash; a ring composes over every row state the lists already have —
playing, soloed, editing, archived, dimmed, dragging, hovered. This is
what fixes problem 4 rather than relocating it.

`inset` shadows are clipped to the padding box, so on the collections
and filter rows the ring sits just inside the reserved
`border-left: 3px` — nested inside the purple solo rule when both are
lit, which is the correct reading.

### Search results keep the ring, not a wash

In `SearchResults` there is no separate focus state: selection *is* the
cursor. It is `selectedIndex`, driven by the arrow keys, and the comment
at `SearchResults.svelte:283` says outright that selection is the
"current row" cue. So `.result-row.selected` takes `--ring-focus` and
drops its fill entirely.

Giving it the parchment *wash* instead was considered and rejected on
two grounds. The wash composites to `rgb(38, 36, 33)` over the app
background — within a hair of the new hover grey, so selected and
hovered rows would be near-indistinguishable by fill. And the wash means
"armed into the search scope" in the filter and collections panels;
spending it on a cursor dilutes the one thing it says reliably. The
selected row already carries a 4px glowing pigment stripe, an inverted
index cell and a full-opacity gauge — it is the most heavily marked
state in the app and needs no fill at all.

### Adoption map

| Selector | Now | After |
| --- | --- | --- |
| `FileTree.svelte:361` `.row-container:hover` | `--bg-focused` | `--bg-container` |
| `FileTree.svelte:405` `.focused > .row-container` | `background: --bg-focused` | `box-shadow: --ring-focus` |
| `CollectionsPanel.svelte:871` `:hover, .kb-focused` | combined, `--bg-focused` | split — hover `--bg-container`, focus ring |
| `SystemsView.svelte:767` `.file:hover` | `--bg-focused` | `--bg-container` |
| `SystemsView.svelte:770` `.file.focused` | `background: --bg-focused` | `box-shadow: --ring-focus` |
| `FilterPanel.svelte:435` `.row:hover, .row.kb-focused` | combined, `--bg-container` | split — hover unchanged, focus ring |
| `SearchResults.svelte:271` `.result-row:hover` | `--bg-focused` | `--bg-container` |
| `SearchResults.svelte:275` `.result-row.selected` | `background: --bg-focused` | `box-shadow: --ring-focus`, no fill |

`CollectionsPanel`'s `.drop-before` / `.drop-after` (`:900`, `:905`)
already use `box-shadow` and are declared after `.kb-focused`, so an
active drag continues to win the ring. No reordering needed.

## Decided non-changes

- **Hover fills on a `--bg-container` rest stay at `--bg-focused`.** The
  rule is a +1 surface step from whatever the element actually rests on,
  not a fixed token. Three cases qualify and are left alone: the settings
  modal body is `--bg-container` (`Modal.svelte:104`), so
  `GameSystemsSettings.svelte:313` `.system-row:hover` is a correctly
  proportioned +15; `SearchInspector.svelte:376` `.open-btn:hover` is the
  same case and already carries a comment citing the grey-step rule; and
  the scope-bar chip fills itself with `--bg-container` at rest
  (`SearchScopeBar.svelte:377`) even though the bar behind it is
  `--bg-app`, so its hover is also a 35 → 50 step. Only rows that rest
  directly on `--bg-app` move.
- **`--bg-focused` as a raised or inset surface is left alone** — menus,
  the modal header, form selects, `kbd` and inline-code chips. That is
  its remaining meaning and it is coherent.
- **Systems-view group headers keep their fill-less hover.**
  `SystemsView.svelte:651` brightens `color` to `--text-primary` and
  paints no background. A section header is not a row; giving it a row
  fill would flatten the hierarchy the heading font already builds.
- **`--bg-active`, `--bg-active-focused`, `--bg-selected`,
  `--bg-selected-focused` (`app.css:82-85`) are unused** and stay that
  way. Noted because they are the obvious place someone would look for
  a focus token; they are dead, and removing them is a separate call.
- **The roving-focus model is untouched.** `focusedRow`, `focusedName`,
  `focusedFilePath` and `selectedIndex` keep driving classes. Only what
  those classes paint changes.

## Notes

- **Why the ring is 1px and the global outline is 2px.** The global rule
  has `outline-offset: 2px` and draws outside the box — 4px of clearance
  a 28px row in a dense list does not have. Inset at 1px keeps the hue
  and the "this is focus" reading without touching the neighbours.
- **`SearchResults.svelte:288` keeps suppressing `:focus-visible`.** The
  suppression exists so a click on a `tabindex=-1` row doesn't stack a
  parchment outline on the selection cue. Under this spec the row draws
  its own parchment ring by class, so the suppression is still what
  prevents a double ring, and its comment stays accurate.
- **Parchment now carries three row-level meanings** — full-strength as
  text, 1px as the caret, 8% as engagement. Different mechanics, one
  hue, which is the point: the hue says "content layer", the mechanic
  says which state. `.sm-btn` already does this (parchment focus ring,
  purple solo fill).
- **Design-system sync.** This redefines two token meanings, so the
  claude.ai/design "Legend Lore" project needs the ramp and the ring
  pushed to it after the change lands.

## Verification

1. `npm run lint:css` — the ring must be a token, not a raw value; the
   stylelint colour rule is the gate.
2. `npm run check` and `npm run test`.
3. Grep gate: no `--bg-focused` remains as a hover or focus fill on any
   element resting on `--bg-app`. The eight rows of the adoption map are
   the complete list. Check the element's own rest fill, not its
   container's — a chip or control that paints itself `--bg-container`
   is a `--bg-container` surface no matter what sits behind it.
4. Keyboard pass in the running app, per pane: arrow through the tree,
   the collections panel, the filter panel, the systems view and the
   search results, and confirm the ring is visible on **every** row
   state — specifically on a soloed filter row and a playing collection,
   which is where the caret vanishes today.
5. Pointer pass: park the mouse over a list, arrow the caret to a
   different row, confirm hover and focus are separately readable.
6. Visual pass on the dock. Expected diffs: every row hover gets quieter
   except the filter panel's, which is unchanged; engaged rows now
   out-read a hovered neighbour rather than the reverse; selected search
   rows lose their grey fill and keep the pigment stripe.
7. Drag pass in the collections panel: with a row keyboard-focused,
   drag another row over it and confirm the drop indicator replaces the
   ring rather than stacking.

## Outcomes

- **The adoption map was wrong by one row, caught during the
  design-system sync.** It originally included
  `SearchScopeBar.svelte:454` `.chip:hover` on the reasoning that the
  scope bar rests on `--bg-app`. The *bar* does; the *chip* does not —
  it paints itself `--bg-container` at rest (`:377`), so moving its
  hover to `--bg-container` made the hover a no-op and silently deleted
  the chip's fill step. Reverted to `--bg-focused` and moved to the
  decided non-changes, where it belongs beside the other two
  `--bg-container`-resting hovers. The lesson is in the grep gate now:
  read the element's own rest fill, not its container's.
- **The other eight rows landed as specified**, no site missed and none
  found late. The grep gate confirms the only `--bg-focused` left in the
  touched components is `CollectionsPanel.svelte:795`, `:1126` and
  `:1171` — the sort menu, the context menu and its submenu, all raised
  surfaces, which is the token's intended remaining meaning.
- **The ring colour changed during drafting.** The working
  recommendation was `--text-tertiary`, chosen to keep the caret out of
  the semantic hues. Writing the spec turned up the global
  `:focus-visible` rule at `app.css:176` — the app already had one focus
  vocabulary, parchment, repeated at three more sites. A neutral ring
  would have been a second, unrelated idea for the same concept.
  Parchment it is.
- **`box-shadow` was deliberately left out of the row `transition`
  declarations.** Rows transition `background` only, so the ring snaps
  rather than fading. A 150ms fade on every arrow keypress lags the
  caret, and the existing `.drop-before` / `.drop-after` indicators
  already set an untransitioned `box-shadow`.
- **Gates that passed:** `npm run lint:css`, `npm run check` (420 files,
  0 errors, 0 warnings), `npm run test` (232 tests, 10 files). The
  stylelint pass is the meaningful one for verification item 1 — the
  ring resolves through `--ring-focus` to `--text-accent` with no raw
  value anywhere.
- **Still outstanding, not reachable by any automated gate:**
  verification items 4-7. Item 4 is the important one — it is the check
  that the caret is now visible on a soloed filter row and a playing
  collection, which is the live bug this spec set out to fix, and
  nothing in the static gates can observe it.
- **Design-system sync is pending.** The ramp and `--ring-focus` still
  need pushing to the claude.ai/design "Legend Lore" project.
