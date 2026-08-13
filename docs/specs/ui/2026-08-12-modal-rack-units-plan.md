# Modals as Rack Units — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild every modal as a rack unit — two `--bg-header` rails bracketing bays of `--bg-app` wells — and rebuild confirmations around the app's 18px hardware switch, with damage stated as a before/after readout.

**Architecture:** `Modal.svelte` grows a rail/commit slot pair and loses its `×`. A new `CommitSwitch.svelte` composes a label with a switch face that shares `.sm-btn`'s recipe through a selector list in `app.css`, so the two can never drift. The keyboard model is extracted into a pure `confirmKeys.ts` module so it is unit-testable: activation prompts leave Enter to the focused button (never a dialog-level Enter listener — that was the audit's F1), removal prompts focus the dialog and commit on the delete chord.

**Tech Stack:** Svelte **5.56.8 in legacy (non-runes) mode** — components use `export let` and `<slot>`, and `svelte.config.js` sets no `runes: true`, so named slots and `$$slots` work as written. (An earlier draft of this plan said Svelte 4; that was wrong, and it matters for `{#each}` keying — see Task 6.) TypeScript, Vitest (pure-logic tests only — there is no jsdom or testing-library in this repo, so components are verified by `svelte-check`, `stylelint`, `vite build`, and the manual passes in Task 12), stylelint with a raw-colour ban over `src/lib/**/*.svelte`.

**Design:** [2026-08-12-modal-rack-units-design.md](2026-08-12-modal-rack-units-design.md)

**Mockups:** https://claude.ai/code/artifact/d79814d1-f2c7-4b6e-ad6f-e09097d6c498

---

## File structure

| File | Responsibility | Task |
|---|---|---|
| `src/lib/confirmKeys.ts` *(new)* | Which key commits, and whether a keydown is it. Pure, testable. | 1 |
| `src/lib/confirmKeys.test.ts` *(new)* | Its tests. | 1 |
| `src/lib/keybindings.ts` | Two `modal`-scope entries + `commitKeyShortcut()`; later, the `switch` flag. | 1, 11 |
| `src/lib/confirmStore.ts` | `ConfirmRow` type; `rows` passthrough. | 2 |
| `src/app.css` | Shared recipes: `.switch-face`, `.commit-switch`, `.modal-bay*`, `.modal-well*`, `.modal-readout`. | 3 |
| `src/lib/Modal.svelte` | The unit shell: rails, slots, escape legend, keydown forwarding. | 4 |
| `src/lib/CommitSwitch.svelte` *(new)* | Label + switch face as one button. | 5 |
| `src/lib/ConfirmDialog.svelte` | The confirm unit: bays, rows, commit strip, keyboard model. | 6 |
| `src/routes/+page.svelte`, `src/lib/GameSystemsSettings.svelte` | Call sites that can fill rows. | 7 |
| `src/lib/DocumentStatsModal.svelte` | Two bays, no commit strip. | 8 |
| `src/lib/GameSystemsSettings.svelte` | Bays, commit strip, hint cut, focus nit. | 9 |
| `src/lib/SettingsModal.svelte`, `src/lib/LibrarySettings.svelte` | Tabs on the rail, sub-tabs unified, Danger Zone as a bay. | 10 |
| `src/lib/KeyboardHelpOverlay.svelte` | Bays, two columns, key caps. | 11 |

Tasks 8, 9, 10 and 11 are independent of each other. Everything depends on 3 and 4.

---

## Task 1: The commit-key model

> **Shipped 2026-08-12** as `33180b9` + `524ff5d`. Code review corrected three
> things this task's snippets got wrong, so read the tree rather than the code
> blocks below: `isCommitChord` collapses to
> `return danger && isDeleteChord(event, mac);` (default parameters fire on an
> explicitly-passed `undefined`, so the ternary defended against nothing); the
> two `commitKeyId` tests were tautologies and became a coupling test against
> `KEYBINDINGS`/`chord()`, because `chord()` returns `''` silently for an
> unknown id and a rename would blank the switch face with every check green;
> and the `modal`-scope comment must name **two** `SCOPE_ORDER` gatekeepers —
> `KeyboardHelpOverlay` and `help/ReferencePane` each keep their own.

**Files:**
- Create: `src/lib/confirmKeys.ts`
- Create: `src/lib/confirmKeys.test.ts`
- Modify: `src/lib/keybindings.ts` (append to `KEYBINDINGS`, add `commitKeyShortcut`)

- [ ] **Step 1: Add the two `modal`-scope bindings**

In `src/lib/keybindings.ts`, append to the end of the `KEYBINDINGS` array (after the `searchResults` group, before the closing `];`):

```ts
  // Modal — excluded from the cheat sheet by KeyboardHelpOverlay's SCOPE_ORDER.
  // Defined anyway so the commit switch's face and the dialog's matcher read the
  // chord from one place instead of hardcoding a glyph in each.
  { id: 'confirm.commit',     keys: { mac: '⌘⌫', other: 'Del' },   label: 'Commit a destructive confirmation', scope: 'modal' },
  { id: 'confirm.commitSafe', keys: { mac: '↵',  other: 'Enter' }, label: 'Commit a confirmation',             scope: 'modal' },
```

- [ ] **Step 2: Add `commitKeyShortcut`**

Append to `src/lib/keybindings.ts`, directly after `isDeleteChord`:

```ts
// aria-keyshortcuts for a destructive commit. keyShortcut() derives from
// `match`, and named keys can't round-trip through eventMatchKey (single
// characters only) — so this binding has no `match` and needs its own.
export function commitKeyShortcut(mac = isMac): string {
  return mac ? 'Meta+Backspace' : 'Delete';
}
```

- [ ] **Step 3: Write the failing tests**

Create `src/lib/confirmKeys.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { commitKeyId, isCommitChord } from './confirmKeys';
import type { ChordEvent } from './keybindings';

const ev = (over: Partial<ChordEvent> = {}): ChordEvent => ({
  key: 'a', code: 'KeyA', metaKey: false, ctrlKey: false, shiftKey: false, altKey: false, ...over,
});

describe('commitKeyId', () => {
  it('names the safe binding for an activation prompt', () => {
    expect(commitKeyId(false)).toBe('confirm.commitSafe');
  });

  it('names the delete binding for a removal prompt', () => {
    expect(commitKeyId(true)).toBe('confirm.commit');
  });
});

describe('isCommitChord', () => {
  // The whole point of F1's fix: an activation prompt keeps focus on its
  // commit button and lets the button take Enter natively. If this module
  // ever returned true for Enter, the dialog would grow the listener the
  // audit deleted.
  it('never matches on an activation prompt, including Enter', () => {
    expect(isCommitChord(ev({ key: 'Enter' }), false, true)).toBe(false);
    expect(isCommitChord(ev({ key: 'Backspace', metaKey: true }), false, true)).toBe(false);
  });

  it('matches the mac delete chord on a removal prompt', () => {
    expect(isCommitChord(ev({ key: 'Backspace', metaKey: true }), true, true)).toBe(true);
  });

  it('matches the non-mac delete key on a removal prompt', () => {
    expect(isCommitChord(ev({ key: 'Delete' }), true, false)).toBe(true);
  });

  // Enter must be inert on a removal prompt: focus sits on the dialog
  // element, so there is no button for it to activate either.
  it('does not match Enter on a removal prompt', () => {
    expect(isCommitChord(ev({ key: 'Enter' }), true, true)).toBe(false);
  });

  it('rejects a bare Backspace on mac', () => {
    expect(isCommitChord(ev({ key: 'Backspace' }), true, true)).toBe(false);
  });

  it('rejects Shift+Delete — that means "delete permanently" elsewhere', () => {
    expect(isCommitChord(ev({ key: 'Delete', shiftKey: true }), true, false)).toBe(false);
  });
});
```

- [ ] **Step 4: Run the tests to verify they fail**

