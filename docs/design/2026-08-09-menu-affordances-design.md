# Menu Affordances — Design

**Date:** 2026-08-09
**Status:** Implemented 2026-08-09 on main, `ad6ecba`…`a56fcbe`. Visual
and VoiceOver passes still outstanding — see Outcomes. Amended during
planning: menu roles were pulled into scope (they are load-bearing for
the ARIA change, not adjacent polish); focus management and
Collections-menu nav remain deferred to #363.

## Problem

Four issues across the three menus — the tree-row `ContextMenu`, the
collection-row menu in `CollectionsPanel`, and the badge dropdown
`SystemTagMenu`.

1. **Selection state is a text glyph.** `✓` at four sites, rendered in
   Crimson Text at `font-weight: 700` — a serif body face drawing a
   symbol it wasn't cut for, sitting on the text baseline rather than
   optically centred on the row. It reads heavy. It is also generic
   OS-menu vocabulary in an app that says "on" with LED glow, pigment
   fill and brackets everywhere else. And one form covers three
   semantics: multi-select (game systems), single-select (pigment,
   sort), and the stateless action rows beside them.
2. **Two vocabularies in one popup.** The sort menu has four `✓` rows,
   a divider, then a live `.app-checkbox` for "Show archived"
   (`CollectionsPanel.svelte:473` and `:481`) — about eight pixels
   apart, reading as unrelated.
3. **Dead and duplicated form-control CSS.** `.app-radio`
   (`app.css:335-369`) is defined and referenced nowhere. The checkbox
   anatomy is declared three times: `app.css:303`, `FileTree.svelte:353`
   and `SystemsView.svelte:739`.
4. **Copy and chord gaps.** The ellipsis carries two meanings in one
   menu; `Re-index` and `Reindex` both ship; and every tree action key
   is dead while the context menu is open, even though each has a row in
   that very menu.

## Decision

### The selection lamp

One shared recipe in `app.css`, beside the form controls. Four
components use it — same reasoning as the header voices.

```css
/* Menu selection lamp — reports which option is in effect on rows whose
   whole surface is the click target. Distinct from .app-checkbox, which
   is a control you press. */
.menu-pip {
  width: 0.9rem;        /* fixed gutter — rows don't reflow on toggle */
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.menu-pip::before {
  content: '';
  width: 5px;
  height: 5px;
  border-radius: 50%;
}
.menu-pip.on::before {
  background: var(--text-accent);
  filter: var(--glow-accent);
}
```

The `0.9rem` gutter is inherited from the current `.submenu-check` so
column alignment does not move. The glow is load-bearing: without it a
5px accent dot is a list bullet, not a lamp.

Unlit rows render an empty gutter. An unlit ring would be more literally
an instrument panel, but with eight game systems that is eight faint
dots competing with eight dice icons. Revisit in the visual pass if the
column reads too sparse.

### Lamp versus control

The two must never be confusable, because only one of them is pressable.

| | Size | Border | Hit target | Reads as |
|---|---|---|---|---|
| `.app-checkbox` | 14px box | 1.5px ring | the box itself | a thing you set |
| `.menu-pip` | 5px dot | none | the whole row | a lamp reporting state |

Size does most of the work. The absent border is the second signal, and
it is true to the metaphor — a panel LED has no bezel you press. **No
rings in menus** is the rule that keeps the two apart.

### Checkbox versus radio moves to ARIA

An earlier draft distinguished multi- from single-select by pip shape:
filled dot against dot-in-ring. That shape *is* `.app-radio:checked`, so
it would draw something that looks exactly like a radio control the user
cannot click. Rejected.

Instead the pip has one form everywhere, and the distinction moves to
the accessibility tree, which is where it is actionable. This is a net
gain: the `✓` was text content, so it is currently the *only* thing
announcing selected state on these rows — the pip is decorative, so the
state has to move somewhere real regardless.

| Site | Semantics | Role |
|---|---|---|
| `ContextMenu.svelte:316` game systems | multi | `menuitemcheckbox` |
| `SystemTagMenu.svelte:67` badge dropdown | multi | `menuitemcheckbox` |
| `CollectionsPanel.svelte:688` pigment (+ `:700` None) | single | `menuitemradio` |
| `CollectionsPanel.svelte:473` sort | single | `menuitemradio` |

