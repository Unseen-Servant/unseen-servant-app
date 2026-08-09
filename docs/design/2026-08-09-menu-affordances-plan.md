# Menu Affordances Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `✓` glyph in every menu with a shared LED pip, give the
menus real ARIA roles, add a keyboard-chord column wired to live accelerators,
fold three copies of the checkbox recipe into one, and settle two copy
inconsistencies — per [the approved spec](2026-08-09-menu-affordances-design.md).

**Architecture:** Two shared recipes (`.menu-pip`, `.menu-chord`) join the form
controls in `src/app.css`; components adopt them in markup and delete their
scoped duplicates. Selected state moves out of text content into
`aria-checked`, which requires real menu roles, so the roles land **first** —
before the glyph is removed — so no commit ever ships with state
unannounced. Chord matching is a pure function in `keybindings.ts` (the only
unit-testable logic here) with the menu resolving chords against its own
rendered rows rather than a second dispatch table.

**Tech Stack:** Svelte 5 scoped CSS, plain CSS in `app.css`, vitest (node
environment, no DOM), stylelint (`npm run lint:css`), svelte-check
(`npm run check`).

**Conventions for every task:**
- Commit after each task, directly on `main`.
- `npm run check` must report zero errors **and zero "Unused CSS selector"
  warnings** in touched files — that warning is the primary signal that a
  scoped block was orphaned by a markup change.
- Shared recipes live in `app.css`; layout (margins, padding, flex) and
  intentional colour overrides stay in component CSS. Precedent: the header
  voices.
- `app.css` is outside the `lint:css` glob (`src/lib/**/*.svelte`). Component
  CSS is linted and must use `var(--*)` tokens for any colour property.

---

### Task 1: Menu roles and `aria-checked`

Goes first. The pip in Task 2 is `aria-hidden`, so selected state must already
live in `aria-checked` before the `✓` text is removed. `menuitemcheckbox` and
`menuitemradio` are only valid owned by a `role="menu"`, so the containers come
with them. The `✓` stays for this one commit — briefly redundant, never absent.

`<hr>` already carries an implicit `separator` role, which is valid inside
`role="menu"`, so the dividers need no attribute.

**Files:**
- Modify: `src/lib/ContextMenu.svelte`
- Modify: `src/lib/SystemTagMenu.svelte`
- Modify: `src/lib/CollectionsPanel.svelte`

- [ ] **Step 1: Add `role="menu"` to the four `ContextMenu` containers**

On the outer `.context-menu` div (~line 269), add `role="menu"` alongside the
existing attributes. On each of the three `.submenu` divs (the tag submenu
~line 309, add ~line 349, remove ~line 393), change:

```svelte
<div class="submenu">
```

to:

```svelte
<div class="submenu" role="menu">
```

- [ ] **Step 2: Add `role="menuitem"` to every plain `ContextMenu` command row**

Every `<button class="context-item" data-mi="item" …>` gets `role="menuitem"`.
That is: Open file, Reveal in folder, Solo, Mute, Re-index file, Get info,
Clear tags, each collection row in the add and remove submenus, `+ New
collection…`, Hide/Unhide, Rename, Delete. Example — the Open file row becomes:

```svelte
<button class="context-item" data-mi="item" role="menuitem" on:click={onOpen}>Open file</button>
```

- [ ] **Step 3: Give the three `ContextMenu` submenu triggers menu semantics**

Each `<div class="context-item submenu-trigger" …>` gets `role="menuitem"`,
`aria-haspopup="menu"` and `aria-expanded`. The tag trigger (~line 298) becomes:

```svelte
    <div
      class="context-item submenu-trigger"
      class:open={openSubmenu === 'tag'}
      data-mi="submenu-trigger"
      data-submenu="tag"
      role="menuitem"
      aria-haspopup="menu"
      aria-expanded={openSubmenu === 'tag'}
      on:mouseenter={() => { openSubmenu = 'tag'; }}
      on:mouseleave={() => { openSubmenu = null; }}
    >
```

Apply the same three attributes to the `add` trigger (~line 338) and the
`remove` trigger (~line 382), matching each one's own `openSubmenu === …`
comparison. This mirrors what `CollectionsPanel.svelte:674` already does.

- [ ] **Step 4: Convert the `ContextMenu` game-system rows to `menuitemcheckbox`**

At ~line 311:

```svelte
            <button
              class="context-item"
              data-mi="item"
              role="menuitemcheckbox"
              aria-checked={currentTags.includes(sys.tag)}
              on:click={() => toggleGameSystem(sys.tag)}
            >
```

- [ ] **Step 5: Apply the same treatment to `SystemTagMenu`**

The `.dropdown` div (~line 59) gets `role="menu"`. The system rows (~line 66)
become:

```svelte
      <button
        class="dropdown-item"
        role="menuitemcheckbox"
        aria-checked={tags.includes(sys.tag)}
        on:click={() => onToggleSystem(sys.tag)}
      >
```

The `Clear tags` button (~line 77) gets `role="menuitem"`.

