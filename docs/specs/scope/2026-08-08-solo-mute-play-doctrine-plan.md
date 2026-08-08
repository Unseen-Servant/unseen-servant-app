# SOLO / MUTE / PLAY Doctrine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rework the scope model so playing collections define the mix that every S/M narrows within, add mute to collections, unify out-of-scope dimming across surfaces behind one token pair, add the opt-in focus lens that hides out-of-scope rows on browsing surfaces, and persist the whole console.

**Architecture:** Pure resolution functions live in `src/lib/searchScope.ts` (new: `resolveMix`, `passesSystemsAxis`, `resolveScopeSet`); `+page.svelte` composes them for both the backend filters and a display-side `resolvedScopeSet` that drives counts and dimming. Components receive inert-by-default props first, then one page-level task wires everything. Persistence is a defensively-parsed single store key.

**Tech Stack:** Svelte 4 (SvelteKit), TypeScript, Vitest, tauri-plugin-store. No sidecar/backend changes.

**Spec:** `docs/specs/scope/2026-08-08-solo-mute-play-doctrine-design.md` — read it first; it defines the algebra, gesture grammar, display doctrine, and empty-state strings this plan implements.

**Verification commands** (used throughout):

- `npx vitest run src/lib/searchScope.test.ts` — scope unit tests
- `npm test` — full vitest suite
- `npm run check` — svelte-check (type + template errors)
- `npm run lint:css` — stylelint token rule