```bash
npx vitest run src/lib/confirmKeys.test.ts
```

Expected: FAIL — `Failed to resolve import "./confirmKeys"`.

- [ ] **Step 5: Write the implementation**

Create `src/lib/confirmKeys.ts`:

```ts
import { isDeleteChord, type ChordEvent } from './keybindings';

/**
 * Which key a confirmation's commit switch wears, and answers to.
 *
 * The split is the design's safety mechanism, not a style choice:
 *
 * - An **activation** prompt (re-index — nothing is destroyed) keeps focus
 *   on its commit button, so Enter is handled natively by the button.
 *   `isCommitChord` therefore never matches for one: a dialog-level Enter
 *   listener is exactly what made Cancel unsafe (F1 in the modal audit),
 *   and it must not come back.
 * - A **removal** prompt focuses the dialog element itself, so Enter has no
 *   button to activate and is inert. It commits on the delete chord —
 *   the key that raised the deletion is the key that commits it.
 *
 * See docs/specs/ui/2026-08-12-modal-rack-units-design.md#the-keyboard.
 */
export function commitKeyId(danger: boolean): 'confirm.commit' | 'confirm.commitSafe' {
  return danger ? 'confirm.commit' : 'confirm.commitSafe';
}

/**
 * True when this keydown should fire the commit. `mac` is a parameter rather
 * than a closed-over constant so tests can exercise both platforms, matching
 * isDeleteChord's own shape.
 */
export function isCommitChord(event: ChordEvent, danger: boolean, mac?: boolean): boolean {
  if (!danger) return false;
  return mac === undefined ? isDeleteChord(event) : isDeleteChord(event, mac);
}
```

- [ ] **Step 6: Run the tests to verify they pass**

```bash
npx vitest run src/lib/confirmKeys.test.ts
```

Expected: PASS, 8 tests.

- [ ] **Step 7: Commit**

```bash
git add src/lib/confirmKeys.ts src/lib/confirmKeys.test.ts src/lib/keybindings.ts && git commit -m "feat(modals): name the key that throws the commit switch"
```

---

## Task 2: Readout rows in the store

> **Shipped 2026-08-12** as `96d3eb0` + `875761c`. The field below was
> originally specified as `from`; review renamed it to `value`, because four of
> the rows this feature actually writes have no `to` at all and the doc comment
> had to apologise for the name on its own first line. The snippets here are
> corrected. Also note vitest does **not** type-check, so this test passes with
> or without the field — `svelte-check` is what actually gates it.

**Files:**
- Modify: `src/lib/confirmStore.ts`
- Modify: `src/lib/confirmStore.test.ts`

- [ ] **Step 1: Write the failing test**

Append inside the existing `describe('confirm store', ...)` block in `src/lib/confirmStore.test.ts`, before its closing `});`:

```ts
  // Rows are optional per call site: a caller with no figures in hand keeps
  // using `message`, so adoption never blocks on data the page can't cheaply
  // get (delete-file has no chunk count — see the design's Readout data).
  it('carries readout rows through untouched, and omits them when absent', () => {
    const store = createConfirmStore();

    void store.request({
      title: 'Delete collection',
      danger: true,
      rows: [
        { label: 'Track', value: 'Session 14' },
        { label: 'Files', value: '12', to: 'Loose', unchanged: true },
      ],
    });

    expect(get(store)?.rows).toEqual([
      { label: 'Track', value: 'Session 14' },
      { label: 'Files', value: '12', to: 'Loose', unchanged: true },
    ]);

    store.answer(false);
    void store.request({ title: 'Delete file', message: 'Move it to Trash?', danger: true });

    expect(get(store)?.rows).toBeUndefined();
  });
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
npx vitest run src/lib/confirmStore.test.ts
```

Expected: FAIL — TypeScript rejects `rows` as it is not in `ConfirmRequest`.

- [ ] **Step 3: Add the type**

In `src/lib/confirmStore.ts`, insert above `export interface ConfirmRequest`:

```ts
/**
 * One line of a confirmation's readout — the app's habit of answering "how
 * much" with a figure rather than an adjective, applied to damage.
 *
 * `value` is the figure; `to` is what it becomes, when there is a transition
 * at all — four of the rows this ships have none. `unchanged` marks a `to` that is a reassurance
 * rather than damage ("untouched", "Loose") so the dialog renders it calm
 * instead of in the prompt's tone — the caller states what the value means
 * and the dialog decides how that looks, keeping this store presentation-free.
 */
export interface ConfirmRow {
  label: string;
  value: string;
  to?: string;
  unchanged?: boolean;
}
```

Then add the field to `ConfirmRequest`, directly after `message`:

```ts
  rows?: ConfirmRow[];
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
npx vitest run src/lib/confirmStore.test.ts
```

Expected: PASS, 7 tests.

- [ ] **Step 5: Commit**

```bash
git add src/lib/confirmStore.ts src/lib/confirmStore.test.ts && git commit -m "feat(modals): let a confirmation state its damage as figures"
```

---

## Task 3: The shared recipes

**Files:**
- Modify: `src/app.css`

`app.css` is not covered by stylelint (`lint:css` globs `src/lib/**/*.svelte`), but every value below is a token anyway.

- [ ] **Step 1: Share the 18px switch recipe with a non-button face**

In `src/app.css`, change the `.sm-btn {` selector at line 329 to a selector list. Find:

```css
.sm-btn {
  flex-shrink: 0;
  width: 18px;
```

Replace the selector line so it reads:

```css
/* `.switch-face` is the same object rendered inside another button (the
   commit switch), where a nested <button> is illegal. One recipe, two
   elements — a copy would drift the moment either is retuned. */
.sm-btn,
.switch-face {
  flex-shrink: 0;
  width: 18px;
```

- [ ] **Step 2: Extend the lit recipes to the commit switch**

Find the `.sm-btn.solo-on,` / `.sm-btn.bypass-on {` rule (app.css:388) and add a third selector:

```css
.sm-btn.solo-on,
.sm-btn.bypass-on,
.commit-switch.activation .switch-face {
```

Find `.sm-btn.mute-on {` and make it:

```css
.sm-btn.mute-on,
.commit-switch.danger .switch-face {
```

Find the two `.motion-ready` animation rules and extend them the same way:

```css
.motion-ready .sm-btn.solo-on,
.motion-ready .sm-btn.bypass-on,
.motion-ready .commit-switch.activation .switch-face {
  animation: detent-glow 110ms ease-out;
}
```

```css
.motion-ready .sm-btn.mute-on,
.motion-ready .commit-switch.danger .switch-face {
  animation: detent-flat 110ms ease-out;
}
```

- [ ] **Step 3: Cover the commit switch in the reduced-motion block**

The block at `app.css:527` lists selectors explicitly, so the switch is **not** covered for free. Find it and add the two new selectors:

```css
@media (prefers-reduced-motion: reduce) {
  dialog[open],
  dialog[open]::backdrop,
  .motion-ready .sm-btn.solo-on,
  .motion-ready .sm-btn.bypass-on,
  .motion-ready .sm-btn.mute-on,
  .motion-ready .commit-switch.activation .switch-face,
  .motion-ready .commit-switch.danger .switch-face {
    animation: none;
  }
}
```

- [ ] **Step 4: Add the unit recipes**

Append to `src/app.css`, after the modal geometry tokens block:

```css
/* --- Modal unit --- */

/* A dialog is a rack unit: two --bg-header rails bracketing its bays, the
   way the Header and StatusBar bracket the workspace (StatusBar.svelte:168).
   The rails themselves are layout and live in Modal.svelte; what is shared
   across surfaces — bays, wells, readouts, the commit switch — lives here.
   See docs/specs/ui/2026-08-12-modal-rack-units-design.md. */

.modal-bays {
  padding: var(--modal-pad);
  display: flex;
  flex-direction: column;
  gap: 0.9rem;
  min-height: 0;
}

.modal-bay {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  min-width: 0;
}

/* Readouts sit *in* the panel, not on it. --radius-well is documented as the
   concentric wrap around --radius-md contents; this is what it was for. */
.modal-well {
  background: var(--bg-app);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-well);
  overflow: hidden;
}

.modal-well-row {
  display: grid;
  grid-template-columns: 5.5rem minmax(0, 1fr);
  align-items: baseline;
  gap: 0.75rem;
  padding: 0.4rem 0.65rem;
}
.modal-well-row + .modal-well-row {
  border-top: 1px solid var(--border-subtle);
}

.modal-readout {
  font-family: var(--font-mono);
  font-size: 0.78rem;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.modal-readout.wrap {
  white-space: normal;
  overflow-wrap: anywhere;
}
.modal-readout .arrow {
  color: var(--text-tertiary);
  opacity: 0.7;
  padding: 0 0.15rem;
}
/* The tone of a `to` comes from the well, not the row: one prompt is one
   kind of change. `.unchanged` is the exception a caller marks. */
.modal-well.removal .modal-readout .to { color: var(--text-danger); }
.modal-well.activation .modal-readout .to { color: var(--text-active); }
.modal-readout .to.unchanged { color: var(--text-secondary); }

/* Commit switch: the label is the switch's nameplate, the face carries the
   key that throws it — the scope bar's `Scope │ B` grammar, mirrored. */
.commit-switch {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  background: none;
  border: none;
  padding: 0.1rem;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-family: var(--font-body);
  transition: transform var(--transition-fast);
}
.commit-switch .commit-label {
  font-size: 0.85rem;
  color: var(--text-secondary);
  transition: filter var(--transition-fast);
}
.commit-switch.danger .commit-label { color: var(--text-danger); }
.commit-switch.activation .commit-label { color: var(--text-active); }
.commit-switch:hover:not(:disabled) .commit-label { filter: brightness(1.2); }
.commit-switch:active:not(:disabled) { transform: scale(0.97); }
.commit-switch:focus-visible { outline: 1px solid var(--text-accent); outline-offset: 2px; }
.commit-switch:disabled { cursor: default; }
.commit-switch:disabled .commit-label { color: var(--text-tertiary); filter: none; }
.commit-switch:disabled .switch-face { opacity: 0.35; }

/* Divides a rail's nameplate from what it carries — the same rule the scope
   bar puts between its master switch and the channels (.master-rule). Shared
   because three surfaces need it and Svelte scopes component styles. */
.rail-rule {
  width: 1px;
  height: 12px;
  background: var(--border-subtle);
  flex-shrink: 0;
}

/* A bay of destructive actions: the well's frame tinted to the same 45% the
   controls inside use, so structure never outranks them. Shared by the Danger
   Zone and the game-system unit. */
.modal-well.danger-bay {
  border-color: color-mix(in srgb, var(--text-danger) 32%, transparent);
}
.modal-well-row.action-row {
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 1rem;
  padding: 0.55rem 0.65rem;
}
.modal-well-row.action-row .row-text {
  font-family: var(--font-body);
  font-size: 0.8rem;
  color: var(--text-secondary);
  line-height: 1.35;
  min-width: 0;
}
.modal-well-row.action-row .row-title {
  display: block;
  font-family: var(--font-heading);
  font-size: 0.85rem;
  color: var(--text-primary);
  margin-bottom: 0.15rem;
}
```

These groups are in `app.css` rather than in a component because **Svelte
scopes component styles** — `danger-bay`, `action-row` and `.rail-rule` are
each needed by two or more of `DocumentStatsModal`, `GameSystemsSettings`,
`SettingsModal` and `LibrarySettings`, and a per-file copy is exactly the
drift this design exists to remove.

(An earlier draft also added a `.step-back` recipe for backing out of an armed
Danger Zone control. Task 10 now retires arm-then-fire entirely, so there is no
armed state to step back out of and the recipe is gone before it was written.)

- [ ] **Step 5: Verify nothing regressed**

```bash
npm run lint:css && npx svelte-check --tsconfig ./tsconfig.json
```

Expected: stylelint clean; svelte-check 0 errors.

- [ ] **Step 6: Commit**

```bash
git add src/app.css && git commit -m "feat(modals): give the rack unit its shared recipes"
```

---

## Task 4: The unit shell

**Files:**
- Modify: `src/lib/Modal.svelte`

- [ ] **Step 1: Add the props**

In `src/lib/Modal.svelte`, after the `describedBy` prop declaration, add:

```ts
  // The rail's dismiss slot names the escape rather than drawing an ×: the
  // word differs because backing out of a question is not the same act as
  // closing a panel. See the design's "Cancel is a legend in the top rail".
  export let escapeWord: 'cancel' | 'close' = 'close';
  $: escapeName = escapeWord === 'cancel' ? 'Cancel' : 'Close';
```

- [ ] **Step 2: Replace the header plate with the rail, and add the commit strip**

Replace the whole `<dialog>` body — everything from `<div class="modal-header">` to `<slot />` inclusive — with:

```svelte
  <div class="modal-rail">
    <span class="dialog-nameplate ledger-label" id={titleId}>{title}</span>
    <slot name="rail" />
    <span class="rail-grow"></span>
    <button type="button" class="modal-escape" on:click={onClose} aria-label={escapeName}>
      <span class="k">esc</span>{escapeWord}
    </button>
  </div>
  <slot />
  {#if $$slots.commit}
    <div class="modal-commit-strip">
      <slot name="commit" />
    </div>
  {/if}
```

- [ ] **Step 3: Forward keydown from the dialog element**

Add `on:keydown` (bare, no handler) to the `<dialog>` element's attribute list, directly below `on:click={handleClick}`:

```svelte
  on:keydown
```

This forwards the DOM event to consumers. It must be on the `<dialog>` itself: a removal prompt focuses the dialog element, and events bubble up — a listener on a child would never see it.

- [ ] **Step 4: Replace the header styles with rail styles**

In the `<style>` block, delete the `.modal-header`, `.modal-header .dialog-title`, `.close-btn`, `.close-btn svg` and `.close-btn:hover` rules, and add:

```css
  /* --bg-header, not --bg-container: the Header and StatusBar wear this plate
     and "bracket the workspace as one piece of chrome" (StatusBar.svelte:168).
     A unit that brackets its own bays the same way reads as a small instance
     of the instrument rather than a card floating over it. */
  .modal-rail {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    height: var(--statusbar-height);
    padding: 0 0.6rem;
    background: var(--bg-header);
    border-bottom: 1px solid var(--border-subtle);
    border-top-left-radius: var(--radius-lg);
    border-top-right-radius: var(--radius-lg);
    flex-shrink: 0;
  }

  .rail-grow {
    flex: 1;
    min-width: 0;
  }

  /* Layout only — the voice stays in app.css. A title carrying a user-supplied
     name has no length limit and would otherwise push the rail's dismiss off
     the plate. */
  .modal-rail .dialog-nameplate {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    flex-shrink: 0;
  }

  /* The dismissal is ambient — it belongs with the unit's identity, not with
     the decision — so it sits here and nowhere else. A real button, drawn as
     the legend it reads as. */
  .modal-escape {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    background: none;
    border: none;
    padding: 0.15rem 0.2rem;
    border-radius: var(--radius-sm);
    cursor: pointer;
    font-family: var(--font-mono);
    font-size: 0.68rem;
    color: var(--text-tertiary);
    opacity: 0.8;
    transition: color var(--transition-fast), opacity var(--transition-fast);
  }
  .modal-escape .k {
    opacity: 0.55;
  }
  .modal-escape:hover {
    color: var(--text-secondary);
    opacity: 1;
  }
  .modal-escape:focus-visible {
    outline: 1px solid var(--text-accent);
    outline-offset: 1px;
  }

  /* The commit rail. Rendered only when a caller fills the slot: a unit that
     ends at its last bay is one you cannot operate, and that absence is the
     signal (Document info relies on it). A caller placing a note instead of a
     commit pushes it left with margin-right: auto. */
  .modal-commit-strip {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 1rem;
    min-height: var(--statusbar-height);
    padding: 0.3rem 0.6rem;
    background: var(--bg-header);
    border-top: 1px solid var(--border-subtle);
    border-bottom-left-radius: var(--radius-lg);
    border-bottom-right-radius: var(--radius-lg);
    flex-shrink: 0;
  }
```