Visually the lit pattern already teaches the semantics — three lit pips
is self-evidently many-of, one lit pip among pigments is self-evidently
one-of, and the swatches say so too.

**The containers get `role="menu"`, in this pass.** This is not optional
polish: `menuitemcheckbox` and `menuitemradio` are only valid owned by a
`role="menu"`, and orphaned, whether `aria-checked` announces is
AT-dependent. Since the pip is `aria-hidden`, shipping the roles without
the containers could remove announceable state and put nothing reliable
back — a regression introduced by this pass, not a deferral.

It is more than the container attribute, because children of
`role="menu"` must themselves be menu roles:

- `role="menu"` on each menu and each submenu — `ContextMenu`'s outer
  menu and its three submenus, `SystemTagMenu`'s dropdown, and
  `CollectionsPanel`'s context menu, pigment submenu and sort menu.
- `role="menuitem"` on every plain command row.
- `role="separator"` on the `<hr>` dividers.
- `menuitemcheckbox` / `menuitemradio` per the table above.

Mechanical and bounded — roughly twenty small edits across three
components. `ContextMenu` currently has no roles at all; `CollectionsPanel`
has one stray `role="menuitem"` at `:674` that folds into the same pass.

What this does *not* buy is AT navigability — see Notes.

### Shared checkbox anatomy

`.app-checkbox` becomes the single recipe for all three copies, keyed on
`aria-checked` so it serves both a native `<input>` and the
`role="checkbox"` buttons in the tree and systems views:

```css
.app-checkbox:checked,
.app-checkbox[aria-checked="true"],
.app-checkbox[aria-checked="mixed"] { /* accent fill + border */ }
```

Converting those buttons to real inputs was considered and rejected — it
would put them in the tab order and risk the tree's roving-focus nav.
The base rule already zeroes `padding`, `border` and `background-color`,
so it neutralises everything a `<button>` brings by default.

Both the tick and the indeterminate bar are `background-image` data URIs
rather than pseudo-elements, extending what `.app-checkbox` already does
— `::after` on an `appearance: none` input is unreliable across
WKWebView and WebView2, and this app ships on both. The bar is currently
a hand-positioned 8×2 pseudo-element on a 14px box; as a data URI it
must be redrawn in the existing `viewBox="0 0 16 16"` / `background-size:
10px 10px` frame, so it needs an eye rather than a coordinate
translation. The tick's knockout
colour is hardcoded `%23191919`, which is exactly `--bg-app`
(`rgb(25, 25, 25)`), so folding the other two in preserves their
appearance. That hardcode is pre-existing and stays; `app.css` is
outside the `lint:css` glob.

**`SystemsView` keeps a hue override.** Its checkboxes render only under
`isCollectionEditMode` and use `--text-active`, not `--text-accent` —
purple because they belong to a mode the user switched on, per the
colour semantics. That is correct and deliberate, not drift. It takes
the shared anatomy and overrides `background-color` / `border-color`
only, exactly as the header voices let components keep intentional
colour overrides.

### The chord column

The reason `R` does nothing with the menu open is not an oversight in
the menu: `fileActionGate` at `+page.svelte:2184` carries `!contextMenu`,
so every action key including `⌘O` is switched off while the menu is up.
Wiring these fills a hole the page already yields — there is no
double-fire risk.

Rows carry a `data-chord` attribute and the handler resolves it against
the `mainItems` array `ContextMenu` already maintains:

```js
const key = `${meta ? 'meta+' : ''}${lk}`;
const hit = !inSub && mainItems.find((el) => el.dataset.chord === key);
if (hit) {
  event.preventDefault();
  if (hit.dataset.mi === 'submenu-trigger') { openSubmenu = hit.dataset.submenu; focusedSubmenuIdx = 0; }
  else hit.click();
}
```

