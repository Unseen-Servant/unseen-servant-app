# Shared Menu Machinery — Design

**Date:** 2026-08-11
**Status:** Designed. Not yet implemented.
**Issue:** #363, items 2 and 3. Item 1 (DOM focus management) is
deliberately deferred — see *Sequencing against focus management*.

## Problem

The [menu affordances pass](2026-08-09-menu-affordances-design.md) gave
four menus proper ARIA: `role="menu"` on the container,
`menuitem` / `menuitemcheckbox` / `menuitemradio` on rows, `separator`
on dividers. The roles landed across the tree-row `ContextMenu` and its
three submenus, the `CollectionsPanel` context menu, the
`CollectionsPanel` sort menu, and `SystemTagMenu`.

Only one of the four can be driven by keyboard.

1. **Three menus carry menu roles they cannot honor.** The Collections
   context menu, the sort menu and `SystemTagMenu` have no arrow
   navigation. `SystemTagMenu` handles Esc and nothing else
   (`SystemTagMenu.svelte:76`); the Collections menus are covered by
   `handleWindowKey`, which claims Esc and then bails out entirely while
   either is open (`CollectionsPanel.svelte:369-382`). The roles promise
   a navigable menu; the code delivers a list you can only click.

2. **Porting nav means copying the part that drifts.** `ContextMenu`'s
   implementation is roughly eighty lines across `refreshItemsAndFocus`,
   `handleKeydown` and `clampOpenSubmenuToViewport`. Perhaps twenty-five
   of those are index arithmetic. The rest — re-querying rows after a
   render, toggling the cursor class, routing arrows and vim keys,
   stepping into and out of submenus, dispatching accelerators, clamping
   a submenu against the viewport — is DOM glue, and DOM glue is exactly
   what a second copy gets wrong. Copying it into three more components
   reproduces on the behavior side the failure the affordances pass was
   fixing on the CSS side.

3. **The Collections menu advertises accelerators that go dead when you
   open it.** Its rows render `chord('collections.*')` — E, P / Space,
   M, R, A, ⌘⌫ — and wire none of them, because of the same early return
   at `CollectionsPanel.svelte:382`. The chords work on a focused row
   with the menu closed and stop working the moment the menu is up. A
   menu that displays a key it then swallows is worse than one that
   displays nothing.

4. **Two chord vocabularies for the same keys.** `ContextMenu` resolves
   accelerators through the keybindings table (`data-chord` +
   `eventMatchKey`). The Collections row handler hardcodes bare letters
   (`CollectionsPanel.svelte:465-489`). Rebinding a collection chord in
   `KEYBINDINGS` today would move the menu's displayed hint and leave the
   row's actual behavior untouched.

5. **The Collections color submenu has no viewport clamping.** Found
   while surveying: `placeContextMenu` clamps the menu itself
   (`CollectionsPanel.svelte:330`), but the color submenu is positioned
   by static CSS alone, so it clips against a window edge. `ContextMenu`
   solved this months ago and the solution is trapped in that file.

## Decision

Three files, split by what each can be tested with.

### `menuNav.ts` — the cursor, as arithmetic

Pure index math. No DOM, no Svelte, node-tested alongside `treeNav.ts`
and `menuSlot.ts`.

```ts
export interface MenuCursor {
  /** -1 = no cursor yet: the menu was opened by mouse and no key has
   *  been pressed. Never rendered as a highlight. */
  idx: number;
  /** null = not inside a submenu. */
  subIdx: number | null;
}

export interface MenuCounts {
  main: number;
  sub: number;
}

export function step(cursor: MenuCursor, delta: 1 | -1, counts: MenuCounts): MenuCursor;
export function clampCursor(cursor: MenuCursor, counts: MenuCounts): MenuCursor;
export function enterSubmenu(cursor: MenuCursor, triggerIdx?: number): MenuCursor;
export function exitSubmenu(cursor: MenuCursor): MenuCursor;
export function inSubmenu(cursor: MenuCursor): boolean;
```

Two behaviors in the current implementation are load-bearing and easy to
lose in a rewrite, so they are stated here as the module's contract:

- **The first arrow promotes rather than steps.** From `idx: -1`, both ↑
  and ↓ land on `0`. Today this falls out of `Math.max(0, -1 - 1)` and
  `Math.min(count - 1, -1 + 1)`; in the module it is explicit and tested
  in both directions.
- **A re-render clamps the upper bound only.** `-1` survives. Clamping
  it to `0` would paint a cursor on the first row of a menu the user is
  driving with the mouse — a highlight nobody asked for, appearing when
  a conditional row happens to render.

Submenu clamping keeps the existing shape too: `subIdx` is clamped into
range only when the submenu actually has rows, so an empty or
not-yet-rendered submenu leaves the cursor alone rather than snapping it
to zero.

