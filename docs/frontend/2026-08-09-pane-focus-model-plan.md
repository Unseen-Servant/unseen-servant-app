# Pane focus model — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the filter panel a keyboard peer of the file tree and collections panel — reachable, navigable, and exitable — by adopting the focus-token pattern those two already share.

**Architecture:** A third mutually-exclusive focus token (`focusedFilterRow`) in `+page.svelte` joins the existing two. `FilterPanel` swaps its integer-index-into-a-DOM-query row model for a pure `computeFilterRows()` producing stable string keys, moves from an element-scoped handler to a window-level one gated on the token, and gains a `claim()` method. New `⌘⌥↑`/`⌘⌥↓` chords navigate within the left dock.

**Tech Stack:** SvelteKit 2 + TypeScript, vitest, svelte-check, stylelint.

**Spec:** `docs/frontend/2026-08-09-pane-focus-model-design.md`

**Testing reality:** Task 1 is a pure module with full TDD. Tasks 2–7 are component and page wiring, and this repo has **no component test harness** — every existing test is a `.ts` unit test. Those tasks are gated on `npm run check`, the unit suite, `npm run lint:css`, and the manual QA checklist in Task 8. Do not scaffold a component test harness.

**Commit convention:** every commit below is path-scoped (`git commit <paths>`). Other sessions commit to `main` concurrently and leave unrelated files staged; a bare `git commit` would sweep them in. Run `git status --short` before each commit.

---

## File structure

| File | Responsibility | Change |
|---|---|---|
| `src/lib/filterRows.ts` | Pure row model: which rows are navigable, in what order, under what keys | **Create** |
| `src/lib/filterRows.test.ts` | Unit tests for the above | **Create** |
| `src/routes/+page.svelte` | Owns all three focus tokens and the arbiter; owns the dock chords | Modify |
| `src/lib/FilterPanel.svelte` | Renders rows from the model; window-level handler; `claim()` | Modify |
| `src/lib/keybindings.ts` | Registry: scope rename, new chords | Modify |
| `src/lib/KeyboardHelpOverlay.svelte` | `?` overlay scope list | Modify |
| `src/lib/help/ReferencePane.svelte` | Help pane scope list | Modify |

---

### Task 1: The pure row model

**Files:**
- Create: `src/lib/filterRows.ts`
- Create: `src/lib/filterRows.test.ts`

- [ ] **Step 1: Write the failing test**