- [ ] **Step 5: Point every caller's title at the new voice and verify**

No caller changes are needed — `title` is still a prop. Run:

```bash
npm run lint:css && npx svelte-check --tsconfig ./tsconfig.json && npx vite build
```

Expected: all clean. Every modal now wears rails; none has a `×`.

- [ ] **Step 6: Verify the × is gone, and note the orphaned voice**

```bash
grep -rn "close-btn\|&times;" src/lib/Modal.svelte && grep -rn "dialog-title" src/lib/ src/app.css
```

Expected: the first grep returns nothing. The second returns only
`src/app.css:676` — `.dialog-title` was used by `Modal.svelte` alone, so the
voice class is now unreferenced.

**Leave it in `app.css`.** It is a documented voice from
`docs/design/2026-08-09-header-voices-design.md`, and deleting a shared voice
is a vocabulary decision, not a side effect of this change. Record it in the
design doc's status note (Task 12, Step 7) so it is decided deliberately.

- [ ] **Step 7: Commit**

```bash
git add src/lib/Modal.svelte && git commit -m "feat(modals): bracket the dialog with rails and name its escape"
```

---

## Task 5: The commit switch component

**Files:**
- Create: `src/lib/CommitSwitch.svelte`

- [ ] **Step 1: Write the component**

Create `src/lib/CommitSwitch.svelte`:

```svelte
<script lang="ts">
  import { chord, commitKeyShortcut } from './keybindings';
  import { commitKeyId } from './confirmKeys';

  export let label: string;
  // Removal (delete, reset) vs activation (re-index). The app's colour law:
  // a mode you switched on is purple and lit; a removal is danger-tinted and
  // deliberately unlit, because a glow marks an activation and a removal is
  // not one.
  export let danger: boolean = false;
  export let disabled: boolean = false;
  export let onClick: () => void = () => {};
  // Marks this as the unit's initial focus target. Modal.svelte queries for
  // [data-autofocus] after showModal(), so it has to be in the markup.
  export let initialFocus: boolean = false;

  // The face carries the key that throws it — the rule the scope bar's bypass
  // already follows. Read from KEYBINDINGS so the glyph has one definition.
  $: face = chord(commitKeyId(danger));

  // aria-keyshortcuts names shortcuts *an author has implemented* (per its
  // spec). A removal prompt's ⌘⌫ is one — ConfirmDialog's own keydown handler
  // implements it. An activation prompt's Enter is not: that is native
  // <button> activation, which answers Space equally, so naming Enter alone
  // would both describe built-in behaviour and imply Enter is special. Omit
  // the attribute there rather than deriving it from confirm.commitSafe —
  // that binding exists only to supply the face glyph, and deriving from it
  // would assert a dependency that does not exist.
  $: ariaKeys = danger ? commitKeyShortcut() : undefined;
</script>

<button
  type="button"
  class="commit-switch"
  class:danger
  class:activation={!danger}
  {disabled}
  data-autofocus={initialFocus || undefined}
  aria-keyshortcuts={ariaKeys}
  on:click={onClick}
>
  <span class="commit-label">{label}</span>
  <!-- A span, not a button: a nested button is illegal, and the face is not
       independently operable — pressing anywhere on the pair fires it. -->
  <span class="switch-face" aria-hidden="true">{face}</span>
</button>
```

There is no `<style>` block: both classes live in `app.css` (Task 3) because the face shares its recipe with `.sm-btn`.

**Only use this where the container implements the key on its face.** The face
asserts that pressing that key fires the control, so a `CommitSwitch` belongs
in a unit's commit rail and nowhere else. A destructive action sitting in a
*bay* — the Danger Zone rows, the game system's Delete and Reset — raises a
prompt rather than committing, and uses `ActionButton kind="confirm" danger`.
See the design's "A face is a promise, and only a commit may make it".

- [ ] **Step 2: Verify it type-checks**

```bash
npx svelte-check --tsconfig ./tsconfig.json
```

Expected: 0 errors.

- [ ] **Step 3: Commit**

```bash
git add src/lib/CommitSwitch.svelte && git commit -m "feat(modals): a commit is a switch wearing the key that throws it"
```

---

## Task 6: The confirm unit

**Files:**
- Modify: `src/lib/ConfirmDialog.svelte`

- [ ] **Step 1: Replace the script block**

Replace the whole `<script lang="ts">` block in `src/lib/ConfirmDialog.svelte` with:

```svelte
<script lang="ts">
  import Modal from './Modal.svelte';
  import CommitSwitch from './CommitSwitch.svelte';
  import { confirmPrompt } from './confirmStore';
  import { isCommitChord } from './confirmKeys';

  // Mounted once at page level; the store decides whether it is on screen and
  // what it asks. See confirmStore.ts for the call-site shape and
  // docs/specs/ui/2026-08-12-modal-rack-units-design.md for the unit.

  const MESSAGE_ID = 'confirm-dialog-message';

  // Esc, the backdrop, and the rail's escape legend all mean the same thing.
  const cancel = () => confirmPrompt.answer(false);
  const accept = () => confirmPrompt.answer(true);

  $: danger = $confirmPrompt?.danger === true;

  // An activation prompt puts focus on its commit, so Enter activates the
  // button natively — there is deliberately no Enter handler here (F1). A
  // removal prompt focuses the dialog itself, leaving Enter inert, and
  // commits on the delete chord instead: the key that raised the deletion is
  // the key that commits it.
  function handleKeydown(e: KeyboardEvent) {
    if (e.isComposing) return;
    if (!$confirmPrompt) return;
    if (!isCommitChord(e, danger)) return;
    // The global handler already bails while a dialog is open
    // (+page.svelte:2127); this stops the browser's own delete handling.
    e.preventDefault();
    accept();
  }
</script>
```

The `inputModality` import and the `viaKeyboard` machinery are **deleted**. They existed to decide whether to paint a ring on an auto-focused Cancel; there is no auto-focused Cancel any more. An activation prompt focuses its commit, which gets a real `:focus-visible` ring from `.commit-switch:focus-visible`; a removal prompt focuses the dialog, which paints nothing by design.

- [ ] **Step 2: Replace the markup**

Replace the `<Modal>…</Modal>` block with:

```svelte
<Modal
  visible={$confirmPrompt !== null}
  onClose={cancel}
  title={$confirmPrompt?.title ?? ''}
  size="sm"
  autofocus={false}
  escapeWord="cancel"
  describedBy={$confirmPrompt?.message ? MESSAGE_ID : undefined}
  on:keydown={handleKeydown}
>
  <div class="modal-bays">
    {#if $confirmPrompt?.rows?.length}
      <div class="modal-bay">
        <div class="modal-well" class:removal={danger} class:activation={!danger}>
          {#each $confirmPrompt.rows as row, i (i)}
            <div class="modal-well-row">
              <span class="ledger-label">{row.label}</span>
              <span class="modal-readout">
                {row.value}{#if row.to}<span class="arrow">→</span><span
                  class="to"
                  class:unchanged={row.unchanged}>{row.to}</span>{/if}
              </span>
            </div>
          {/each}
        </div>
      </div>
    {/if}
    {#if $confirmPrompt?.message}
      <p id={MESSAGE_ID} class="message">{$confirmPrompt.message}</p>
    {/if}
  </div>

  <svelte:fragment slot="commit">
    <CommitSwitch
      label={$confirmPrompt?.confirmLabel ?? 'Confirm'}
      {danger}
      onClick={accept}
      initialFocus={!danger}
    />
  </svelte:fragment>
</Modal>
```

