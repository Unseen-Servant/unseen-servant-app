# Search View Behavior Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make search a stateful view entered by focusing the search bar and left only explicitly (view switch, Cmd+J/T, or the Escape ladder) — Escape never clears the query.

**Architecture:** A new `searchViewOpen` boolean in `+page.svelte`, orthogonal to the persisted `viewMode: 'tree' | 'systems'` (which is the "previous view" exits return to). Render precedence: `searchViewOpen` → else `viewMode`. `searchActive` (committed query non-empty) keeps its result-wiring meaning. Spec: `docs/frontend/2026-08-08-search-view-behavior-design.md`.

**Tech Stack:** Svelte 4 (SvelteKit), TypeScript, Tauri v2 webview (WKWebView on macOS). No sidecar/Rust changes.

**Verification model:** Repo convention is vitest on pure modules only; this is keyboard/DOM glue in `+page.svelte`, so no new unit tests. Every task ends with `npm run check` (svelte-check must report 0 errors) and a commit; the final task adds `npm run lint:css`, `npm test`, and a manual walkthrough.

**Line numbers** below are as of commit `939dd37`; they shift as tasks land — anchor on the quoted code, not the numbers.

---

### Task 1: Enter via focus + render the search view (with empty-state hint)

The search view appears whenever the bar has been focused, even with no query. Old Escape behavior is untouched in this task; the app stays fully usable at the commit.

**Files:**
- Modify: `src/routes/+page.svelte` (state ~line 224, handlers ~line 498, Header instance ~line 2896, render ~lines 2976/3002)
- Modify: `src/lib/Header.svelte` (props ~line 10, input ~line 142)
- Modify: `src/lib/SearchResults.svelte` (state branches ~line 124)

- [ ] **Step 1: Add the state flag in `+page.svelte`**

After `let searchQuery = '';` / `let committedQuery = '';` block (near line 213), add:

```ts
  // The search view is stateful, not derived: entered by focusing the
  // search bar, left only explicitly (view switch, Cmd+J/T, or the
  // Escape ladder). Never persisted — the app launches into the browse
  // view. searchActive (committed query) keeps meaning "has a query".
  let searchViewOpen = false;
```

- [ ] **Step 2: Add the focus handler in `+page.svelte`**

Next to `function handleSearchClear()` (line 498), add:

```ts
  function handleSearchFocus() {
    searchViewOpen = true;
  }
```

- [ ] **Step 3: Wire it into the Header instance in `+page.svelte`**

In the `<Header ... />` instance (line 2896), add one prop alongside `onClear={handleSearchClear}`:

```svelte
    onFocus={handleSearchFocus}
```

- [ ] **Step 4: Add the `onFocus` prop in `src/lib/Header.svelte`**

With the other callback props (after `export let onClear: () => void = () => {};`):

```ts
  export let onFocus: () => void = () => {};
```

And on the `<input class="search-input" ...>` element, add alongside `on:keydown={handleKeydown}`:

```svelte
      on:focus={onFocus}
```

- [ ] **Step 5: Swap the render gates in `+page.svelte`**

Line 2976 — the file area class:

```svelte
      <div class="file-tree-area" class:search-mode={searchViewOpen} on:mousedown={handleFileTreeAreaMousedown}>
```

Line 3002 — the view precedence:

```svelte
        {#if searchViewOpen}
```

(The `{:else if viewMode === 'systems'}` / `{:else}` branches are unchanged.)

- [ ] **Step 6: Empty-query hint in `src/lib/SearchResults.svelte`**

The current branch chain (line 116) ends with `{:else if results.length === 0 && query}` → `{:else}`. Insert a new branch between them:

```svelte
  {:else if results.length === 0 && query}
    {#if indexedFileCount === 0}
      <div class="state-msg">No indexed files.</div>
    {:else}
      <div class="state-msg">0 results for &ldquo;{query}&rdquo;</div>
    {/if}
  {:else if results.length === 0}
    <!-- Search view opened from an empty bar (first use, or after ✕) -->
    <div class="state-msg">Type to search your library.</div>
  {:else}
```

