# Systems View Row-Grain Dim Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dim individual systems-view rows by resolved-scope membership (mute one file → that row dims; solo one file → its shelf-mates dim), and make the focus lens drop out-of-scope rows, matching the tree.

**Architecture:** One shared predicate (`isIndexedRowOutOfScope` in `treeNav.ts`) consumed by both the template and the keyboard nav so render and nav never drift. Row dim is gated on the group being bright so dims never stack. No algebra changes; `searchScope.ts` untouched. Spec: the "Row-grain dim (amended 2026-08-14)" section of `docs/frontend/2026-08-13-systems-view-row-sm-design.md`.

**Tech Stack:** Svelte 4, TypeScript, vitest, stylelint.

**Verification:** `npm run test`, `npm run check`, `npm run lint:css` — all green before each commit.

---

### Task 1: Predicate — `isIndexedRowOutOfScope` (TDD)

**Files:**
- Modify: `src/lib/treeNav.ts` (insert directly after `isRowOutOfScope`)
- Test: `src/lib/treeNav.test.ts` (append a describe)

- [ ] **Step 1: Write the failing tests.** Append to `src/lib/treeNav.test.ts`, adding `isIndexedRowOutOfScope` to the existing import from `./treeNav`:

```ts
describe('isIndexedRowOutOfScope', () => {
  test('no narrowing engaged (null bright set) — nothing is out of scope', () => {
    expect(isIndexedRowOutOfScope('/a.pdf', null)).toBe(false);
  });

  test('a row in the bright set is in scope', () => {
    expect(isIndexedRowOutOfScope('/a.pdf', new Set(['/a.pdf']))).toBe(false);
  });

  test('a row outside the bright set is out of scope', () => {
    expect(isIndexedRowOutOfScope('/a.pdf', new Set(['/b.pdf']))).toBe(true);
  });

  test('an empty bright set puts every row out of scope', () => {
    expect(isIndexedRowOutOfScope('/a.pdf', new Set())).toBe(true);
  });
});
```

- [ ] **Step 2:** `npm run test -- src/lib/treeNav.test.ts` — expect FAIL (not exported).

- [ ] **Step 3: Implement.** Insert into `src/lib/treeNav.ts` after the closing brace of `isRowOutOfScope`:

```ts
/** A systems-view row is indexed by construction, so out-of-scope
 * reduces to bright-set membership (null = no narrowing engaged,
 * nothing dims). Lives beside isRowOutOfScope so every surface's dim
 * predicate stays in this one module; SystemsView's template and its
 * keyboard nav both call it, so render and nav can never drift. */
export function isIndexedRowOutOfScope(
  path: string,
  scopeBrightPaths: Set<string> | null,
): boolean {
  return scopeBrightPaths !== null && !scopeBrightPaths.has(path);
}
```

- [ ] **Step 4:** `npm run test -- src/lib/treeNav.test.ts` — expect PASS.

- [ ] **Step 5: Commit.**

```bash
git add src/lib/treeNav.ts src/lib/treeNav.test.ts
git commit -m "feat(scope): reduce a systems row's dim to bright-set membership

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: SystemsView wiring — dim class, lens, CSS

**Files:**
- Modify: `src/lib/SystemsView.svelte`

- [ ] **Step 1: Import.** Extend the existing treeNav import (or add one if none exists) so `isIndexedRowOutOfScope` is imported from `./treeNav`.

- [ ] **Step 2: Keyboard nav mirrors the lens.** In the `$: visibleEntries` derivation, replace the inner loop:

```ts
      for (const e of g.entries) out.push({ path: e.path, entry: e, tag: g.tag });
```

with:

```ts
      for (const e of g.entries) {
        if (hideOutOfScope && isIndexedRowOutOfScope(e.path, scopeBrightPaths)) continue;
        out.push({ path: e.path, entry: e, tag: g.tag });
      }