### `menuGeometry.ts` — gains `placeSubmenu`

`clampOpenSubmenuToViewport`'s decision logic, with the DOM writes
lifted out:

```ts
export interface SubmenuPlacement {
  vertical: 'top' | 'bottom';
  /** Space available on the chosen side, floored at 120px. Applied as
   *  --submenu-room; the stylesheet takes the smaller of it and
   *  --menu-max-height so the scroll ceiling stays declared once. */
  room: number;
  horizontal: 'left' | 'right';
}

export function placeSubmenu(
  trigger: Size & Point,
  submenu: Size,
  menu: Size & Point,
  viewport: Size,
  padding?: number,
): SubmenuPlacement;
```

It lands beside `clampToViewport`, which already answers the same
question for whole menus. The rules are unchanged from the current
implementation — anchor on whichever side of the trigger has more room,
flip to the left of the menu when the submenu overflows right and the
left side has more space — but they become node-testable instead of
living inside a component method that reads `getBoundingClientRect`.

This is what fixes problem 5: the Collections color submenu gets
clamping by adopting the shared action, not as a separate errand.

### `menuKeys.ts` — a Svelte action owning the DOM

Attached to the `role="menu"` element. It owns:

- The `window` keydown listener, registered on mount and removed on
  destroy. This replaces four separate `svelte:window` handlers with one
  lifetime that a single file is responsible for.
- Re-querying `[data-mi]` rows through a `MutationObserver`, so
  conditional rows appearing or vanishing cannot desync the cursor.
- Applying `.kb-focused`.
- Arrow and vim key routing, Enter → `click()`, and the Esc ladder
  (inside a submenu, Esc exits it; otherwise Esc closes the menu).
- Accelerator dispatch through `eventMatchKey` against `data-chord`.
- Applying `placeSubmenu`'s answer as inline styles.

What it deliberately does **not** own is *which* submenu is open. That
is component state — it drives `class:open`, hover-opens and rendering —
so it arrives as an option and changes through a callback:

```ts
export interface MenuKeysOptions {
  onClose: () => void;
  openSubmenu?: string | null;
  onOpenSubmenu?: (which: string | null) => void;
}
```

There is no flag for accelerators. A row carrying `data-chord` is
dispatchable and a row without one is not, which is already how
`ContextMenu` decides — Reveal shows ⌥⌘R and stays display-only by
simply not carrying the attribute.

The action owns the cursor; the component owns the open submenu. Keeping
that line clean is what lets `SystemTagMenu` and the sort menu — neither
of which has submenus — adopt it in two lines.

`menuSlot` claiming stays exactly where it is. The components claim the
slot at different lifetimes (`ContextMenu` on mount, the others on
toggle), that machinery is already shared and already tested, and
pulling it into the action would be scope creep with no dedup to show
for it.

### Sequencing against focus management

#363 item 1 — moving real DOM focus into the menu so assistive tech can
follow the visual cursor — is **not** in this pass, and this design is
shaped so that it stays cheap.

The cursor is modelled as an index, not as a focus target. Nothing in
`menuNav.ts` knows how the cursor is painted. Today `menuKeys.ts` paints
it with `classList.toggle('kb-focused')`; item 1 replaces that with
roving `tabindex` or `aria-activedescendant`. That is one edit, inside
one file, and all four menus inherit it — which is precisely the
argument for extracting before attempting it rather than after.

The parts of item 1 that genuinely need their own design pass — what
happens to the outside-`mousedown` handler and `on:click={onClose}` once
focus lives inside the menu, and where focus returns on close — are
untouched here and remain open.

### Adoption

**`ContextMenu`** is the reference port and the one commit that must be
verifiable as a pure refactor: no user-visible change. Out go
`refreshItemsAndFocus`, `handleKeydown`, `clampOpenSubmenuToViewport`,
the four cursor variables, the `afterUpdate`, and `on:keydown` from
`svelte:window`. In goes `use:menuKeys`. `on:click={onClose}` and
`handleOutsideMouseDown` stay untouched — that is mouse lifecycle, and
#279 settled it. Row markup does not change: `data-mi`, `data-chord` and
`data-submenu` are already the attributes the action reads.

The behavior most at risk in this port is the C-chord path, where the
menu opens directly into a submenu and the trigger's index must be
resolved so ← and Esc have a row to fall back to. The action handles it
on attach when `openSubmenu` is already set, and it gets an explicit
test rather than a careful read.

**Collections context menu** gains `data-mi` on its rows,
`data-submenu="color"` on the color trigger, `data-chord` where a chord
exists, and `use:menuKeys`. `handleWindowKey` gives up its
Esc-when-`ctxMenu` branch to the action and keeps the `|| ctxMenu` early
return.