- [ ] **Step 7: Verify**

Run: `npm run check`
Expected: 0 errors, 0 warnings (same as before the change).

Run: `npm run tauri dev`, then: click the search bar with no query → the file area swaps to the search split showing "Type to search your library."; type a query → results appear as before. (Escape still clears at this point — that changes in Task 3.)

- [ ] **Step 8: Commit**

```bash
git add src/routes/+page.svelte src/lib/Header.svelte src/lib/SearchResults.svelte
git commit -m "feat(search): focusing the bar opens the search view, empty-state hint"
```

---

### Task 2: Exits — setViewMode closes the view; picker visible with idle segments; Cmd+J/T ungated

**Files:**
- Modify: `src/routes/+page.svelte` (`setViewMode` line 784, Cmd+J/T handlers lines 1951–1967, `viewToggleVisible` line 2909)
- Modify: `src/lib/Header.svelte` (props, view-switch segments lines 100–135)

- [ ] **Step 1: Make `setViewMode` the universal exit in `+page.svelte`**

Replace the whole function (line 784):

```ts
  async function setViewMode(mode: 'tree' | 'systems') {
    // Selecting a view is also the exit from the search view. Blur the
    // bar if it holds focus — Cmd+J/T can fire from inside it, and a
    // focused input would keep feeding a view no longer on screen.
    searchViewOpen = false;
    const ae = document.activeElement as HTMLElement | null;
    if (ae?.classList.contains('search-input')) ae.blur();
    viewMode = mode;
    try {
      const store = await load('settings.json');
      await store.set('viewMode', mode);
      await store.save();
    } catch (e) {
      console.log('Could not persist viewMode:', e);
    }
  }
```

