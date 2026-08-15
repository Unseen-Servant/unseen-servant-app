# Systems View Row S/M Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every file row in the systems view an inline S/M cluster on the folder/file axis, retarget bare `S`/`M` to the focused row's file, and lift group toggles to `⇧S`/`⇧M`.

**Architecture:** No algebra changes — row chips are a second render of the tree's folder/file-axis state (`soloedScopePaths`/`mutedScopePaths` + `toggleScopeSolo`/`toggleScopeMute`) threaded into `SystemsView` and converted per-row via the existing `entryToFileItem`. Keyboard dispatch becomes a pure, unit-tested function in `keybindings.ts`; all four gestures run through the existing hold latch (tap latches, hold is momentary). Spec: `docs/frontend/2026-08-13-systems-view-row-sm-design.md`.

**Tech Stack:** Svelte 4 (SvelteKit), TypeScript, vitest, stylelint. No sidecar/backend changes.

**Verification commands:** `npm run test` (vitest), `npm run check` (svelte-check), `npm run lint:css` (stylelint). All three must be green before the final commit.

---

### Task 1: Pure keyboard dispatch — `systemsRowScopeKey`

The decision "which axis and which kind does this S/M keypress mean" becomes a pure function so the untagged rules and the shift grammar are pinned by unit tests, not buried in a component handler.

**Files:**
- Modify: `src/lib/keybindings.ts` (insert after `eventMatchKey`, before the `// The match key for a binding id…` comment, ~line 246)
- Test: `src/lib/keybindings.test.ts` (append a new `describe` at the end of the file)

- [ ] **Step 1: Write the failing tests**

Append to `src/lib/keybindings.test.ts` (the `ev` helper at the top of the file already builds `ChordEvent`s; add `systemsRowScopeKey` to the existing import list from `./keybindings`):

```ts
describe('systemsRowScopeKey', () => {
  test('bare S and M act on the file', () => {
    expect(systemsRowScopeKey(ev({ key: 's' }), false)).toEqual({ axis: 'file', kind: 'solo' });
    expect(systemsRowScopeKey(ev({ key: 'm' }), false)).toEqual({ axis: 'file', kind: 'mute' });
  });

  test('shifted S and M lift to the system', () => {
    expect(systemsRowScopeKey(ev({ key: 'S', shiftKey: true }), false)).toEqual({ axis: 'system', kind: 'solo' });
    expect(systemsRowScopeKey(ev({ key: 'M', shiftKey: true }), false)).toEqual({ axis: 'system', kind: 'mute' });
  });

  test('a capital letter without shift (CapsLock) still acts on the file', () => {
    expect(systemsRowScopeKey(ev({ key: 'S' }), false)).toEqual({ axis: 'file', kind: 'solo' });
  });

  test('untagged: bare S solos the file, shift+S is inert, shift+M still mutes the system', () => {
    expect(systemsRowScopeKey(ev({ key: 's' }), true)).toEqual({ axis: 'file', kind: 'solo' });
    expect(systemsRowScopeKey(ev({ key: 'S', shiftKey: true }), true)).toBeNull();
    expect(systemsRowScopeKey(ev({ key: 'M', shiftKey: true }), true)).toEqual({ axis: 'system', kind: 'mute' });
  });

  test('meta, ctrl, and alt combinations are someone else\'s chord', () => {
    // ⌘S is sync.commit — it must never read as a scope gesture.
    expect(systemsRowScopeKey(ev({ key: 's', metaKey: true }), false)).toBeNull();
    expect(systemsRowScopeKey(ev({ key: 's', ctrlKey: true }), false)).toBeNull();
    expect(systemsRowScopeKey(ev({ key: 'm', altKey: true }), false)).toBeNull();
  });

  test('other keys are not scope chords', () => {
    expect(systemsRowScopeKey(ev({ key: 'x' }), false)).toBeNull();
    expect(systemsRowScopeKey(ev({ key: 'Enter' }), false)).toBeNull();
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npm run test -- src/lib/keybindings.test.ts`
Expected: FAIL — `systemsRowScopeKey` is not exported from `./keybindings`.

- [ ] **Step 3: Implement the helper**

Insert into `src/lib/keybindings.ts` after the closing brace of `eventMatchKey` and before the `// The match key for a binding id, or '' when the binding has no accelerator.` comment:

```ts
// S/M dispatch for a focused systems-view row. Bare letters act on the
// row's file (the folder/file axis — the tree's "act on the row you're
// on" grammar); ⇧S/⇧M lift to the row's group on the systems axis. The
// system axis stays mute-only for the untagged bucket (#307): ⇧S is
// inert there, while bare S still solos the untagged file itself.
// Meta/Ctrl/Alt combinations are someone else's chord (⌘S is sync).
export type SystemsRowScopeAction = {
  axis: 'file' | 'system';
  kind: 'solo' | 'mute';
};

export function systemsRowScopeKey(
  event: ChordEvent,
  untagged: boolean,
): SystemsRowScopeAction | null {
  if (event.metaKey || event.ctrlKey || event.altKey) return null;
  const key = event.key.toLowerCase();
  if (key !== 's' && key !== 'm') return null;
  const kind = key === 's' ? 'solo' : 'mute';
  if (!event.shiftKey) return { axis: 'file', kind };
  if (kind === 'solo' && untagged) return null;
  return { axis: 'system', kind };
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npm run test -- src/lib/keybindings.test.ts`
Expected: PASS (all describes, including the pre-existing ones).

- [ ] **Step 5: Commit**

```bash
git add src/lib/keybindings.ts src/lib/keybindings.test.ts
git commit -m "feat(keys): decide a systems row's S/M chord in one pure place

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Registry entries for the new grammar

The shortcut sheet reads `KEYBINDINGS`. `systems.solo`/`systems.mute` relabel to the file; two new entries document `⇧S`/`⇧M` for the group. They are hint-only (no `match` — `eventMatchKey` deliberately can't express shift, and `SystemsView` dispatches its own keys, like the tree's `⇧F10`), but they DO throw the header's physical squares, so they carry `switch: true` — which requires amending the "never marks a modifier chord" test invariant to "never marks a meta/alt chord" (shift here is a reach modifier on the same 18px square, not a different kind of control).

**Files:**
- Modify: `src/lib/keybindings.ts` (the `// Systems view` section of `KEYBINDINGS`, ~lines 103–107)
- Test: `src/lib/keybindings.test.ts` (the `describe('switch bindings')` block at the end)

- [ ] **Step 1: Update the switch-bindings tests first**

In `src/lib/keybindings.test.ts`, inside `describe('switch bindings', …)`:

Add to the `marks the keys that light a switch` test's expectations, after `expect(ids).toContain('scope.bypass');`:

```ts
    expect(ids).toContain('systems.solo');
    expect(ids).toContain('systems.soloGroup');
    expect(ids).toContain('systems.muteGroup');
```

Replace the entire `never marks a modifier chord` test (comment included) with:

```ts
  // A meta/alt chord is a command, not a switch — a cap would lie about
  // it. Shift is different since 2026-08-13: ⇧S/⇧M throw the systems
  // view's group squares from a file row — the same physical switch,
  // reached with a modifier. The renderer still draws them as text
  // (isBareKeyChord is false for '⇧S'), so no cap lies either way.
  test('never marks a meta or alt chord', () => {
    for (const k of KEYBINDINGS.filter(e => e.switch)) {
      expect(k.keys.mac).not.toMatch(/[⌘⌥⌃]/);
    }
  });
```

- [ ] **Step 2: Run to verify the new expectations fail**

Run: `npm run test -- src/lib/keybindings.test.ts`
Expected: FAIL — `ids` does not contain `systems.soloGroup` / `systems.muteGroup`.

- [ ] **Step 3: Update the registry**

In `src/lib/keybindings.ts`, replace:

```ts
  { id: 'systems.solo',          keys: { mac: 'S',    other: 'S' },             label: "Solo the row's system",        scope: 'systemsView', switch: true },
  { id: 'systems.mute',          keys: { mac: 'M',    other: 'M' },             label: "Mute the row's system",        scope: 'systemsView', switch: true },
```

with:

```ts
  { id: 'systems.solo',          keys: { mac: 'S',    other: 'S' },             label: 'Solo focused row (narrow search to it)', scope: 'systemsView', switch: true },
  { id: 'systems.mute',          keys: { mac: 'M',    other: 'M' },             label: 'Mute focused row (drop from search)',    scope: 'systemsView', switch: true },
  { id: 'systems.soloGroup',     keys: { mac: '⇧S',   other: 'Shift+S' },       label: "Solo the row's system",        scope: 'systemsView', switch: true },
  { id: 'systems.muteGroup',     keys: { mac: '⇧M',   other: 'Shift+M' },       label: "Mute the row's system",        scope: 'systemsView', switch: true },
```

