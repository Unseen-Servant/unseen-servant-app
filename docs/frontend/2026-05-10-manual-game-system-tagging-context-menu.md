# Manual game-system tagging via context menu — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Game system…" submenu to the file-tree context menu so any indexed PDF can have its game-system tags set or toggled via right-click. Remove the now-redundant `+` button on indexed-untagged tree rows.

**Architecture:** Frontend-only change. New submenu in `ContextMenu.svelte` mirrors the existing "Add to collection…" pattern (hover-opens, `data-mi` for kb focus tracking from #273). Page passes `knownSystems`, the file's current tags, and a wrapper around the existing `handleSetGameSystems` handler. Backend (`set_game_systems` Tauri command + `/api/set-game-systems`) already does the metadata flip with no re-index.

**Tech Stack:** Svelte 5, Tauri 2, TypeScript. Manual verification via `npm run tauri dev`; no Svelte component test infrastructure in this repo, so we don't add one.

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `src/lib/ContextMenu.svelte` | Modify | Add new submenu trigger + content for game-system tagging. Extend `openSubmenu` union to include `'tag'`. |
| `src/routes/+page.svelte` | Modify | Pass `knownSystems`, `currentTags`, `onSetGameSystems` props to the rendered `ContextMenu`. |
| `src/lib/FileTree.svelte` | Modify | Remove the `{:else if isIndexed}` branch that renders the `+` button; remove its CSS. |

---

## Task 1: Extend ContextMenu submenu state and add Game system trigger

**Files:**
- Modify: `src/lib/ContextMenu.svelte`

- [ ] **Step 1: Add new props for game-system tagging**

In `src/lib/ContextMenu.svelte`, after the existing `export let initialSubmenu: 'add' | 'remove' | null = null;` declaration and the existing `KnownGameSystem` import, add:

```typescript
// Add KnownGameSystem to the existing type import line (top of <script>):
//   import type { FileItem, CollectionInfo } from './types';
// becomes:
//   import type { FileItem, CollectionInfo, KnownGameSystem } from './types';

// New props (place near the other export let declarations):
export let knownSystems: KnownGameSystem[] = [];
export let currentTags: string[] = [];
export let onSetGameSystems: (tags: string[]) => void = () => {};
```

Then change the `openSubmenu` union from `'add' | 'remove' | null` to `'add' | 'remove' | 'tag' | null` everywhere it appears in the file (5 sites: `initialSubmenu` prop type, `openSubmenu` state, `focusedSubmenuIdx` initializer, `handleKeydown`'s `which` cast, `data-submenu` selector).

- [ ] **Step 2: Run svelte-check to verify the union widening compiles**

Run: `npm run check`
Expected: 0 errors, 0 warnings.

- [ ] **Step 3: Add the toggle helper in the script block**

After the existing `$: hasContainingCollections = ...` reactive block, add:

```typescript
$: canTag = !item.is_dir && isIndexed && knownSystems.length > 0;

function toggleGameSystem(tag: string) {
  const next = currentTags.includes(tag)
    ? currentTags.filter((t) => t !== tag)
    : [...currentTags, tag];
  onSetGameSystems(next);
}

function clearGameSystems() {
  onSetGameSystems([]);
}
```

- [ ] **Step 4: Add the submenu trigger markup**

In the template, immediately after the `{#if !item.is_dir && isIndexed}` block that contains the *Re-index file* and *Get info* buttons, and before the `{#if canAddToCollection}` block, insert:

```svelte
{#if canTag}
  <hr class="context-divider" />
  <!-- svelte-ignore a11y-mouse-events-have-key-events -->
  <div
    class="context-item submenu-trigger"
    class:open={openSubmenu === 'tag'}
    data-mi="submenu-trigger"
    data-submenu="tag"
    on:mouseenter={() => { openSubmenu = 'tag'; }}
    on:mouseleave={() => { openSubmenu = null; }}
  >
    <span>Game system&hellip;</span>
    <span class="submenu-caret">&#9656;</span>
    {#if openSubmenu === 'tag'}
      <div class="submenu">
        {#each knownSystems as sys}
          <button
            class="context-item"
            data-mi="item"
            on:click={() => toggleGameSystem(sys.tag)}
          >
            <span class="submenu-check">{currentTags.includes(sys.tag) ? '✓' : ''}</span>
            <span>{sys.tag}</span>
          </button>
        {/each}
        {#if currentTags.length > 0}
          <hr class="context-divider" />
          <button class="context-item" data-mi="item" on:click={clearGameSystems}>
            Clear tags
          </button>
        {/if}
      </div>
    {/if}
  </div>
{/if}
```

- [ ] **Step 5: Add CSS for the check column**

In the `<style>` block, after the `.submenu-caret` rule, add:

```css
.submenu-check {
  display: inline-block;
  width: 1rem;
  text-align: center;
  margin-right: 0.25rem;
  color: var(--text-accent);
}
```

- [ ] **Step 6: Verify svelte-check still passes**

Run: `npm run check`
Expected: 0 errors, 0 warnings.

- [ ] **Step 7: Commit**

```bash
git add src/lib/ContextMenu.svelte
git commit -m "Context menu: add Game system submenu

New submenu trigger between Get info and Add to collection that lists
known game systems with check marks for currently-applied tags. Click
toggles. Files only — hidden for folders, unindexed files, or when
knownSystems is empty.

Same submenu-trigger pattern as Add to collection so the kb-focused
fix from #273 applies. Underlying set_game_systems backend is
unchanged; this is a new entry point to an existing handler."
```

---

## Task 2: Wire the new props from the page

**Files:**
- Modify: `src/routes/+page.svelte`

- [ ] **Step 1: Pass the new props to ContextMenu**

Find the `<ContextMenu` instantiation (around line 2986). Add these three lines among the existing props (insertion point: after `containingCollections={...}` and before `excludeFromAdd={...}` is fine):

```svelte
        knownSystems={knownSystems}
        currentTags={effectiveGameSystemMap.get(contextMenu.item.path) ?? []}
        onSetGameSystems={(tags) => handleSetGameSystems(contextMenu.item.path, contextMenu.item.name, tags)}
```

`knownSystems`, `effectiveGameSystemMap`, and `handleSetGameSystems` already exist in `+page.svelte` — no other declarations needed.

- [ ] **Step 2: Verify svelte-check passes**

Run: `npm run check`
Expected: 0 errors, 0 warnings.

- [ ] **Step 3: Commit**

```bash
git add src/routes/+page.svelte
git commit -m "Page: wire Game system submenu props to ContextMenu

Passes knownSystems, the file's current tags, and a wrapper around
the existing handleSetGameSystems handler. No new state — reuses the
optimistic-update path the badge dropdown already uses."
```

---

## Task 3: Remove the now-redundant "+" button from FileTree

**Files:**
- Modify: `src/lib/FileTree.svelte`

- [ ] **Step 1: Remove the "+" button branch**

In `src/lib/FileTree.svelte`, find lines 262-266:

```svelte
    {:else if isIndexed}
      <div class="badge-wrapper">
        <button class="add-tag-btn" on:click={toggleDropdown}>+</button>
      </div>
    {/if}
```

Replace with just:

```svelte
    {/if}
```

(The closing `{/if}` for the outer `{#if hasTag}` stays. The `{:else if isIndexed}` branch is what's removed.)

- [ ] **Step 2: Remove the orphaned CSS**

In the `<style>` block of the same file, find and delete both rules:

```css
  .add-tag-btn {
    display: inline-block;
    padding: 0 0.35rem;
    margin-left: 0.5rem;
    border-radius: 3px;
    font-size: 0.75rem;
    background: transparent;
    color: var(--text-tertiary);
    border: 1px dashed var(--bg-category);
    cursor: pointer;
    line-height: 1.4;
    transition: all var(--transition-fast);
  }
  .add-tag-btn:hover {
    background: rgba(182, 159, 129, 0.1);
    color: var(--text-accent);
    border-color: var(--text-accent);
  }
```

The badge cluster's `toggleDropdown`, `toggleSystem`, `clearSystem`, and the dropdown markup all stay — they're still used by the badge cluster path for tagged files.

- [ ] **Step 3: Verify svelte-check passes**

Run: `npm run check`
Expected: 0 errors, 0 warnings.

- [ ] **Step 4: Commit**

```bash
git add src/lib/FileTree.svelte
git commit -m "FileTree: remove the '+' affordance for untagged files

The dashed '+' button was the awkward retrofit of the badge approach
for the empty-tag case — easy to miss because nothing visible
suggested it was tappable. Now that the context menu's 'Game system…'
submenu serves the same purpose more discoverably, drop the '+' and
its CSS.

Rule: tags visible → click the badge to edit. No tags → right-click
to add."
```

---

## Task 4: Manual smoke + finishing

**Files:** none (verification + final touches)

- [ ] **Step 1: Run dev app**

Run: `npm run tauri dev`

Wait for the window to open and the sidecar to come up.

- [ ] **Step 2: Smoke — indexed-untagged file**

Pick an indexed PDF whose game system the auto-detector hasn't identified (one displaying no badge in the tree row).

Right-click → confirm "Game system…" appears as a submenu trigger between *Get info* and *Add to collection…*.
Hover it → submenu opens with all known systems unchecked.
Click any system → submenu closes (or stays — check the existing Add submenu's behaviour for parity), badge appears in the tree row, no error toast.

- [ ] **Step 3: Smoke — indexed-tagged file**

Pick a tagged file. Right-click → "Game system…" → submenu shows the file's tag(s) with a check mark.
Click the checked tag → check disappears, badge disappears from the row.
Click again → check returns, badge returns.

- [ ] **Step 4: Smoke — guards**

- Right-click a folder → confirm no "Game system…" entry.
- Right-click an unindexed PDF → confirm no "Game system…" entry.
- Right-click on indexed-untagged file from Task 4.2 again → confirm no `+` button anywhere on the tree row (only the new context menu path).

- [ ] **Step 5: Smoke — keyboard nav (regression check for #273)**

Right-click a file. Press ↓ until "Game system…" is highlighted. Press →. Submenu opens with the first system focused. Press ↓ a few times, then ←. Returns to the trigger row, no stuck `.kb-focused` highlight.

- [ ] **Step 6: Push branch and open PR**

```bash
git push -u origin feat/game-system-context-menu
gh pr create --title "Context menu: Game system submenu for any indexed file" --body "$(cat <<'EOF'
## Summary

Closes the v2 release-blocker: an indexed PDF with no auto-detected
game system had no obvious way to receive a first tag. The pre-existing
\`+\` button on indexed-untagged tree rows was small, dashed, and the
user's natural reach for \"do something to this file\" is right-click.

This PR adds a discoverable right-click path while removing the
redundant \`+\` affordance.

Spec: \`docs/frontend/2026-05-10-manual-game-system-tagging-context-menu-design.md\`
Plan: \`docs/frontend/2026-05-10-manual-game-system-tagging-context-menu.md\`

## What changes

- New \"Game system…\" submenu in \`ContextMenu.svelte\` between *Get
  info* and *Add to collection…*. Hover opens a panel listing all
  \`knownSystems\` with check marks for currently-applied tags. Click
  toggles. \"Clear tags\" footer when at least one tag is applied.
- \`+page.svelte\` wires \`knownSystems\`, the file's current tags, and
  a wrapper around the existing \`handleSetGameSystems\` to the
  rendered ContextMenu.
- \`FileTree.svelte\` drops the \`{:else if isIndexed}\` branch that
  rendered the \`+\` button and its CSS. Badge-cluster path unchanged
  for tagged files.

Backend untouched: \`set_game_systems\` already does the metadata flip
with no re-index.

## Test plan

Manual smoke in dev (per the plan):
- [x] svelte-check 0 errors
- [ ] Indexed-untagged file: right-click → Game system… → pick a
      system → badge appears
- [ ] Indexed-tagged file: right-click → Game system… → uncheck the
      current tag → badge disappears; re-check returns it
- [ ] Folder: no \"Game system…\" entry
- [ ] Unindexed PDF: no \"Game system…\" entry
- [ ] No \`+\` button anywhere on tree rows
- [ ] Keyboard nav into and out of the submenu doesn't strand
      \`kb-focused\` (regression check for #273)
EOF
)"
```

---

## Self-Review

**Spec coverage check:**

| Spec section | Implemented in task |
|---|---|
| New submenu trigger between *Get info* and *Add to collection* | Task 1 step 4 |
| Three new props (`knownSystems`, `currentTags`, `onSetGameSystems`) | Task 1 step 1 |
| Submenu shows known systems with check marks | Task 1 step 4 (each loop with `currentTags.includes(sys.tag) ? '✓' : ''`) |
| "Clear tags" footer only when tags applied | Task 1 step 4 (`{#if currentTags.length > 0}`) |
| `isIndexed && !item.is_dir && knownSystems.length > 0` guard | Task 1 step 3 (`canTag` reactive) |
| Page passes the new props | Task 2 step 1 |
| Wraps existing `handleSetGameSystems` (no new handler) | Task 2 step 1 |
| Remove `+` button + CSS in FileTree | Task 3 steps 1–2 |
| Badge cluster, `toggleDropdown`, dropdown markup all stay | Task 3 step 2 (only `add-tag-btn` CSS removed; everything else untouched) |
| Manual smoke covers both first-tag and toggle paths | Task 4 steps 2–3 |
| Edge case: folder/unindexed → submenu hidden | Task 4 step 4 |
| Edge case: knownSystems empty → trigger hidden | Covered by `canTag` guard from Task 1 step 3 |
| Keyboard nav regression check | Task 4 step 5 |

**Placeholder scan:** None — every step has the exact code, exact path, exact command.

**Type consistency:** `KnownGameSystem` imported from `./types`. `currentTags: string[]`, `onSetGameSystems: (tags: string[]) => void`, and `knownSystems: KnownGameSystem[]` consistent across all task steps and the page wiring. The page-side wrapper `(tags) => handleSetGameSystems(...)` matches the prop type.

**Spec coverage gap:** The spec mentioned a Vitest test for "trigger renders for indexed-untagged files and hides for unindexed files." That's been deliberately dropped from the plan because the codebase has no Svelte component testing infrastructure (all existing tests are pure-function). Adding `@testing-library/svelte` for one test is scope creep against the established convention. Manual verification (Task 4) covers the same surface.