- [ ] **Step 6: Add roles to the `CollectionsPanel` context menu**

The `.context-menu` div (~line 661) and the pigment `.submenu` div (~line 682)
each get `role="menu"`. `Rename`, `Add files…`, `Archive`/`Unarchive` and
`Delete collection` each get `role="menuitem"`. The pigment trigger at line 674
already has `role="menuitem"`, `aria-haspopup` and `aria-expanded` — leave it.

The pigment rows (~line 685) and the `None` row (~line 697) become
`menuitemradio`:

```svelte
            <button
              class="context-item"
              role="menuitemradio"
              aria-checked={col?.color === pig.hex}
              on:click|stopPropagation={() => ctxAction((name) => onSetColor(name, pig.hex))}
            >
```

and for `None`:

```svelte
          <button
            class="context-item"
            role="menuitemradio"
            aria-checked={!col?.color}
            on:click|stopPropagation={() => ctxAction((name) => onSetColor(name, null))}
          >
```

- [ ] **Step 7: Add roles to the `CollectionsPanel` sort menu**

The `.sort-menu` div (~line 467) gets `role="menu"`. The sort options (~line
469) become:

```svelte
            <button
              class="sort-item"
              role="menuitemradio"
              aria-checked={sortKey === opt.value}
              on:click={() => pickSort(opt.value)}
            >
```

The "Show archived" row is a `<label>` wrapping a real `.app-checkbox` input.
A `<label>` is not a valid child of `role="menu"`, so mark the label
presentational and put the menu role on the input:

```svelte
            <label class="sort-toggle" role="none">
              <span>Show archived</span>
              <input
                class="app-checkbox"
                type="checkbox"
                role="menuitemcheckbox"
                aria-checked={showArchived}
                bind:checked={showArchived}
              />
            </label>
```

The visual control is unchanged — this is the contrast the spec relies on to
teach the lamp-vs-control vocabulary. If the VoiceOver check in Step 9 shows
this announcing badly, the documented fallback is to convert the row to a
`<button role="menuitemcheckbox">` styled like the others; record the outcome
in the design doc either way.

- [ ] **Step 8: Verify nothing broke**

Run: `npm run check && npm run lint:css`
Expected: zero errors, zero warnings. No CSS changed in this task, so any
"Unused CSS selector" warning means a class was dropped by accident.

- [ ] **Step 9: VoiceOver spot-check**

With the app running, open the tree context menu on an indexed PDF and step
into the Game system submenu with VoiceOver on (Cmd+F5). A tagged system must
announce its checked state. Repeat for a pigment in the collections menu and
for the active sort option. Both the `✓` and the ARIA state are present at this
commit, so the glyph may be announced too — that is expected and goes away in
Task 2.

- [ ] **Step 10: Commit**

```bash
git add src/lib/ContextMenu.svelte src/lib/SystemTagMenu.svelte src/lib/CollectionsPanel.svelte
git commit -m "a11y(menus): add menu roles and aria-checked ahead of the pip swap

menuitemcheckbox/menuitemradio are only valid inside a role=menu, and the
incoming .menu-pip is aria-hidden — so selected state has to live in
aria-checked before the checkmark glyph goes away. Roles land first and the
glyph stays for this commit: briefly redundant, never absent.

Refs #363 for the focus management that sits behind these labels."
```

---

### Task 2: The `.menu-pip` selection lamp

**Files:**
- Modify: `src/app.css` (after the `.app-radio` block, ~line 369)
- Modify: `src/lib/ContextMenu.svelte`
- Modify: `src/lib/SystemTagMenu.svelte`
- Modify: `src/lib/CollectionsPanel.svelte`

- [ ] **Step 1: Add the shared recipe to `app.css`**

Append after the form controls, before `/* --- Font Utilities --- */`:

```css
/* --- Menu Vocabulary --- */

/* Menu selection lamp — reports which option is in effect on rows whose whole
   surface is the click target. Deliberately unlike .app-checkbox: 5px vs 14px
   and no border, because a panel LED has no bezel you press. Decorative;
   the announced state is aria-checked on the row. */
.menu-pip {
  width: 0.9rem;
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

- [ ] **Step 2: Convert the `ContextMenu` game-system rows**

Replace line ~316:

```svelte
              <span class="submenu-check">{currentTags.includes(sys.tag) ? '✓' : ''}</span>
```

with:

```svelte
              <span class="menu-pip" class:on={currentTags.includes(sys.tag)} aria-hidden="true"></span>
```

Then delete the now-orphaned `.submenu-check` block from the scoped style
(~line 490):

```css
  .submenu-check {
    width: 0.9rem;
    color: var(--text-accent);
    font-weight: 700;
    flex-shrink: 0;
  }
```

- [ ] **Step 3: Convert `SystemTagMenu`**

Replace line ~67:

```svelte
        <span class="dropdown-check">{tags.includes(sys.tag) ? '✓' : ''}</span>
```

with:

```svelte
        <span class="menu-pip" class:on={tags.includes(sys.tag)} aria-hidden="true"></span>