(The bare-letter labels intentionally match `tree.solo`/`tree.mute` word-for-word — same gesture, same words.)

- [ ] **Step 4: Run the full keybindings suite**

Run: `npm run test -- src/lib/keybindings.test.ts`
Expected: PASS. (The `menu accelerators` and `bareness` tests only iterate entries with `match` or a pinned id list — the new hint-only entries don't join either.)

- [ ] **Step 5: Commit**

```bash
git add src/lib/keybindings.ts src/lib/keybindings.test.ts
git commit -m "feat(keys): register the systems view's file and group chords

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Thread the folder/file-axis props into SystemsView

Pure wiring, no rendered change yet. The four props are the same ones `FileTree` rows take.

**Files:**
- Modify: `src/lib/SystemsView.svelte` (props block — insert directly after the `export let scopeBypassed: boolean = false;` line, ~line 58)
- Modify: `src/routes/+page.svelte` (the `<SystemsView` instantiation — find it with `grep -n '<SystemsView' src/routes/+page.svelte`; insert after the `onToggleSystemSolo={toggleSystemSolo}` line)

- [ ] **Step 1: Add the four exports to SystemsView**

Insert after the `scopeBypassed` export (keep the existing comment style — "Collection-axis" is the name `FileTree.svelte:46` and `ContextMenu.svelte:16` already use for this axis):

```ts
  // Collection-axis S/M for the row's file — the same four props the
  // tree rows take. Lit state is path-keyed, so a multi-tagged file
  // lights under every group it appears in.
  export let soloedScopePaths: Set<string> = new Set();
  export let mutedScopePaths: Set<string> = new Set();
  export let onToggleScopeSolo: (item: FileItem) => void = () => {};
  export let onToggleScopeMute: (item: FileItem) => void = () => {};
```

(`FileItem` is already imported at the top of the file.)

- [ ] **Step 2: Pass them at the page instantiation**

In `src/routes/+page.svelte`, inside the `<SystemsView … />` block, after `onToggleSystemSolo={toggleSystemSolo}`, add:

```svelte
            {soloedScopePaths}
            {mutedScopePaths}
            onToggleScopeSolo={toggleScopeSolo}
            onToggleScopeMute={toggleScopeMute}
```

(`soloedScopePaths`/`mutedScopePaths` are the derived sets at `+page.svelte:1648-1649`; `toggleScopeSolo`/`toggleScopeMute` are the same handlers the `FileTree` instantiation below already receives.)

- [ ] **Step 3: Verify types**

Run: `npm run check`
Expected: 0 errors, 0 warnings (unused-export warnings do not occur — Svelte props are consumed by the instantiation).

- [ ] **Step 4: Commit**

```bash
git add src/lib/SystemsView.svelte src/routes/+page.svelte
git commit -m "feat(scope): thread the file axis into the systems view

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: The row cluster — markup and CSS

Every row gets the S/M pair (every row is indexed by construction, so there is no gate), right-aligned before the indexed-time meta so engaged chips form one console column under the header's cluster. Reveal follows the established rule: hidden at rest; row hover, focus-within, keyboard focus, or an engaged chip reveals.

**Files:**
- Modify: `src/lib/SystemsView.svelte` (row template + `<style>`)

- [ ] **Step 1: Add the lit-state consts**

In the row `{#each}`, after `{@const ribbonSplit = splitRibbons(ribbons)}`, add:

```svelte
              {@const rowSoloed = soloedScopePaths.has(entry.path)}
              {@const rowMuted = mutedScopePaths.has(entry.path)}
```

- [ ] **Step 2: Insert the cluster before the meta**

Directly before the `{#if entry.indexed_at}` block in the row template, add:

```svelte
                <span class="sm" class:engaged={rowSoloed || rowMuted}>
                  <button
                    type="button"
                    class="sm-btn"
                    class:solo-on={rowSoloed}
                    on:click|stopPropagation={() => onToggleScopeSolo(entryToFileItem(entry))}
                    on:mousedown|stopPropagation
                    on:dblclick|stopPropagation
                    aria-pressed={rowSoloed}
                    title={rowSoloed ? `Stop soloing ${entry.filename} (S)` : `Solo ${entry.filename} (S)`}
                  >S</button>
                  <button
                    type="button"
                    class="sm-btn"
                    class:mute-on={rowMuted}
                    on:click|stopPropagation={() => onToggleScopeMute(entryToFileItem(entry))}
                    on:mousedown|stopPropagation
                    on:dblclick|stopPropagation
                    aria-pressed={rowMuted}
                    title={rowMuted ? `Unmute ${entry.filename} (M)` : `Mute ${entry.filename} (M)`}
                  >M</button>
                </span>
```

(`mousedown`/`dblclick` are stopped because the row itself handles both — same guards the `row-checkbox` uses. `.sm-btn` anatomy, including `solo-on`/`mute-on` colors, is shared app-wide from `app.css` — no new color rules here.)

- [ ] **Step 3: CSS — reveal, right-alignment**

In the `<style>` block, replace:

```css
  .group-head-row:hover .sm,
  .group-head-row:focus-within .sm,
  .sm.engaged {
    opacity: 1;
  }
```

with:

```css
  .group-head-row:hover .sm,
  .group-head-row:focus-within .sm,
  .file:hover .sm,
  .file:focus-within .sm,
  .file.focused .sm,
  .sm.engaged {
    opacity: 1;
  }
```

Then add, after the `.file.hidden-item .file-name` rule:

```css
  /* The row cluster keeps the flush-right slot: it carries the auto
     margin the meta used to, so chips and readout pack together on the
     right edge, one console column under the header's own cluster. */
  .file .sm {
    margin-left: auto;
  }
```

And in the `.file-meta` rule, delete the `margin-left: auto;` line (the cluster now carries it; the row's `gap: 0.4rem` separates chips from readout).

- [ ] **Step 4: Verify**

Run: `npm run check && npm run lint:css`
Expected: both clean (the new CSS introduces no raw color values).

- [ ] **Step 5: Commit**

```bash
git add src/lib/SystemsView.svelte
git commit -m "feat(scope): give systems-view rows their channel S/M

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Keyboard retarget + header hints

Bare `S`/`M` act on the focused row's file; `⇧S`/`⇧M` lift to the group. All four through the hold latch under the existing `'s'`/`'m'` ids — the page-level `keyup` release lowercases `event.key`, so a held `⇧S` releases the same latch with no extra wiring.

**Files:**
- Modify: `src/lib/SystemsView.svelte` (imports, `handleWindowKey`, header button titles)
- Modify: `src/routes/+page.svelte` (one stale comment)

- [ ] **Step 1: Import the dispatcher**

In `src/lib/SystemsView.svelte`'s imports, after `import { holdLatch } from './holdLatch';`, add:

```ts
  import { systemsRowScopeKey } from './keybindings';
```

- [ ] **Step 2: Replace the S/M block in `handleWindowKey`**

Replace this exact block (~lines 393–409):

```ts
    // S / M toggle solo / mute for the focused row's group — same
    // bare-letter guard as j/k. Untagged gets no solo (untagged files
    // never pass under solos) and mutes under the backend's key.
    if (bareLetter && lk === 's' && focused.tag !== 'Untagged') {
      event.preventDefault();
      if (event.repeat) return;
      const tag = focused.tag;
      holdLatch.press('s', () => onToggleSystemSolo(tag));
      return;
    }
    if (bareLetter && lk === 'm') {
      event.preventDefault();
      if (event.repeat) return;
      const key = focused.tag === 'Untagged' ? UNTAGGED_KEY : focused.tag;
      holdLatch.press('m', () => onToggleSystemFilter(key));
      return;
    }
```

with:

```ts
    // S / M — bare letters solo/mute the focused row's file (the tree's
    // grammar: act on the row you're on); ⇧S/⇧M lift to the row's group.
    // All four are hold-latch keys: tap latches, hold is momentary. The
    // system axis stays mute-only for Untagged (#307), so ⇧S is inert
    // there — while bare S still solos the untagged file itself.
    const scopeAction = systemsRowScopeKey(event, focused.tag === 'Untagged');
    if (scopeAction) {
      event.preventDefault();
      if (event.repeat) return;
      const latchId = scopeAction.kind === 'solo' ? 's' : 'm';
      if (scopeAction.axis === 'file') {
        const item = entryToFileItem(focused.entry);
        holdLatch.press(latchId, () =>
          scopeAction.kind === 'solo' ? onToggleScopeSolo(item) : onToggleScopeMute(item),
        );
      } else if (scopeAction.kind === 'solo') {
        const tag = focused.tag;
        holdLatch.press(latchId, () => onToggleSystemSolo(tag));
      } else {
        const key = focused.tag === 'Untagged' ? UNTAGGED_KEY : focused.tag;
        holdLatch.press(latchId, () => onToggleSystemFilter(key));
      }
      return;
    }
```

(`bareLetter` and `lk` remain in use by the surrounding j/k and X handlers — do not remove them.)

- [ ] **Step 3: Header titles gain the shift hints**

In the group-header cluster, the four title strings change `(S)`→`(⇧S)` and `(M)`→`(⇧M)`:

```svelte
                title={soloedSystems.has(group.tag) ? `Stop soloing ${group.tag} (⇧S)` : `Solo ${group.tag} (⇧S)`}
```

```svelte
              title={group.muted ? `Unmute ${smLabel} (⇧M)` : `Mute ${smLabel} (⇧M)`}
```

- [ ] **Step 4: Fix the stale page comment**

In `src/routes/+page.svelte` (~line 2089), the tree-handler comment ends "…in systems view they fall through to SystemsView's own handler, which works the systems axis." Replace that final clause so it reads:

```
      // S/M are the one narrowing model on both axes. In tree view they
      // solo/mute the focused row on the collection axis; in systems
      // view they fall through to SystemsView's own handler — bare
      // letters work the focused file, ⇧S/⇧M its group. The context
      // menu moves to Shift+F10 / the Menu key (M used to open it).
```

- [ ] **Step 5: Verify**

Run: `npm run check && npm run test`
Expected: both green.

- [ ] **Step 6: Commit**

```bash
git add src/lib/SystemsView.svelte src/routes/+page.svelte
git commit -m "feat(scope): bare S/M work the row, shift lifts to the group

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Docs — status flip, changelog, QA handoff

**Files:**
- Modify: `docs/frontend/2026-08-13-systems-view-row-sm-design.md` (Status line)
- Modify: `CHANGELOG.md` (`## [Unreleased]` → end of the `### Changed` list)

- [ ] **Step 1: Flip the design doc status**

Replace `**Status:** Designed; implementation pending.` with:

```
**Status:** Implemented 2026-08-13 on main (automated checks green;
manual QA pending — see Testing).
```

- [ ] **Step 2: Changelog entry**

Append to the end of the `### Changed` bullet list under `## [Unreleased]` (locate the section end with the next `##` heading):

```markdown
- **The systems view's rows are channels.** Every file row in the by-system view carries its own S/M pair beside the system's, so the view works as the asset library it is: solo or mute one book without leaving it. Bare `S`/`M` on a focused row act on the file; `⇧S`/`⇧M` still throw the system's switches, and holding any of them stays momentary. Untagged books can finally be soloed — one at a time, as files
```

- [ ] **Step 3: Full verification**

Run: `npm run test && npm run check && npm run lint:css`
Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add docs/frontend/2026-08-13-systems-view-row-sm-design.md CHANGELOG.md
git commit -m "docs(scope): record rows-as-channels as shipped

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

- [ ] **Step 5: Hand the manual QA list to the user**

Do not launch the app (project convention — the user drives their own instance). Report these checks from the design doc's Testing section for the user to run:

1. Chips reveal on row hover and keyboard focus; engaged chips stay visible at rest.
2. Bare `S`/`M` on a focused row toggle the row's own chip; `⇧S`/`⇧M` toggle the header cluster.
3. Hold `S` on a row: solo engages only while held, snaps back on release.
4. Solo a group header, then solo a row in another group → "Nothing under the soloed items." and the scope-bar meter reads "… of 0 files".
5. Tap `B`: row dims lift, engaged chips stay lit.
6. A multi-tagged file's chip lights under every group it appears in.
7. An Untagged row solos with `S`; `⇧S` does nothing on it; `⇧M` mutes the untagged bucket.

---

## Self-review notes

- **Spec coverage:** decision statement (Task 4+5), cluster placement/reveal (Task 4), keyboard grammar + hold latch + untagged (Tasks 1, 5), registry (Task 2), display/bypass (inherited — no code needed, verified by QA items 5), collision narration (pre-existing, QA item 4), doctrine amendments (already committed with the design doc), testing (Tasks 1, 2, QA list).
- **Consistency:** `SystemsRowScopeAction` uses `axis: 'file' | 'system'` everywhere; latch ids stay `'s'`/`'m'`; props named exactly as `FileTree`'s.
- **Known non-goals honored:** no shared cluster component, no header keyboard focus, no exclusive solo, no backend changes.