- [ ] **Step 3: Replace the styles**

Replace the whole `<style>` block with:

```svelte
<style>
  /* The prose line, when a caller has one. Rows carry the figures; this
     carries what a figure can't — what the change means. */
  .message {
    margin: 0;
    font-size: 0.9rem;
    color: var(--text-secondary);
    line-height: 1.4;
  }
</style>
```

`.body`, `.actions` and the `.ringed` focus-ring block are all deleted: padding now comes from `.modal-bays`, the buttons from the commit strip, and the ring from `.commit-switch:focus-visible`.

- [ ] **Step 4: Verify**

```bash
npm run lint:css && npx svelte-check --tsconfig ./tsconfig.json && npm test
```

Expected: stylelint clean, 0 svelte-check errors, all tests pass.

- [ ] **Step 5: Confirm the Enter listener really is gone**

```bash
grep -n "Enter" src/lib/ConfirmDialog.svelte
```

Expected: no output. (The only Enter path is the browser activating a focused button.)

- [ ] **Step 6: Commit**

```bash
git add src/lib/ConfirmDialog.svelte && git commit -m "feat(modals): rebuild the confirmation as a rack unit"
```

---

## Task 7: Fill the readouts where the data is in hand

Three of the five call sites hold real figures (Task 10 adds two more when it retires the two-step). Two do not — delete-file and re-index-file have only a `FileItem` (`name`, `path`, `is_dir`, `children`), and `+page.svelte` keeps no path→chunk-count map. Those keep `message` only, which is exactly the optional path Task 2 built.

**Files:**
- Modify: `src/routes/+page.svelte:2978` (delete collection)
- Modify: `src/lib/GameSystemsSettings.svelte:124`, `:141` (delete system, reset)

- [ ] **Step 1: Delete collection**

`collections` is a `Record<string, CollectionInfo>` in scope at `+page.svelte:172`, and `CollectionInfo.file_count` is populated. Replace the request in `requestDeleteCollection`:

```ts
    const info = collections[name];
    const confirmed = await confirmPrompt.request({
      title: 'Delete collection',
      rows: [
        { label: 'Track', value: name },
        ...(info
          ? [
              { label: 'Files', value: String(info.file_count), to: 'Loose', unchanged: true },
            ]
          : []),
      ],
      message: 'The track goes; its books stay in your library.',
      confirmLabel: 'Delete',
      danger: true,
    });
```

- [ ] **Step 2: Delete game system**

In `src/lib/GameSystemsSettings.svelte`, replace the request in the delete handler:

```ts
    const confirmed = await confirmPrompt.request({
      title: 'Delete game system',
      rows: [
        { label: 'Tag', value: editOriginalTag },
        { label: 'Keywords', value: modalKeywords || '—' },
        { label: 'Tagged', value: 'files already tagged', to: 'unchanged', unchanged: true },
      ],
      message: 'You can add the tag again at any time.',
      confirmLabel: 'Delete',
      danger: true,
    });
```

- [ ] **Step 3: Reset to defaults**

Replace the request in the reset handler:

```ts
    const confirmed = await confirmPrompt.request({
      title: 'Reset to defaults',
      rows: [
        { label: 'Tag', value: editOriginalTag },
        { label: 'Keywords', value: modalKeywords || '—', to: 'built-in set' },
      ],
      message: 'Your changes to this system are discarded.',
      confirmLabel: 'Reset',
      danger: true,
    });
```

- [ ] **Step 4: Verify**

```bash
npx svelte-check --tsconfig ./tsconfig.json && npm test
```

Expected: 0 errors, all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/routes/+page.svelte src/lib/GameSystemsSettings.svelte && git commit -m "feat(modals): state the damage as figures where the page knows them"
```

---

## Task 8: Document info as two bays

**Files:**
- Modify: `src/lib/DocumentStatsModal.svelte`

- [ ] **Step 1: Retitle the unit and fill the rail**

Replace the `<Modal …>` opening tag with:

```svelte
<Modal visible={true} {onClose} title="Document" size="md" escapeWord="close">
  <svelte:fragment slot="rail">
    <span class="rail-rule" aria-hidden="true"></span>
    <span class="lamp" class:live={!!stats?.indexed_at} aria-hidden="true"></span>
    <span class="rail-note">{stats?.indexed_at ? 'indexed' : 'not indexed'}</span>
  </svelte:fragment>
```

The filename leaves the title: as a rail nameplate it would truncate at ~48 characters, and as the first readout row it gets the full 560px in the same mono column as everything else about it.

- [ ] **Step 2: Replace the body**

Replace the whole `<div class="body">…</div>` with:

```svelte
  <div class="modal-bays">
    {#if error}
      <p class="error">Could not load stats: {error}</p>
    {:else if !stats}
      <p class="loading">Loading…</p>
    {:else}
      <div class="modal-bay">
        <div class="modal-well">
          <div class="modal-well-row">
            <span class="ledger-label">File</span>
            <span class="modal-readout" title={stats.filename}>{stats.filename}</span>
          </div>
          <div class="modal-well-row">
            <span class="ledger-label">Path</span>
            <span class="modal-readout" title={stats.source}>{stats.source}</span>
          </div>
          <div class="modal-well-row">
            <span class="ledger-label">System</span>
            <span class="modal-readout wrap">{(stats.game_systems && stats.game_systems.length > 0) ? stats.game_systems.join(', ') : displaySystem(stats.game_system || 'unknown')}</span>
          </div>
        </div>
      </div>

      <div class="modal-bay">
        <span class="ledger-label">Index</span>
        <div class="modal-well">
          <div class="modal-well-row">
            <span class="ledger-label">Chunks</span>
            <span class="modal-readout">{stats.chunks.toLocaleString()}</span>
          </div>
          <div class="modal-well-row">
            <span class="ledger-label">Pages</span>
            <span class="modal-readout">{stats.pages > 0 ? stats.pages.toLocaleString() : '—'}</span>
          </div>
          <div class="modal-well-row">
            <span class="ledger-label">Size</span>
            <span class="modal-readout">{formatBytes(stats.file_size_bytes)}</span>
          </div>
          <div class="modal-well-row">
            <span class="ledger-label">Indexed</span>
            <span class="modal-readout">{formatRelative(stats.indexed_at)}<span class="stamp">{indexedAbsolute}</span></span>
          </div>
        </div>
      </div>
    {/if}
  </div>
```

There is **no** `slot="commit"`: nothing here is operable, and the missing rail is the signal.

- [ ] **Step 3: Replace the styles**

Replace the whole `<style>` block with:

```svelte
<style>
  .loading,
  .error {
    color: var(--text-secondary);
    font-size: 0.85rem;
    padding: 0.5rem 0;
    margin: 0;
  }
  .error {
    color: var(--text-danger);
  }

  /* `.rail-rule` is global (Task 3) — three surfaces need it. */

  /* Amber is connectivity in this system, and "live in the index" is exactly
     that. Dark when the file has never been indexed. */
  .lamp {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--text-tertiary);
    opacity: 0.4;
    flex-shrink: 0;
  }
  .lamp.live {
    background: var(--text-connected);
    opacity: 1;
  }

  .rail-note {
    font-family: var(--font-body);
    font-size: 0.75rem;
    color: var(--text-tertiary);
  }

  /* The exact stamp used to exist only as a title attribute — invisible on an
     instrument panel and unreachable by touch or keyboard. The well has room. */
  .stamp {
    color: var(--text-tertiary);
    opacity: 0.8;
    margin-left: 0.5rem;
  }
</style>
```

- [ ] **Step 4: Verify**

```bash
npm run lint:css && npx svelte-check --tsconfig ./tsconfig.json
```

Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add src/lib/DocumentStatsModal.svelte && git commit -m "feat(modals): read a document out of two bays instead of a grid"
```

---

## Task 9: Game system edit as a unit

