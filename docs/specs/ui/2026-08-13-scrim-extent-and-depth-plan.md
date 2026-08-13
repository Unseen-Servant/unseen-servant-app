# The Scrim: Extent and Depth — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Inset the modal scrim to the workspace so the app's chrome frames the dialog instead of being dimmed by it, dim that chrome one step so it reads inert rather than falsely live, and scrim a stacked dialog lighter so the modal it asks about stays legible.

**Architecture:** One small store (`dialogStack.ts`) counts open dialogs. `Modal.svelte` owns the lifecycle already, so it increments on show and decrements on close *and* on destroy; reading the count before incrementing tells a dialog whether it is stacked. The store is the whole of the logic and is the only unit-testable part — this repo has no jsdom, so everything else is verified by linters, a browser probe, and the manual passes.

**Tech Stack:** Svelte 5.56.8 in legacy (non-runes) mode, TypeScript, Vitest (pure-logic only), stylelint with a raw-colour ban over `src/lib/**/*.svelte`.

**Design:** [2026-08-13-scrim-extent-and-depth-design.md](2026-08-13-scrim-extent-and-depth-design.md)

---

## File structure

| File | Responsibility | Task |
|---|---|---|
| `src/lib/dialogStack.ts` *(new)* | Count open dialogs. Pure, testable. | 1 |
| `src/lib/dialogStack.test.ts` *(new)* | Its tests. | 1 |
| `src/lib/Modal.svelte` | Register/release; mark itself `stacked`. | 2 |
| `src/app.css` | Scrim inset, stacked token, chrome dim. | 3 |
| `src/routes/+page.svelte` | `class:dialog-open` on `<main>`. | 3 |
| — | Backdrop-click probe; settles a design assumption. | 4 |

---

## Task 1: The dialog counter

**Files:**
- Create: `src/lib/dialogStack.ts`
- Create: `src/lib/dialogStack.test.ts`

- [ ] **Step 1: Write the failing tests**

Create `src/lib/dialogStack.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { get } from 'svelte/store';
import { createDialogStack } from './dialogStack';

describe('dialog stack', () => {
  it('starts empty and is not stacked', () => {
    const s = createDialogStack();
    expect(get(s)).toBe(0);
  });

  // The return value is the whole point: a dialog learns whether it is
  // stacked from what was already open when it registered, and CSS has no
  // way to ask that question.
  it('tells the first dialog it is not stacked, and the second that it is', () => {
    const s = createDialogStack();
    expect(s.register()).toBe(false);
    expect(s.register()).toBe(true);
    expect(get(s)).toBe(2);
  });

  it('releases back down', () => {
    const s = createDialogStack();
    s.register();
    s.register();
    s.release();
    expect(get(s)).toBe(1);
    s.release();
    expect(get(s)).toBe(0);
  });

  // Modal releases on close AND on destroy, because DocumentStatsModal is
  // unmounted by {#if statsModalPath} rather than by flipping `visible` —
  // the same asymmetry that leaked focus restoration once before. Both
  // paths can therefore fire for one register, and a double release must
  // not drive the count negative: a negative count would leave
  // `$openDialogs > 0` false with a dialog still open, un-dimming the
  // chrome underneath it.
  it('never goes negative on a double release', () => {
    const s = createDialogStack();
    s.register();
    s.release();
    s.release();
    s.release();
    expect(get(s)).toBe(0);
  });

  it('is idle after a matched register/release cycle', () => {
    const s = createDialogStack();
    s.register();
    s.release();
    expect(get(s)).toBe(0);
    expect(s.register()).toBe(false);
  });
});
```

- [ ] **Step 2: Run to verify they fail**

```bash
npx vitest run src/lib/dialogStack.test.ts
```

Expected: FAIL — `Failed to resolve import "./dialogStack"`.

- [ ] **Step 3: Implement**

Create `src/lib/dialogStack.ts`:

```ts
import { writable } from 'svelte/store';

/**
 * How many modal dialogs are open, and whether a given one is stacked.
 *
 * Two questions need answering that CSS cannot ask. "Is any dialog open?"
 * drives the chrome dim, since the Header and StatusBar stay outside the
 * scrim and must read inert rather than falsely live. "Am I the second
 * dialog?" drives the lighter stacked scrim, so a prompt does not
 * extinguish the modal it is asking about.
 *
 * `:has(dialog[open])` would answer the first and not the second, and this
 * app ships on both WKWebView and WebView2 with no minimum system version
 * pinned — it has already been bitten once assuming ::backdrop behaved
 * uniformly across engines. State is cheap and certain.
 *
 * See docs/specs/ui/2026-08-13-scrim-extent-and-depth-design.md.
 */
export function createDialogStack() {
  const { subscribe, update } = writable(0);

  /** Registers an opening dialog. Returns true if one was already open. */
  function register(): boolean {
    let stacked = false;
    update((n) => {
      stacked = n > 0;
      return n + 1;
    });
    return stacked;
  }

  /**
   * Releases a closing dialog. Floors at zero: Modal releases on both close
   * and destroy, and a dialog unmounted without closing fires both. A
   * negative count would report "no dialogs open" while one still is.
   */
  function release(): void {
    update((n) => (n > 0 ? n - 1 : 0));
  }

  return { subscribe, register, release };
}

export const openDialogs = createDialogStack();
```

- [ ] **Step 4: Run to verify they pass**

```bash
npx vitest run src/lib/dialogStack.test.ts
```

Expected: PASS, 5 tests. Suite total goes 411 → 416.

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(modals): count the open dialogs" -- src/lib/dialogStack.ts src/lib/dialogStack.test.ts
```

---

## Task 2: Modal registers and marks itself

**Files:**
- Modify: `src/lib/Modal.svelte`

- [ ] **Step 1: Import and add state**

Add to the imports:

```ts
  import { openDialogs } from './dialogStack';
```

and beside the other component state:

```ts
  // Set from the count at showModal() time: a dialog that opens while
  // another is already open scrims lighter, so it does not extinguish the
  // modal it is asking about.
  let stacked = false;
  // Guards the release: `visible` and unmount are independent paths into
  // closing, and DocumentStatsModal takes the second one.
  let registered = false;
```

- [ ] **Step 2: Register on show, release on close**

In `sync()`, immediately after `returnTarget = document.activeElement …` and **before** `dialogEl.showModal()`:

```ts
      stacked = openDialogs.register();
      registered = true;
```

Registering before `showModal()` matters: the class must be on the element when the backdrop first paints, or the stacked dialog flashes a full-strength scrim for a frame.

Then in `handleClose()`, before `restoreFocus()`:

```ts
    releaseDialog();
```

- [ ] **Step 3: Release exactly once**

Add beside `restoreFocus`:

```ts
  // Idempotent for the same reason restoreFocus is: `close` and `destroy`
  // are both reachable for one open, and DocumentStatsModal exercises the
  // destroy path because {#if statsModalPath} unmounts it outright.
  function releaseDialog() {
    if (!registered) return;
    registered = false;
    openDialogs.release();
  }
```

and extend the existing `onDestroy`:

```ts
  onDestroy(() => {
    releaseDialog();
    restoreFocus();
  });
```

- [ ] **Step 4: Put the class on the dialog**

Add to the `<dialog>` element's attribute list, after `class="modal"`:

```svelte
  class:stacked
```

- [ ] **Step 5: Verify**

```bash
npm run lint:css && npx svelte-check --tsconfig ./tsconfig.json && npx vitest run && npm run build
```

Expected: all clean, 416 tests.

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(modals): let a dialog know it opened on top of another" -- src/lib/Modal.svelte
```

---

## Task 3: The scrim and the chrome

**Files:**
- Modify: `src/app.css`
- Modify: `src/routes/+page.svelte`

- [ ] **Step 1: Add the stacked token**

In `src/app.css`, extend the existing declaration — do **not** start a second one. Whether `::backdrop` inherits custom properties is engine-dependent, and an unresolved `var()` yields no background at all, which is a missing scrim rather than a fallback one:

```css
:root,
dialog::backdrop {
  --scrim-modal: rgba(0, 0, 0, 0.6);
  --scrim-modal-stacked: rgba(0, 0, 0, 0.35);
}
```

- [ ] **Step 2: Inset the scrim and lighten it when stacked**

Replace the existing `dialog::backdrop { background: … }` rule with:

```css
/* The scrim covers the workspace, not the frame. A rack unit wears
   --bg-header rails so it reads as part of the instrument; dimming the
   instrument it quotes undercuts that, and the StatusBar's lamps and sync
   spinner sometimes answer the very question the prompt is asking. The
   heights are the same tokens that size the two bars, so the edges cannot
   drift apart. */
dialog::backdrop {
  background: var(--scrim-modal);
  top: var(--header-height);
  bottom: var(--statusbar-height);
}

/* A second dialog's backdrop sits *between* the two dialogs, so at full
   strength a prompt darkens the modal it is asking about by 60%. Lighter
   keeps that modal legible as context while still reading as inactive. */
dialog.stacked::backdrop {
  background: var(--scrim-modal-stacked);
}
```