```

Delete the `.dropdown-check` block (~line 116).

- [ ] **Step 4: Convert both `CollectionsPanel` sites**

Sort menu, line ~473:

```svelte
              <span class="menu-pip" class:on={sortKey === opt.value} aria-hidden="true"></span>
```

Pigment rows, line ~688:

```svelte
              <span class="menu-pip" class:on={col?.color === pig.hex} aria-hidden="true"></span>
```

The `None` row, line ~700:

```svelte
            <span class="menu-pip" class:on={!col?.color} aria-hidden="true"></span>
```

Delete the combined `.check, .pig-check` block (~lines 799-800 and its body).

- [ ] **Step 5: Confirm no glyph survives**

Run: `grep -rn '✓' src/`
Expected: no matches.

- [ ] **Step 6: Verify**

Run: `npm run check && npm run lint:css`
Expected: zero errors, zero "Unused CSS selector" warnings. A warning naming
`.submenu-check`, `.dropdown-check`, `.check` or `.pig-check` means Step 2-4
missed a deletion.

- [ ] **Step 7: Commit**

```bash
git add src/app.css src/lib/ContextMenu.svelte src/lib/SystemTagMenu.svelte src/lib/CollectionsPanel.svelte
git commit -m "feat(menus): replace the checkmark glyph with a shared LED pip

The checkmark was a text glyph at font-weight 700 in a serif body face —
baseline-aligned, font-dependent, and generic OS-menu vocabulary in an app that
says 'on' with LED glow everywhere else. One .menu-pip recipe now serves all
four sites; checkbox-vs-radio semantics live in the roles added last commit
rather than in the pip's shape (a dot-in-ring would have looked exactly like
the .app-radio control it isn't)."
```

---

### Task 3: Extend `.app-checkbox`, delete `.app-radio`

Pure `app.css`. Nothing references the new selectors yet, so there is no visual
change — the two adopting components follow in Tasks 4 and 5.

**Files:**
- Modify: `src/app.css:303-369`

- [ ] **Step 1: Key the checked state on `aria-checked` as well as `:checked`**

Replace the `.app-checkbox:checked` block (~line 323) with:

```css
/* Both a native input and a role="checkbox" button drive this recipe — the
   tree and systems views use buttons so their rows keep control of focus and
   click handling. The tick and the indeterminate bar are background images
   rather than pseudo-elements: ::after on an appearance:none input is
   unreliable across WKWebView and WebView2, and this app ships on both. */
.app-checkbox:checked,
.app-checkbox[aria-checked="true"],
.app-checkbox[aria-checked="mixed"] {
  background-color: var(--text-accent);
  border-color: var(--text-accent);
}
.app-checkbox:checked,
.app-checkbox[aria-checked="true"] {
  background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'><path fill='none' stroke='%23191919' stroke-width='3' stroke-linecap='round' stroke-linejoin='round' d='M3 8 L7 12 L13 4'/></svg>");
}
.app-checkbox[aria-checked="mixed"] {
  background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'><path fill='none' stroke='%23191919' stroke-width='3' stroke-linecap='round' d='M4 8 L12 8'/></svg>");
}
```

`%23191919` is `--bg-app` (`rgb(25, 25, 25)`) URL-encoded; it already appears in
this file and stays. The bar is redrawn in the `viewBox="0 0 16 16"` /
`background-size: 10px 10px` frame rather than translated from the old
hand-positioned 8×2 pseudo-element — check it by eye in Tasks 4 and 5.

- [ ] **Step 2: Delete the unused `.app-radio` recipe**

Delete `app.css:335-369` entirely — the `.app-radio` base, `:hover`,
`:checked`, `:checked::after`, `:disabled` and `:focus-visible` rules. Nothing
in `src/` references it, and under the spec's "no rings in menus" rule nothing
will.

- [ ] **Step 3: Verify it is genuinely unreferenced**

Run: `grep -rn "app-radio" src/`
Expected: no matches.

- [ ] **Step 4: Verify**

Run: `npm run check && npm run test`
Expected: pass. No component changed, so this should be inert.

- [ ] **Step 5: Commit**

```bash
git add src/app.css
git commit -m "refactor(css): key .app-checkbox on aria-checked; drop dead .app-radio

Lets one recipe serve both the native input and the role=checkbox buttons in
the tree and systems views, which keep their own focus and click handling.
Adds the indeterminate bar as a second data URI. .app-radio was defined and
referenced nowhere."
```

---

### Task 4: `FileTree` adopts the shared checkbox

**Files:**
- Modify: `src/lib/FileTree.svelte:208-216` (markup), `:353-397` (scoped CSS)

- [ ] **Step 1: Swap the class in markup**

The `class:checked` / `class:indeterminate` directives become redundant —
`aria-checked` already encodes both states and now drives the styling. Replace
the button at ~line 208 with:

```svelte
    <button
      class="app-checkbox row-checkbox"
      on:click|stopPropagation={handleCheckboxChange}
      role="checkbox"
      aria-label="Select {item.name}"
      aria-checked={isIndeterminate ? 'mixed' : isChecked}
    ></button>