A DOM lookup rather than a second dispatch table, so an accelerator can
only fire when its row is actually rendered — which matters, since
Solo/Mute exist only under `canScope` and Hide under its own condition.
Dispatching a real `.click()` means keyboard and mouse cannot diverge.
Gated on `!inSub` so letters stay free inside submenus. `.` needs the
`NumpadDecimal` fallback the global handler already uses (`:1907`). The
submenu-trigger branch exists because `C` opens the Add submenu rather
than firing a command, and those triggers are divs with no click
handler; it reuses the ArrowRight logic.

Wired and displayed in `ContextMenu`, with the `data-chord` value each
row carries:

| Row | Display | `data-chord` |
|---|---|---|
| Reveal in folder | `⌘O` | `meta+o` |
| Solo / Stop soloing | `S` | `s` |
| Mute / Unmute | `M` | `m` |
| Get info | `⌘I` | `meta+i` |
| Add to collection | `C` | `c` |
| Hide / Unhide | `.` | `.` |
| Rename | `R` | `r` |

`Open file` / Space is deliberately skipped — Space in an open menu
conventionally activates the focused row, so claiming it would be a real
conflict rather than a gap. Delete, Re-index and Game system have no
bindings and get a blank column.

`CollectionsPanel` displays `F2` / `F` / `A` but wires nothing: that menu
has no keydown handler at all, and accelerators in a menu you cannot
otherwise drive by keyboard are half a story. The hints are still
accurate — those chords act on the focused panel row.

Display strings come from `chord(id)`, not `chordHint(id)` — the latter
wraps in parens for `title` attributes.

Styling: `.menu-chord`, `--font-mono`, ~0.7rem, `margin-left: auto`,
ahead of the caret on trigger rows.

### Copy

**Ellipsis.** The rule that actually holds here:

> Ellipsis when the command opens a **separate surface** for input; none
> for in-place editing of the row you clicked; none on submenu triggers.

"Opens a dialog" is the wrong rule for this app — `+ New collection…`
calls `startDraftCollection` (`+page.svelte:2711`) and `Add files…`
calls `startEditCollection` (`:2487`); neither opens a modal, both enter
an input mode on another surface. `Rename file` correctly has none: it
edits in place, and no file manager ellipsizes rename.

- Drop from `Game system…` (`ContextMenu.svelte:306`), `Add to
  collection…` (`:346`), `Remove from collection…` (`:390`) and
  `Pigment…` (`CollectionsPanel.svelte:679`) — the caret already says
  "submenu", and the ellipsis contradicts it.
- Keep on `Add files…` and `+ New collection…`.
- `+ collection` (`CollectionsPanel.svelte:654`) becomes `+ New
  collection…`, matching the submenu row for the same kind of action.

**Re-index.** Standardise on the hyphenated form. `LibrarySettings`
contradicts itself as well as the menus — "re-indexed chunks" at `:271`
against "Reindex all files" at `:326` and "Reindex all" at `:358`, plus
"needs reindexing" at `:49`.

**Object nouns.** *Amended 2026-08-12, superseding the "already right"
non-change below.* The noun does two jobs: **disambiguation**, saying
which kind of row you grabbed, and **gravity**, marking an action that
changes or destroys the thing. Which jobs a menu needs decides the rule:

> A polymorphic menu names the object on every command row. A
> monomorphic menu names it on management verbs and leaves transport
> verbs bare.

The tree menu is polymorphic — files and folders — so `Rename file`,
`Hide folder` and `Solo file` all carry the noun. The Collections menu
is monomorphic, so only gravity is left to do: `Rename collection`,
`Archive collection` and `Delete collection` take it, while `Arm`,
`Play` and `Mute` stay bare. Those three are mixer grammar — the
panel's own transport controls are unlabeled icon buttons, and a
channel's transport verbs never name the channel.

The superseded rule (bare verbs throughout a monomorphic menu) was
internally coherent but invisible from inside the app: the same verb
read `Rename file` in one pane and `Rename` in another, with the reason
legible only to someone holding both menus in mind. `Delete collection`
made it worse, reading as drift rather than as emphasis.