Create `src/lib/filterRows.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { computeFilterRows, stepFilterRow, type FilterRowsInput } from './filterRows';

function input(over: Partial<FilterRowsInput> = {}): FilterRowsInput {
  return {
    hasHidden: false,
    showCollectionFilter: false,
    showSystemFilter: false,
    systems: [],
    untaggedCount: 0,
    ...over,
  };
}

describe('computeFilterRows', () => {
  it('always offers the two unconditional view rows', () => {
    expect(computeFilterRows(input()).map(r => r.key)).toEqual([
      'view:hideUnindexed',
      'view:hideOutOfScope',
    ]);
  });

  it('omits view:showHidden when nothing is hidden', () => {
    expect(computeFilterRows(input()).map(r => r.key)).not.toContain('view:showHidden');
  });

  it('includes view:showHidden when something is hidden', () => {
    expect(computeFilterRows(input({ hasHidden: true })).map(r => r.key)).toContain('view:showHidden');
  });

  it('omits curation rows when the section is hidden', () => {
    expect(computeFilterRows(input()).map(r => r.key)).not.toContain('curation:collected');
  });

  it('includes both curation rows when the section shows', () => {
    const keys = computeFilterRows(input({ showCollectionFilter: true })).map(r => r.key);
    expect(keys).toContain('curation:collected');
    expect(keys).toContain('curation:loose');
  });

  it('omits system rows when the section is hidden', () => {
    const keys = computeFilterRows(input({ systems: [{ name: 'D&D', count: 3 }] })).map(r => r.key);
    expect(keys).not.toContain('system:D&D');
  });

  it('includes one row per system when the section shows', () => {
    const keys = computeFilterRows(input({
      showSystemFilter: true,
      systems: [{ name: 'D&D', count: 3 }, { name: 'CoC', count: 1 }],
    })).map(r => r.key);
    expect(keys).toContain('system:D&D');
    expect(keys).toContain('system:CoC');
  });

  it('omits the untagged bucket when its count is zero', () => {
    const keys = computeFilterRows(input({ showSystemFilter: true })).map(r => r.key);
    expect(keys).not.toContain('system:unknown');
  });

  it('includes the untagged bucket when its count is positive', () => {
    const keys = computeFilterRows(input({ showSystemFilter: true, untaggedCount: 4 })).map(r => r.key);
    expect(keys).toContain('system:unknown');
  });

  it('orders rows Curation then Systems then View, matching the rendered panel', () => {
    const keys = computeFilterRows(input({
      hasHidden: true,
      showCollectionFilter: true,
      showSystemFilter: true,
      systems: [{ name: 'D&D', count: 3 }],
      untaggedCount: 2,
    })).map(r => r.key);
    expect(keys).toEqual([
      'curation:collected',
      'curation:loose',
      'system:D&D',
      'system:unknown',
      'view:showHidden',
      'view:hideUnindexed',
      'view:hideOutOfScope',
    ]);
  });

  it('keeps a row key stable when another system is added — the case an index got wrong', () => {
    const before = computeFilterRows(input({ showSystemFilter: true, systems: [{ name: 'D&D', count: 3 }] }));
    const after = computeFilterRows(input({
      showSystemFilter: true,
      systems: [{ name: 'CoC', count: 1 }, { name: 'D&D', count: 3 }],
    }));
    expect(before.find(r => r.key === 'system:D&D')).toBeDefined();
    expect(after.find(r => r.key === 'system:D&D')).toBeDefined();
    // The index moved; the key did not.
    expect(before.findIndex(r => r.key === 'system:D&D'))
      .not.toBe(after.findIndex(r => r.key === 'system:D&D'));
  });
});

describe('stepFilterRow', () => {
  const rows = computeFilterRows(input({ hasHidden: true }));
  // rows: view:showHidden, view:hideUnindexed, view:hideOutOfScope

  it('returns null for an empty row list', () => {
    expect(stepFilterRow([], null, 1)).toBeNull();
  });

  it('enters at the first row when moving down from nothing', () => {
    expect(stepFilterRow(rows, null, 1)).toBe('view:showHidden');
  });

  it('enters at the last row when moving up from nothing', () => {
    expect(stepFilterRow(rows, null, -1)).toBe('view:hideOutOfScope');
  });

  it('moves down one row', () => {
    expect(stepFilterRow(rows, 'view:showHidden', 1)).toBe('view:hideUnindexed');
  });

  it('moves up one row', () => {
    expect(stepFilterRow(rows, 'view:hideUnindexed', -1)).toBe('view:showHidden');
  });

  it('clamps at the bottom rather than wrapping', () => {
    expect(stepFilterRow(rows, 'view:hideOutOfScope', 1)).toBe('view:hideOutOfScope');
  });

  it('clamps at the top rather than wrapping', () => {
    expect(stepFilterRow(rows, 'view:showHidden', -1)).toBe('view:showHidden');
  });

  it('recovers to an end row when the current key is stale', () => {
    expect(stepFilterRow(rows, 'system:vanished', 1)).toBe('view:showHidden');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
npx vitest run src/lib/filterRows.test.ts
```

Expected: FAIL — cannot resolve `./filterRows`.

- [ ] **Step 3: Write minimal implementation**

Create `src/lib/filterRows.ts`:

```ts
// Which filter-console rows the keyboard can land on, in rendered order.
//
// Replaces an integer index into a live querySelectorAll('[data-fm]'): the
// systems list grows as files are indexed and whole sections appear and
// disappear with view mode, so an index means a different row from one
// render to the next. Keys are stable; indices are not.
//
// Order here IS the j/k navigation order, so it must track the template.
// The panel renders Curation, then Game systems, then the Hidden-items
// view switches (moved to the bottom in c4f4f81).

import { UNTAGGED_KEY } from './searchScope';

export type FilterRowKind = 'view' | 'curation' | 'system';

export interface FilterRow {
  key: string;
  kind: FilterRowKind;
}

export interface FilterRowsInput {
  /** Something is hidden, so the "Show hidden items" row is enabled. A
   *  disabled row never takes the cursor. */
  hasHidden: boolean;
  showCollectionFilter: boolean;
  showSystemFilter: boolean;
  systems: { name: string; count: number }[];
  /** The untagged channel renders only when this is positive. */
  untaggedCount: number;
}

export function computeFilterRows(input: FilterRowsInput): FilterRow[] {
  const rows: FilterRow[] = [];

  if (input.showCollectionFilter) {
    rows.push({ key: 'curation:collected', kind: 'curation' });
    rows.push({ key: 'curation:loose', kind: 'curation' });
  }

  if (input.showSystemFilter) {
    for (const s of input.systems) rows.push({ key: `system:${s.name}`, kind: 'system' });
    if (input.untaggedCount > 0) rows.push({ key: `system:${UNTAGGED_KEY}`, kind: 'system' });
  }

  if (input.hasHidden) rows.push({ key: 'view:showHidden', kind: 'view' });
  rows.push({ key: 'view:hideUnindexed', kind: 'view' });
  rows.push({ key: 'view:hideOutOfScope', kind: 'view' });

  return rows;
}

/** Move the cursor one row. Clamps rather than wrapping, matching the tree
 *  and collections panels. A stale key (its row vanished under the cursor)
 *  re-enters from the end the user was heading toward. */
export function stepFilterRow(
  rows: FilterRow[],
  current: string | null,
  delta: 1 | -1,
): string | null {
  if (rows.length === 0) return null;
  const idx = rows.findIndex((r) => r.key === current);
  if (idx < 0) return delta === 1 ? rows[0].key : rows[rows.length - 1].key;
  return rows[Math.min(rows.length - 1, Math.max(0, idx + delta))].key;
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
npx vitest run src/lib/filterRows.test.ts
```