```

- [ ] **Step 2: Replace the scoped CSS block with layout only**

Delete all six `.checkbox*` rules (`:353-397`) and put back only what is
layout — the shared recipe supplies every other property:

```css
  .row-checkbox {
    margin-right: 0.5rem;
    margin-left: 0.2rem;
  }
```

- [ ] **Step 3: Verify**

Run: `npm run check && npm run lint:css`
Expected: zero errors and no "Unused CSS selector" warning for `.checkbox`.

- [ ] **Step 4: Visual check**

With the app running, confirm in the file tree that an unchecked row shows a
parchment-bordered empty box, a checked file shows the accent fill with the
dark tick, and a partially-selected folder shows the accent fill with the dark
bar. The bar is the piece most likely to have shifted.

- [ ] **Step 5: Commit**

```bash
git add src/lib/FileTree.svelte
git commit -m "refactor(tree): adopt the shared .app-checkbox recipe

Drops 45 lines of scoped CSS that duplicated app.css's anatomy, keeping only
the row margins. aria-checked already carried both states, so the class:checked
and class:indeterminate directives go with it."
```

---

### Task 5: `SystemsView` adopts the shared checkbox, keeping its hue

Its checkboxes render only under `isCollectionEditMode` and use
`--text-active`, not `--text-accent` — purple because they belong to a mode the
user switched on, per the colour semantics. That is deliberate and survives.

**Files:**
- Modify: `src/lib/SystemsView.svelte:486-494` and `:558-568` (markup), `:739-782` (scoped CSS)

- [ ] **Step 1: Swap the class on the group checkbox**

At ~line 486:

```svelte
            <button
              class="app-checkbox group-checkbox"
              on:click={(e) => handleGroupCheckboxClick(e, group.entries)}
              role="checkbox"
              aria-label="Select all in {group.tag}"
              aria-checked={groupState === 'some' ? 'mixed' : groupState === 'all'}
            ></button>
```

- [ ] **Step 2: Swap the class on the row checkbox**

At ~line 558:

```svelte
                  <button
                    class="app-checkbox row-checkbox"
                    on:click={(e) => handleCheckboxClick(e, entry, group.tag, group.entries)}
                    on:mousedown|stopPropagation
                    on:dblclick|stopPropagation
                    role="checkbox"
                    aria-label="Add {entry.filename} to collection"
                    aria-checked={isChecked}
                  ></button>
```

- [ ] **Step 3: Replace the scoped CSS with the hue override plus layout**

Delete the six `.checkbox*` rules at `:739-782` and replace with:

```css
  /* Edit-mode selection is a mode the user switched on, so these boxes take
     --text-active rather than the shared recipe's --text-accent. Anatomy and
     both knockout glyphs come from .app-checkbox. */
  .app-checkbox {
    align-self: center;
  }
  .app-checkbox:hover {
    border-color: var(--text-active);
  }
  .app-checkbox[aria-checked="true"],
  .app-checkbox[aria-checked="mixed"] {
    background-color: var(--text-active);
    border-color: var(--text-active);
  }
```

Leave the existing `.group-checkbox` (~line 781) and `.row-checkbox` (~line
784) margin rules in place — both class names stay on the markup alongside
`.app-checkbox`, so neither goes unused.

- [ ] **Step 4: Verify**

Run: `npm run check && npm run lint:css`
Expected: zero errors, no "Unused CSS selector" warning for `.checkbox`. The
override uses `var(--text-active)`, so the stylelint colour rule is satisfied.

- [ ] **Step 5: Visual check**

Start editing a collection so the checkboxes appear. Confirm rows are purple
when checked, that a partially-selected group header shows the purple fill with
the dark bar, and that hover turns the border purple — not parchment.

- [ ] **Step 6: Commit**

```bash
git add src/lib/SystemsView.svelte
git commit -m "refactor(systems): adopt .app-checkbox, keep the --text-active hue

Third and last copy of the checkbox anatomy. The purple is not drift: these
boxes exist only in collection-edit mode, and purple is the token for a mode
the user switched on — so the component keeps a hue override and takes
everything else from the shared recipe."
```

---

### Task 6: Chord matching in `keybindings.ts` (TDD)

The only unit-testable logic in this plan. `vitest` runs in the default node
environment with no DOM (`vitest.config.ts` includes `src/**/*.test.ts`), so
the helper takes a structural type that a real `KeyboardEvent` satisfies rather
than the DOM type.

**Files:**
- Modify: `src/lib/keybindings.ts`
- Test: `src/lib/keybindings.test.ts` (create)

- [ ] **Step 1: Write the failing test**

Create `src/lib/keybindings.test.ts`:

```ts
import { describe, expect, test } from 'vitest';
import { KEYBINDINGS, eventMatchKey, matchKey, type ChordEvent } from './keybindings';

const ev = (over: Partial<ChordEvent>): ChordEvent => ({
  key: '',
  code: '',
  metaKey: false,
  ctrlKey: false,
  shiftKey: false,
  altKey: false,
  ...over,
});