**Files:**
- Modify: `src/lib/GameSystemsSettings.svelte`

- [ ] **Step 1: Drop the duplicate focus call**

Delete line 41 (the audit recorded it at `:39`; it has drifted two lines):

```ts
  $: if (showModal && tagInput) tagInput.focus();
```

`Modal.svelte`'s text-input heuristic already focuses the same element. Two focus calls racing across a reactive flush is exactly what `[data-autofocus]` exists to avoid.

- [ ] **Step 2: Move the destructive actions into a bay and the commit onto the rail**

Replace the modal's `<div class="body">…</div>` and the `<div class="footer">` inside it with:

```svelte
  <div class="modal-bays">
    <div class="modal-bay">
      <span class="ledger-label">Tag</span>
      <input id="sys-tag" type="text" class="input" bind:value={modalTag} bind:this={tagInput} placeholder="e.g. Cairn" />
    </div>

    <div class="modal-bay">
      <span class="ledger-label">Keywords</span>
      <input id="sys-keywords" type="text" class="input" bind:value={modalKeywords} placeholder="e.g. cairn, cairn rpg" />
      <p class="hint">
        Comma-separated. A folder named &ldquo;<em>{modalTag.trim() || 'Cairn'}</em>&rdquo;
        beats a match found inside the PDF.
      </p>
    </div>

    {#if modalError}
      <div class="error-msg">{modalError}</div>
    {/if}

    {#if modalMode === 'edit' && (editIsBuiltin ? editIsCustomized : true)}
      <div class="modal-bay">
        <div class="modal-well danger-bay">
          <div class="modal-well-row action-row">
            <span class="row-text">
              {editIsBuiltin
                ? 'Discard your changes and restore the built-in keywords.'
                : 'Remove this tag and its keywords. Files already tagged are not changed.'}
            </span>
            {#if editIsBuiltin}
              <ActionButton kind="confirm" danger label="Reset to defaults" onClick={handleReset} />
            {:else}
              <ActionButton kind="confirm" danger label="Delete" onClick={handleDelete} />
            {/if}
          </div>
        </div>
      </div>
    {/if}
  </div>

  <svelte:fragment slot="commit">
    <CommitSwitch
      label={modalMode === 'add' ? 'Add' : 'Save'}
      onClick={handleSave}
      disabled={!canSave}
    />
  </svelte:fragment>
```

Add the import at the top of the script block:

```ts
  import CommitSwitch from './CommitSwitch.svelte';
```

and remove the now-unused `ActionButton` import if nothing else in the file uses it (check with `grep -n "ActionButton" src/lib/GameSystemsSettings.svelte`).

Set `escapeWord="close"` on the `<Modal>` tag.

- [ ] **Step 3: Move the deleted hint into the Reference pane**

The second hint paragraph is reference material — true, useful once, re-read
never. Delete it from the modal and add it to
`src/lib/help/ReferencePane.svelte`, in the existing game-systems section:

```svelte
      <p>
        Keyword matching ignores case, spaces, punctuation, and accents — so
        <em>d&amp;d 5e</em>, <em>dnd-5e</em>, and <em>DnD 5E</em> all match the
        same keyword. Avoid very short keywords such as two-letter
        abbreviations: they false-positive on unrelated paths.
      </p>
```

Match the surrounding markup in that file — if its prose is wrapped in a
different element or class, use that instead of a bare `<p>`.

- [ ] **Step 4: Remove the dead footer styles**

Delete the `.footer`, `.footer-left` and `.footer-right` rules from the
component's `<style>` block. No new rules are needed: `danger-bay`,
`action-row` and `.row-text` are all global (Task 3).

- [ ] **Step 5: Verify**