Expected: PASS — 19 tests.

- [ ] **Step 5: Commit**

```bash
git add src/lib/filterRows.ts src/lib/filterRows.test.ts && git commit src/lib/filterRows.ts src/lib/filterRows.test.ts -m "feat(keys): add the filter-console row model"
```

---

### Task 2: The third focus token

**Files:**
- Modify: `src/routes/+page.svelte:70-86` (tokens, arbiter, memory)

- [ ] **Step 1: Add the token and extend the arbiter**

Lines 70–86 currently read:

```ts
  let focusedCollectionName: string | null = null;

  function setFocusedFilePath(path: string | null) {
    focusedFilePath = path;
    if (path) focusedCollectionName = null;
  }
  function setFocusedCollectionName(name: string | null) {
    focusedCollectionName = name;
    if (name) focusedFilePath = null;
  }
  // Remember the last non-null focus on each side so Cmd+Alt+←/→ can
  // restore the user to where they were instead of always landing on
  // row 0 of the target region.
  let lastFocusedFilePath: string | null = null;
  let lastFocusedCollectionName: string | null = null;
  $: if (focusedFilePath !== null) lastFocusedFilePath = focusedFilePath;
  $: if (focusedCollectionName !== null) lastFocusedCollectionName = focusedCollectionName;
```

Replace with:

```ts
  let focusedCollectionName: string | null = null;
  // Third pane: the filter console. Holds a filterRows key, not an index.
  let focusedFilterRow: string | null = null;

  function setFocusedFilePath(path: string | null) {
    focusedFilePath = path;
    if (path) { focusedCollectionName = null; focusedFilterRow = null; }
  }
  function setFocusedCollectionName(name: string | null) {
    focusedCollectionName = name;
    if (name) { focusedFilePath = null; focusedFilterRow = null; }
  }
  function setFocusedFilterRow(key: string | null) {
    focusedFilterRow = key;
    if (key) { focusedFilePath = null; focusedCollectionName = null; }
  }
  // Remember the last non-null focus in each pane so Cmd+Alt+←/→/↑/↓ can
  // restore the user to where they were instead of always landing on
  // row 0 of the target region.
  let lastFocusedFilePath: string | null = null;
  let lastFocusedCollectionName: string | null = null;
  let lastFocusedFilterRow: string | null = null;
  $: if (focusedFilePath !== null) lastFocusedFilePath = focusedFilePath;
  $: if (focusedCollectionName !== null) lastFocusedCollectionName = focusedCollectionName;
  $: if (focusedFilterRow !== null) lastFocusedFilterRow = focusedFilterRow;
  // Which of the dock's two panels the user was last in, so Cmd+Alt+←
  // returns there rather than always landing on Collections.
  let lastFocusedDockPane: 'collections' | 'filters' = 'collections';
  $: if (focusedCollectionName !== null) lastFocusedDockPane = 'collections';
  $: if (focusedFilterRow !== null) lastFocusedDockPane = 'filters';
```

- [ ] **Step 2: Verify types**

```bash
npm run check
```

Expected: 0 errors. `setFocusedFilterRow` and `lastFocusedFilterRow` are unused until Task 3 — that is expected and svelte-check does not flag it.

- [ ] **Step 3: Commit**