- [ ] **Step 3: Dim the chrome**

Append near the scrim rules:

```css
/* The frame stays outside the scrim, so it must say for itself that it is
   not available: the page behind an open dialog is inert, and a bright
   Header whose buttons do nothing is a false affordance — a click there
   does not even dismiss the dialog. This is the app's existing step for
   "present but not available", the one the scope bar's bypass uses on the
   principle that the point of a bypass is to see what you are bypassing. */
.app-layout.dialog-open > .header,
.app-layout.dialog-open > .statusbar {
  opacity: var(--opacity-out-of-scope);
  transition: opacity var(--transition-fast);
}
```

Confirm the child selectors match the real markup — `Header` and `StatusBar` are components, so check what element and class each renders as its root and adjust rather than assuming `> .header` matches.

- [ ] **Step 4: Drive the class**

In `src/routes/+page.svelte`, add the import:

```ts
  import { openDialogs } from '../lib/dialogStack';
```

and extend the existing `<main>` tag:

```svelte
<main class="app-layout" class:motion-ready={motionReady} class:dialog-open={$openDialogs > 0}>
```

- [ ] **Step 5: Verify**

```bash
npm run lint:css && npx svelte-check --tsconfig ./tsconfig.json && npx vitest run && npm run build
```

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(modals): scrim the workspace, frame it with the instrument" -- src/app.css src/routes/+page.svelte
```

---

## Task 4: Settle the backdrop-click question

The design records an assumption rather than resting on it: it is **unverified** whether clicking outside a modal dismisses it today. `handleClick` tests `e.target === dialogEl`, but that fires on the dialog's own border/padding box — `::backdrop` is a pseudo-element and receives no events. The prior audit listed "the backdrop" as a dismissal route without testing it.

This matters now because insetting the scrim changes which region is visually "outside".

**Files:** none committed — this task produces an answer, not code.

- [ ] **Step 1: Build a probe**

The browser pane will not execute scripts on files outside the project, but `build/` is gitignored *and* inside it. Write `build/backdrop-probe.html` containing a `<dialog>` opened with `showModal()`, styled with the same inset backdrop, and a click listener logging `e.target` identity for clicks in three regions: on the dialog, in the scrimmed workspace area outside it, and in the un-scrimmed chrome strip.

- [ ] **Step 2: Measure**

Load it in the browser pane and click each region. Record for each: does a `click` event reach the dialog, and does `e.target === dialogEl`?

- [ ] **Step 3: Delete the probe and report**

Remove `build/backdrop-probe.html`. Report the three results plainly.

- [ ] **Step 4: Record the answer**

Update the design's Risks section with what was measured. Three outcomes and what each means:
- **Clicks outside never reach the dialog** — backdrop dismissal has never worked; the audit's claim was wrong. Say so in the design; do not add it now (that is a separate decision about whether the app wants it).
- **Clicks outside reach it in both regions** — dismissal works, and the chrome strip now dismisses too, which is wrong: that strip is *outside* the scrim and should not read as backdrop. Restrict `handleClick`.
- **Clicks reach it only in the scrimmed region** — the behaviour is already correct and the inset improved it. Record and move on.

```bash
git commit -m "docs(modals): settle whether the backdrop ever dismissed" -- docs/specs/ui/2026-08-13-scrim-extent-and-depth-design.md
```

---

## Task 5: Verification sweep

- [ ] **Step 1: Automated**

```bash
npm run lint:css && npx svelte-check --tsconfig ./tsconfig.json && npx vitest run && npm run build
```

Expected: clean, 416 tests across 23 files.

- [ ] **Step 2: Manual passes** — these need the app and are the user's to run.

- Open any modal: Header and StatusBar visible at one dim step, workspace scrimmed, modal reads as inside the frame. A lit sidecar lamp and a running sync spinner stay legible.
- Settings ▸ Library ▸ Delete index: the Settings modal behind the prompt stays readable, and the chrome does not double-dim.
- **Open Document info, then close it. The chrome must un-dim.** This is the failure mode the store is tested for — that modal unmounts rather than closing, and a leaked count leaves the app permanently dimmed.
- Esc and the rail's escape legend still dismiss.