**Naming trap:** in current code, `soloCollections`/`mutedCollections` in `+page.svelte` are Maps of **folder/file paths** (the tree's S/M), NOT collections. Task 4 renames them to `scopeSolos`/`scopeMutes` before the new collection-name state lands. Do not skip Task 4.

---

### Task 1: `resolveMix` — the transport layer as a pure function

**Files:**
- Modify: `src/lib/searchScope.ts`
- Test: `src/lib/searchScope.test.ts`

- [ ] **Step 1: Write the failing tests**

Append to `src/lib/searchScope.test.ts` (add `resolveMix` to the existing import from `./searchScope`):

```ts
describe('resolveMix', () => {
  const COLS = {
    Strahd: { file_paths: ['/lib/strahd.pdf', '/lib/shared.pdf'] },
    Homebrew: { file_paths: ['/lib/brew.pdf', '/lib/shared.pdf'] },
    Ghost: { file_paths: ['/gone/x.pdf'] },
  };
  const INDEXED = new Set([
    '/lib/strahd.pdf',
    '/lib/shared.pdf',
    '/lib/brew.pdf',
    '/lib/loose.pdf',
  ]);

  it('returns null when the transport is idle and nothing is muted', () => {
    expect(resolveMix(new Set(), new Set(), COLS, INDEXED)).toBeNull();
  });

  it('playing collections union their indexed files', () => {
    const out = resolveMix(new Set(['Strahd', 'Homebrew']), new Set(), COLS, INDEXED);
    expect([...out!].sort()).toEqual(['/lib/brew.pdf', '/lib/shared.pdf', '/lib/strahd.pdf']);
  });

  it('idle transport with a muted collection carves it from the whole library', () => {
    const out = resolveMix(new Set(), new Set(['Homebrew']), COLS, INDEXED);
    expect([...out!].sort()).toEqual(['/lib/loose.pdf', '/lib/strahd.pdf']);
  });

  it('mute wins over play — a playing, muted collection contributes nothing', () => {
    const out = resolveMix(new Set(['Strahd']), new Set(['Strahd']), COLS, INDEXED);
    expect(out).toEqual(new Set());
  });

  it('a file in both a playing and a muted collection is carved out', () => {
    const out = resolveMix(new Set(['Strahd']), new Set(['Homebrew']), COLS, INDEXED);
    expect([...out!]).toEqual(['/lib/strahd.pdf']);
  });

  it('playing a collection with no indexed files yields an empty mix, not the library', () => {
    expect(resolveMix(new Set(['Ghost']), new Set(), COLS, INDEXED)).toEqual(new Set());
  });

  it('stale collection names resolve away harmlessly', () => {
    expect(resolveMix(new Set(['Missing']), new Set(), COLS, INDEXED)).toEqual(new Set());
    const idleMuted = resolveMix(new Set(), new Set(['Missing']), COLS, INDEXED);
    expect(idleMuted).toEqual(INDEXED);
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npx vitest run src/lib/searchScope.test.ts`
Expected: FAIL — `resolveMix` is not exported.

- [ ] **Step 3: Implement `resolveMix`**

Append to `src/lib/searchScope.ts`:

```ts
/** Resolve the transport layer to the mix — the universe every
 * narrowing axis filters within.
 *
 * base = union of playing collections' indexed files (the whole library
 * when the transport is idle); muted collections' files subtract from
 * the base. Mute wins over play while lit — a playing, muted collection
 * contributes nothing, and a file reached by both a playing and a muted
 * collection is out (mute is a carve on the mix, not a per-track
 * fader). Returns null when the transport is idle and no collection is
 * muted: no mix narrowing, the universe is the whole indexed library. */
export function resolveMix(
  playing: Set<string>,
  mutedNames: Set<string>,
  collections: Record<string, { file_paths: string[] }>,
  allIndexed: Set<string>
): Set<string> | null {
  if (playing.size === 0 && mutedNames.size === 0) return null;
  const base = new Set<string>();
  if (playing.size > 0) {
    for (const name of playing) {
      const col = collections[name];
      if (!col) continue;
      for (const p of col.file_paths) if (allIndexed.has(p)) base.add(p);
    }
  } else {
    for (const p of allIndexed) base.add(p);
  }
  for (const name of mutedNames) {
    const col = collections[name];
    if (!col) continue;
    for (const p of col.file_paths) base.delete(p);
  }
  return base;
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npx vitest run src/lib/searchScope.test.ts`
Expected: PASS (all existing tests still green).

- [ ] **Step 5: Commit**

```bash
git add src/lib/searchScope.ts src/lib/searchScope.test.ts
git commit -m "feat(scope): resolveMix — playing/muted collections resolve to the mix layer"
```

---

### Task 2: `passesSystemsAxis` — extract the per-file systems predicate

**Files:**
- Modify: `src/lib/searchScope.ts`
- Test: `src/lib/searchScope.test.ts`

This extracts the tag logic currently inlined in `+page.svelte`'s `searchableFileCount` (lines ~353–363) so the count and the display scope share one tested predicate. Task 11 deletes the inline copy.

- [ ] **Step 1: Write the failing tests**

Append to `src/lib/searchScope.test.ts` (import `passesSystemsAxis`):

```ts
describe('passesSystemsAxis', () => {
  const none = new Set<string>();

  it('everything passes when nothing is engaged', () => {
    expect(passesSystemsAxis(['D&D 5E'], none, none)).toBe(true);
    expect(passesSystemsAxis([], none, none)).toBe(true);
  });

  it('under solos only files with a soloed tag pass', () => {
    const solo = new Set(['D&D 5E']);
    expect(passesSystemsAxis(['D&D 5E', 'Dragonbane'], solo, none)).toBe(true);
    expect(passesSystemsAxis(['Dragonbane'], solo, none)).toBe(false);
  });

  it('untagged files never pass under solos', () => {
    expect(passesSystemsAxis([], new Set(['D&D 5E']), none)).toBe(false);
  });

  it('under mutes a file passes while it keeps one unmuted tag', () => {
    const muted = new Set(['Dragonbane']);
    expect(passesSystemsAxis(['Dragonbane', 'D&D 5E'], none, muted)).toBe(true);
    expect(passesSystemsAxis(['Dragonbane'], none, muted)).toBe(false);
  });

  it('untagged files pass under mutes unless the Untagged bucket is muted (#307)', () => {
    expect(passesSystemsAxis([], none, new Set(['Dragonbane']))).toBe(true);
    expect(passesSystemsAxis([], none, new Set([UNTAGGED_KEY]))).toBe(false);
  });

  it('solo overrides mute', () => {
    const solo = new Set(['Dragonbane']);
    const muted = new Set(['Dragonbane']);
    expect(passesSystemsAxis(['Dragonbane'], solo, muted)).toBe(true);
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `npx vitest run src/lib/searchScope.test.ts`
Expected: FAIL — `passesSystemsAxis` is not exported.

- [ ] **Step 3: Implement**

Append to `src/lib/searchScope.ts`:

```ts
/** Frontend mirror of the systems-axis include-list semantics for a
 * single file's tags: under solos only soloed systems pass (untagged
 * files never do); under mutes a file passes while it keeps at least
 * one unmuted tag, and untagged files pass unless the Untagged bucket
 * itself is muted (issue #307). */
export function passesSystemsAxis(
  tags: string[],
  soloed: Set<string>,
  muted: Set<string>
): boolean {
  if (soloed.size > 0) return tags.some((t) => soloed.has(t));
  if (tags.length === 0) return !muted.has(UNTAGGED_KEY);
  return tags.some((t) => !muted.has(t));
}
```

- [ ] **Step 4: Run to verify pass**

Run: `npx vitest run src/lib/searchScope.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/lib/searchScope.ts src/lib/searchScope.test.ts
git commit -m "feat(scope): passesSystemsAxis — per-file systems predicate extracted for reuse"
```

---

### Task 3: `resolveScopeSet` — full console resolution

**Files:**
- Modify: `src/lib/searchScope.ts`
- Test: `src/lib/searchScope.test.ts`

One function resolves mix + all three axes to the set of in-scope files. `runSearch` calls it with empty system sets (the backend applies `game_systems` per chunk); display calls it with the real system state. Folder/file solo sets are intersected with the universe **inside** this function — that is the Strahd/Bestiary intersect the whole redesign exists for.

- [ ] **Step 1: Write the failing tests**

Append to `src/lib/searchScope.test.ts` (import `resolveScopeSet`):

```ts
describe('resolveScopeSet', () => {
  const INDEXED = new Set([
    '/lib/strahd/map.pdf',
    '/lib/bestiary/dragons.pdf',
    '/lib/bestiary/undead.pdf',
    '/lib/loose.pdf',
  ]);
  const TAGS = new Map<string, string[]>([
    ['/lib/strahd/map.pdf', ['D&D 5E']],
    ['/lib/bestiary/dragons.pdf', ['D&D 5E']],
    ['/lib/bestiary/undead.pdf', ['Dragonbane']],
  ]);
  const COLLECTED = new Set(['/lib/strahd/map.pdf', '/lib/bestiary/undead.pdf']);
  const BESTIARY = ['/lib/bestiary/dragons.pdf', '/lib/bestiary/undead.pdf'];
  const noStr = new Set<string>();
  const noCur = new Set<CurationKey>();

  const resolve = (
    mix: Set<string> | null,
    soloSets: string[][] = [],
    muteSets: string[][] = [],
    opts: Partial<{
      curationSolos: Set<CurationKey>;
      curationMutes: Set<CurationKey>;
      soloedSystems: Set<string>;
      mutedSystems: Set<string>;
    }> = {}
  ) =>
    resolveScopeSet(
      mix,
      soloSets,
      muteSets,
      opts.curationSolos ?? noCur,
      opts.curationMutes ?? noCur,
      COLLECTED,
      opts.soloedSystems ?? noStr,
      opts.mutedSystems ?? noStr,
      TAGS,
      INDEXED
    );

  it('returns null when nothing is engaged anywhere', () => {
    expect(resolve(null)).toBeNull();
  });

  it('a mix alone IS the scope', () => {
    const mix = new Set(['/lib/strahd/map.pdf']);
    expect(resolve(mix)).toEqual(mix);
  });

  it('a folder solo intersects the playing mix — the Strahd/Bestiary case', () => {
    const mix = new Set(['/lib/strahd/map.pdf', '/lib/bestiary/undead.pdf']);
    const out = resolve(mix, [BESTIARY]);
    expect(out).toEqual(new Set(['/lib/bestiary/undead.pdf']));
  });

  it('a solo with nothing inside the mix resolves empty, not to the solo', () => {
    const mix = new Set(['/lib/strahd/map.pdf']);
    expect(resolve(mix, [BESTIARY])).toEqual(new Set());
  });

  it('mutes carve within the mix', () => {
    const mix = new Set(['/lib/strahd/map.pdf', '/lib/bestiary/dragons.pdf']);
    const out = resolve(mix, [], [['/lib/bestiary/dragons.pdf']]);
    expect(out).toEqual(new Set(['/lib/strahd/map.pdf']));
  });

  it('the curation axis intersects within the mix', () => {
    const mix = new Set(['/lib/strahd/map.pdf', '/lib/bestiary/dragons.pdf']);
    const out = resolve(mix, [], [], { curationSolos: new Set<CurationKey>(['collected']) });
    expect(out).toEqual(new Set(['/lib/strahd/map.pdf']));
  });

  it('the systems axis intersects within the mix', () => {
    const mix = new Set(['/lib/bestiary/dragons.pdf', '/lib/bestiary/undead.pdf']);
    const out = resolve(mix, [], [], { soloedSystems: new Set(['Dragonbane']) });
    expect(out).toEqual(new Set(['/lib/bestiary/undead.pdf']));
  });

  it('axes narrow the whole library when no mix is armed', () => {
    const out = resolve(null, [BESTIARY]);
    expect(out).toEqual(new Set(BESTIARY));
  });

  it('with empty system sets and an untagged file, the file survives (runSearch mode)', () => {
    const out = resolve(null, [], [['/lib/strahd/map.pdf']]);
    expect(out!.has('/lib/loose.pdf')).toBe(true);
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `npx vitest run src/lib/searchScope.test.ts`
Expected: FAIL — `resolveScopeSet` is not exported.

- [ ] **Step 3: Implement**

Append to `src/lib/searchScope.ts`:

```ts
/** Resolve the full console — mix plus all three narrowing axes — to
 * the set of indexed files search can currently see.
 *
 * Solo sets are intersected with the universe (the mix, or the whole
 * library when no mix is armed) before the axis resolves: soloing a
 * folder while a collection plays narrows to the folder's slice of the
 * mix, never adds material to it. Mute sets need no restriction —
 * subtraction composes on its own. Callers that want backend-shaped
 * path filtering (runSearch) pass empty system sets and an empty tag
 * map; the sidecar applies `game_systems` per chunk.
 *
 * Returns null when nothing is engaged anywhere: no narrowing, every
 * indexed file is in scope. */
export function resolveScopeSet(
  mix: Set<string> | null,
  soloSets: string[][],
  muteSets: string[][],
  curationSolos: Set<CurationKey>,
  curationMutes: Set<CurationKey>,
  collectedPaths: Set<string>,
  soloedSystems: Set<string>,
  mutedSystems: Set<string>,
  tagsByPath: Map<string, string[]>,
  allIndexed: Set<string>
): Set<string> | null {
  const noAxes =
    soloSets.length === 0 &&
    muteSets.length === 0 &&
    curationSolos.size === 0 &&
    curationMutes.size === 0 &&
    soloedSystems.size === 0 &&
    mutedSystems.size === 0;
  if (mix === null && noAxes) return null;
  const universe = mix ?? allIndexed;
  const soloInUniverse = soloSets.map((s) => s.filter((p) => universe.has(p)));
  let paths: Iterable<string> =
    searchSourcePathsFilter(soloInUniverse, muteSets, universe) ?? universe;
  const curation = searchCurationFilter(curationSolos, curationMutes, collectedPaths, paths);
  if (curation !== null) paths = curation;
  const out = new Set<string>();
  for (const p of paths) {
    if (passesSystemsAxis(tagsByPath.get(p) ?? [], soloedSystems, mutedSystems)) out.add(p);
  }
  return out;
}
```

- [ ] **Step 4: Run to verify pass**

Run: `npx vitest run src/lib/searchScope.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/lib/searchScope.ts src/lib/searchScope.test.ts
git commit -m "feat(scope): resolveScopeSet — mix-then-narrow resolution for search and display"
```

---

### Task 4: Rename the path-keyed S/M state in `+page.svelte`

**Files:**
- Modify: `src/routes/+page.svelte`

Mechanical rename so the collection-name mute state added in Task 11 can't be confused with the path-keyed maps: `soloCollections` → `scopeSolos`, `mutedCollections` → `scopeMutes`. This matches the existing derived names (`soloedScopePaths`, `mutedScopePaths`) and handlers (`toggleScopeSolo`, `toggleScopeMute`). The rename is confined to `+page.svelte` — no child component prop is named `soloCollections`/`mutedCollections` (the scope-bar props `collectionSolos`/`collectionMutes` are different, derived values; leave them).

- [ ] **Step 1: Rename all occurrences**

In `src/routes/+page.svelte`, replace every occurrence of the identifier `soloCollections` with `scopeSolos` and `mutedCollections` with `scopeMutes` (declaration at ~lines 159–160, comment at ~148, chip deriveds at ~267–279, `computeCollectionAxisInclude` call sites at ~330 and ~386, empty-state check at ~405, `toggleScopeSolo`/`toggleScopeMute` at ~827–845, `clearAllFilters` at ~867–868, `highlightPaths`/`mutedScopePaths`/`soloedScopePaths` deriveds at ~1400–1416, and any others `grep -n "soloCollections\|mutedCollections" src/routes/+page.svelte` reveals — the grep must return zero rows when done).

- [ ] **Step 2: Verify**

Run: `npm run check`
Expected: 0 errors (same error/warning count as before the rename).
Run: `grep -c "soloCollections\|mutedCollections" src/routes/+page.svelte`
Expected: `0`.

- [ ] **Step 3: Commit**

```bash
git add src/routes/+page.svelte
git commit -m "refactor(scope): rename path-keyed S/M maps to scopeSolos/scopeMutes"
```

---

### Task 5: Out-of-scope opacity tokens

**Files:**
- Modify: `src/app.css`
- Modify: `src/lib/FileTree.svelte`, `src/lib/SystemsView.svelte`, `src/lib/CollectionsPanel.svelte`, `src/lib/FilterPanel.svelte`

Every surface currently hard-codes 0.45 rest / 0.7 hover. One token pair replaces them (spec: Display doctrine).

- [ ] **Step 1: Add the tokens**

In `src/app.css`, inside the `:root` block (near the `--glow-*` tokens at ~line 117), add:

```css
  /* Out-of-scope dim — one level on every surface; hover restores
     legibility, rows never hide (except under the opt-in focus lens). */
  --opacity-out-of-scope: 0.45;
  --opacity-out-of-scope-hover: 0.7;
```

- [ ] **Step 2: Adopt in each surface**

- `src/lib/FileTree.svelte` (~lines 426–431): in `.muted-scope > .row-container` replace `opacity: 0.45;` with `opacity: var(--opacity-out-of-scope);` and in its `:hover` rule replace `opacity: 0.7;` with `opacity: var(--opacity-out-of-scope-hover);`.
- `src/lib/SystemsView.svelte` (~lines 709–715): same two substitutions in `.group-files.dimmed` and `.group-files.dimmed:hover`.
- `src/lib/CollectionsPanel.svelte` (~lines 850–855): same two substitutions in `.row-container.dimmed > :not(.tr)` and `.row-container.dimmed:hover > :not(.tr)`; also `.child-row.dimmed` (~line 1039) `opacity: 0.45;` → `var(--opacity-out-of-scope)`.
- `src/lib/FilterPanel.svelte` (~lines 512–516): in the `.row.dimmed .row-name, …` rule replace `opacity: 0.45;` with `opacity: var(--opacity-out-of-scope);`.

- [ ] **Step 3: Verify**

Run: `npm run check && npm run lint:css`
Expected: both clean.

- [ ] **Step 4: Commit**

```bash
git add src/app.css src/lib/FileTree.svelte src/lib/SystemsView.svelte src/lib/CollectionsPanel.svelte src/lib/FilterPanel.svelte
git commit -m "style(tokens): out-of-scope dim becomes one token pair across surfaces"
```

---

### Task 6: CollectionsPanel — mute button, keyboard M, muted treatment

**Files:**
- Modify: `src/lib/CollectionsPanel.svelte`

Props default to inert; `+page.svelte` wires them in Task 11. Spec: Gesture grammar (collections get transport + M; archived rows M only; mute wins over play).

- [ ] **Step 1: Add props**

Next to the existing `playingNames` prop (~line 24):

```ts
  // Collection mutes — names carved out of the mix (or the library,
  // when the transport is idle). Mute wins over play while lit; a
  // muted, playing row keeps its armed transport and contributes
  // nothing until unmuted. Archived rows keep M (no transport).
  export let mutedNames: Set<string> = new Set();
  export let onToggleMute: (name: string) => void = () => {};
```

- [ ] **Step 2: Keyboard M**

In the `bareLetter` block of the row keydown handler (after the `p`/Space branch, ~line 368):

```ts
      if (lk === 'm') { event.preventDefault(); onToggleMute(col.name); return; }
```

(No `col.archived` guard — muting a shelved collection is the "retired homebrew" carve.)

- [ ] **Step 3: Row markup**

In the `{#each rows as col, i (col.name)}` block, next to the existing `{@const playing = playingNames.has(col.name)}` add:

```svelte
      {@const muted = mutedNames.has(col.name)}
```

On the `.row-container` div, change `class:dimmed={anyPlaying && !playing && !col.archived}` to:

```svelte
          class:dimmed={muted || (anyPlaying && !playing && !col.archived)}
```

Replace the transport branch `{:else if !isRenamingRow && !col.archived} … {/if}` (the `<span class="tr">…</span>` block) with a branch that renders for archived rows too, transport gated inside, M always present:

```svelte
          {:else if !isRenamingRow}
            <span class="tr" class:engaged={playing || muted}>
              {#if !col.archived}
                <!-- Archived rows carry no transport — unarchive to play. -->
                <button
                  type="button"
                  class="tr-btn"
                  class:playing
                  on:click|stopPropagation={() => onTogglePlay(col.name)}
                  aria-pressed={playing}
                  title={playing ? `Stop ${col.name} (P)` : `Play ${col.name} (P)`}
                >
                  {#if playing}
                    <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M5 5h14v14H5z"/></svg>
                  {:else}
                    <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M6 4.2v15.6L20 12z"/></svg>
                  {/if}
                </button>
              {/if}
              <button
                type="button"
                class="sm-btn"
                class:mute-on={muted}
                on:click|stopPropagation={() => onToggleMute(col.name)}
                aria-pressed={muted}
                title={muted ? `Unmute ${col.name} (M)` : `Mute ${col.name} (M)`}
              >M</button>
            </span>
          {/if}
```

(`.sm-btn` / `.mute-on` anatomy is the shared style in `app.css` — no local button CSS needed. If the `.tr` span lacks a gap, add `gap: 0.25rem;` to its rule.)

Child rows (~line 610): change `class:washed={playing}` to `class:washed={playing && !muted}` and `class:dimmed={anyPlaying && !playing}` to `class:dimmed={muted || (anyPlaying && !playing)}`.

- [ ] **Step 4: Verify**

Run: `npm run check && npm run lint:css`
Expected: clean. (Props are inert until Task 11 — behavior unchanged in the app.)

- [ ] **Step 5: Commit**

```bash
git add src/lib/CollectionsPanel.svelte
git commit -m "feat(collections): mute button joins the transport — M carves a track from the mix"
```

---

### Task 7: SearchScopeBar — collection-mute chips, suppression fix

**Files:**
- Modify: `src/lib/SearchScopeBar.svelte`

Spec: every narrowing materializes a chip; collection mutes wear the vermilion mute dressing with the collection's pigment ribbon; mix-layer mutes are never suppressed (mute wins over play). Folder/file mute chips stay suppressed only by folder/file **solos** — playing no longer overrides them.

- [ ] **Step 1: Props**

After the `collectionMutes` prop (~line 17):

```ts
  export let collectionTrackMutes: { key: string; label: string; color: string | null }[] = [];
  export let onClearCollectionTrackMute: (key: string) => void = () => {};
```

- [ ] **Step 2: Fix the suppression derived**

Replace (~lines 47–48):

```ts
  $: shownCollectionMutes =
    collectionPlays.length > 0 || collectionSolos.length > 0 ? [] : collectionMutes;
```

with:

```ts
  // Folder/file solos override folder/file mutes within their axis, so
  // those mute chips would mislead and are suppressed. Playing no
  // longer suppresses them: S/M narrows within the mix, both apply.
  $: shownCollectionMutes = collectionSolos.length > 0 ? [] : collectionMutes;
```

- [ ] **Step 3: Chip markup**

Directly after the `{#each collectionPlays …}` block (so the mix-layer chips group together), add:

```svelte
    {#each collectionTrackMutes as chip (chip.key)}
      <button
        type="button"
        class="chip exclusion"
        on:click|stopPropagation={() => onClearCollectionTrackMute(chip.key)}
        title="Unmute {chip.label}"
        aria-label="Unmute {chip.label}"
      >
        <span class="chip-prefix">mute</span>
        {#if chip.color}
          <!-- Bookmark ribbon — the collection keeps its pigment even muted -->
          <svg class="chip-mark" viewBox="0 0 24 24" fill={chip.color} aria-hidden="true">
            <path d="M5 2h14v20l-7-5.2L5 22z"/>
          </svg>
        {:else}
          <svg class="chip-mark" viewBox="0 0 24 24" fill="none" stroke="var(--text-tertiary)" stroke-width="2.2" stroke-linejoin="round" aria-hidden="true">
            <path d="M6 3h12v18l-6-4.4L6 21z"/>
          </svg>
        {/if}
        <span class="chip-label">{chip.label}</span>
        <span class="chip-clear" aria-hidden="true">×</span>
      </button>
    {/each}
```

(`chip exclusion` is the existing vermilion mute dressing — see `.chip.exclusion` at ~line 321. Note the exclusion styles already tint `.chip-mark`; if the pigment fill gets overridden by that rule, scope the exclusion `.chip-mark` tint to exclude ribbons with an inline `fill` — check rendering in Task 13's QA pass.)

- [ ] **Step 4: Verify**

Run: `npm run check && npm run lint:css`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add src/lib/SearchScopeBar.svelte
git commit -m "feat(scope-bar): collection-mute chips; folder mutes only yield to folder solos"
```

---

### Task 8: FileTree — unified out-of-scope dim, focus lens

**Files:**
- Modify: `src/lib/FileTree.svelte`

Spec: Display doctrine. The unified predicate replaces both the mute-prefix dim and the highlight wash. A file row dims when indexed-but-out-of-scope; a folder dims when it has indexed descendants and none in scope. `scopeBrightPaths` (in-scope files ∪ their ancestors, or null when no scope is engaged) and `indexedFolderPaths` (ancestors of indexed files) arrive as props in Task 11.

- [ ] **Step 1: Props**

Replace the `highlightPaths` prop (~lines 34–37) and the S/M comment block (~lines 50–52) region as follows. Delete:

```ts
  // Collection-preview prop — paths get an accent stripe when previewing a
  // collection's contents from the panel (separate from collection-edit,
  // which now lives entirely in SystemsView).
  export let highlightPaths: Set<string> = new Set();
```

Add (near the `soloedScopePaths`/`mutedScopePaths` props, whose comment becomes):

```ts
  // Collection-axis S/M lit states for the folder-row buttons. The dim
  // itself no longer derives from these: out-of-scope rows dim through
  // scopeBrightPaths, which already accounts for mutes.
  export let soloedScopePaths: Set<string> = new Set();
  export let mutedScopePaths: Set<string> = new Set();
  export let onToggleScopeSolo: (item: FileItem) => void = () => {};
  export let onToggleScopeMute: (item: FileItem) => void = () => {};

  // Scope membership (spec: docs/specs/scope/2026-08-08-solo-mute-play-
  // doctrine-design.md). null = no narrowing engaged, nothing dims.
  // Contains every in-scope indexed file plus its ancestor folders, so
  // the path to in-scope material stays bright.
  export let scopeBrightPaths: Set<string> | null = null;
  // Folders that contain at least one indexed file — a folder with no
  // indexed descendants has nothing to say about scope and never dims.
  export let indexedFolderPaths: Set<string> = new Set();
  // Focus lens: hide (don't render) out-of-scope rows instead of
  // dimming them. Browsing surfaces only — console surfaces never hide.
  export let hideOutOfScope: boolean = false;
```

- [ ] **Step 2: Replace the deriveds**

Replace (~lines 58–64):

```ts
  $: isSoloedScope = soloedScopePaths.has(item.path);
  $: isMutedHere = mutedScopePaths.has(item.path);
  $: isMutedScope = isPathOrAncestorIn(item.path, mutedScopePaths);

  $: isHiddenItem = isPathOrAncestorIn(item.path, hiddenPaths);
  $: hidden = (displayPaths !== null && !displayPaths.has(item.path)) ||
              (isHiddenItem && !showHidden);
```

with:

```ts
  $: isSoloedScope = soloedScopePaths.has(item.path);
  $: isMutedHere = mutedScopePaths.has(item.path);
  // Out-of-scope: dimming only speaks about searchability of indexed
  // material — unindexed files keep their existing treatments.
  $: outOfScope = scopeBrightPaths !== null &&
    (item.is_dir ? indexedFolderPaths.has(item.path) : indexedPaths.has(item.path)) &&
    !scopeBrightPaths.has(item.path);

  $: isHiddenItem = isPathOrAncestorIn(item.path, hiddenPaths);
  $: hidden = (displayPaths !== null && !displayPaths.has(item.path)) ||
              (isHiddenItem && !showHidden) ||
              (outOfScope && hideOutOfScope);
```

Also delete the now-unused `$: isHighlighted = highlightPaths.size > 0 && highlightPaths.has(item.path);` (~line 94).

- [ ] **Step 3: Markup and styles**

On the row div (~line 222): remove `class:highlighted={isHighlighted}`, replace `class:muted-scope={isMutedScope}` with `class:out-of-scope={outOfScope}`.

In the `<svelte:self>` recursion (~lines 338–345): remove `{highlightPaths}`; add `{scopeBrightPaths}`, `{indexedFolderPaths}`, `{hideOutOfScope}` alongside the existing scope props.

In the styles: delete the `.highlighted` rule (~lines 448–452). Replace the `.muted-scope` rules and comment (~lines 422–431) with:

```css
  /* Out of the resolved scope — dimmed, never hidden (unless the focus
     lens is on, which drops the row from the render instead). Only the
     row itself dims (each descendant row evaluates its own membership),
     so nesting doesn't compound the opacity. Hover restores
     legibility, mirroring the systems view's dimmed groups. */
  .out-of-scope > .row-container {
    opacity: var(--opacity-out-of-scope);
  }
  .out-of-scope > .row-container:hover {
    opacity: var(--opacity-out-of-scope-hover);
  }
```

- [ ] **Step 4: Verify**

Run: `npm run check`
Expected: one new warning is acceptable at this stage — `+page.svelte` still passes `highlightPaths`; Task 11 removes it. No errors.

- [ ] **Step 5: Commit**

```bash
git add src/lib/FileTree.svelte
git commit -m "feat(tree): unified out-of-scope dim + focus lens replace wash and mute-prefix dim"
```

---

### Task 9: SystemsView — scope dim condition, focus lens

**Files:**
- Modify: `src/lib/SystemsView.svelte`

Spec: system groups dim when the channel is muted, when another channel's solo excludes them, or when none of their files are in scope; under the lens, dimmed groups drop.

- [ ] **Step 1: Props**

Delete the `highlightPaths` prop (~line 34). Near the `soloedSystems` prop add:

```ts
  // Scope membership — see FileTree. null = no narrowing engaged.
  export let scopeBrightPaths: Set<string> | null = null;
  // Focus lens: dimmed groups drop from the render entirely.
  export let hideOutOfScope: boolean = false;
```

- [ ] **Step 2: Group dim + lens**

In the template's group loop, the `<ul class="group-files" class:dimmed={…}>` (~line 526) currently reads:

```svelte
            class:dimmed={group.muted || (soloedSystems.size > 0 && !soloedSystems.has(group.tag))}
```

Hoist the condition to an `{@const}` at the top of the group's `{#each}` body and wrap the whole group (header + list) in a lens guard:

```svelte
        {@const groupDimmed = group.muted
          || (soloedSystems.size > 0 && !soloedSystems.has(group.tag))
          || (scopeBrightPaths !== null && !group.entries.some((e) => scopeBrightPaths.has(e.path)))}
        {#if !(hideOutOfScope && groupDimmed)}
          … existing group header markup …
          <ul class="group-files" class:dimmed={groupDimmed}>
          … existing entries markup …
        {/if}
```

(Exact wrapping: the guard encloses everything rendered per group — find the group header element directly above the `sm` cluster markup at ~line 499 and close the `{/if}` after the `</ul>`/collapse block. Keyboard row collection (`rowEls`) is DOM-driven, so hidden groups drop out of navigation automatically.)

Remove `class:highlighted={highlightPaths.has(entry.path)}` from the entry rows (~line 534) and delete the `.file.highlighted` style rule (~line 796).

Update the muted-groups comment at ~line 18 ("groups stay visible but dim — hiding them would take the M button with them") to note the lens exception:

```ts
  // groups stay visible but dim — hiding them would take the M button
  // with them. The opt-in focus lens is the exception: it drops dimmed
  // groups entirely; recovery lives in the filter console and the
  // scope-bar chips (console surfaces never hide).
```

- [ ] **Step 3: Verify**

Run: `npm run check`
Expected: no errors (a stale-prop warning from `+page.svelte` is acceptable until Task 11).

- [ ] **Step 4: Commit**

```bash
git add src/lib/SystemsView.svelte
git commit -m "feat(systems-view): groups dim outside the resolved scope; focus lens drops them"
```

---

### Task 10: FilterPanel — "Hide out-of-scope items" lens row

**Files:**
- Modify: `src/lib/FilterPanel.svelte`

Spec: Focus lens — a toggle in the filter console masthead area, sibling to "Show hidden items"; lit state wears purple (`--text-active`), it's a mode the user switched on.

- [ ] **Step 1: Props**

Near `showHidden`/`onToggleShowHidden`:

```ts
  // Focus lens (spec: scope doctrine) — hide out-of-scope rows on the
  // browsing surfaces (tree, systems view). Console surfaces — this
  // panel, the collections panel, the scope bar — never hide.
  export let hideOutOfScope: boolean = false;
  export let onToggleHideOutOfScope: () => void = () => {};
```

- [ ] **Step 2: Markup**

Directly after the "Show hidden items" `<label class="row" …>…</label>` block (~line 205), add:

```svelte
    <label
      class="row lens-row"
      title="Hide dimmed out-of-scope rows in the tree and systems view"
      data-fm="row"
    >
      <span class="row-name muted-name">Hide out-of-scope items</span>
      <input
        class="app-checkbox lens-checkbox"
        type="checkbox"
        checked={hideOutOfScope}
        on:change={onToggleHideOutOfScope}
      />
    </label>
```

- [ ] **Step 3: Purple lit state**

The shared `.app-checkbox:checked` is parchment (`--text-accent`); the lens is a switched-on mode, so its checked state wears purple. Add to this component's styles:

```css
  /* The lens is a mode the user switched on — checked wears purple,
     not the parchment content accent. */
  .lens-checkbox:checked {
    background-color: var(--text-active);
    border-color: var(--text-active);
  }
```

- [ ] **Step 4: Verify**

Run: `npm run check && npm run lint:css`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add src/lib/FilterPanel.svelte
git commit -m "feat(filter-console): focus lens toggle — hide out-of-scope items"
```

---

### Task 11: `+page.svelte` — the rewire

**Files:**
- Modify: `src/routes/+page.svelte`

Everything converges here: play leaves the collection axis, the three empty-state messages land, the display scope set drives counts and dimming, and all the new component props get wired. Work through the sub-steps in order; run `npm run check` after each lettered group if anything is uncertain.

- [ ] **Step 1: Imports and state**

Extend the `searchScope` import (~line 31) to include the new functions:

```ts
  import { resolveMix, resolveScopeSet, searchGameSystemsFilter, UNTAGGED_KEY, type CurationKey, type ScopeRef } from '../lib/searchScope';
```

(`searchCurationFilter` and `searchSourcePathsFilter` become unused in this file once the steps below land — remove them from the import.)

Replace the narrowing comment block and state (~lines 145–163) with:

```ts
  // Library narrowing — the scope doctrine (docs/specs/scope/
  // 2026-08-08-solo-mute-play-doctrine-design.md): the transport arms
  // material into the mix; S narrows within what's armed; M carves out
  // of it. playingCollections ∪-minus-mutedCollectionNames resolve to
  // the mix (the universe); three axes narrow within it by
  // intersection, each with DAW semantics (solos union within the
  // axis, solo overrides mute):
  //   - systems axis:    filterExcludedSystems (muted) + soloedSystems.
  //   - path axis:       scopeSolos + scopeMutes, keyed by tree
  //     folder/file path.
  //   - curation axis:   soloCuration + mutedCuration over the
  //     collected/loose domain.
  // The whole console persists across launches ("full console recall")
  // via the scopeConsole store key.
  let filterExcludedSystems = new Set<string>();
  let soloedSystems = new Set<string>();
  let scopeSolos = new Map<string, ScopeRef>();
  let scopeMutes = new Map<string, ScopeRef>();
  let playingCollections = new Set<string>();
  let mutedCollectionNames = new Set<string>();
  let soloCuration = new Set<CurationKey>();
  let mutedCuration = new Set<CurationKey>();
  // Focus lens — hide out-of-scope rows on browsing surfaces.
  let hideOutOfScope = false;
```

- [ ] **Step 2: Resolution helpers**

Replace `computeCollectionAxisInclude` and its reactive mirror (~lines 301–332) with:

```ts
  // Path-axis solo/mute Maps resolved to raw file-path arrays. The
  // universe restriction (solo ∩ mix) happens inside resolveScopeSet.
  //
  // Plain function, not a `$:` value: the S/M and transport toggles
  // call runSearch synchronously after mutating their state, and
  // derived values don't flush until the end of the microtask.
  function scopeRefSets(solos: Map<string, ScopeRef>, mutes: Map<string, ScopeRef>) {
    const refFiles = (key: string, kind: ScopeRef['kind']) =>
      kind === 'folder'
        ? indexedPdfsUnderPath(key)
        : indexedPaths.has(key) ? [key] : [];
    return {
      soloSets: [...solos].map(([p, r]) => refFiles(p, r.kind)),
      muteSets: [...mutes].map(([p, r]) => refFiles(p, r.kind)),
    };
  }

  const EMPTY_SYSTEMS = new Set<string>();
  const EMPTY_TAGS = new Map<string, string[]>();
```

- [ ] **Step 3: Display scope set and counts**

Replace the `searchableFileCount` block (~lines 334–365) with:

```ts
  // The resolved scope — mix ∩ all three axes — as the display sees it.
  // null = nothing engaged, every indexed file is in scope. Drives the
  // scope-bar denominator and every surface's out-of-scope dimming.
  $: resolvedScopeSet = (() => {
    const { soloSets, muteSets } = scopeRefSets(scopeSolos, scopeMutes);
    return resolveScopeSet(
      resolveMix(playingCollections, mutedCollectionNames, collections, indexedPaths),
      soloSets,
      muteSets,
      soloCuration,
      mutedCuration,
      collectedPaths,
      soloedSystems,
      filterExcludedSystems,
      effectiveGameSystemMap,
      indexedPaths
    );
  })();
  $: searchableFileCount = resolvedScopeSet !== null ? resolvedScopeSet.size : indexedPathsSet.size;
  // In-scope files plus their ancestor folders — the tree rows that
  // stay bright. null = no scope engaged, nothing dims.
  $: scopeBrightPaths = resolvedScopeSet === null
    ? null
    : new Set<string>([...resolvedScopeSet, ...computeAncestorPaths(resolvedScopeSet)]);
  // Folders containing at least one indexed file — the rows the dim
  // predicate is allowed to speak about.
  $: indexedFolderPaths = computeAncestorPaths(indexedPaths);
```

(Svelte's reactivity tracks the identifiers referenced in the statement — `playingCollections`, `mutedCollectionNames`, `collections`, `scopeSolos`, `scopeMutes`, `indexedPaths`, `soloCuration`, `mutedCuration`, `collectedPaths`, `soloedSystems`, `filterExcludedSystems`, `effectiveGameSystemMap` are all named, so the derived recomputes on every toggle. If the inline spread reads poorly, an equivalent IIFE that calls `scopeRefSets` and then `resolveScopeSet` with named locals is fine — keep every state identifier textually present in the reactive statement.)

- [ ] **Step 4: runSearch — mix resolution and the three messages**

In `runSearch`, replace everything from the `// Collection axis` comment (~line 382) through the end of the `if (gameSystems !== null && gameSystems.length === 0) { … }` block (~line 427) — inclusive of that block — with:

```ts
    // Mix first: the transport layer resolves before any narrowing.
    // Computed fresh (not from the deriveds) — toggles call runSearch
    // synchronously after mutating state; see scopeRefSets.
    const mix = resolveMix(playingCollections, mutedCollectionNames, collections, indexedPaths);
    if (mix !== null && mix.size === 0) {
      searchError = playingCollections.size > 0
        ? 'Nothing indexed is playing.'
        : 'Everything is muted.';
      searchResults = [];
      isSearching = false;
      return;
    }

    // Path + curation axes narrow within the mix. Systems stay out of
    // this resolution (empty sets) — the backend applies game_systems
    // per chunk.
    const { soloSets, muteSets } = scopeRefSets(scopeSolos, scopeMutes);
    const pathScope = resolveScopeSet(
      mix, soloSets, muteSets,
      soloCuration, mutedCuration, collectedPaths,
      EMPTY_SYSTEMS, EMPTY_SYSTEMS, EMPTY_TAGS, indexedPaths
    );
    const sourcePaths = pathScope === null ? null : [...pathScope];

    if (sourcePaths !== null && sourcePaths.length === 0) {
      searchError = scopeSolos.size > 0 || soloCuration.size > 0
        ? 'Nothing under the soloed items.'
        : 'Everything is muted.';
      searchResults = [];
      isSearching = false;
      return;
    }

    // Systems axis → backend game_systems include-list (issue #307:
    // the untagged bucket must be named explicitly under mutes).
    const gameSystems = searchGameSystemsFilter(
      soloedSystems,
      filterExcludedSystems,
      gameSystemStats.map((s) => s.name)
    );
    if (gameSystems !== null && gameSystems.length === 0) {
      searchError = 'Everything is muted.';
      searchResults = [];
      isSearching = false;
      return;
    }
```

(The old `'Nothing indexed under the soloed or playing items.'`, `'All game systems are filtered out.'` strings die here; the spec's three messages replace them. `let sourcePaths` becomes `const`.)

- [ ] **Step 5: Toggles, clear-all, chips**

After `togglePlayCollection` (~line 851) add:

```ts
  // Mute a collection — carve its files from the mix (or from the
  // whole library while the transport is idle). Mute wins over play;
  // the armed state survives and unmuting restores the contribution.
  function toggleCollectionMute(name: string) {
    if (mutedCollectionNames.has(name)) {
      mutedCollectionNames.delete(name);
    } else {
      mutedCollectionNames.add(name);
    }
    mutedCollectionNames = mutedCollectionNames;
    if (committedQuery) runSearch(committedQuery);
  }

  function toggleHideOutOfScope() {
    hideOutOfScope = !hideOutOfScope;
  }
```

In `clearAllFilters` (~line 864) add `mutedCollectionNames = new Set();` beside `playingCollections = new Set();` (the lens is a view mode, not a narrowing — clear-all leaves `hideOutOfScope` alone).

Beside the `collectionMutes` chip derived (~line 268), add:

```ts
  // Collection-track mutes chip like plays — pigment ribbon, mute
  // dressing. Never suppressed: mute wins over play on the mix layer.
  $: collectionTrackMutes = isCollectionEditMode
    ? []
    : [...mutedCollectionNames].map((name) => ({
        key: name,
        label: name,
        color: collections[name]?.color || null,
      }));
```

- [ ] **Step 6: Rename migration**

In `renameCollection` (~line 2634), after the `playingCollections` migration block, add:

```ts
      if (mutedCollectionNames.has(name)) {
        mutedCollectionNames.delete(name);
        mutedCollectionNames.add(newName);
        mutedCollectionNames = mutedCollectionNames;
      }
```

- [ ] **Step 7: Retire the wash**

Delete the `highlightPaths` derived (~lines 1386–1410, the block computing playing/solo files plus ancestors) and the comment above it. Keep `mutedScopePaths`/`soloedScopePaths` (they light the S/M buttons):

```ts
  // Lit states for the tree's S/M buttons. The dim itself comes from
  // scopeBrightPaths (out-of-scope membership), not from these.
  $: mutedScopePaths = new Set(scopeMutes.keys());
  $: soloedScopePaths = new Set(scopeSolos.keys());
```

- [ ] **Step 8: Wire the components**

In the template:

- `<CollectionsPanel …>` (~line 2922): add `mutedNames={mutedCollectionNames}` and `onToggleMute={toggleCollectionMute}`.
- `<FilterPanel …>` (~line 2949): add `{hideOutOfScope}` and `onToggleHideOutOfScope={toggleHideOutOfScope}`.
- `<SearchScopeBar …>` (~line 2980): add `{collectionTrackMutes}` and `onClearCollectionTrackMute={toggleCollectionMute}`.
- `<SystemsView …>` (~line 3035): remove `{highlightPaths}`; add `{scopeBrightPaths}` and `{hideOutOfScope}`.
- `<FileTree …>` (~line 3062): remove `{highlightPaths}`; add `{scopeBrightPaths}`, `{indexedFolderPaths}`, `{hideOutOfScope}`.

- [ ] **Step 9: Tree empty-state placeholder**

In the tree branch of the template (the `{:else}` before `{#each files as file (file.path)}` at ~line 3061), add before the `{#each}`:

```svelte
          {#if hideOutOfScope && resolvedScopeSet !== null && resolvedScopeSet.size === 0}
            <div class="scope-empty">Everything is out of scope.</div>
          {/if}
```

And in the page's `<style>` block:

```css
  .scope-empty {
    padding: 1rem 0.8rem;
    font-style: italic;
    color: var(--text-tertiary);
  }
```

- [ ] **Step 10: Verify**

Run: `npm run check`
Expected: 0 errors, and the stale-prop warnings from Tasks 8–9 are gone.
Run: `npm test`
Expected: full suite green.
Run: `grep -n "highlightPaths\|All game systems are filtered\|soloed or playing" src/routes/+page.svelte`
Expected: no matches.

- [ ] **Step 11: Commit**

```bash
git add src/routes/+page.svelte
git commit -m "feat(scope): play becomes the mix layer — S/M narrows within, three empty states"
```

---

### Task 12: Persistence — full console recall

**Files:**
- Create: `src/lib/scopeConsole.ts`
- Create: `src/lib/scopeConsole.test.ts`
- Modify: `src/routes/+page.svelte`

Spec: Persistence. One store key (`scopeConsole`) holding the whole console; defensive per-field parsing (a corrupt field falls back alone, it doesn't nuke the console); stale names/paths stay in state so their chips remain visible and removable — resolution already intersects them away.

- [ ] **Step 1: Write the failing tests**

Create `src/lib/scopeConsole.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { parseScopeConsoleState } from './scopeConsole';
import type { ScopeConsoleState } from './scopeConsole';

const FULL: ScopeConsoleState = {
  playing: ['Strahd'],
  mutedCollections: ['Homebrew'],
  soloedSystems: ['D&D 5E'],
  mutedSystems: ['unknown'],
  scopeSolos: [['/lib/bestiary', { kind: 'folder', label: 'bestiary' }]],
  scopeMutes: [['/lib/old.pdf', { kind: 'file', label: 'old.pdf' }]],
  curationSolos: ['collected'],
  curationMutes: [],
  hideOutOfScope: true,
};

describe('parseScopeConsoleState', () => {
  it('round-trips a full console through JSON', () => {
    expect(parseScopeConsoleState(JSON.parse(JSON.stringify(FULL)))).toEqual(FULL);
  });

  it('returns undefined for absent or non-object values', () => {
    expect(parseScopeConsoleState(undefined)).toBeUndefined();
    expect(parseScopeConsoleState(null)).toBeUndefined();
    expect(parseScopeConsoleState('nope')).toBeUndefined();
  });

  it('a corrupt field falls back alone — the rest of the console survives', () => {
    const mangled = { ...JSON.parse(JSON.stringify(FULL)), playing: 'not-an-array' };
    const out = parseScopeConsoleState(mangled)!;
    expect(out.playing).toEqual([]);
    expect(out.mutedCollections).toEqual(['Homebrew']);
    expect(out.hideOutOfScope).toBe(true);
  });

  it('drops malformed scope-ref entries but keeps well-formed ones', () => {
    const mangled = JSON.parse(JSON.stringify(FULL));
    mangled.scopeSolos.push(['/bad', { kind: 'nonsense', label: 3 }]);
    const out = parseScopeConsoleState(mangled)!;
    expect(out.scopeSolos).toEqual(FULL.scopeSolos);
  });

  it('drops curation keys outside the two-value domain', () => {
    const mangled = { ...JSON.parse(JSON.stringify(FULL)), curationSolos: ['collected', 'weird'] };
    expect(parseScopeConsoleState(mangled)!.curationSolos).toEqual(['collected']);
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `npx vitest run src/lib/scopeConsole.test.ts`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement**

Create `src/lib/scopeConsole.ts`:

```ts
// Serialization of the scope console (solo/mute/play/lens state) for
// full console recall across launches — spec: docs/specs/scope/
// 2026-08-08-solo-mute-play-doctrine-design.md. One store key holds
// the whole console; parsing is defensive per field, so one corrupt
// field falls back to empty without nuking the rest. Stale collection
// names and paths are kept as-is: resolution intersects them away, and
// their chips stay visible and removable rather than silently ignored.

import { parseStringArray, parseRecord } from './storeParsers';
import type { CurationKey, ScopeRef } from './searchScope';

export interface ScopeConsoleState {
  playing: string[];
  mutedCollections: string[];
  soloedSystems: string[];
  mutedSystems: string[];
  scopeSolos: [string, ScopeRef][];
  scopeMutes: [string, ScopeRef][];
  curationSolos: CurationKey[];
  curationMutes: CurationKey[];
  hideOutOfScope: boolean;
}

function parseScopeRefEntries(v: unknown): [string, ScopeRef][] {
  if (!Array.isArray(v)) return [];
  const out: [string, ScopeRef][] = [];
  for (const entry of v) {
    if (!Array.isArray(entry) || entry.length !== 2) continue;
    const [path, ref] = entry;
    if (typeof path !== 'string') continue;
    const rec = parseRecord(ref);
    if (!rec) continue;
    if (rec.kind !== 'folder' && rec.kind !== 'file') continue;
    if (typeof rec.label !== 'string') continue;
    out.push([path, { kind: rec.kind, label: rec.label }]);
  }
  return out;
}

function parseCurationKeys(v: unknown): CurationKey[] {
  const arr = parseStringArray(v) ?? [];
  return arr.filter((k): k is CurationKey => k === 'collected' || k === 'loose');
}

/** Parse a stored console. Returns undefined only when the value is
 * absent or not an object; individual malformed fields fall back to
 * empty on their own. */
export function parseScopeConsoleState(v: unknown): ScopeConsoleState | undefined {
  const rec = parseRecord(v);
  if (!rec) return undefined;
  return {
    playing: parseStringArray(rec.playing) ?? [],
    mutedCollections: parseStringArray(rec.mutedCollections) ?? [],
    soloedSystems: parseStringArray(rec.soloedSystems) ?? [],
    mutedSystems: parseStringArray(rec.mutedSystems) ?? [],
    scopeSolos: parseScopeRefEntries(rec.scopeSolos),
    scopeMutes: parseScopeRefEntries(rec.scopeMutes),
    curationSolos: parseCurationKeys(rec.curationSolos),
    curationMutes: parseCurationKeys(rec.curationMutes),
    hideOutOfScope: rec.hideOutOfScope === true,
  };
}
```

- [ ] **Step 4: Run to verify pass**

Run: `npx vitest run src/lib/scopeConsole.test.ts`
Expected: PASS.

- [ ] **Step 5: Wire into `+page.svelte`**

Import (with the other lib imports):

```ts
  import { parseScopeConsoleState } from '../lib/scopeConsole';
  import type { ScopeConsoleState } from '../lib/scopeConsole';
```

Add near the other persist helpers (e.g. after `persistHidden`, ~line 890):

```ts
  function snapshotScopeConsole(): ScopeConsoleState {
    return {
      playing: [...playingCollections],
      mutedCollections: [...mutedCollectionNames],
      soloedSystems: [...soloedSystems],
      mutedSystems: [...filterExcludedSystems],
      scopeSolos: [...scopeSolos],
      scopeMutes: [...scopeMutes],
      curationSolos: [...soloCuration],
      curationMutes: [...mutedCuration],
      hideOutOfScope,
    };
  }

  async function persistScopeConsole() {
    try {
      const store = await load('settings.json');
      await store.set('scopeConsole', snapshotScopeConsole());
      await store.save();
    } catch (e) {
      console.log('Could not persist scope console:', e);
    }
  }
```

Add a `persistScopeConsole();` call (fire-and-forget, before the `runSearch` line where one exists) at the end of each of: `toggleSystemFilter`, `toggleSystemSolo`, `toggleScopeSolo`, `toggleScopeMute`, `togglePlayCollection`, `toggleCollectionMute`, `toggleCurationSolo`, `toggleCurationMute`, `toggleHideOutOfScope`, `clearAllFilters`, and in `renameCollection` directly after the two migration blocks.

In `onMount`, **after** the old curation-radio migration block (~line 666, so recall wins over the one-time migration) and before `await loadCollections();`, add:

```ts
      // Full console recall — the session reopens as it was left.
      const savedConsole = parseScopeConsoleState(await store.get('scopeConsole'));
      if (savedConsole) {
        playingCollections = new Set(savedConsole.playing);
        mutedCollectionNames = new Set(savedConsole.mutedCollections);
        soloedSystems = new Set(savedConsole.soloedSystems);
        filterExcludedSystems = new Set(savedConsole.mutedSystems);
        scopeSolos = new Map(savedConsole.scopeSolos);
        scopeMutes = new Map(savedConsole.scopeMutes);
        soloCuration = new Set(savedConsole.curationSolos);
        mutedCuration = new Set(savedConsole.curationMutes);
        hideOutOfScope = savedConsole.hideOutOfScope;
      }
```

- [ ] **Step 6: Verify**

Run: `npm run check && npm test`
Expected: clean, all tests green.

- [ ] **Step 7: Commit**

```bash
git add src/lib/scopeConsole.ts src/lib/scopeConsole.test.ts src/routes/+page.svelte
git commit -m "feat(scope): full console recall — solo/mute/play/lens persist across launches"
```

---

### Task 13: Full verification and manual QA

**Files:** none (verification only)

- [ ] **Step 1: Full automated pass**

Run: `npm run check && npm test && npm run lint:css && npm run build`
Expected: all four clean. Fix anything that surfaces before proceeding.

- [ ] **Step 2: Manual QA in the dev app**

Run `npm run tauri dev` (the user runs this if the environment can't) and walk the checklist against a real library:

1. **Mix layer:** play collection A → tree dims everything outside A; scope bar shows a play chip; search only hits A. Play B too → union. Stop both → everything bright.
2. **Strahd/Bestiary:** while A plays, solo a folder outside A → results and count go to the intersection (likely empty → "Nothing under the soloed items."), NOT to the union.
3. **Mute wins over play:** mute playing collection A (M on its row) → ▶ stays armed, M lit vermilion, row content dims, A's files leave the scope; unmute → contribution returns.
4. **Idle-transport mute:** stop everything, mute collection A → library-wide search excludes A's files; vermilion mute chip with A's pigment appears; chip click unmutes.
5. **Archived M:** archive a collection (show-archived on) → row has M but no transport; muting it works.
6. **Empty states:** play an empty/unindexed collection → "Nothing indexed is playing." Mute every system in the filter console → "Everything is muted."
7. **Focus lens:** engage narrowing, toggle "Hide out-of-scope items" → tree and systems view drop dimmed rows; filter console, collections panel, scope bar unchanged; toggle lit purple. Clear all narrowing with the lens on → everything renders (no-op). Narrow to empty with the lens on → tree shows "Everything is out of scope."
8. **Keyboard:** M on a focused collection row toggles mute; S/M on tree folder rows and systems groups unchanged; P/Space transport unchanged.
9. **Recall:** arrange a mix (play + mutes + a solo + lens on), quit, relaunch → console restores exactly; chips all present; [clear all] resets everything except the lens.
10. **Rename migration:** rename a playing, muted collection → both chips follow the new name.

- [ ] **Step 3: Update the spec status line**

In `docs/specs/scope/2026-08-08-solo-mute-play-doctrine-design.md`, change `**Status:** Approved design, not yet implemented.` to `**Status:** Implemented <date of completion> on branch claude/unseen-servant-solo-mute-play-02b695.`

- [ ] **Step 4: Commit**

```bash
git add docs/specs/scope/2026-08-08-solo-mute-play-doctrine-design.md
git commit -m "docs(scope): mark solo/mute/play doctrine implemented"
```