```bash
git add src/routes/+page.svelte && git commit src/routes/+page.svelte -m "feat(keys): add the filter pane's focus token to the arbiter"
```

---

### Task 3: FilterPanel adopts the pane pattern

The core task. It replaces the row model, the handler, and the focus
plumbing together, because splitting them leaves the panel keyboard-dead
in between.

**Files:**
- Modify: `src/lib/FilterPanel.svelte` — imports (line 9), props, lines 79–171 (all focus machinery), row templates, CSS at lines 427 and 524

- [ ] **Step 1: Fix the imports**

Line 9 currently:

```ts
  import { afterUpdate, onDestroy, onMount, tick } from 'svelte';
```

Replace with (only `afterUpdate` survives — it will scroll the cursor into view):

```ts
  import { afterUpdate } from 'svelte';
  import { computeFilterRows, stepFilterRow } from './filterRows';
```

- [ ] **Step 2: Add the two new props**

After the `onToggleHideUnindexed` prop, add:

```ts
  // Pane focus, owned by +page.svelte and mutually exclusive with the tree
  // and collections tokens. null means this pane does not hold the keyboard,
  // and no cursor is drawn.
  export let focusedRow: string | null = null;
  export let onFocusRow: (key: string | null) => void = () => {};
```

- [ ] **Step 3: Replace all focus machinery**

Delete lines 79–171 entirely — `panelEl`/`focusedIdx`/`rowEls`,
`previouslyFocused`, the `onMount` self-focus, the `onDestroy` restore,
`refreshRowsAndFocus`, `afterUpdate(refreshRowsAndFocus)`, and
`handleKey`. Replace with:

```ts
  let panelEl: HTMLElement;

  // The navigable row set, derived not queried. Order is the j/k order.
  $: rows = computeFilterRows({
    hasHidden,
    showCollectionFilter,
    showSystemFilter,
    systems,
    untaggedCount,
  });

  function rowElByKey(key: string): HTMLElement | null {
    return panelEl?.querySelector<HTMLElement>(`[data-fm-key="${CSS.escape(key)}"]`) ?? null;
  }

  // The panel body scrolls, and the cursor no longer moves DOM focus, so
  // nothing scrolls it into view for us any more.
  let lastScrolled: string | null = null;
  afterUpdate(() => {
    if (!focusedRow) { lastScrolled = null; return; }
    if (focusedRow === lastScrolled) return;
    lastScrolled = focusedRow;
    rowElByKey(focusedRow)?.scrollIntoView({ block: 'nearest' });
  });

  /** Claim the pane, restoring `preferred` when that row still exists. */
  export function claim(preferred: string | null) {
    if (rows.length === 0) return;
    const target = preferred && rows.some((r) => r.key === preferred) ? preferred : rows[0].key;
    onFocusRow(target);
  }

  // Window-level, gated on the token — the same shape CollectionsPanel uses,
  // so exactly one pane responds to a keystroke.
  function handleWindowKey(event: KeyboardEvent) {
    if (focusedRow === null) return;
    if (event.isComposing) return;
    // Yield to popovers and modals that own the keyboard while open.
    if (document.querySelector('.sort-menu, .dropdown, .context-menu')) return;
    if (document.querySelector('dialog[open]')) return;
    const target = event.target as HTMLElement | null;
    if (target?.matches('input, textarea, [contenteditable="true"]')) return;

    const meta = event.metaKey || event.ctrlKey;
    const lk = event.key.toLowerCase();
    const bareLetter = !meta && !event.shiftKey && !event.altKey;
    const isDown = event.key === 'ArrowDown' || (bareLetter && lk === 'j');
    const isUp   = event.key === 'ArrowUp'   || (bareLetter && lk === 'k');

    if (event.key === 'Escape') {
      // Release the pane. Not a close — the panel is docked furniture whose
      // open state is persisted, and the header toggle is its close
      // affordance. Matches CollectionsPanel's onFocusCollection(null).
      event.preventDefault();
      onFocusRow(null);
      return;
    }
    if (isDown) {
      event.preventDefault();
      onFocusRow(stepFilterRow(rows, focusedRow, 1));
      return;
    }
    if (isUp) {
      event.preventDefault();
      onFocusRow(stepFilterRow(rows, focusedRow, -1));
      return;
    }
    if (event.key === 'Home' && !meta && rows.length > 0) {
      event.preventDefault();
      onFocusRow(rows[0].key);
      return;
    }
    if (event.key === 'End' && !meta && rows.length > 0) {
      event.preventDefault();
      onFocusRow(rows[rows.length - 1].key);
      return;
    }
    if (event.key === ' ' || event.key === 'Enter') {
      // A channel row's default action is its M toggle. A view row has no
      // M — its own control is the only button, so click that.
      event.preventDefault();
      const el = rowElByKey(focusedRow);
      const m = el?.querySelector<HTMLElement>('[data-sm-m]');
      (m ?? el?.querySelector<HTMLElement>('[data-fm-action]'))?.click();
      return;
    }
    if (bareLetter && (lk === 's' || lk === 'm')) {
      event.preventDefault();
      rowElByKey(focusedRow)
        ?.querySelector<HTMLElement>(lk === 's' ? '[data-sm-s]' : '[data-sm-m]')
        ?.click();
    }
  }

  $: hasHidden = hiddenCount > 0;
  $: curationRows = [
    { key: 'collected' as CurationKey, name: 'In a collection', count: collectedCount },
    { key: 'loose' as CurationKey, name: 'Loose', count: uncollectedCount },
  ];
```

