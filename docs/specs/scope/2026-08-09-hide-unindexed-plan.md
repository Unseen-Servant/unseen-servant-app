# Hide unindexed items — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a third filter-console switch, "Hide unindexed items", that drops tree rows the library knows nothing about — neither indexed nor selected for indexing.

**Architecture:** One new pure predicate in `treeNav.ts` (`rowHasLibraryMaterial`) composed from the existing `rowHasIndexedMaterial`, consumed by both `computeVisibleRows` (keyboard nav) and `FileTree.svelte` (render) so the two can never drift — the same discipline the focus lens follows through `isRowOutOfScope`. The flag rides in a `LibraryKnowledge` struct mirroring `ScopeVisibility`. Everything else is wiring: a console row, a scope-bar chip, page state, and a store key.

**Tech Stack:** SvelteKit 2 + TypeScript, vitest for unit tests, svelte-check for type checking, stylelint for the tokens-only CSS rule.

**Spec:** `docs/specs/scope/2026-08-09-hide-unindexed-design.md`

**Testing reality:** Tasks 1–2 are pure functions and get full TDD. Tasks 3–7 touch `.svelte` files, and this repo has **no component test harness** — every existing test is a `.ts` unit test. Those tasks are verified by `npm run check` (svelte-check), the unit suite staying green, `npm run lint:css`, and the manual QA checklist in Task 8. Do not scaffold a component test harness; that is out of scope for this change.

---

### Task 1: The `rowHasLibraryMaterial` predicate

**Files:**
- Modify: `src/lib/treeNav.ts` (add after `rowHasIndexedMaterial`, ~line 33)
- Test: `src/lib/treeNav.test.ts` (add a describe block after the `rowHasIndexedMaterial` block, ~line 213)

- [ ] **Step 1: Write the failing test**

Add to `src/lib/treeNav.test.ts` immediately after the closing `});` of the `rowHasIndexedMaterial` describe block:

```ts
// --- rowHasLibraryMaterial ---

describe('rowHasLibraryMaterial', () => {
  // /root/A/a.pdf is indexed; /root/A/queued.pdf is selected but not yet
  // indexed (the `to_add` case); /root/junk holds neither.
  const known: LibraryKnowledge = {
    indexedPaths: new Set(['/root/A/a.pdf']),
    indexedFolderPaths: new Set(['/root', '/root/A']),
    selectedPaths: new Set(['/root/A/a.pdf', '/root/B/queued.pdf']),
    foldersWithSelections: new Set(['/root', '/root/A', '/root/B']),
    hideUnindexed: true,
  };

  it('is true for an indexed file', () => {
    expect(rowHasLibraryMaterial('/root/A/a.pdf', false, known)).toBe(true);
  });

  it('is true for a selected-but-unindexed file (to_add stays visible)', () => {
    expect(rowHasLibraryMaterial('/root/B/queued.pdf', false, known)).toBe(true);
  });

  it('is false for a file that is neither indexed nor selected', () => {
    expect(rowHasLibraryMaterial('/root/A/notes.txt', false, known)).toBe(false);
  });

  it('is true for a folder with an indexed descendant', () => {
    expect(rowHasLibraryMaterial('/root/A', true, known)).toBe(true);
  });

  it('is true for a folder whose only descendant is selected, not indexed', () => {
    expect(rowHasLibraryMaterial('/root/B', true, known)).toBe(true);
  });

  it('is false for a folder with neither indexed nor selected descendants', () => {
    expect(rowHasLibraryMaterial('/root/junk', true, known)).toBe(false);
  });

  it('is true for an indexed file that has been deselected (to_remove stays visible)', () => {
    const deselected: LibraryKnowledge = {
      ...known,
      selectedPaths: new Set(),
      foldersWithSelections: new Set(),
    };
    expect(rowHasLibraryMaterial('/root/A/a.pdf', false, deselected)).toBe(true);
  });
});
```

Update the import on line 3 of the same file to:

```ts
import { computeVisibleRows, indexOfPath, isRowOutOfScope, rowHasIndexedMaterial, rowHasLibraryMaterial, type LibraryKnowledge, type ScopeVisibility } from './treeNav';
```

- [ ] **Step 2: Run test to verify it fails**