**Ribbon.** The Collections submenu trigger is `Ribbon`, not `Pigment`.
It names the glyph the user actually sees, and the ribbon↔collection
mapping is already taught in four places — panel rows, tree rows, scope
chips and search-result index cells. `Ribbon ▸ None` also reads
correctly where `Pigment ▸ None` did not: an undyed ribbon is still a
ribbon. Only the two user-visible strings changed (the trigger and the
`Could not set ribbon` toast); the palette entries stay `Pigment` in
code, because `Ribbon` is already `collectionRibbons.ts`'s per-file type
and a rename would collide. The trigger is filed above `Rename
collection` so the two chord-bearing rows sit together rather than being
split by a caret row.

## Decided non-changes

Recorded so they are not re-litigated.

- **The dice-d6 stays.** It renders identically on every row and so
  discriminates nothing, but it marks those rows as data rather than
  commands. Kept by decision.
- **`Reveal in folder` stays.** Platform-specific copy (`Reveal in
  Finder` / `Show in File Explorer`) was available via the existing
  `isMac` check and declined.
- **Object nouns are already right.** *Superseded 2026-08-12 — see
  "Object nouns" under Copy. Kept for the reasoning, which is still the
  best case against the current rule.* The tree menu names its object
  because it is polymorphic — one menu serves files and folders, so
  "Rename file" vs "Rename folder" tells you what you right-clicked. The
  Collections menu is monomorphic, so bare verbs carry the same
  information, and it already keeps the noun on the destructive one
  (`Delete collection`). Two menus, two correct answers.
- **`Get info` stays.** It is the idiomatic partner to `⌘I`, and the
  chord column renders `chord()`, which returns keys only — it never
  touches the registry's `label`, so the wording need not match
  `keybindings.ts:46`.
- **Command rows get no icons.** Actions stay text per the design
  conventions; an icon column there is the SaaS look and would crowd the
  chord column. This keeps a clean invariant: an icon means the row is a
  thing, no icon means the row is a verb.

## Notes

- **Chord colour: measured and settled — `--text-secondary`, with a
  recorded gap.** This spec originally assumed tertiary might fail on
  `--bg-focused` and that secondary would be the fallback. Against
  `--bg-focused` (`rgb(50, 50, 50)`), tertiary `#7d8590` is 3.44:1 and
  secondary `#8b949e` is 4.17:1 — *both* under the 4.5:1 AA threshold
  for small text. Only `--text-primary` clears it (8.31:1), and that
  would make the hint as loud as the command it annotates. Minting a
  token at `#929ba6` (4.56:1) was rejected: it sits a hair from
  secondary and would collapse the text ramp. So secondary, with the
  gap accepted on the same grounds the header-voices pass accepted its
  tertiary gaps — the chord is supplementary, the row label names the
  command, and the `?` overlay repeats every binding on a darker
  surface.
- **Labelled, not navigable — the honest limit of this pass.** Tracked
  in #363. The roles land here; nothing behind them does.
  `ContextMenu` has no DOM focus management at all: the keyboard cursor
  is a `.kb-focused` class toggled at `:104` while DOM focus stays
  wherever it was before the menu opened. So an AT cursor cannot follow
  the visual one. Roving `tabindex` or `aria-activedescendant` is the
  fix, and it is deferred for a real reason — the current keyboard
  implementation works *because* focus never moves. The handler is on
  `svelte:window` (`:266`) alongside `on:click={onClose}` and an
  outside-`mousedown` handler; moving focus means rethinking all three
  at once.
- **`CollectionsPanel`'s menu will carry roles it cannot honor by
  keyboard.** It has no keydown handler at all. Recorded as a known gap
  rather than left implicit. Porting nav means duplicating ~60 lines
  from `ContextMenu` — a second copy that drifts, which is the failure
  this pass is fixing on the CSS side — so the right sequence is to
  extract shared menu machinery first. Also #363.
- **Wiring accelerators in `CollectionsPanel`** rides along with that
  nav work. The displayed `F2` / `F` / `A` hints stay accurate meanwhile:
  those chords act on the focused panel row.