describe('eventMatchKey', () => {
  test('lowercases a bare letter', () => {
    expect(eventMatchKey(ev({ key: 'R', code: 'KeyR' }))).toBe('r');
  });

  test('normalizes Cmd and Ctrl to the same key so one table serves both platforms', () => {
    expect(eventMatchKey(ev({ key: 'o', code: 'KeyO', metaKey: true }))).toBe('meta+o');
    expect(eventMatchKey(ev({ key: 'o', code: 'KeyO', ctrlKey: true }))).toBe('meta+o');
  });

  test('treats the numpad period as a period regardless of layout', () => {
    expect(eventMatchKey(ev({ key: '.', code: 'Period' }))).toBe('.');
    // Some layouts (e.g. German) report ',' for the numpad decimal key.
    expect(eventMatchKey(ev({ key: ',', code: 'NumpadDecimal' }))).toBe('.');
  });

  test('rejects shift and alt combinations', () => {
    expect(eventMatchKey(ev({ key: 'R', code: 'KeyR', shiftKey: true }))).toBeNull();
    expect(eventMatchKey(ev({ key: 'r', code: 'KeyR', altKey: true }))).toBeNull();
  });

  test('rejects non-character keys', () => {
    expect(eventMatchKey(ev({ key: 'ArrowDown', code: 'ArrowDown' }))).toBeNull();
    expect(eventMatchKey(ev({ key: 'Enter', code: 'Enter' }))).toBeNull();
  });
});

describe('menu accelerators', () => {
  test('no two bindings claim the same match key', () => {
    const matches = KEYBINDINGS.filter((k) => k.match).map((k) => k.match);
    expect(new Set(matches).size).toBe(matches.length);
  });

  test('every declared match key is reachable from a real keypress', () => {
    for (const entry of KEYBINDINGS.filter((k) => k.match)) {
      const meta = entry.match!.startsWith('meta+');
      const char = meta ? entry.match!.slice(5) : entry.match!;
      expect(eventMatchKey(ev({ key: char, metaKey: meta }))).toBe(entry.match);
    }
  });

  test('matchKey resolves a known id and returns empty for an unknown one', () => {
    expect(matchKey('tree.rename')).toBe('r');
    expect(matchKey('nope.missing')).toBe('');
  });
});
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `npx vitest run src/lib/keybindings.test.ts`
Expected: FAIL — `eventMatchKey`, `matchKey` and `ChordEvent` are not exported.

- [ ] **Step 3: Add the `match` field to the interface**

In `src/lib/keybindings.ts`, extend `KeybindingEntry` (~line 20):

```ts
export interface KeybindingEntry {
  id: string;
  keys: { mac: string; other: string };
  label: string;
  scope: KeyScope;
  // Normalized form used to dispatch this chord from inside an open menu.
  // Present only on bindings a menu re-exposes as an accelerator; the menu
  // matches on this rather than on the display string in `keys`.
  match?: string;
}
```

- [ ] **Step 4: Tag the seven dispatchable bindings**

Add `match` to exactly these entries, leaving every other field untouched:

| id | add |
|---|---|
| `info.show` | `match: 'meta+i'` |
| `tree.openExternal` | `match: 'meta+o'` |
| `tree.rename` | `match: 'r'` |
| `tree.solo` | `match: 's'` |
| `tree.mute` | `match: 'm'` |
| `tree.hide` | `match: '.'` |
| `tree.addToCollection` | `match: 'c'` |

For example, `tree.rename` becomes:

```ts
  { id: 'tree.rename',           keys: { mac: 'R',    other: 'R' },             label: 'Rename focused row',           scope: 'fileTree', match: 'r' },
```

- [ ] **Step 5: Add the two helpers**

Append to `src/lib/keybindings.ts`, after `chordHint`:

```ts
// Structural stand-in for KeyboardEvent so this stays testable under vitest's
// node environment — a real KeyboardEvent satisfies it.
export interface ChordEvent {
  key: string;
  code: string;
  metaKey: boolean;
  ctrlKey: boolean;
  shiftKey: boolean;
  altKey: boolean;
}

// Normalized lookup key for a keydown, matching KeybindingEntry.match. Cmd and
// Ctrl both fold to `meta+` so one table serves both platforms. Returns null
// for anything no accelerator uses.
export function eventMatchKey(event: ChordEvent): string | null {
  if (event.shiftKey || event.altKey) return null;
  // event.code is layout-independent; some layouts report ',' for the numpad
  // decimal key.
  const base = event.code === 'NumpadDecimal' ? '.' : event.key.toLowerCase();
  if (base.length !== 1) return null;
  return event.metaKey || event.ctrlKey ? `meta+${base}` : base;
}

// The match key for a binding id, or '' when the binding has no accelerator.
export function matchKey(id: string): string {
  return BY_ID.get(id)?.match ?? '';
}
```

- [ ] **Step 6: Run the tests**

Run: `npx vitest run src/lib/keybindings.test.ts`
Expected: PASS, 8 tests.