**Sort menu** and **`SystemTagMenu`**: `data-mi` on rows, `use:menuKeys`
with the close function each already has. `SystemTagMenu` drops
`handleWindowKeydown`; its `on:click={closeDropdown}` stays.

### Accelerators

Five `collections.*` entries gain a `match` field: arm `e`, play `p`,
mute `m`, rename `r`, archive `a`. Two deliberate exclusions:

- **Delete stays display-only in the menu.** ⌘⌫ / Del is a named key and
  cannot round-trip through `eventMatchKey`, which is why `isDeleteChord`
  exists as its own predicate. The tree's context menu already shows
  Delete as a hint it does not dispatch; Collections matches it.
- **Space stays row-only.** `collections.play` displays "P / Space" and a
  `match` field holds one key. P works inside the menu; Space keeps
  working on a focused row through its existing branch. On a highlighted
  menu row Space reads as "activate", which Enter already does.

The row handler conversion swaps the predicate and keeps the structure:
`bareLetter && lk === 'r'` becomes a comparison against
`matchKey('collections.rename')`, branch by branch, with every existing
comment left in place — the "E for edit, not F" reasoning and the
archived-inert rules for arm and play. `eventMatchKey` already rejects
Shift and Alt and folds ⌘/Ctrl into a `meta+` prefix, so the
`bareLetter` guard falls out of those branches on its own.

After this, one table is the source of truth for a collection chord, in
the menu and on the row alike.

## Decided non-changes

- **No `<Menu>` wrapper component.** It would have to absorb three
  different positioning strategies — viewport-clamped at a click point,
  trigger-anchored, submenu-relative-with-flip — and rewrite markup at
  four call sites. Positioning is #279 territory, which is closed and
  working.
- **`menuSlot` stays where it is.** Already shared, already tested,
  different lifetimes per component.
- **Mouse lifecycle is untouched.** Hover intent, rapid re-opens,
  outside-click: settled in #279.
- **No focus management.** #363 item 1, deferred on purpose above.
- **Space is not bound inside menus.** See *Accelerators*.

## Notes

**Two window keydown listeners coexist** while the Collections menu is
open: the panel's and the action's. The panel's early return on
`ctxMenu` makes the outcome independent of registration order. That
guard now has a second job and reads like dead code without knowing it —
it needs a comment saying so, or a later cleanup will remove it and
break in-menu accelerators in a way that is hard to trace back.

**`MutationObserver` is a microtask, `afterUpdate` was synchronous.**
Safe as designed: the action applies the cursor synchronously inside its
own key handler, and the observer only covers rows appearing or
vanishing from an external re-render, where the delay is invisible. It
is still a real behavioral difference and is recorded here so it is not
rediscovered as a bug.

**Svelte 5 in legacy syntax.** The codebase runs Svelte 5 with Svelte 4
authoring (`export let`, `on:click`, `afterUpdate`). Actions are fully
supported there; this design introduces no migration pressure.

## Verification

`menuNav.test.ts`, node environment:

- `-1` promotes to `0` on the first ↑ and on the first ↓.
- Upper bound clamps when a conditional row disappears; `-1` survives a
  re-render.
- Submenu enter, exit, and clamp-only-when-populated.
- Both zero-length cases.

`menuGeometry.test.ts`, extended:

- Flips above when space below is short.
- Flips left when the submenu overflows right and left has more room.
- Floors reported room at 120px.

`menuKeys.test.ts`, `// @vitest-environment jsdom` docblock so only this
file runs in jsdom and every existing test stays on node. Adds `jsdom`
as a devDep; CI is Linux-only, so the added minutes are noise.

- Cursor moves on arrows and on vim keys.
- Enter clicks the cursor row.
- Esc exits a submenu before it closes the menu.
- An accelerator dispatches to the row carrying that `data-chord`.
- A submenu-trigger accelerator opens the submenu *and* resolves the
  cursor, so ← and Esc have somewhere to land.
- `destroy` removes the window listener.

Manual, in the running app, after the `ContextMenu` port: the port is a
refactor, so the check is that nothing changed — arrows, vim keys,
submenu stepping, the C chord opening straight into Add-to-collection,
and every tree accelerator still firing from inside the menu.

## Implementation sequence

Separate commits on main:

1. `menuNav.ts` + tests
2. `placeSubmenu` in `menuGeometry.ts` + tests
3. `menuKeys.ts` + jsdom tests
4. Port `ContextMenu` — behavior-identical, lands alone
5. Adopt in the Collections context menu, sort menu, `SystemTagMenu`
6. Accelerators: `match` fields, menu wiring, row handler conversion

## Outcomes

To be recorded on implementation.