```bash
npm run lint:css && npx svelte-check --tsconfig ./tsconfig.json && npm test
```

Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/lib/GameSystemsSettings.svelte src/lib/help/ReferencePane.svelte && git commit -m "feat(modals): edit a game system in bays, commit on the rail"
```

---

## Task 10: Settings — tabs on the rail, Danger Zone as a bay

**Files:**
- Modify: `src/lib/SettingsModal.svelte`
- Modify: `src/lib/LibrarySettings.svelte`

- [ ] **Step 1: Move the tabs onto the rail**

In `src/lib/SettingsModal.svelte`, add `escapeWord="close"` to the `<Modal>` tag, move the `<nav class="tab-nav">` block into a `<svelte:fragment slot="rail">`, and change its markup to the segmented well:

```svelte
  <svelte:fragment slot="rail">
    <span class="rail-rule" aria-hidden="true"></span>
    <nav class="seg" aria-label="Settings sections">
      {#each tabs as tab}
        <button
          class="seg-btn"
          class:current={activeTab === tab.id}
          aria-current={activeTab === tab.id ? 'page' : undefined}
          on:click={() => { activeTab = tab.id; }}
        >{tab.label}</button>
      {/each}
    </nav>
  </svelte:fragment>
```

Then replace the Help sub-tab nav — the `<nav class="subtab-nav">` block inside
`{:else if activeTab === 'help'}` — with the same picker, so the two are one
vocabulary rather than two that differ by a pixel of underline:

```svelte
          <nav class="seg subtab-seg" aria-label="Help sections">
            {#each helpSubTabs as sub}
              <button
                class="seg-btn"
                class:current={activeHelpSubTab === sub.id}
                aria-current={activeHelpSubTab === sub.id ? 'page' : undefined}
                on:click={() => { activeHelpSubTab = sub.id; }}
              >{sub.label}</button>
            {/each}
          </nav>
```

- [ ] **Step 2: Add the commit strip note**

Add before `</Modal>`:

```svelte
  <svelte:fragment slot="commit">
    <span class="apply-note">Changes apply immediately</span>
  </svelte:fragment>
```

- [ ] **Step 3: Replace the tab styles**

Delete the `.tab-nav`, `.tab-btn`, `.tab-btn:hover:not(.active)`, `.tab-btn.active`, `.subtab-nav`, `.subtab-btn`, `.subtab-btn:hover:not(.active)` and `.subtab-btn.active` rules. Add:

```css
  /* One picker vocabulary, reusing the header's view switch: a segmented
     control recessed into a darker well, the current segment raised. Never
     purple — it is a position, not a mode. */
  .seg {
    display: flex;
    gap: 2px;
    padding: 2px;
    background: var(--bg-app);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-well);
    flex-shrink: 0;
  }
  .seg-btn {
    display: inline-flex;
    align-items: center;
    height: 20px;
    padding: 0.1rem 0.55rem;
    background: transparent;
    border: none;
    border-radius: var(--radius-sm);
    font-family: var(--font-heading);
    font-size: 0.72rem;
    letter-spacing: 0.03em;
    color: var(--text-tertiary);
    cursor: pointer;
    transition: color var(--transition-fast), background var(--transition-fast);
  }
  .seg-btn:hover:not(.current) {
    color: var(--text-primary);
  }
  .seg-btn.current {
    background: var(--bg-header);
    color: var(--text-primary);
  }
  .seg-btn:focus-visible {
    outline: 1px solid var(--text-accent);
    outline-offset: 1px;
  }

  /* The sub-picker sits inside the pane rather than on the rail, so it needs
     its own top margin. Same size and colours — nesting is the only difference,
     which is what the hierarchy actually is. */
  .seg.subtab-seg {
    align-self: flex-start;
    margin: 0.5rem 1rem 0;
  }

  /* `.rail-rule` is global (Task 3). */

  /* Where a Save button would be. Saying why there isn't one is more useful
     than the button would have been. */
  .apply-note {
    margin-right: auto;
    font-family: var(--font-body);
    font-size: 0.78rem;
    color: var(--text-tertiary);
  }
```

Change the `height` prop on `<Modal>` from `min(520px, 80vh)` to `min(486px, 80vh)` — the tab band's ~34px is bought back by the rail.

- [ ] **Step 4: Retire the arm-then-fire two-step**

**Decision, 2026-08-12:** the design's open decision 1 is now resolved —
one idiom, not two. The Danger Zone rows stop arming in place and raise a
unit like every other destructive action.

What forced it: a review tallied the rows Task 7 actually writes and found
four identity rows, three reassurances, and exactly **one** genuine damage
transition. The design's flagship readout, `CHUNKS 3,412 → 0`, shipped
nowhere — delete-file has no chunk count (`FileItem` carries only
`name`/`path`/`is_dir`/`children`) and delete-index never opened a prompt.
Delete-index is where the figures are real, so that is where the well has
to appear or the feature does not make its own argument.

In `src/lib/LibrarySettings.svelte`, delete the whole arm-then-fire
apparatus at `:62-93` — `confirmingReindex`, `confirmingDelete`,
`cancelReindex`, `cancelDelete`, and the two-branch bodies of
`handleReindexClick` / `handleDeleteClick` — and replace the two handlers
with prompt-raising ones:

```ts
  async function handleReindexClick() {
    if (isSyncing || indexedFileCount === 0) return;
    const files = `${indexedFileCount} ${indexedFileCount === 1 ? 'file' : 'files'}`;
    if (!(await confirmPrompt.request({
      title: 'Re-index all files',
      rows: [
        { label: 'Files', value: files, to: 'reprocessed' },
        { label: 'Chunks', value: totalChunks.toLocaleString(), to: 'rebuilt' },
      ],
      message: 'Every file is re-extracted and re-embedded. Nothing is deleted.',
      confirmLabel: 'Re-index all',
    }))) return;
    onReindexAll();
  }

  async function handleDeleteClick() {
    if (isSyncing || indexedFileCount === 0) return;
    if (!(await confirmPrompt.request({
      title: 'Delete the index',
      rows: [
        { label: 'Files', value: String(indexedFileCount), to: '0' },
        { label: 'Chunks', value: totalChunks.toLocaleString(), to: '0' },
        { label: 'Storage', value: formatSize(storageBytes), to: '0 B' },
        { label: 'PDFs', value: String(indexedFileCount), to: 'untouched', unchanged: true },
      ],
      message: 'Your library folder is not touched. The index rebuilds on the next sync.',
      confirmLabel: 'Delete index',
      danger: true,
    }))) return;
    onDeleteIndex();
  }
```

Note the two differ in `danger`: re-indexing rebuilds and destroys nothing,
so it is an **activation** (purple, lit, Enter commits). Deleting the index
is a **removal** (danger tint, no glow, ⌘⌫ commits). That is the same grading
the design applies everywhere, and it is why re-index keeps no `danger` flag
despite living in the Danger Zone — the zone names the blast radius, the flag
names the kind of change.

`totalChunks`, `storageBytes` and `indexedFileCount` are already props on this
component, and `formatSize` is already defined at `:94`. Add
`import { confirmPrompt } from './confirmStore';`.

Then replace both rows' markup — the `{#if confirmingReindex}` / `{#if confirmingDelete}`
branches collapse to a single control each:

```svelte
        <div class="modal-well-row action-row">
          <span class="row-text">
            <span class="row-title">Re-index all files</span>
            Re-extracts and re-embeds every file in your index. Use after the
            extractor has been upgraded, or if search results look stale.
          </span>
          <ActionButton
            kind="confirm"
            danger
            label={isSyncing ? 'Sync in progress…' : 'Re-index all'}
            onClick={handleReindexClick}
            disabled={isSyncing || indexedFileCount === 0}
          />
        </div>
        <div class="modal-well-row action-row">
          <span class="row-text">
            <span class="row-title">Delete the index</span>
            Removes every chunk and embedding. Your PDFs are untouched; the
            index is rebuilt from scratch on the next sync.
          </span>
          <ActionButton
            kind="confirm"
            danger
            label="Delete index"
            onClick={handleDeleteClick}
            disabled={isSyncing || indexedFileCount === 0}
          />
        </div>
```

Wrap both rows in `<div class="modal-well danger-bay">` inside a
`<div class="modal-bay">` whose `.ledger-label` caption is `Danger zone` in
`--text-danger` at 0.85 opacity. Delete the old `.danger-zone`,
`.danger-title`, `.danger-row`, `.danger-row-text`, `.danger-row-title`,
`.danger-row-desc` and `.danger-row-action` rules.

Then delete the `.btn-danger`, `.btn-danger:hover:not(:disabled)`,
`.btn-danger.armed`, `.btn-danger.armed:hover:not(:disabled)`, `.btn-ghost`
and `.btn-ghost:hover:not(:disabled)` rules. **`.step-back` is no longer
needed either** — there is no armed state to step back out of — so drop it
from Task 3's `app.css` additions if that task has already run, and skip it
if it has not.

Add `import ActionButton from './ActionButton.svelte';` to the script block.

**What is lost, recorded deliberately:** the armed label naming the damage
(*"Reprocess 128 files?"*) was the best confirmation copy in the app. It is
not being thrown away — it becomes the readout rows above, which say the same
thing in more detail and in the app's own tabular-figure idiom. If the prompt
turns out to read worse than the two-step did, that judgement belongs in the
visual pass (Task 12), and reverting is one commit.

- [ ] **Step 5: Verify the old button families are gone**

```bash
grep -rn "btn-danger\|btn-ghost" src/lib/
```

Expected: no output.

- [ ] **Step 6: Verify and commit**

```bash
npm run lint:css && npx svelte-check --tsconfig ./tsconfig.json && npx vite build
```

Expected: clean.

```bash
git add src/lib/SettingsModal.svelte src/lib/LibrarySettings.svelte && git commit -m "feat(modals): hang Settings' pickers on the rail, its danger zone in a bay"
```

---

## Task 11: The panel legend

**Files:**
- Modify: `src/lib/keybindings.ts`
- Modify: `src/lib/keybindings.test.ts`
- Modify: `src/lib/KeyboardHelpOverlay.svelte`

- [ ] **Step 1: Write the failing test**

Append to `src/lib/keybindings.test.ts`:

```ts
describe('switch bindings', () => {
  // A key cap in the legend means "there is a square in the window for this".
  test('marks the keys that light a switch', () => {
    const ids = KEYBINDINGS.filter(k => k.switch).map(k => k.id);
    expect(ids).toContain('tree.solo');
    expect(ids).toContain('tree.mute');
    expect(ids).toContain('collections.play');
    expect(ids).toContain('collections.arm');
    expect(ids).toContain('scope.bypass');
  });

  test('does not mark bare keys with no switch behind them', () => {
    const byId = new Map(KEYBINDINGS.map(k => [k.id, k]));
    expect(byId.get('tree.rename')?.switch).toBeUndefined();
    expect(byId.get('collections.archive')?.switch).toBeUndefined();
  });

  // A modifier chord is a command, not a switch — a cap would lie about it.
  // Note this cannot assert a single character: collections.play is a real
  // switch whose chord reads "P / Space". It renders as text rather than a cap
  // (isBareKeyChord is false for it), which is correct — the flag records what
  // the key does, the renderer decides what that earns.
  test('never marks a modifier chord', () => {
    for (const k of KEYBINDINGS.filter(e => e.switch)) {
      expect(k.keys.mac).not.toMatch(/[⌘⌥⇧⌃]/);
    }
  });
});
```

This file imports `test` (not `it`) from vitest, and already imports
`KEYBINDINGS` and `isBareKeyChord` — no import changes are needed. Match that
style or the suite will fail to resolve `it`.

- [ ] **Step 2: Run it to verify it fails**

```bash
npx vitest run src/lib/keybindings.test.ts
```

Expected: FAIL — `switch` is not a property of `KeybindingEntry`.

- [ ] **Step 3: Add the flag**

In `src/lib/keybindings.ts`, add to `KeybindingEntry` after `match`:

```ts
  // True when this bare key throws a physical switch in the window — an
  // .sm-btn that lights when engaged. The cheat sheet draws those as key
  // caps and everything else as text, because the difference is real:
  // a switch has a square you can point at, a command does not.
  switch?: true;
```

Then add `switch: true` to exactly these entries: `scope.bypass`, `tree.toggleSelect`, `tree.solo`, `tree.mute`, `systems.toggleSelect`, `systems.solo`, `systems.mute`, `collections.play`, `collections.mute`, `collections.arm`, `filterPanel.toggle`, `filterPanel.solo`, `filterPanel.mute`.

Do **not** add it to `tree.rename`, `tree.hide`, `tree.addToCollection`, `systems.rename`, `collections.rename`, `collections.archive` or `help.overlay` — those are bare keys with no switch behind them.

- [ ] **Step 4: Run it to verify it passes**

```bash
npx vitest run src/lib/keybindings.test.ts
```

Expected: PASS.

- [ ] **Step 5: Rebuild the sheet**

In `src/lib/KeyboardHelpOverlay.svelte`, add `escapeWord="close"` to the `<Modal>` tag, and replace the body with:

```svelte
  <div class="legend-body">
    {#each grouped as group (group.scope)}
      <section class="lgroup">
        <span class="ledger-label">{group.label}</span>
        {#each group.entries as entry (entry.id)}
          <div class="lrow">
            <span class="keys">
              {#if isBareKeyChord(entry.id)}
                <span class="keycap" class:switch-key={entry.switch}>{chord(entry.id)}</span>
              {:else}
                <span class="mono">{chord(entry.id)}</span>
              {/if}
            </span>
            <span class="desc">{entry.label}</span>
          </div>
        {/each}
      </section>
    {/each}
  </div>
```

Replace the `<style>` block with:

```svelte
<style>
  .legend-body {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding: var(--modal-pad);
    column-count: 2;
    column-gap: 1.5rem;
    column-rule: 1px solid var(--border-subtle);
  }

  /* Scopes are independent blocks, so multi-column does the whole job — the
     groups flow and stay intact, halving a sheet that ran five screens. */
  .lgroup {
    break-inside: avoid;
    margin: 0 0 1rem;
  }
  .lgroup > .ledger-label {
    display: block;
    margin-bottom: 0.4rem;
  }

  /* Right-aligned against a shared gap: the fixed 9rem column sized itself
     for the longest chord and floated every short one away from its label. */
  .lrow {
    display: grid;
    grid-template-columns: 4.6rem minmax(0, 1fr);
    gap: 0.65rem;
    align-items: center;
    padding: 0.1rem 0;
  }
  .keys {
    display: flex;
    justify-content: flex-end;
    gap: 3px;
    align-items: center;
  }
  .mono {
    font-family: var(--font-mono);
    font-size: 0.76rem;
    color: var(--text-primary);
    white-space: nowrap;
  }
  .desc {
    font-size: 0.82rem;
    color: var(--text-secondary);
    line-height: 1.3;
  }

  /* A cap means "there is a square in the window for this key". The purple
     edge marks the ones that light purple when engaged. */
  .keycap {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 17px;
    height: 17px;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    background: var(--bg-app);
    font-family: var(--font-body);
    font-size: 0.62rem;
    font-weight: 700;
    color: var(--text-primary);
    flex-shrink: 0;
  }
  .keycap.switch-key {
    border-color: color-mix(in srgb, var(--text-active) 40%, transparent);
    color: var(--text-active);
  }
</style>
```

The `.chord-bare` bracket treatment is superseded here: a cap is a stronger frame than brackets and doing both would double the marker. Leave `.chord-bare` in `app.css` — the menus still use it.

- [ ] **Step 6: Verify and commit**

```bash
npm run lint:css && npx svelte-check --tsconfig ./tsconfig.json && npm test
```

```bash
git add src/lib/keybindings.ts src/lib/keybindings.test.ts src/lib/KeyboardHelpOverlay.svelte && git commit -m "feat(modals): draw the shortcut sheet as the panel's legend"
```

---

## Task 12: Verification sweep

**Files:** none — this task only runs checks and records results.

- [ ] **Step 1: Full automated suite**

```bash
npm run lint:css && npx svelte-check --tsconfig ./tsconfig.json && npx vite build && npm test
```

Expected: stylelint clean, 0 svelte-check errors, build succeeds, all tests pass.

- [ ] **Step 2: Grep assertions from the design's Verification section**

```bash
grep -rn "close-btn" src/lib/ ; grep -rn "btn-danger\|btn-ghost" src/lib/ ; grep -rn "ActionButton\|Enter" src/lib/ConfirmDialog.svelte
```

Expected: no output from any of the three.

Note the `×` check is **scoped to the shell**, not repo-wide — `&times;`
legitimately survives in `Header.svelte:177` (the search field's clear) and
`StatusBar.svelte:138` (dismiss a note), neither of which is a modal:

```bash
grep -rn "&times;" src/lib/Modal.svelte
```

Expected: no output.

- [ ] **Step 3: Keyboard pass — run the app and check each prompt nature**

```bash
npm run tauri dev
```

- Activation prompt (context-menu ▸ Re-index on a file): the commit switch has a visible focus ring; **Enter commits**; Esc cancels.
- Removal prompt (⌘⌫ on a file row): **Enter does nothing**; ⌘⌫ commits; Esc cancels; Tab reaches the rail escape, then the commit, then wraps.
- Nested (Settings ▸ Game Systems ▸ edit a custom system ▸ Delete): the prompt opens above the edit unit, which stays visible; ⌘⌫ commits the prompt and does **not** reach the form underneath; cancel returns focus to the button that raised it.

- [ ] **Step 4: Detent pass**

The commit switch's dressing is present from the moment the unit opens, so its
detent fires **once as the dialog appears** rather than on a click — which is
correct, and reads as the switch arriving lit alongside the `modal-in` scale.

Confirm the flash is actually there. If it is missing, the cause is DOM
ancestry, not CSS: `.motion-ready` is set on `<main class="app-layout">`
(`+page.svelte:3435`) and the detent selectors are descendants of it. The top
layer changes paint order, not ancestry, so `<ConfirmDialog />` must stay
inside `<main>` (`:3743`). `KeyboardHelpOverlay` (`:3801`) is already outside
it and needs no detent.

- [ ] **Step 5: Reduced-motion pass**

With System Settings ▸ Accessibility ▸ Reduce motion on, open a removal prompt: the switch shows its danger dressing with **no** detent flash, and the dialog does not scale in.

- [ ] **Step 6: Screen-reader pass (VoiceOver, ⌘F5)**

The unit announces its rail nameplate; rows are read as label/value pairs; the rail escape announces as a button named "Cancel" (confirms) or "Close" (everything else); the commit announces its label and its `aria-keyshortcuts`.

- [ ] **Step 7: Visual pass by the user**

Compare against the mockups: https://claude.ai/code/artifact/d79814d1-f2c7-4b6e-ad6f-e09097d6c498

- [ ] **Step 8: Record the outcome**

Update the design doc's **Status** line to `Implemented <date>`, and append any corrections to what the plan assumed — the audit doc's per-step "what this turned out to be" notes are the format to follow.

```bash
git add docs/specs/ui/2026-08-12-modal-rack-units-design.md && git commit -m "docs(modals): record what the rack-unit build turned out to be"
```

---

## Not in this plan

Carried from the design's [Open decisions](2026-08-12-modal-rack-units-design.md#open-decisions), each needing its own change:

- **Retiring the inline two-step** in favour of prompts everywhere (decision 1). Task 10 restyles the Danger Zone and deliberately leaves arm-then-fire intact.
- **The stacked scrim** — `--scrim-modal-stacked` at ~0.35, set by a class the store applies when another `dialog[open]` exists (decision 2).
- **Delete-file's chunk row**, which needs an `await invoke('get_document_stats')` before the prompt renders (decision 3).
- **Grading confirmations by reversibility** rather than by trigger (the audit's own open decision 1).