- **Stale comment.** `+page.svelte:2180` lists the action keys as
  "R/F/./M/C"; the code implements `S`, not `F`. Line 1868 describes the
  same set correctly. Corrected in passing since the block is being
  edited.
- **`.app-radio` will not be missed.** Under "no rings in menus" nothing
  in the current design wants it back. If a settings radio group appears
  later it can be restored from git.

## Verification

1. `npm run lint:css`, `npm run check` and `npm run test` pass.
2. Grep confirms no `✓` glyph remains in `src/lib/`, and no component
   still declares checkbox anatomy (14px / 1.5px border / radius) in
   scoped CSS.
3. Contrast check on the chord colour against `--bg-focused`, recorded
   here.
4. Role audit: every `role="menu"` container has only menu-role children
   (`menuitem`, `menuitemcheckbox`, `menuitemradio`, `separator`), and a
   VoiceOver spot-check confirms a checked game system and the current
   pigment both announce their state — the thing the `✓` used to do by
   accident.
5. Keyboard pass in the running app: each of the seven chords fires from
   the open menu and matches what clicking the row does; letters stay
   inert inside a submenu; `.` works on the main row and numpad.
6. Visual pass on all four menus plus both checkbox sites. Expected
   diffs: pips replace checkmarks; tree checkbox unchanged in accent;
   systems-view checkbox unchanged in purple, including its
   indeterminate bar — the bar is the piece most likely to shift, moving
   from a hand-positioned pseudo-element to a shared data URI.

## Outcomes

Recorded on completion; the two open questions this spec asked to settle,
plus what the automated gates could and could not reach.

- **Chord contrast — settled at `--text-secondary`, gap accepted.**
  Measured 4.17:1 on `--bg-focused`. The spec's original fallback plan
  was wrong: it assumed tertiary might fail and secondary would rescue
  it, but tertiary is 3.44:1 and secondary is also under the 4.5:1 AA
  threshold for small text. Only `--text-primary` clears it (8.31:1),
  which would make the hint as loud as the command; a token at `#929ba6`
  would pass at 4.56:1 but sits a hair from secondary and would collapse
  the text ramp. Accepted on the same grounds as the header-voices
  tertiary gaps — the chord is supplementary and the `?` overlay repeats
  every binding on a darker surface.
- **The sort menu's "Show archived" row did NOT need the button
  fallback.** It kept the planned `<label role="none">` wrapping an
  `<input role="menuitemcheckbox" aria-checked>`. Nothing in the role
  audit or the build gates objected. Note this is a *static* result —
  the fallback existed for the case where VoiceOver announced the
  construct badly, and that check has not run yet, so the question is
  answered structurally but not behaviourally.
- **Gates that passed:** `npm run check` (418 files, 0 errors, 0
  warnings), `npm run lint:css`, the frontend suite, the full sidecar
  suite (594), `cargo fmt --check`, `cargo clippy --all-targets -D
  warnings`. Verification items 1-3 and the static half of 4 are
  satisfied by inspection.
- **Still outstanding, and not reachable by any automated gate:** the
  VoiceOver spot-checks (items 4), the live keyboard pass (item 5), and
  the visual pass (item 6). The indeterminate bar is the highest-risk
  visual item — it moved from a hand-positioned pseudo-element to a
  shared data URI and is now ~6.25px wide against the old 8px, matched
  deliberately to the tick's span. The tree checkbox's tick also
  shrinks ~35-40% and centres, converging it onto the `.app-checkbox`
  already shipping in FilterPanel.

## Related work found on the way

Neither is part of this spec; both were pre-existing and are recorded
here because they surfaced while verifying the menus.

- **`29d2954`** — tagging a game system 500'd on any file with more than
  5461 chunks, Chroma's local write cap, because `_apply_game_systems`
  rewrote every chunk in one `collection.update()`. Two of six books in
  a small test library could never be retagged. Now batched.
- **`0136432`, `8014378`** — that bug was invisible because four Tauri
  commands discarded the sidecar's response body (reporting only
  "Sidecar error: 500"), and because `handleSetGameSystems` wrapped both
  the write and the follow-up refresh in one `try`, so a refresh failure
  rolled back a tag that had actually saved.