```

and update the comment above the derivation: the clause "Mirrors the template's lens guard via isGroupDimmed" becomes "Mirrors the template's lens guards via isGroupDimmed and isIndexedRowOutOfScope".

- [ ] **Step 3: Template.** In the row `{#each}`:

(a) After `{@const rowMuted = mutedScopePaths.has(entry.path)}`, add:

```svelte
              {@const rowOutOfScope = isIndexedRowOutOfScope(entry.path, scopeBrightPaths)}
```

(b) Wrap the row in the lens guard, same no-reindent pattern the group `<section>` wrapper uses: directly before the `<!-- svelte-ignore a11y-click-events-have-key-events a11y-no-noninteractive-element-interactions -->` comment add a line:

```svelte
              {#if !(hideOutOfScope && rowOutOfScope)}
```

and directly after the row's closing `</li>` add:

```svelte
              {/if}
```

Do NOT re-indent the `<li>` body.

(c) On the `<li class="file"` element, after the `class:hidden-item={...}` line, add:

```svelte
                class:out-of-scope={rowOutOfScope && !groupDimmed}
```

- [ ] **Step 4: CSS.** Directly after the `.group-files.dimmed:hover > .file > :not(.sm)` rule, add:

```css
  /* A row out of the resolved scope dims inside a bright group — the
     surface's grain became the row when rows became channels. The
     class is gated on the group being bright, so dims never stack; a
     dimmed group dims as one. Chips stay lit: same :not(.sm) grammar. */
  .file.out-of-scope > :not(.sm) {
    opacity: var(--opacity-out-of-scope);
    transition: opacity var(--transition-fast);
  }
  .file.out-of-scope:hover > :not(.sm) {
    opacity: var(--opacity-out-of-scope-hover);
  }
```

- [ ] **Step 5: Verify.** `npm run check` (0/0), `npm run lint:css` (clean), `npm run test` (all passing).

- [ ] **Step 6: Commit.**

```bash
git add src/lib/SystemsView.svelte
git commit -m "feat(scope): dim the systems view at the row, like the tree

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Docs — QA items and changelog

**Files:**
- Modify: `docs/frontend/2026-08-13-systems-view-row-sm-design.md` (Testing list)
- Modify: `CHANGELOG.md`

- [ ] **Step 1: QA items.** In the design doc's Testing section, the manual-QA sentence currently ends "untagged rows solo while `⇧S` stays inert." Extend the list so it ends: "untagged rows solo while `⇧S` stays inert; muting one file dims that row (in every group it appears under) with M lit; soloing one file dims its same-group shelf-mates; the lens hides out-of-scope rows; bypass lifts row dims."

- [ ] **Step 2: Changelog.** Append as the LAST bullet of `## [Unreleased]` → `### Changed`:

```markdown
- **A muted book dims where it stands.** Muting a single file in the by-system view now dims that row — in every system it appears under — and soloing one file dims its shelf-mates, so the view reads scope at the row the way the tree does, instead of only at the whole system. The focus lens likewise hides out-of-scope rows, not just whole systems
```

- [ ] **Step 3: Verify.** `npm run test && npm run check && npm run lint:css` — all green.

- [ ] **Step 4: Commit.**

```bash
git add docs/frontend/2026-08-13-systems-view-row-sm-design.md CHANGELOG.md
git commit -m "docs(scope): record the row-grain dim amendment as shipped

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Self-review notes

- Spec coverage: predicate + shared-consumption (Task 1, 2), row dim gated on bright group (Task 2 step 3c), lens rows (Task 2 steps 2, 3b), no-stack CSS (Task 2 step 4), bypass-lift (free — bypass nulls `scopeBrightPaths`), QA + changelog (Task 3). Doctrine amendments already committed with the spec.
- Group counts intentionally untouched (doctrine: channel meters stay whole-library).
- Empty-state: a bright group cannot lens-lose all rows (a group with no in-scope file is already group-dimmed), so no new empty-state work.