- [ ] **Step 4: Add the window listener and drop the element handler**

The `<aside>` currently reads:

```svelte
<aside
  class="filter-panel"
  bind:this={panelEl}
  on:keydown={handleKey}
  tabindex="-1"
>
```

Replace with (the panel no longer takes focus, so `tabindex` goes too):

```svelte
<svelte:window on:keydown={handleWindowKey} />

<aside class="filter-panel" bind:this={panelEl}>
```

Leave the `<!-- svelte-ignore a11y-no-noninteractive-element-interactions -->`
comment above it in place only if svelte-check still requires it; if
`npm run check` reports it as unused, delete the comment.

- [ ] **Step 5: Key the curation rows**

On the curation `<div class="row channel-row" …>`, replace
`data-fm="row"` with:

```svelte
          data-fm-key="curation:{ch.key}"
          class:kb-focused={focusedRow === `curation:${ch.key}`}
```

- [ ] **Step 6: Key the system rows**

On the systems `<div class="row channel-row" …>`, replace
`data-fm="row"` with:

```svelte
            data-fm-key="system:{name}"
            class:kb-focused={focusedRow === `system:${name}`}
```

On the untagged `<div class="row channel-row untagged-row" …>`, replace
`data-fm="row"` with:

```svelte
            data-fm-key="system:{UNTAGGED_KEY}"
            class:kb-focused={focusedRow === `system:${UNTAGGED_KEY}`}
```

- [ ] **Step 7: Make the cursor class scoped**

`.kb-focused` was applied imperatively via `classList.toggle`, so its CSS
needed `:global()`. It is now a Svelte class directive and is scoped, so
both selectors must drop the wrapper.

Line 427 currently:

```css
  .row:hover,
  .row:global(.kb-focused) {
```

becomes:

```css
  .row:hover,
  .row.kb-focused {
```

Line 524 currently:

```css
  .row:global(.kb-focused) .sm,
```

becomes:

```css
  .row.kb-focused .sm,
```

- [ ] **Step 8: Drop the dead container-focus rule**

Lines 386–393 style the container's focus ring, which no longer exists:

```css
  /* The panel holds programmatic focus so the keyboard model works the
     moment it opens. Per-row keyboard cursor is already drawn via
     `.kb-focused` on individual rows — a focus ring on the container
     itself would be redundant noise. */
  .filter-panel:focus,
  .filter-panel:focus-visible {
    outline: none;
  }
```

Delete that whole block.

- [ ] **Step 9: Verify**

```bash
npm run check && npm test && npm run lint:css
```

Expected: 0 errors, all tests pass, stylelint clean. The three view rows
are not keyed yet — Task 4 converts them — so they are temporarily
unreachable by keyboard. That is expected between these two tasks.

- [ ] **Step 10: Commit**

```bash
git add src/lib/FilterPanel.svelte && git commit src/lib/FilterPanel.svelte -m "refactor(console): drive filter-panel focus from a pane token"
```

---

### Task 4: The view rows become `role="checkbox"`

**Files:**
- Modify: `src/lib/FilterPanel.svelte` — the three Hidden-items rows

Under a window-level handler, a `<label><input type="checkbox">` row gives
Space two competing activation paths and makes the `input, textarea`
yield-guard ambiguous on the panel's own rows. Converting matches both the
panel's channel rows and the pattern `app.css` documents at `.app-checkbox`.

- [ ] **Step 1: Convert "Show hidden items"**