- [ ] **Step 7: Verify the whole suite**

Run: `npm run test && npm run check`
Expected: pass.

- [ ] **Step 8: Commit**

```bash
git add src/lib/keybindings.ts src/lib/keybindings.test.ts
git commit -m "feat(keys): add normalized chord matching to the binding registry

Menus need to dispatch the same chords that work on a focused row, so the
registry gains a match field and a pure eventMatchKey helper. Deriving both the
display string and the match key from one entry keeps them from drifting; the
tests pin the numpad-period and Cmd/Ctrl folding, and guard against two
bindings claiming the same key."
```

---

### Task 7: The chord column

**Contrast decision, settled before writing any CSS.** The spec assumed
`--text-tertiary` might fail on `--bg-focused` and that `--text-secondary`
would be the fallback. Measured against `--bg-focused` (`rgb(50, 50, 50)`):
tertiary `#7d8590` is **3.44:1** and secondary `#8b949e` is **4.17:1** — *both*
below the 4.5:1 AA threshold for small text. Only `--text-primary` clears it, at
8.31:1, and that would make the hint as loud as the command it annotates.

Use `--text-secondary` and record the gap. Minting a token at `#929ba6`
(4.56:1) was rejected: it sits a hair from secondary and would collapse the
text ramp, which the ramp rule forbids. This matches the posture the
header-voices pass already took for quiet chrome, and the chord is genuinely
supplementary — the row's label fully identifies the command, and the `?`
overlay carries the same information on a darker surface.

**Files:**
- Modify: `src/app.css` (the Menu Vocabulary block from Task 2)
- Modify: `src/lib/ContextMenu.svelte`
- Modify: `src/lib/CollectionsPanel.svelte`

- [ ] **Step 1: Add the recipe to `app.css`**

Append inside the Menu Vocabulary block, after `.menu-pip.on::before`:

```css
/* Keyboard hint riding at the trailing edge of a menu row. --text-secondary is
   4.17:1 on --bg-focused, below AA for small text: an accepted gap, consistent
   with the tertiary gaps recorded in the header-voices pass. The chord is
   supplementary — the row label names the command, and the ? overlay repeats
   every binding on a darker surface. Primary would clear AA but would make the
   hint as loud as the command. */
.menu-chord {
  margin-left: auto;
  padding-left: 1rem;
  font-family: var(--font-mono);
  font-size: 0.7rem;
  color: var(--text-secondary);
  white-space: nowrap;
}
```

- [ ] **Step 2: Let the caret share a row with the chord**

`.submenu-trigger` currently uses `justify-content: space-between`, which with
three children would strand the chord in the middle. Push both to the trailing
edge instead. In `ContextMenu.svelte`, change the `.submenu-trigger` rule
(~line 474) to drop `justify-content: space-between`:

```css
  .submenu-trigger {
    position: relative;
    display: flex;
    align-items: center;
    user-select: none;
  }
```

and change `.submenu-caret` (~line 485) from `margin-left: 0.5rem` to:

```css
  .submenu-caret {
    font-size: 0.7rem;
    opacity: 0.6;
    margin-left: auto;
  }
```

On a trigger with a chord, the chord's own `margin-left: auto` absorbs the free
space first and the caret follows immediately after it.

- [ ] **Step 3: Import the helper in `ContextMenu`**

At the top of the `<script>` block (~line 3):

```ts
  import { chord, matchKey } from './keybindings';
```

- [ ] **Step 4: Add the hint and `data-chord` to the seven rows**

Each row gains `data-chord` for matching and a trailing `<span class="menu-chord">`
for display, both derived from the registry. Reveal in folder (~line 279):

```svelte
  <button class="context-item" data-mi="item" role="menuitem" data-chord={matchKey('tree.openExternal')} on:click={onReveal}>
    Reveal in folder
    <span class="menu-chord">{chord('tree.openExternal')}</span>
  </button>
```

Solo (~line 282) and Mute (~line 285):

```svelte
    <button class="context-item" data-mi="item" role="menuitem" data-chord={matchKey('tree.solo')} on:click={onToggleSolo}>
      {isSoloed ? 'Stop soloing' : 'Solo'} this {item.is_dir ? 'folder' : 'file'}
      <span class="menu-chord">{chord('tree.solo')}</span>
    </button>
    <button class="context-item" data-mi="item" role="menuitem" data-chord={matchKey('tree.mute')} on:click={onToggleMute}>
      {isMuted ? 'Unmute' : 'Mute'} this {item.is_dir ? 'folder' : 'file'}
      <span class="menu-chord">{chord('tree.mute')}</span>
    </button>
```

Get info (~line 292):

```svelte
    <button class="context-item" data-mi="item" role="menuitem" data-chord={matchKey('info.show')} on:click={onShowStats}>
      Get info
      <span class="menu-chord">{chord('info.show')}</span>
    </button>
```

Hide/Unhide (~line 425):