Note: `startEditCollection` and `startDraftCollection` already call `setViewMode('systems')`, so entering collection edit mode now closes the search view for free (spec's edit-mode edge case — no extra code).

- [ ] **Step 2: Ungate Cmd+J / Cmd+T in `+page.svelte`**

Replace the two chord handlers and their comment (lines 1951–1967):

```ts
    // Cmd/Ctrl+J: switch to Systems view; Cmd/Ctrl+T: switch to Tree view,
    // or collapse the whole tree when already there (the view switch's
    // repeat action). Both match the visible switch and double as search-
    // view exits — during search the repeat action never fires (the tree
    // isn't on screen). 'J' was chosen over '\' because backslash isn't a
    // single key on Canadian CSA and several other ISO layouts.
    if (meta && !event.shiftKey && lk === 'j' && selectedFolder) {
      event.preventDefault();
      if (searchViewOpen || viewMode !== 'systems') setViewMode('systems');
      return;
    }
    if (meta && !event.shiftKey && lk === 't' && selectedFolder) {
      event.preventDefault();
      if (!searchViewOpen && viewMode === 'tree') collapseAll();
      else setViewMode('tree');
      return;
    }
```

- [ ] **Step 3: Keep the picker visible during search in `+page.svelte`**

In the `<Header ... />` instance, change `viewToggleVisible={!!selectedFolder && !searchActive}` (line 2909) to:

```svelte
    viewToggleVisible={!!selectedFolder}
    {searchViewOpen}
```

- [ ] **Step 4: Idle segments in `src/lib/Header.svelte`**

Add with the other props:

```ts
  export let searchViewOpen: boolean = false;
```

Add after the prop declarations (near `const DEBOUNCE_MS`):

```ts
  // Which segment reads as "where you are". None while the search view
  // is up — search is entered from the bar, not the picker, so both
  // segments sit idle as exits.
  $: currentSegment = searchViewOpen ? null : viewMode;
```

Replace the two segment buttons' dynamic bits (lines 105–127; SVGs and the surrounding `view-switch` div unchanged). Systems segment:

```svelte
        <button
          class="view-segment"
          class:current={currentSegment === 'systems'}
          on:click={() => { if (currentSegment !== 'systems') onSetViewMode('systems'); }}
          title={'Shelve by system' + chordHint('view.systems')}
          aria-label="Shelve by system"
          aria-pressed={currentSegment === 'systems'}
        >
```

Tree segment:

```svelte
        <button
          class="view-segment"
          class:current={currentSegment === 'tree'}
          on:click={() => (currentSegment === 'tree' ? onCollapseAll() : onSetViewMode('tree'))}
          title={(currentSegment === 'tree' ? 'Tree view — again collapses all' : 'Tree view') + chordHint('view.tree')}
          aria-label="Tree view"
          aria-pressed={currentSegment === 'tree'}
        >
```

Also update the comment above the `view-switch` div — it currently says "one view is always on"; append the search exception:

```svelte
      <!-- View switch — a picker, not a mode: one view is always on, so the
           current segment sits on a raised fill instead of lighting purple.
           Repeating the tree action collapses the whole tree. While the
           search view is up neither segment is current; both act as exits. -->
```

- [ ] **Step 5: Verify**

Run: `npm run check`
Expected: 0 errors.

Manual (`npm run tauri dev`): focus the bar → picker stays visible, both segments idle; click the segment matching your stored view → back to it (no collapse-all); Cmd+J and Cmd+T exit search from inside the bar and the bar loses focus; in tree view with search closed, Cmd+T still collapses all.

- [ ] **Step 6: Commit**

```bash
git add src/routes/+page.svelte src/lib/Header.svelte
git commit -m "feat(search): view switch and Cmd+J/T exit the search view, segments idle while searching"
```

---

### Task 3: Escape ladder rework — Escape never clears

**Files:**
- Modify: `src/lib/Header.svelte` (`handleKeydown` line 43)
- Modify: `src/routes/+page.svelte` (ladder comment line 1856, Escape block lines 1897–1924, results-block gate line 2114, dead Escape branch lines 2156–2159)

- [ ] **Step 1: Delete the Escape-clears-text branch in `src/lib/Header.svelte`**

Replace `handleKeydown` (line 43):

```ts
  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter') {
      e.preventDefault();
      clearDebounce();
      onSubmit(searchQuery);
    }
    // Escape is handled by the page-level ladder: it steps the search
    // view closed and never clears the query — ✕ is the only clear.
  }
```

- [ ] **Step 2: Update the ladder comment in `+page.svelte`**

Replace the comment block at lines 1856–1863:

```ts
  // Escape ladder (closing precedence, top-most first):
  //   1. Open context menu               → close
  //   2. Inline rename in flight         → cancel
  //   3. Competing popover               → its own handler
  //   4. Search view, focus not in bar   → focus the search bar
  //   5. Search view, focus in bar       → leave to the browse view
  //   6. Focused tree row                → clear focus
  //   (modal Esc handled by Modal.svelte; the docked filter panel claims
  //   its own Esc while focus is inside it)
```

- [ ] **Step 3: Replace the Escape block in `handleGlobalKeydown`**

Replace lines 1897–1924 (from `if (event.key === 'Escape') {` through the closing brace after the `focusedFilePath` clear):

```ts
    if (event.key === 'Escape') {
      // Yield to ContextMenu's own Esc handler — it knows about submenu
      // state, so it can step back from a submenu to the parent menu
      // before closing the whole thing. Closing here would skip that
      // step and slam the menu shut. focusedFilePath is intentionally
      // left intact across menu open/close.
      if (contextMenu) return;
      if (renamingFilePath) { renamingFilePath = null; return; }
      // A competing popover (sort menu / dropdown / the collections
      // panel's context menu) handles its own Esc. Don't reach the
      // branches below — that would close the search view or wipe the
      // tree highlight as a side effect of closing a menu.
      if (document.querySelector('.sort-menu, .dropdown, .context-menu')) return;
      // Search-view ladder: anywhere in the view funnels focus to the
      // bar; the bar steps out to the browse view. The query is never
      // cleared here — ✕ is the only clear, and it isn't an exit.
      if (searchViewOpen) {
        event.preventDefault();
        if (inSearchInput) {
          searchViewOpen = false;
          (target as HTMLInputElement).blur();
          // The browse view isn't in the DOM until Svelte flushes the
          // swap; focusFileRegion queries rows / the SystemsView binding.
          void tick().then(() => focusFileRegion());
        } else {
          headerComponent?.focus();
        }
        return;
      }
      if (focusedFilePath) { focusedFilePath = null; }
    }
```

(This drops the old "empty search input → blur and focus first tree row" branch — superseded by the in-bar exit. `tick` is already imported from `'svelte'` at line 2.)

- [ ] **Step 4: Gate the results-list key block on visibility**

Line 2114 — change:

```ts
    if (!searchActive || searchResults.length === 0) return;
```

to:

```ts
    // Gate on the view being on screen, not on the committed query —
    // after exiting, query and results persist while tree/systems is
    // visible, and Cmd+1–9 must not jump to rows that aren't rendered.
    if (!searchViewOpen || searchResults.length === 0) return;
```

- [ ] **Step 5: Remove the now-dead Escape-in-list branch**

Delete lines 2156–2159:

```ts
    } else if (event.key === 'Escape' && inList) {
      event.preventDefault();
      headerComponent?.focus();
    }
```

(The ladder's step 4 handles it earlier in the handler.) Also update the combobox comment above (line 2131–2134): change "Enter on a focused row opens; Escape returns to input." to "Enter on a focused row opens; Escape is handled by the ladder above."

- [ ] **Step 6: Verify**

Run: `npm run check`
Expected: 0 errors.

Manual: type a query, ArrowDown into results, then Escape ×3 → focus hops to the bar, then the browse view returns with the query still in the bar, with keyboard focus on a row; refocus the bar → previous results reappear instantly; Escape with text never clears; ✕ clears but stays in the (empty) search view.

- [ ] **Step 7: Commit**

```bash
git add src/routes/+page.svelte src/lib/Header.svelte
git commit -m "feat(search): Escape steps out of the search view instead of clearing the query"
```

---

### Task 4: Gate audit — remaining `searchActive` gates that mean "search view on screen"

**Files:**
- Modify: `src/routes/+page.svelte` (lines 245–246, 1676, 1974, 2094–2096, 2101–2111, scope-bar props line 2992)

- [ ] **Step 1: Filter-relevance flags (lines 245–246)**

```ts
  $: systemsFilterRelevant = viewMode === 'systems' || searchViewOpen;
  $: curationFilterRelevant = viewMode === 'systems' || searchViewOpen;
```

(The comment above them stays accurate — filters apply where the organizing axis is the tag or where the search backend consumes them.)

- [ ] **Step 2: File-area chrome clicks (line 1676)**

In `handleFileTreeAreaMousedown`, change `if (searchActive) return;` to:

```ts
    if (searchViewOpen) return;
```

- [ ] **Step 3: Region-jump chord gate (line 1974)**

Change `!searchActive` to `!searchViewOpen` in the Cmd+Alt+←/→ condition:

```ts
    if (meta && event.altKey && !event.shiftKey && selectedFolder && !searchViewOpen
        && (event.key === 'ArrowLeft' || event.key === 'ArrowRight')) {
```

- [ ] **Step 4: File-action and tree-nav gates (lines 2094–2111)**

In `fileActionGate`, change `!searchActive` to `!searchViewOpen`:

```ts
    const fileActionGate =
      selectedFolder && !searchViewOpen && !contextMenu && !renamingFilePath &&
      !competingMenuOpen && !focusedCollectionName && !inAnyInput;
```

In the tree-nav block, change the gate and **delete the ArrowDown-from-empty-input branch** (the tree is never on screen while the input is focused). The whole block becomes:

```ts
    // Tree-row arrow navigation. Systems view owns its own arrow nav,
    // so this block is gated to tree mode only.
    if (selectedFolder && !searchViewOpen && !contextMenu && !renamingFilePath && !competingMenuOpen && !focusedCollectionName && viewMode === 'tree') {
      if (!inAnyInput && handleTreeNavKey(event)) return;
    }
```

- [ ] **Step 5: Scope-bar meter only while the search view is visible (line 2992)**

Query and results now outlive the view, so the raw `searchActive` would paint the hits meter over the tree. In the `<SearchScopeBar ... />` instance, change `{searchActive}` to:

```svelte
          searchActive={searchViewOpen && searchActive}
```

(Accepted behavior, noted: filter toggles while the view is closed still re-run the hidden search — `if (committedQuery) runSearch(...)` sites are untouched; results stay fresh for the next open, cost is local.)

- [ ] **Step 6: Confirm no `searchActive` gate was missed**

Run: `command grep -n "searchActive" src/routes/+page.svelte src/lib/*.svelte`
Expected remaining uses only where "has a committed query" is the true meaning: its `$:` definition (line 237), `stale`/pagination internals, the `searchActive={searchViewOpen && searchActive}` pass, and `SearchScopeBar.svelte`'s own prop. Anything else: stop and re-derive which meaning it carries before continuing.

- [ ] **Step 7: Verify**

Run: `npm run check`
Expected: 0 errors.

Manual: exit search to tree with a query still in the bar → no hits meter, tree arrows/letter keys work, clicking pane chrome claims a row; in search view, chips still show; Cmd+Alt+←/→ works in browse views, not during search.

- [ ] **Step 8: Commit**

```bash
git add src/routes/+page.svelte
git commit -m "fix(search): audit view gates — searchViewOpen where 'on screen' was meant"
```

---

### Task 5: Keybindings/help cleanup + full verification

**Files:**
- Modify: `src/lib/keybindings.ts` (lines 55–57)

- [ ] **Step 1: Update the searchInput scope entries**

Remove the `search.intoTree` entry (line 57) — the tree is never on screen while the input is focused. Document the two changed Escape behaviors. Lines 55–57 become:

```ts
  { id: 'search.submit',         keys: { mac: '↵',    other: 'Enter' },         label: 'Submit search',                scope: 'searchInput' },
  { id: 'search.intoResults',    keys: { mac: '↓',    other: '↓' },             label: 'Move focus into results',      scope: 'searchInput' },
  { id: 'search.exit',           keys: { mac: 'Esc',  other: 'Esc' },           label: 'Leave search — back to browse view', scope: 'searchInput' },
```

And in the `searchResults` scope block (after `results.jumpN`, line 111), add:

```ts
  { id: 'results.toInput',       keys: { mac: 'Esc',  other: 'Esc' },           label: 'Back to search input',         scope: 'searchResults' },
```

(KeyboardHelpOverlay and ReferencePane render these scopes from this list — no other file changes.)

- [ ] **Step 2: Full check suite**

Run: `npm run check` — expected: 0 errors.
Run: `npm run lint:css` — expected: clean (no raw color values were introduced).
Run: `npm test` — expected: all existing vitest suites pass (none touch the changed files).

- [ ] **Step 3: Manual walkthrough (from the spec)**

In `npm run tauri dev`:

1. Enter via click, Tab, and Cmd+F → search view each time; empty bar shows the hint.
2. Exit via each picker segment, Cmd+J, Cmd+T → lands in that view; segment matching the stored view returns without collapse-all; Cmd+T in tree (search closed) still collapses.
3. Focused result → Escape ×3: result list → bar → browse view, query text intact, keyboard focus on a row.
4. Escape with text in the bar: text survives. ✕: clears, stays in empty search view, input keeps focus.
5. ArrowDown from the bar with results → into the list; ArrowUp from the first row → back to the bar.
6. Edit a collection while the search view is open → search view closes into systems view; search bar disabled during edit.
7. Toggle the filter panel open/closed with Esc while in search view → panel closes, search view stays.
8. Relaunch the app → starts in the persisted browse view, never in search.

- [ ] **Step 4: Commit**

```bash
git add src/lib/keybindings.ts
git commit -m "docs(keybindings): search-view Escape entries, drop stale into-tree binding"
```