Replace the whole `<label class="row" class:row-disabled={!hasHidden} …>`
block with:

```svelte
    <div
      class="row"
      class:row-disabled={!hasHidden}
      class:kb-focused={focusedRow === 'view:showHidden'}
      title={hasHidden ? 'Reveal hidden files and folders in the tree' : 'Right-click any file or folder to hide it'}
      data-fm-key="view:showHidden"
    >
      <span class="row-name muted-name">Show hidden items</span>
      <span class="row-count">{hiddenCount}</span>
      <button
        type="button"
        class="app-checkbox"
        role="checkbox"
        aria-checked={showHidden}
        aria-label="Show hidden items"
        disabled={!hasHidden}
        data-fm-action
        on:click|stopPropagation={onToggleShowHidden}
      ></button>
    </div>
```

- [ ] **Step 2: Convert "Hide unindexed items"**

```svelte
    <div
      class="row lens-row"
      class:kb-focused={focusedRow === 'view:hideUnindexed'}
      title="Hide files and folders the library knows nothing about — not indexed, not selected for indexing"
      data-fm-key="view:hideUnindexed"
    >
      <span class="row-name muted-name">Hide unindexed items</span>
      <button
        type="button"
        class="app-checkbox lens-checkbox"
        role="checkbox"
        aria-checked={hideUnindexed}
        aria-label="Hide unindexed items"
        data-fm-action
        on:click|stopPropagation={onToggleHideUnindexed}
      ></button>
    </div>
```

- [ ] **Step 3: Convert "Hide out-of-scope items"**

```svelte
    <div
      class="row lens-row"
      class:kb-focused={focusedRow === 'view:hideOutOfScope'}
      title="Hide dimmed out-of-scope rows in the tree and systems view"
      data-fm-key="view:hideOutOfScope"
    >
      <span class="row-name muted-name">Hide out-of-scope items</span>
      <button
        type="button"
        class="app-checkbox lens-checkbox"
        role="checkbox"
        aria-checked={hideOutOfScope}
        aria-label="Hide out-of-scope items"
        data-fm-action
        on:click|stopPropagation={onToggleHideOutOfScope}
      ></button>
    </div>
```

- [ ] **Step 4: Remove the now-dead label cursor rule**

`label.row { cursor: pointer; }` (around line 430) has no `label.row` left
to match. Delete it.

- [ ] **Step 5: Verify**

```bash
npm run check && npm run lint:css
```

Expected: clean. `.app-checkbox[aria-checked="true"]` already exists in
`src/app.css`, so the checked state styles itself with no CSS change.

- [ ] **Step 6: Commit**

```bash
git add src/lib/FilterPanel.svelte && git commit src/lib/FilterPanel.svelte -m "refactor(console): view rows become role=checkbox buttons"
```

**Deliberate consequence:** clicking the row background no longer toggles
the switch — the checkbox itself is the click target, exactly as the S/M
channel rows already behave. This makes every row in the panel consistent.
If the smaller mouse target proves annoying, adding a row-level click back
is a two-line change, but it would reintroduce the double-activation
hazard on Space unless the handler is adjusted with it.

---

### Task 5: Wire the panel to the page

**Files:**
- Modify: `src/routes/+page.svelte` — a component binding, two props on `<FilterPanel>`

- [ ] **Step 1: Add the component binding**

Beside `let collectionsPanelComponent: CollectionsPanel | undefined;`
(line 243), add:

```ts
  let filterPanelComponent: FilterPanel | undefined;
```

- [ ] **Step 2: Pass the binding and the two props**

On the `<FilterPanel>` element, add `bind:this` as the first attribute and
the focus props after `onClearAll`:

```svelte
            <FilterPanel
              bind:this={filterPanelComponent}
```

```svelte
              onClearAll={clearAllFilters}
              focusedRow={focusedFilterRow}
              onFocusRow={setFocusedFilterRow}
            />
```

- [ ] **Step 3: Verify**

```bash
npm run check && npm test
```

Expected: 0 errors, 213+ tests pass. The panel is now navigable once
something claims it — Task 6 adds the chord that does.

- [ ] **Step 4: Commit**

```bash
git add src/routes/+page.svelte && git commit src/routes/+page.svelte -m "feat(keys): wire the filter pane's focus token to the panel"
```

---

### Task 6: The dock chords

**Files:**
- Modify: `src/routes/+page.svelte:1743-1748` (`focusCollectionsRegion`), the `⌘⌥` branch at lines 2094–2100