```svelte
    <button class="context-item" data-mi="item" role="menuitem" data-chord={matchKey('tree.hide')} on:click={onToggleHidden}>
      {directlyHidden ? 'Unhide' : 'Hide'} {item.is_dir ? 'folder' : 'file'}
      <span class="menu-chord">{chord('tree.hide')}</span>
    </button>
```

Rename (~line 431):

```svelte
  <button class="context-item" data-mi="item" role="menuitem" data-chord={matchKey('tree.rename')} on:click={onRename}>
    Rename {item.is_dir ? 'folder' : 'file'}
    <span class="menu-chord">{chord('tree.rename')}</span>
  </button>
```

The Add to collection trigger (~line 338) takes `data-chord` too, with the
chord span placed between the label and the caret:

```svelte
      <span>Add to collection</span>
      <span class="menu-chord">{chord('tree.addToCollection')}</span>
      <span class="submenu-caret">&#9656;</span>
```

and `data-chord={matchKey('tree.addToCollection')}` added to the trigger div's
attribute list.

Note the label here has already lost its ellipsis — Task 9 removes it from the
other three triggers. Write it without the `&hellip;` and leave the rest to
Task 9.

- [ ] **Step 5: Add display-only hints to the `CollectionsPanel` menu**

That menu has no keydown handler, so these rows get a hint and no `data-chord`
— the chords act on the focused panel row. Import `chord` in that component's
script, then:

```svelte
    <button class="context-item" role="menuitem" on:click={() => ctxAction(startRename)}>
      Rename
      <span class="menu-chord">{chord('collections.rename')}</span>
    </button>
```

```svelte
    <button class="context-item" role="menuitem" on:click={() => ctxAction(onEditFiles)}>
      Add files&hellip;
      <span class="menu-chord">{chord('collections.editFiles')}</span>
    </button>
    <button class="context-item" role="menuitem" on:click={() => ctxAction((name) => onToggleArchived(name, !col?.archived))}>
      {col?.archived ? 'Unarchive' : 'Archive'}
      <span class="menu-chord">{chord('collections.archive')}</span>
    </button>
```

- [ ] **Step 6: Verify**

Run: `npm run check && npm run lint:css`
Expected: zero errors. `.menu-chord` lives in `app.css`, so the stylelint colour
rule never sees it.

- [ ] **Step 7: Visual check**

Open both menus. Chords sit right-aligned in mono, quieter than the labels.
On "Add to collection" the order reads label → `C` → `▸`, and the two triggers
without chords still have their caret hard right.

- [ ] **Step 8: Commit**

```bash
git add src/app.css src/lib/ContextMenu.svelte src/lib/CollectionsPanel.svelte
git commit -m "feat(menus): show keyboard chords on menu rows

Both display string and match key come from the binding registry so they can't
drift apart. --text-secondary is 4.17:1 on --bg-focused, under AA for small
text and recorded as an accepted gap: tertiary is worse at 3.44:1, primary
would make the hint as loud as the command, and a token between secondary and
primary would collapse the text ramp. The chord is supplementary — the label
names the command and the ? overlay repeats every binding."
```

---

### Task 8: Wire the accelerators

**Files:**
- Modify: `src/lib/ContextMenu.svelte:164-220`
- Modify: `src/routes/+page.svelte:1892` (stale comment)

- [ ] **Step 1: Import the matcher**

Extend the import added in Task 7:

```ts
  import { chord, matchKey, eventMatchKey } from './keybindings';
```

- [ ] **Step 2: Add the accelerator branch to `handleKeydown`**

Insert after the `isLeft` branch and before the `Enter` branch (~line 205), so
`h`/`j`/`k`/`l` navigation always wins:

```js
    // Accelerators: the same chords that work on a focused tree row, live
    // inside the menu. The page's fileActionGate switches them off while a
    // context menu is open (+page.svelte:2184), so nothing else claims them.
    // Resolved against the rendered rows rather than a second dispatch table,
    // so a chord can only fire when its row actually exists — Solo/Mute only
    // render under canScope, Hide under its own condition.
    if (!inSub) {
      const mk = eventMatchKey(event);
      const hit = mk ? mainItems.find((el) => el.dataset.chord === mk) : undefined;
      if (hit) {
        event.preventDefault();
        const sub = hit.dataset.submenu as 'add' | 'remove' | 'tag' | undefined;
        if (hit.dataset.mi === 'submenu-trigger' && sub) {
          // Triggers are divs with no click handler — mirror the ArrowRight path.
          openSubmenu = sub;
          focusedSubmenuIdx = 0;
        } else {
          hit.click();
        }
        return;
      }
    }
```

- [ ] **Step 3: Correct the stale comment on the global handler**

`+page.svelte:2180` lists the action keys as "R/F/./M/C"; the code implements
`S`, not `F`. (Line 1868 describes the same set correctly as "R/S/./M/C" — that
one is already right and stays untouched.) Change line 2180 from:

```js
    // Action keys (R/F/./M/C, Cmd+O reveal, Shift+F10/ContextMenu) work
```

to:

```js
    // Action keys (R/S/./M/C, Cmd+O reveal, Shift+F10/ContextMenu) work
```

