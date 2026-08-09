# Menu Affordances — Design

**Date:** 2026-08-09
**Status:** Approved, not yet implemented.

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

Strictly, those roles want `role="menu"` on their containers. The
containers are plain divs today, with one stray `role="menuitem"` at
`CollectionsPanel.svelte:672`, so this is already inconsistent.
Deferred — see Notes.

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

## Decided non-changes

Recorded so they are not re-litigated.

- **The dice-d6 stays.** It renders identically on every row and so
  discriminates nothing, but it marks those rows as data rather than
  commands. Kept by decision.
- **`Reveal in folder` stays.** Platform-specific copy (`Reveal in
  Finder` / `Show in File Explorer`) was available via the existing
  `isMac` check and declined.
- **Object nouns are already right.** The tree menu names its object
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

- **`--text-tertiary` on `--bg-focused` needs checking** before the
  chord column ships. The token was brightened for WCAG against
  `--bg-app` in 608caa0, and the header-voices work already records
  tertiary on `--bg-focused` at 3.44:1 as an accepted gap for quiet
  chrome. Chord hints may or may not qualify; step to
  `--text-secondary` if not.
- **`role="menu"` on the four containers is deferred.** It is a
  correctness improvement the new roles imply, but it is a separate
  keyboard-semantics pass, and `CollectionsPanel`'s menu needs arrow
  nav before it is worth doing properly.
- **Wiring accelerators in `CollectionsPanel`** is deferred with that
  same nav work.
- **Stale comment.** `+page.svelte:1892` lists the action keys as
  "R/F/./M/C"; the code implements `S`, not `F`. Corrected in passing
  since the block is being edited.
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
4. Keyboard pass in the running app: each of the seven chords fires from
   the open menu and matches what clicking the row does; letters stay
   inert inside a submenu; `.` works on the main row and numpad.
5. Visual pass on all four menus plus both checkbox sites. Expected
   diffs: pips replace checkmarks; tree checkbox unchanged in accent;
   systems-view checkbox unchanged in purple, including its
   indeterminate bar — the bar is the piece most likely to shift, moving
   from a hand-positioned pseudo-element to a shared data URI.