- [ ] **Step 1: Add the dock-focus helpers**

After `focusCollectionsRegion` (which ends at line 1748), add:

```ts
  // Cmd+Alt+↑/↓ move within the left dock. The dock stacks Collections over
  // Filters, so the chords are vertical and literal. A closed panel is
  // skipped; with neither open the chord is a no-op rather than opening one
  // — a chord that opens panels is hard to undo by accident.
  function focusFilterRegion() {
    if (focusedFilterRow !== null) return;
    if (!filterPanelOpen) return;
    filterPanelComponent?.claim(lastFocusedFilterRow);
  }

  // Cmd+Alt+← target: the dock's last-focused panel, not always Collections.
  // Falls through to focusCollectionsRegion, which still opens the dock when
  // it is closed — today's behavior for that chord is preserved.
  async function focusDockRegion() {
    if (focusedCollectionName !== null || focusedFilterRow !== null) return;
    const preferFilters = lastFocusedDockPane === 'filters' || !collectionsPanelOpen;
    if (filterPanelOpen && preferFilters) { focusFilterRegion(); return; }
    await focusCollectionsRegion();
  }
```

- [ ] **Step 2: Route the chords**

Lines 2094–2100 currently:

```ts
    if (meta && event.altKey && !event.shiftKey && selectedFolder && !searchViewOpen
        && (event.key === 'ArrowLeft' || event.key === 'ArrowRight')) {
      event.preventDefault();
      if (event.key === 'ArrowLeft') focusCollectionsRegion();
      else focusFileRegion();
      return;
    }
```

Replace with:

```ts
    if (meta && event.altKey && !event.shiftKey && selectedFolder && !searchViewOpen
        && (event.key === 'ArrowLeft' || event.key === 'ArrowRight')) {
      event.preventDefault();
      if (event.key === 'ArrowLeft') focusDockRegion();
      else focusFileRegion();
      return;
    }

    // Cmd+Alt+↑/↓: move between the two panels stacked in the left dock.
    if (meta && event.altKey && !event.shiftKey && selectedFolder && !searchViewOpen
        && (event.key === 'ArrowUp' || event.key === 'ArrowDown')) {
      event.preventDefault();
      if (event.key === 'ArrowDown') {
        // Collections sits above Filters.
        if (focusedCollectionName !== null) { setFocusedCollectionName(null); focusFilterRegion(); }
      } else if (focusedFilterRow !== null) {
        setFocusedFilterRow(null);
        void focusCollectionsRegion();
      }
      return;
    }
```

- [ ] **Step 3: Verify**

```bash
npm run check && npm test && npm run lint:css
```

Expected: all clean.

- [ ] **Step 4: Commit**

```bash
git add src/routes/+page.svelte && git commit src/routes/+page.svelte -m "feat(keys): add Cmd+Alt+Up/Down to move within the left dock"
```

---

### Task 7: Registry and help surfaces

**Files:**
- Modify: `src/lib/keybindings.ts:16` and lines 43, 97–102
- Modify: `src/lib/KeyboardHelpOverlay.svelte:18,29`
- Modify: `src/lib/help/ReferencePane.svelte:11,22`

`keybindings.ts` declares itself the single source of truth and `?` renders
from it, so the chords added in Task 6 must be registered.

- [ ] **Step 1: Rename the scope**

In `src/lib/keybindings.ts`, line 16, change `| 'filterMenu'` to
`| 'filterPanel'`. Then rename the five binding ids at lines 98–102 from
`filterMenu.*` to `filterPanel.*` and change each entry's
`scope: 'filterMenu'` to `scope: 'filterPanel'`.

- [ ] **Step 2: Add the new entries**

Change line 43's label and add the dock chords beneath it:

```ts
  { id: 'focus.dock',            keys: { mac: '⌘⌥←',  other: 'Ctrl+Alt+←' },    label: 'Focus the left dock',         scope: 'global' },
  { id: 'focus.files',           keys: { mac: '⌘⌥→',  other: 'Ctrl+Alt+→' },    label: 'Focus right pane',            scope: 'global' },
  { id: 'focus.dockDown',        keys: { mac: '⌘⌥↓',  other: 'Ctrl+Alt+↓' },    label: 'Dock: Collections → Filters', scope: 'global' },
  { id: 'focus.dockUp',          keys: { mac: '⌘⌥↑',  other: 'Ctrl+Alt+↑' },    label: 'Dock: Filters → Collections', scope: 'global' },
```