- [ ] **Step 4: Verify**

Run: `npm run check && npm run test && npm run lint:css`
Expected: pass.

- [ ] **Step 5: Keyboard check in the running app**

With a context menu open on an indexed PDF inside a collection:

- `r` starts a rename, `s` toggles solo, `m` toggles mute, `.` toggles hidden —
  each matching what clicking the row does.
- `c` opens the Add to collection submenu; `h`/`←` closes it again.
- `⌘o` reveals in Finder, `⌘i` opens the info modal.
- With a submenu open, `r`/`s`/`m` do nothing — letters stay inert inside it.
- `j`/`k` still navigate and are never swallowed by an accelerator.
- On a folder row with no indexed content, `s` and `m` do nothing, because
  those rows are not rendered.

- [ ] **Step 6: Commit**

```bash
git add src/lib/ContextMenu.svelte src/routes/+page.svelte
git commit -m "feat(menus): wire tree action chords inside the context menu

fileActionGate already excludes !contextMenu, so these keys were dead while the
menu was open even though every one of them has a row in it. The menu now
resolves a keypress against its own rendered rows and dispatches a real click,
so keyboard and mouse cannot diverge and a chord can only fire when its row
exists. Also corrects a stale comment listing the action keys as R/F/./M/C."
```

---

### Task 9: Copy fixes

**Files:**
- Modify: `src/lib/ContextMenu.svelte`
- Modify: `src/lib/CollectionsPanel.svelte`
- Modify: `src/lib/LibrarySettings.svelte`

- [ ] **Step 1: Drop the ellipsis from the submenu triggers**

A caret already says "submenu"; an ellipsis says "this asks you for something
first", which these do not. In `ContextMenu.svelte`:

- line ~306: `<span>Game system&hellip;</span>` → `<span>Game system</span>`
- line ~390: `<span>Remove from collection&hellip;</span>` → `<span>Remove from collection</span>`

`Add to collection` was already rewritten without its ellipsis in Task 7 Step 4
— confirm it reads `<span>Add to collection</span>`.

In `CollectionsPanel.svelte` line ~679: `<span>Pigment&hellip;</span>` →
`<span>Pigment</span>`.

- [ ] **Step 2: Give the panel's create button the full label**

`Add files…` and `+ New collection…` keep their ellipses — both open a separate
surface for input. The panel button does the same thing as the submenu row, so
it takes the same label. Line ~654:

```svelte
    <button class="add-coll" on:click={onCreate}>+ New collection&hellip;</button>
```

The scoped CSS comment at ~line 836 refers to `the "+ collection" row` — update
that string to `the "+ New collection" row` so it still describes the markup.

- [ ] **Step 3: Standardize on the hyphenated `Re-index`**

`LibrarySettings.svelte` contradicts both the menus and itself. Change:

- line ~49: `needs reindexing.` → `needs re-indexing.`
- line ~158: `use Reindex all below to rebuild.` → `use Re-index all below to rebuild.`
- line ~326: `Reindex all files` → `Re-index all files`
- line ~358: `'Reindex all'` → `'Re-index all'`

Line ~271 already reads `re-indexed chunks` — leave it. Identifiers
(`confirmingReindex`, `cancelReindex`) are code, not copy: leave them alone.

- [ ] **Step 4: Confirm no unhyphenated user-facing form survives**

Run: `grep -rn "Reindex\|reindexing" src/ --include="*.svelte"`
Expected: only identifier matches (`confirmingReindex`, `cancelReindex`), no
display strings.

- [ ] **Step 5: Verify**

Run: `npm run check && npm run lint:css`
Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add src/lib/ContextMenu.svelte src/lib/CollectionsPanel.svelte src/lib/LibrarySettings.svelte
git commit -m "fix(ui): settle the menu ellipsis rule and the Re-index spelling

Ellipsis now means one thing: the command opens a separate surface for input.
Submenu triggers lose theirs — the caret already says submenu — while Add
files… and + New collection… keep theirs, and the panel's create button takes
the same label as the submenu row that does the same job. Re-index is
hyphenated everywhere; LibrarySettings had been contradicting both the menus
and itself."
```

---

## Final verification

- [ ] `npm run lint:css && npm run check && npm run test` all pass.
- [ ] `grep -rn '✓' src/` returns nothing.
- [ ] `grep -rn "app-radio" src/` returns nothing.
- [ ] No component declares checkbox anatomy (14px / 1.5px border /
      `--radius-sm`) in scoped CSS — only `.app-checkbox` in `app.css`, plus
      SystemsView's hue override and the two margin rules.
- [ ] Role audit: every `role="menu"` container has only menu-role children,
      and a VoiceOver pass confirms a checked game system, the current pigment
      and the active sort option each announce their state.
- [ ] Update the design doc's Status line to "Implemented 2026-08-09 on main"
      and record the two results it asks for: the measured chord contrast
      (4.17:1, accepted) and whether the sort menu's "Show archived" row
      needed the button fallback from Task 1 Step 7.