```bash
npx vitest run src/lib/treeNav.test.ts
```

Expected: FAIL — `rowHasLibraryMaterial is not a function` (and a TS error on the missing `LibraryKnowledge` export).

- [ ] **Step 3: Write minimal implementation**

In `src/lib/treeNav.ts`, add immediately after the closing brace of `rowHasIndexedMaterial` (currently line 33):

```ts
/** What the library knows about a row: the index, plus the selection
 * that feeds it. Selection is part of the picture because
 * `indexedPaths` is built from up_to_date + to_update + to_remove and
 * deliberately excludes `to_add` — keying on the index alone would make
 * a row vanish the moment its box was checked, and keep every queued
 * file invisible until the run finished. */
export interface LibraryKnowledge {
  indexedPaths: Set<string>;
  indexedFolderPaths: Set<string>;
  selectedPaths: Set<string>;
  foldersWithSelections: Set<string>;
  hideUnindexed: boolean;
}

/** A row is library material when the index or the selection knows
 * about it — an indexed or queued file, or a folder with such a
 * descendant. "Hide unindexed items" drops everything else. FileTree's
 * render and the keyboard nav's row model both call this — keep them in
 * sync through it, never by copy.
 *
 * Composed from rowHasIndexedMaterial rather than unioning the two path
 * sets: a union would rebuild a multi-thousand-path Set on every
 * selection click, which the `reuseIfSame` pattern in +page.svelte
 * exists to avoid. Two O(1) lookups instead. */
export function rowHasLibraryMaterial(
  path: string,
  isDir: boolean,
  known: LibraryKnowledge,
): boolean {
  return (
    rowHasIndexedMaterial(path, isDir, known.indexedPaths, known.indexedFolderPaths) ||
    rowHasIndexedMaterial(path, isDir, known.selectedPaths, known.foldersWithSelections)
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
npx vitest run src/lib/treeNav.test.ts
```

Expected: PASS — all 7 new assertions green, all pre-existing `treeNav` tests still green.

- [ ] **Step 5: Commit**

```bash
git add src/lib/treeNav.ts src/lib/treeNav.test.ts && git commit src/lib/treeNav.ts src/lib/treeNav.test.ts -m "feat(tree): add the rowHasLibraryMaterial predicate"
```

> **Note on commit commands throughout this plan:** every commit is path-scoped (`git commit <paths>`) rather than a bare `git commit`. Other sessions commit to `main` concurrently and may leave unrelated files staged — a bare commit would sweep them in. Run `git status --short` before each commit and confirm you are only committing your own paths.

---

### Task 2: `computeVisibleRows` honors the switch

**Files:**
- Modify: `src/lib/treeNav.ts:51-76` (`computeVisibleRows`)
- Test: `src/lib/treeNav.test.ts` (new describe block inside the existing `computeVisibleRows` describe, after the `focus lens (scope)` block at ~line 189)

- [ ] **Step 1: Write the failing test**

Add inside the outer `describe('computeVisibleRows', ...)`, immediately after the closing `});` of `describe('focus lens (scope)', ...)`:

```ts
  describe('hide unindexed', () => {
    // nestedTree(): /root/parent/{sub/{x.pdf,y.pdf}, sibling.pdf}
    // Only /root/parent/sub/x.pdf is indexed. sibling.pdf and y.pdf are
    // unknown to the library unless a test selects them.
    function library(over: Partial<LibraryKnowledge> = {}): LibraryKnowledge {
      return {
        indexedPaths: new Set(['/root/parent/sub/x.pdf']),
        indexedFolderPaths: new Set(['/root/parent', '/root/parent/sub']),
        selectedPaths: new Set(),
        foldersWithSelections: new Set(),
        hideUnindexed: true,
        ...over,
      };
    }

    const expanded = new Set(['/root/parent', '/root/parent/sub']);

    it('drops rows the library knows nothing about', () => {
      const rows = computeVisibleRows(nestedTree(), expanded, null, new Set(), false, null, library());
      expect(rows.map(r => r.path)).toEqual([
        '/root/parent',
        '/root/parent/sub',
        '/root/parent/sub/x.pdf',
      ]);
    });

    it('keeps a selected-but-unindexed file and its folder', () => {
      const rows = computeVisibleRows(nestedTree(), expanded, null, new Set(), false, null, library({
        selectedPaths: new Set(['/root/parent/sibling.pdf']),
        foldersWithSelections: new Set(['/root/parent']),
      }));
      expect(rows.map(r => r.path)).toContain('/root/parent/sibling.pdf');
    });

    it('skips a whole folder subtree when nothing under it is known', () => {
      const rows = computeVisibleRows(nestedTree(), expanded, null, new Set(), false, null, library({
        indexedPaths: new Set(['/root/parent/sibling.pdf']),
        indexedFolderPaths: new Set(['/root/parent']),
      }));
      expect(rows.map(r => r.path)).toEqual([
        '/root/parent',
        '/root/parent/sibling.pdf',
      ]);
    });

    it('is inert when hideUnindexed is false', () => {
      const rows = computeVisibleRows(nestedTree(), expanded, null, new Set(), false, null, library({ hideUnindexed: false }));
      expect(rows.map(r => r.path)).toEqual([
        '/root/parent',
        '/root/parent/sub',
        '/root/parent/sub/x.pdf',
        '/root/parent/sub/y.pdf',
        '/root/parent/sibling.pdf',
      ]);
    });

    it('is inert when library is null', () => {
      const rows = computeVisibleRows(nestedTree(), expanded, null, new Set(), false, null, null);
      expect(rows).toHaveLength(5);
    });

    it('composes with the focus lens — a row dropped by either is absent', () => {
      // sub/ is indexed material out of scope (lens drops it);
      // sibling.pdf is unknown to the library (the switch drops it).
      const scope: ScopeVisibility = {
        scopeBrightPaths: new Set(['/root/parent']),
        indexedFolderPaths: new Set(['/root/parent/sub']),
        indexedPaths: new Set(['/root/parent/sub/x.pdf']),
        hideOutOfScope: true,
      };
      const rows = computeVisibleRows(nestedTree(), expanded, null, new Set(), false, scope, library());
      expect(rows.map(r => r.path)).toEqual(['/root/parent']);
    });
  });
```

- [ ] **Step 2: Run test to verify it fails**

```bash
npx vitest run src/lib/treeNav.test.ts
```

Expected: FAIL — `computeVisibleRows` takes 6 parameters, so the 7th argument is ignored and `drops rows the library knows nothing about` returns all 5 paths instead of 3.

- [ ] **Step 3: Write minimal implementation**

In `src/lib/treeNav.ts`, replace the comment block and signature at lines 45–58. Current:

```ts
// Flattens the file tree into the rows the user can actually navigate to,
// respecting expansion state, the optional collection filter, the
// hidden-paths rule (descendants of a hidden ancestor stay hidden unless
// `showHidden` is on), and the focus lens (out-of-scope subtrees are
// skipped entirely when `scope.hideOutOfScope` is on). Order matches the
// rendered DOM order, so consecutive rows here are visually adjacent.
export function computeVisibleRows(
  files: FileItem[],
  expandedPaths: Set<string>,
  displayPaths: Set<string> | null,
  hiddenPaths: Set<string>,
  showHidden: boolean,
  scope: ScopeVisibility | null = null,
): VisibleRow[] {
```

Replace with:

```ts
// Flattens the file tree into the rows the user can actually navigate to,
// respecting expansion state, the optional collection filter, the
// hidden-paths rule (descendants of a hidden ancestor stay hidden unless
// `showHidden` is on), the "Hide unindexed items" switch (rows the
// library knows nothing about are skipped when `library.hideUnindexed`
// is on), and the focus lens (out-of-scope subtrees are skipped entirely
// when `scope.hideOutOfScope` is on). Order matches the rendered DOM
// order, so consecutive rows here are visually adjacent.
export function computeVisibleRows(
  files: FileItem[],
  expandedPaths: Set<string>,
  displayPaths: Set<string> | null,
  hiddenPaths: Set<string>,
  showHidden: boolean,
  scope: ScopeVisibility | null = null,
  library: LibraryKnowledge | null = null,
): VisibleRow[] {
```

Then inside `walk`, add one line after the hidden-paths guard. Current lines 62–65:

```ts
    if (displayPaths !== null && !displayPaths.has(item.path)) return;
    const hiddenByUser = isPathOrAncestorIn(item.path, hiddenPaths);
    if (hiddenByUser && !showHidden) return;
    if (scope?.hideOutOfScope && isRowOutOfScope(item.path, item.is_dir, scope)) return;
```

Replace with:

```ts
    if (displayPaths !== null && !displayPaths.has(item.path)) return;
    const hiddenByUser = isPathOrAncestorIn(item.path, hiddenPaths);
    if (hiddenByUser && !showHidden) return;
    if (library?.hideUnindexed && !rowHasLibraryMaterial(item.path, item.is_dir, library)) return;
    if (scope?.hideOutOfScope && isRowOutOfScope(item.path, item.is_dir, scope)) return;
```

- [ ] **Step 4: Run test to verify it passes**

```bash
npx vitest run src/lib/treeNav.test.ts
```

Expected: PASS — all 6 new assertions green, all pre-existing `computeVisibleRows` tests still green (the new parameter is defaulted, so every existing call site is unaffected).

- [ ] **Step 5: Commit**

```bash
git add src/lib/treeNav.ts src/lib/treeNav.test.ts && git commit src/lib/treeNav.ts src/lib/treeNav.test.ts -m "feat(tree): skip library-unknown rows in computeVisibleRows"
```

---

### Task 3: `FileTree` drops the rows

**Files:**
- Modify: `src/lib/FileTree.svelte:8` (import), `:65` (prop), `:76-81` (hidden calc), `:328` (recursion)

No test in this task — see the Testing reality note in the header. `npm run check` is the gate.

- [ ] **Step 1: Import the predicate**

Line 8 currently:

```ts
  import { isRowOutOfScope, rowHasIndexedMaterial } from './treeNav';
```

Replace with:

```ts
  import { isRowOutOfScope, rowHasIndexedMaterial, rowHasLibraryMaterial } from './treeNav';
```

- [ ] **Step 2: Add the prop**

After the `hideOutOfScope` prop (currently line 65), add:

```ts
  // "Hide unindexed items": drop rows the library knows nothing about —
  // neither in the index nor selected for it. Tree only; SystemsView
  // renders indexStatus entries and holds nothing unindexed to hide.
  export let hideUnindexed: boolean = false;
```

- [ ] **Step 3: Fold it into the hidden calculation**

Lines 78–81 currently:

```ts
  $: isHiddenItem = isPathOrAncestorIn(item.path, hiddenPaths);
  $: hidden = (displayPaths !== null && !displayPaths.has(item.path)) ||
              (isHiddenItem && !showHidden) ||
              (outOfScope && hideOutOfScope);
```

Replace with:

```ts
  // Rows the library knows nothing about. Unlike out-of-scope, this has
  // no dim tier — the switch off reproduces today's tree exactly.
  $: outsideLibrary = hideUnindexed && !rowHasLibraryMaterial(item.path, item.is_dir, {
    indexedPaths, indexedFolderPaths, selectedPaths, foldersWithSelections, hideUnindexed,
  });

  $: isHiddenItem = isPathOrAncestorIn(item.path, hiddenPaths);
  $: hidden = (displayPaths !== null && !displayPaths.has(item.path)) ||
              (isHiddenItem && !showHidden) ||
              (outOfScope && hideOutOfScope) ||
              outsideLibrary;
```

- [ ] **Step 4: Thread the prop through the recursion**

In the `<svelte:self>` block, after `{hideOutOfScope}` (currently line 328), add:

```svelte
          {hideUnindexed}
```

- [ ] **Step 5: Verify types**

```bash
npm run check
```

Expected: no new errors. (`selectedPaths` and `foldersWithSelections` are already props at lines 14–15, so nothing else needs threading.)

- [ ] **Step 6: Commit**

```bash
git add src/lib/FileTree.svelte && git commit src/lib/FileTree.svelte -m "feat(tree): hide library-unknown rows under the new switch"
```

---

### Task 4: The filter-console row

**Files:**
- Modify: `src/lib/FilterPanel.svelte:52-53` (props), `:213-214` (new row)

- [ ] **Step 1: Add the props**

After the `onToggleHideOutOfScope` prop (currently line 53), add:

```ts
  // "Hide unindexed items" — the bulk gesture for material scope can't
  // speak about, sibling to per-item hide. Spec: docs/specs/scope/
  // 2026-08-09-hide-unindexed-design.md.
  export let hideUnindexed: boolean = false;
  export let onToggleHideUnindexed: () => void = () => {};
```

- [ ] **Step 2: Add the row**

Between the "Show hidden items" `</label>` (line 213) and the existing lens `<label>` (line 215), insert:

```svelte
    <label
      class="row lens-row"
      title="Hide files and folders the library knows nothing about — not indexed, not selected for indexing"
      data-fm="row"
    >
      <span class="row-name muted-name">Hide unindexed items</span>
      <input
        class="app-checkbox lens-checkbox"
        type="checkbox"
        checked={hideUnindexed}
        on:change={onToggleHideUnindexed}
      />
    </label>
```

Order is deliberate: Show hidden → Hide unindexed → Hide out-of-scope, running from the switch least entangled with scope to the one that is scope. Reusing `.lens-row` and `.lens-checkbox` means **no CSS change** — `.lens-row` carries no rules of its own, and `.lens-checkbox:checked` (line 569) supplies the purple that marks a mode the user switched on.

- [ ] **Step 3: Verify types and CSS**

```bash
npm run check && npm run lint:css
```

Expected: both clean. `lint:css` matters here — it enforces the tokens-only colour rule, and this row adds no raw values.

- [ ] **Step 4: Commit**

```bash
git add src/lib/FilterPanel.svelte && git commit src/lib/FilterPanel.svelte -m "feat(console): add the Hide unindexed items row"
```

---

### Task 5: The scope-bar chip

**Files:**
- Modify: `src/lib/SearchScopeBar.svelte:24` and `:37` (props), `:247` (chip), `:418-421` (CSS)

- [ ] **Step 1: Add the props**

After `export let hideOutOfScope: boolean = false;` (line 24), add:

```ts
  export let hideUnindexed: boolean = false;
```

After `export let onToggleHideOutOfScope: () => void = () => {};` (line 37), add:

```ts
  export let onToggleHideUnindexed: () => void = () => {};
```

- [ ] **Step 2: Add the chip**

Immediately before the existing `{#if hideOutOfScope}` block (line 248), insert:

```svelte
    {#if hideUnindexed}
      <button
        type="button"
        class="chip indexed-only"
        on:click|stopPropagation={onToggleHideUnindexed}
        title="Show unindexed items again"
        aria-label="Show unindexed items again"
      >
        <span class="chip-label">indexed only</span>
        <span class="chip-clear" aria-hidden="true">×</span>
      </button>
    {/if}
```

- [ ] **Step 3: Share the purple rule**

Lines 418–421 currently:

```css
  .chip.lens-on {
    border-color: color-mix(in srgb, var(--text-active) 35%, transparent);
    color: var(--text-active);
  }
```

Replace with:

```css
  /* Both are modes the user switched on, so both wear purple. A shared
     rule rather than a reused class name — "lens-on" would misname the
     unindexed chip, which is not the focus lens. */
  .chip.lens-on,
  .chip.indexed-only {
    border-color: color-mix(in srgb, var(--text-active) 35%, transparent);
    color: var(--text-active);
  }
```

- [ ] **Step 4: Verify types and CSS**

```bash
npm run check && npm run lint:css
```

Expected: both clean.

- [ ] **Step 5: Commit**

```bash
git add src/lib/SearchScopeBar.svelte && git commit src/lib/SearchScopeBar.svelte -m "feat(scope-bar): add the indexed-only chip"
```

---

### Task 6: Page state and persistence

**Files:**
- Modify: `src/routes/+page.svelte:177` (state), `:657` (load), `:955` (save), `:1020` (toggle)

- [ ] **Step 1: Add the state**

After `let showHidden = false;` (line 177), add:

```ts
  // "Hide unindexed items" — a view mode over what the library knows,
  // not a narrowing, so it lives beside showHidden rather than in the
  // scope console (and survives [clear all], as the focus lens does).
  let hideUnindexed = false;
```

- [ ] **Step 2: Load it**

After the `savedShowHidden` block (lines 654–657), add:

```ts
      const savedHideUnindexed = parseBoolean(await store.get('hideUnindexed'));
      if (savedHideUnindexed !== undefined) {
        hideUnindexed = savedHideUnindexed;
      }
```

`parseBoolean` is already imported — it is what line 654 uses.

- [ ] **Step 3: Save it**

In `persistHidden`, after `await store.set('showHidden', showHidden);` (line 955), add:

```ts
      await store.set('hideUnindexed', hideUnindexed);
```

`persistHidden` is the store-write for tree visibility flags; the new flag gets its own key there rather than joining the `scopeConsole` blob, keeping it out of `parseScopeConsoleState` and out of `[clear all]`.

- [ ] **Step 4: Add the toggle handler**

After `toggleShowHidden` (lines 1017–1020), add:

```ts
  function toggleHideUnindexed() {
    hideUnindexed = !hideUnindexed;
    persistHidden();
  }
```

Note there is deliberately **no** auto-reset guard of the kind `toggleHidden` applies to `showHidden` at line 1007. The equivalent check ("is anything unindexed?") would need a whole-tree scan, and the switch is a harmless no-op when everything is known.

- [ ] **Step 5: Verify types**

```bash
npm run check
```

Expected: no new errors. `toggleHideUnindexed` is unused at this point — that is fine, Task 7 wires it. If svelte-check flags it as unused, leave it; the next task resolves it.

- [ ] **Step 6: Commit**

```bash
git add src/routes/+page.svelte && git commit src/routes/+page.svelte -m "feat(tree): persist the hide-unindexed view mode"
```

---

### Task 7: Wire the page together

**Files:**
- Modify: `src/routes/+page.svelte:1591-1593` (nav rows), `:3103-3104` (FilterPanel), `:3134` and `:3148` (SearchScopeBar), `:3211-3213` (empty state), `:3240` (FileTree)

- [ ] **Step 1: Feed the keyboard-nav row model**

Lines 1591–1593 currently:

```ts
  $: visibleTreeRows = computeVisibleRows(files, expandedPaths, displayPaths, hiddenPaths, showHidden, {
    scopeBrightPaths, indexedFolderPaths, indexedPaths, hideOutOfScope,
  });
```

Replace with:

```ts
  $: visibleTreeRows = computeVisibleRows(files, expandedPaths, displayPaths, hiddenPaths, showHidden, {
    scopeBrightPaths, indexedFolderPaths, indexedPaths, hideOutOfScope,
  }, {
    indexedPaths, indexedFolderPaths, selectedPaths, foldersWithSelections, hideUnindexed,
  });
```

This is the step that keeps arrow-key navigation from walking onto rows that aren't rendered.

- [ ] **Step 2: Wire the FilterPanel**

After `onToggleHideOutOfScope={toggleHideOutOfScope}` (line 3104), add:

```svelte
              {hideUnindexed}
              onToggleHideUnindexed={toggleHideUnindexed}
```

- [ ] **Step 3: Wire the SearchScopeBar**

After `{hideOutOfScope}` (line 3134), add:

```svelte
          {hideUnindexed}
```

After `onToggleHideOutOfScope={toggleHideOutOfScope}` (line 3148), add:

```svelte
          onToggleHideUnindexed={toggleHideUnindexed}
```

- [ ] **Step 4: Wire the FileTree**

After `{hideOutOfScope}` in the `<FileTree>` block (line 3240), add:

```svelte
              {hideUnindexed}
```

Do **not** add the prop to `<SystemsView>` (line ~3189). It renders `indexStatus` entries only, so it holds nothing unindexed to hide.

- [ ] **Step 5: Add the empty-state placeholder**

Lines 3211–3213 currently:

```svelte
          {#if hideOutOfScope && scopeBrightPaths !== null && scopeBrightPaths.size === 0}
            <div class="scope-empty">Everything is out of scope.</div>
          {/if}
```

Replace with:

```svelte
          {#if hideOutOfScope && scopeBrightPaths !== null && scopeBrightPaths.size === 0}
            <div class="scope-empty">Everything is out of scope.</div>
          {:else if hideUnindexed && indexedPaths.size === 0 && selectedPaths.size === 0}
            <div class="scope-empty">Nothing in the library yet.</div>
          {/if}
```