This replaces the old `focus.collections` entry. Both `focus.collections`
and `focus.files` are registry-only — verified: they have no `chordHint`
callers anywhere in `src/`, so no `title` attribute needs updating and the
id can simply be renamed.

Then add the Escape entry to the filter-panel group:

```ts
  { id: 'filterPanel.release',   keys: { mac: 'Esc',  other: 'Esc' },           label: 'Release focus / leave the panel', scope: 'filterPanel' },
```

- [ ] **Step 3: Update both scope lists**

In `src/lib/KeyboardHelpOverlay.svelte`, change `'filterMenu'` to
`'filterPanel'` in `SCOPE_ORDER` (line 18) and rename the
`filterMenu: 'Filters panel'` key to `filterPanel: 'Filters panel'`
(line 29). The displayed label is unchanged.

In `src/lib/help/ReferencePane.svelte`, do the same at lines 11 and 22,
keeping the label `'Filter console'`.

- [ ] **Step 4: Verify no stale references remain**

```bash
grep -rn "filterMenu\|focus.collections" src/
```

Expected: no output.

- [ ] **Step 5: Verify**

```bash
npm run check && npm test
```

Expected: 0 errors, all tests pass. `KeyScope` is a union type, so a missed
rename in either scope list is a type error rather than a silent gap.

- [ ] **Step 6: Commit**

```bash
git add src/lib/keybindings.ts src/lib/KeyboardHelpOverlay.svelte src/lib/help/ReferencePane.svelte && git commit src/lib/keybindings.ts src/lib/KeyboardHelpOverlay.svelte src/lib/help/ReferencePane.svelte -m "feat(keys): register the dock chords; rename the filterMenu scope"
```

---

### Task 8: Full verification and manual QA

- [ ] **Step 1: Run everything**

```bash
npm run check && npm test && npm run lint:css && npm run build
```

Expected: all four clean.

- [ ] **Step 2: Manual QA**

```bash
npm run tauri dev
```

1. **Entry.** `⌘⌥←` with both dock panels open lands on Collections; `⌘⌥↓` moves to Filters at row 1.
2. **Memory.** Move to a system row in Filters, `⌘⌥↑` to Collections, `⌘⌥↓` back — the cursor returns to that system row, not row 1.
3. **Cursor visibility.** With focus in the tree, no filter row is highlighted. This is the bug that started this work.
4. **Exit.** Escape in Filters clears the cursor and does **not** close the panel.
5. **No cross-talk.** Escape in Filters leaves the tree highlight alone; claiming any pane visibly releases the other two.
6. **Actions.** `S`/`M` act on the cursor row; `Space` toggles a view row and mutes a channel row.
7. **Scrolling.** With a long systems list, `j` past the fold scrolls the cursor into view.
8. **Stale key.** Focus a system row, then re-index so that system disappears; `j` recovers to a real row rather than dead-ending.
9. **Closed panel.** `⌘⌥↓` with Filters closed is a no-op. Closing Filters while it holds focus does not strand the keyboard.
10. **Mouse unaffected.** Clicking the three view checkboxes still toggles them; the checked tick renders as before.
11. **Help.** `?` lists the dock chords under Global and Escape under "Filters panel".

- [ ] **Step 3: Mark the spec implemented**

In `docs/frontend/2026-08-09-pane-focus-model-design.md`, change
`**Status:** Designed; not implemented.` to name the real date and the
commits from Tasks 1–7, following the format used in
`docs/frontend/2026-08-09-hide-unindexed-design.md`.

- [ ] **Step 4: Commit**

```bash
git add docs/frontend/2026-08-09-pane-focus-model-design.md && git commit docs/frontend/2026-08-09-pane-focus-model-design.md -m "docs(keyboard): mark the pane focus model implemented"
```

---

## Spec coverage

| Spec section | Task |
|---|---|
| Third token + arbiter + memory | 2 |
| `claim()`, window handler, yield stack | 3 |
| Row identity, stable keys, ordering | 1 |
| Escape releases the token | 3 (handler), 7 (registry) |
| `⌘⌥↑/↓`, dock-aware `⌘⌥←` | 6 |
| Cursor `scrollIntoView` | 3 step 3 |
| `role="checkbox"` conversion | 4 |
| Deletions (popover machinery, `data-fm`) | 3 steps 1/3/4, 4 step 4 |
| Registry + both help surfaces | 7 |
| `filterRows` tests | 1 |
| Manual QA list | 8 |
| Follow-up C (shared pane module) | Not this plan — recorded in the spec |