`{:else if}` rather than a second `{#if}`: when the scope is empty *and* the library is empty, one message is enough, and the scope message is the more specific of the two. The condition is exact — if the library knows nothing, every row hides, and no other state produces a fully empty tree. Reuses the existing `.scope-empty` class, so no CSS change.

- [ ] **Step 6: Verify types, tests, and CSS**

```bash
npm run check && npm test && npm run lint:css
```

Expected: all three clean, `toggleHideUnindexed` no longer unused.

- [ ] **Step 7: Commit**

```bash
git add src/routes/+page.svelte && git commit src/routes/+page.svelte -m "feat(tree): wire the Hide unindexed items switch"
```

---

### Task 8: Full verification and manual QA

**Files:** none modified unless a check fails.

- [ ] **Step 1: Run the full automated suite**

```bash
npm run check && npm test && npm run lint:css && npm run build
```

Expected: all four clean. These are the same three checks `frontend-checks` runs in CI plus the vite build, so a green run here predicts a green push.

- [ ] **Step 2: Manual QA in the running app**

```bash
npm run tauri dev
```

Walk this checklist — these are the behaviors no unit test in this repo can reach:

1. **Switch off = no visual change.** Toggle it on and off; the tree returns to exactly its prior contents. No dimming appears at any point.
2. **Bulk hide works.** With the switch on, folders containing only unindexed files disappear along with their subtrees; folders on the path to indexed files stay.
3. **Queued files stay visible.** Switch off, check an unindexed file's box, switch on — the row remains (this is the `to_add` case the predicate exists for). Uncheck it and it disappears.
4. **Chip recovery.** The `indexed only` chip appears on the scope bar in purple; clicking it turns the switch off and the rows return.
5. **Keyboard nav matches render.** With the switch on, arrow through the tree top to bottom — focus never lands on an invisible row and never skips a visible one.
6. **Composes with the lens.** Turn both on with a solo engaged; rows dropped by either stay dropped, and clearing one chip restores only its own rows.
7. **Persistence.** Toggle on, quit, relaunch — the switch and its chip come back on.
8. **`[clear all]` leaves it alone.** With the switch on and some solos engaged, hit `[clear all]`: solos clear, the switch stays on (it is a view mode, matching the focus lens).
9. **Empty-library placeholder.** With nothing indexed and nothing selected, the switch on shows "Nothing in the library yet." rather than a blank pane.

- [ ] **Step 3: Mark the spec implemented**

In `docs/specs/scope/2026-08-09-hide-unindexed-design.md`, change the status line from:

```markdown
**Status:** Designed; not implemented.
```

to (substituting the real date and commit range):

```markdown
**Status:** Implemented 2026-08-09 on main (automated checks green; manual QA checklist walked).
```

- [ ] **Step 4: Commit and push**

```bash
git add docs/specs/scope/2026-08-09-hide-unindexed-design.md && git commit docs/specs/scope/2026-08-09-hide-unindexed-design.md -m "docs(scope): mark the hide-unindexed spec implemented"
```

```bash
git push origin main
```

Then confirm the Linux CI suite goes green on the push before considering the work done.

---

## Spec coverage

| Spec section | Task |
|---|---|
| Third masthead row, ordering | 4 |
| Hide only, never dim | 3 (no dim tier added) |
| File + folder predicate, selection-aware | 1 |
| Tree only, not SystemsView | 7 step 4 |
| Empty state placeholder | 7 step 5 |
| Chip, purple, two-deep recovery | 5 |
| Accepted cost (no mode-suppression) | 6 step 4 (no guard, documented) |
| Delta 1: `treeNav.ts` predicate | 1 |
| Delta 2: `computeVisibleRows` | 2 |
| Delta 3: `FileTree.svelte` | 3 |
| Delta 4: `FilterPanel.svelte` | 4 |
| Delta 5: `SearchScopeBar.svelte` | 5 |
| Delta 6: `+page.svelte` | 6, 7 |
| Delta 7: doctrine amendment | already landed in 8f1fdda |
| Persistence, own key, out of `[clear all]` | 6 |
| Testing list | 1, 2, plus QA in 8 |
