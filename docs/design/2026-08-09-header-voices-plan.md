# Header Voices Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate all header/label typography into six shared voice classes in `src/app.css`, per [the approved spec](2026-08-09-header-voices-design.md).

**Architecture:** Add six recipe-only classes (font, size, tracking, case, line-height, default color) to app.css's Font Utilities region. Each component adopts a class in markup and deletes the recipe properties from its scoped CSS, keeping only layout (margins, padding, flex) and intentional color overrides. Scoped overrides win by specificity (Svelte adds a hash class), so state colors and identity colors keep working.

**Tech Stack:** Svelte scoped CSS, plain CSS in app.css, stylelint (`npm run lint:css`), svelte-check (`npm run check`).

**Conventions for every task:**
- When a component's scoped class would become empty after removing recipe props, delete the scoped block AND replace the class name in markup with the voice class. When scoped rules remain (layout or overrides), keep the original class and append the voice class: `class="sect ledger-label"`.
- The `font-heading` utility class is removed from markup wherever the voice class now supplies the font.
- Verification after each task: `npm run lint:css` and `npm run check` — expect zero errors and zero "Unused CSS selector" warnings in touched files.
- Commit after each task, directly on `main`.

---

### Task 1: Add the six voice classes to app.css

**Files:**
- Modify: `src/app.css` (append after the `.font-display` block, ~line 383)

- [ ] **Step 1: Append the Header Voices block**

```css

/* --- Header Voices --- */
/* One class per header voice; recipe only (font, size, tracking, case,
   line-height, default color) — layout stays in components.
   See docs/design/2026-08-09-header-voices-design.md. */

.panel-title {
  font-family: var(--font-display);
  font-size: 0.8rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  line-height: 1.2;
  color: var(--text-accent);
}

.dialog-title {
  font-family: var(--font-heading);
  font-size: 1rem;
  line-height: 1.2;
  color: var(--text-accent);
}

.section-title {
  font-family: var(--font-heading);
  font-size: 0.95rem;
  line-height: 1.2;
  color: var(--text-primary);
}

.ledger-label {
  font-family: var(--font-heading);
  font-size: 0.7rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  line-height: 1.2;
  color: var(--text-tertiary);
}

.readout-label {
  font-family: var(--font-heading);
  font-size: 0.7rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  line-height: 1.2;
  color: var(--text-secondary);
}

.micro-label {
  font-family: var(--font-body);
  font-size: 0.65rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  line-height: 1.2;
  color: var(--text-tertiary);
}
```

- [ ] **Step 2: Verify**

Run: `npm run lint:css && npm run check`
Expected: both pass (no component touched yet; app.css is outside the stylelint glob but must not break the build).

- [ ] **Step 3: Commit**

```bash
git add src/app.css
git commit -m "refactor(headers): add six shared header-voice classes to app.css"
```

---

### Task 2: Adopt `.panel-title` (CollectionsPanel, FilterPanel)

The global class has the same name as the existing scoped classes, so markup keeps `class="panel-title"` untouched; only scoped CSS shrinks.

**Files:**
- Modify: `src/lib/CollectionsPanel.svelte:729-736`
- Modify: `src/lib/FilterPanel.svelte:385-391`

- [ ] **Step 1: CollectionsPanel — reduce scoped `.panel-title` to layout**

Before:
```css
.panel-title {
  font-family: var(--font-display);
  font-size: 0.8rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--text-accent);
  flex: 1;
}
```
After:
```css
.panel-title {
  flex: 1;
}
```

- [ ] **Step 2: FilterPanel — delete scoped `.panel-title` block entirely** (it is recipe-only). Markup at line 187 keeps `<span class="panel-title">Filters</span>`.

- [ ] **Step 3: Verify**

Run: `npm run lint:css && npm run check`
Expected: pass, no unused-selector warnings.

- [ ] **Step 4: Commit**

```bash
git add src/lib/CollectionsPanel.svelte src/lib/FilterPanel.svelte
git commit -m "refactor(headers): panel nameplates adopt shared .panel-title voice"
```

---

### Task 3: Adopt `.dialog-title` (Modal, ConfirmDialog)

**Files:**
- Modify: `src/lib/Modal.svelte:96` (markup), `:147-150` (CSS)
- Modify: `src/lib/ConfirmDialog.svelte:61` (markup), `:93-99` (CSS)

- [ ] **Step 1: Modal — markup**

Before: `<span class="modal-title font-heading">{title}</span>`
After: `<span class="dialog-title">{title}</span>`

- [ ] **Step 2: Modal — delete scoped `.modal-title` block** (font-size + color only).

- [ ] **Step 3: ConfirmDialog — markup**

Before: `<div class="title">{title}</div>`
After: `<div class="title dialog-title">{title}</div>`

- [ ] **Step 4: ConfirmDialog — reduce scoped `.title`** (this drops the app's only bold header)

Before:
```css
.title {
  font-family: var(--font-heading);
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-accent);
  margin-bottom: 0.5rem;
}
```
After:
```css
.title {
  margin-bottom: 0.5rem;
}
```

- [ ] **Step 5: Verify** — `npm run lint:css && npm run check`, expect pass.

- [ ] **Step 6: Commit**

```bash
git add src/lib/Modal.svelte src/lib/ConfirmDialog.svelte
git commit -m "refactor(headers): modal titles adopt shared .dialog-title voice"
```

---

### Task 4: Adopt `.section-title` (7 components)

Pattern for every site: markup swaps `font-heading` for `section-title`; scoped CSS keeps layout only. Visual changes limited to GuidesPane (1 → 0.95rem) and danger-title (0.9 → 0.95rem).

**Files:**
- Modify: `src/lib/LibrarySettings.svelte` — markup 128, 155, 203, 268, 322; CSS 422-426, 699-705
- Modify: `src/lib/GeneralSettings.svelte` — markup 70, 81; CSS 219-223
- Modify: `src/lib/GettingStartedSteps.svelte` — markup 25, 54, 87, 124, 149; CSS 216-222
- Modify: `src/lib/KeyboardHelpOverlay.svelte` — markup 54; CSS 83-87
- Modify: `src/lib/help/ReferencePane.svelte` — markup 39, 63; CSS 115-119
- Modify: `src/lib/help/AboutPane.svelte` — markup 30, 56; CSS 91-95
- Modify: `src/lib/help/GuidesPane.svelte` — markup 16; CSS 48-52

- [ ] **Step 1: Markup — all `<h3 class="field-title font-heading">` → `<h3 class="field-title section-title">`** (LibrarySettings ×4, GeneralSettings ×2, GettingStartedSteps ×5)

- [ ] **Step 2: LibrarySettings + GeneralSettings — reduce scoped `.field-title`**

Before (identical in both):
```css
.field-title {
  font-size: 0.95rem;
  color: var(--text-primary);
  margin: 0 0 0.35rem;
}
```
After:
```css
.field-title {
  margin: 0 0 0.35rem;
}
```

- [ ] **Step 3: GettingStartedSteps — reduce scoped `.field-title`**

Before:
```css
.field-title {
  flex: 1;
  min-width: 0;
  font-size: 0.95rem;
  color: var(--text-primary);
  margin: 0;
}
```
After:
```css
.field-title {
  flex: 1;
  min-width: 0;
  margin: 0;
}
```

- [ ] **Step 4: LibrarySettings danger-title**

Markup: `<h3 class="danger-title font-heading">Danger Zone</h3>` → `<h3 class="danger-title section-title">Danger Zone</h3>`

CSS before:
```css
.danger-title {
  font-size: 0.9rem;
  color: var(--text-danger);
  margin: 0;
  padding: 0.6rem 0.85rem;
  border-bottom: 1px solid var(--border-subtle);
}
```
After (color override stays — danger is a hue swap):
```css
.danger-title {
  color: var(--text-danger);
  margin: 0;
  padding: 0.6rem 0.85rem;
  border-bottom: 1px solid var(--border-subtle);
}
```

- [ ] **Step 5: KeyboardHelpOverlay `.group-title`, ReferencePane + AboutPane `.block-title`, GuidesPane `.pane-title`**

Markup: swap `font-heading` for `section-title` in each (`group-title font-heading` → `group-title section-title`, etc.).

CSS — all four blocks currently `margin: 0` + font-size + color; reduce each to:
```css
/* .group-title / .block-title / .pane-title respectively */
.group-title {
  margin: 0;
}
```
(GuidesPane's `.pane-title` loses its `font-size: 1rem` — intentional, lands on 0.95rem.)

- [ ] **Step 6: Verify** — `npm run lint:css && npm run check`, expect pass.

- [ ] **Step 7: Commit**

```bash
git add src/lib/LibrarySettings.svelte src/lib/GeneralSettings.svelte src/lib/GettingStartedSteps.svelte src/lib/KeyboardHelpOverlay.svelte src/lib/help/ReferencePane.svelte src/lib/help/AboutPane.svelte src/lib/help/GuidesPane.svelte
git commit -m "refactor(headers): section headers adopt shared .section-title voice"
```

---

### Task 5: Adopt `.ledger-label` (4 components)

Visual changes: sect 0.72→0.7rem + tracking, kb-group 0.78→0.7rem, col-header font swap, group-name 0.85→0.7rem (the flagged demotion — knob is the class's font-size if the visual pass rejects it).

**Files:**
- Modify: `src/lib/FilterPanel.svelte` — markup 230, 280; CSS 402-409
- Modify: `src/lib/help/ReferencePane.svelte` — markup 49; CSS 151-157
- Modify: `src/lib/GameSystemsSettings.svelte` — markup 143, 144; CSS 250-262
- Modify: `src/lib/SystemsView.svelte` — markup 518; CSS ~676-681

- [ ] **Step 1: FilterPanel `.sect`**

Markup ×2: `<div class="sect">Curation</div>` → `<div class="sect ledger-label">Curation</div>` (same for `Game systems`).

CSS before:
```css
/* Quiet small-caps section headers — ledger voice, like the tree.
   No rule under them. */
.sect {
  padding: 0.6rem 0.25rem 0.15rem 0.75rem;
  font-family: var(--font-heading);
  font-size: 0.72rem;
  letter-spacing: 0.09em;
  text-transform: uppercase;
  color: var(--text-tertiary);
}
```
After:
```css
/* Quiet small-caps section headers — ledger voice, like the tree.
   No rule under them. */
.sect {
  padding: 0.6rem 0.25rem 0.15rem 0.75rem;
}
```

- [ ] **Step 2: ReferencePane `.kb-group-title`**

Markup: `<h4 class="kb-group-title font-heading">{group.label}</h4>` → `<h4 class="kb-group-title ledger-label">{group.label}</h4>`

CSS before:
```css
.kb-group-title {
  margin: 0;
  font-size: 0.78rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-tertiary);
}
```
After:
```css
.kb-group-title {
  margin: 0;
}
```

- [ ] **Step 3: GameSystemsSettings `.col-header`**

Markup: `<button class="col-header col-tag" on:click={toggleSort}>Tag</button>` → `<button class="col-header col-tag ledger-label" on:click={toggleSort}>Tag</button>`; same append on the `col-keywords` span.

CSS before:
```css
.col-header {
  font-family: var(--font-body);
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--text-secondary);
  text-align: left;
  padding: 0;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  transition: color var(--transition-fast);
}
```
After (secondary override stays; sort-button hover rules untouched):
```css
.col-header {
  color: var(--text-secondary);
  text-align: left;
  padding: 0;
  transition: color var(--transition-fast);
}
```

- [ ] **Step 4: SystemsView `.group-name`**

Markup: `<span class="group-name">{group.tag}</span>` → `<span class="group-name ledger-label">{group.tag}</span>`

CSS before:
```css
.group-name {
  flex: 1;
  font-size: 0.85rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
```
After — **`color: inherit` is required**: the voice class sets tertiary, but group names take their per-system `--group-color` (and its hover change) from the parent `.group-head`:
```css
.group-name {
  flex: 1;
  color: inherit;
}
```

- [ ] **Step 5: Verify** — `npm run lint:css && npm run check`, expect pass.

- [ ] **Step 6: Commit**

```bash
git add src/lib/FilterPanel.svelte src/lib/help/ReferencePane.svelte src/lib/GameSystemsSettings.svelte src/lib/SystemsView.svelte
git commit -m "refactor(headers): ledger labels adopt shared .ledger-label voice"
```

---

### Task 6: Adopt `.readout-label` (6 components, zero visual change)

**Files:**
- Modify: `src/lib/LibrarySettings.svelte` — markup 134, 140, 144, 229, 250, 300; CSS 478-484 (stat-label), 649-657 (policy-legend), ~654-661 (meta-label)
- Modify: `src/lib/GeneralSettings.svelte` — markup 153; CSS 306-313
- Modify: `src/lib/help/AboutPane.svelte` — markup 38, 41; CSS 115-122
- Modify: `src/lib/DocumentStatsModal.svelte` — markup 73, 77, 81, 85, 89; CSS 133-139
- Modify: `src/lib/OllamaStatus.svelte` — markup 10; CSS 37-42
- Modify: `src/lib/GettingStartedSteps.svelte` — markup 55, 88, 125, 152; CSS 233-243

- [ ] **Step 1: LibrarySettings**

`.stat-label` is recipe-only → delete the block; markup ×3: `<div class="stat-label">INDEXED</div>` → `<div class="readout-label">INDEXED</div>` (same for CHUNKS, SYS).

`.meta-label` — markup: `<span class="meta-label">Last sync</span>` → `<span class="meta-label readout-label">Last sync</span>` (same for Storage); CSS keeps only:
```css
.meta-label {
  flex-shrink: 0;
}
```

`.policy-legend` — markup: `<legend class="policy-legend">…` → `<legend class="policy-legend readout-label">…`; CSS keeps only:
```css
.policy-legend {
  padding: 0 0.3rem;
}
```

- [ ] **Step 2: GeneralSettings `.experimental-legend`** — markup appends `readout-label`; CSS keeps only `padding: 0 0.3rem;`.

- [ ] **Step 3: AboutPane `.meta-label`** — markup ×2 appends `readout-label`; CSS keeps only `margin: 0;`.

- [ ] **Step 4: DocumentStatsModal `.stat-label`** — recipe-only → delete block; markup ×5: `<div class="stat-label">CHUNKS</div>` → `<div class="readout-label">CHUNKS</div>`.

- [ ] **Step 5: OllamaStatus `.badge` (status lamp)**

Markup: `class="badge font-heading"` → `class="badge readout-label"`.

CSS before:
```css
.badge {
  font-size: 0.7rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-tertiary);
}
```
After (tertiary rest-state override; `.badge.ok` / `.badge.partial` untouched):
```css
.badge {
  color: var(--text-tertiary);
}
```

- [ ] **Step 6: GettingStartedSteps `.field-status` (status lamp)**

Markup ×4: `<span class="field-status" class:ok={…}>` → `<span class="field-status readout-label" class:ok={…}>`.

CSS before:
```css
.field-status {
  flex-shrink: 0;
  font-family: var(--font-heading, var(--font-body));
  font-size: 0.7rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-tertiary);
}
```
After (`.field-status.ok` untouched):
```css
.field-status {
  flex-shrink: 0;
  color: var(--text-tertiary);
}
```

- [ ] **Step 7: Verify** — `npm run lint:css && npm run check`, expect pass.

- [ ] **Step 8: Commit**

```bash
git add src/lib/LibrarySettings.svelte src/lib/GeneralSettings.svelte src/lib/help/AboutPane.svelte src/lib/DocumentStatsModal.svelte src/lib/OllamaStatus.svelte src/lib/GettingStartedSteps.svelte
git commit -m "refactor(headers): readout labels and status lamps adopt .readout-label voice"
```

---

### Task 7: Adopt `.micro-label` (3 components)

Only visual change: hidden-badge 0.6 → 0.65rem.

**Files:**
- Modify: `src/lib/SearchInspector.svelte` — markup 91; CSS 232-241
- Modify: `src/lib/SearchResults.svelte` — markup 177; CSS 419-429
- Modify: `src/lib/SearchScopeBar.svelte` — markup 69, 94, 118, 143, 163, 181, 206, 225 (+ the ninth `chip-prefix` near 256); CSS 393-397

- [ ] **Step 1: SearchInspector `.badge`**

Markup: `<span class="badge" title="…">hidden</span>` → `<span class="badge micro-label" title="…">hidden</span>`.

CSS: keep pill anatomy, drop recipe:
```css
.badge {
  flex-shrink: 0;
  padding: 0.05rem 0.35rem;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  font-style: italic;
}
```

- [ ] **Step 2: SearchResults `.hidden-badge`**

Markup: `<span class="hidden-badge" title="This file is hidden in the tree.">hidden</span>` → `<span class="hidden-badge micro-label" title="This file is hidden in the tree.">hidden</span>`.

CSS: keep pill anatomy, drop recipe (`font-size: 0.6rem`, tracking, transform, color):
```css
.hidden-badge {
  flex-shrink: 0;
  padding: 0.05rem 0.35rem;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  font-style: italic;
}
```

- [ ] **Step 3: SearchScopeBar `.chip-prefix`**

Markup: append `micro-label` to every `<span class="chip-prefix">` (9 sites).

CSS: delete the base `.chip-prefix` block (recipe-only) — but KEEP the state overrides `.chip.exclusion .chip-prefix` and `.chip.solo .chip-prefix`, which is why the `chip-prefix` class stays in markup.

- [ ] **Step 4: Verify** — `npm run lint:css && npm run check`, expect pass.

- [ ] **Step 5: Commit**

```bash
git add src/lib/SearchInspector.svelte src/lib/SearchResults.svelte src/lib/SearchScopeBar.svelte
git commit -m "refactor(headers): badges and chip prefixes adopt .micro-label voice"
```

---

### Task 8: Contrast check (spec-required gate)

**Files:**
- Create: `<scratchpad>/contrast.mjs` (not committed)
- Modify: `docs/design/2026-08-09-header-voices-design.md` (record results in Notes)

- [ ] **Step 1: Write the script** (token values from `src/app.css:82-103`)

```js
// WCAG 2.1 contrast of label colors vs surface tokens
const colors = {
  'text-tertiary (#6e7681)': [0x6e, 0x76, 0x81],
  'text-secondary (#8b949e)': [0x8b, 0x94, 0x9e],
};
const surfaces = {
  'bg-app (25,25,25)': [25, 25, 25],
  'bg-container (35,35,35)': [35, 35, 35],
  'bg-header (46,46,46)': [46, 46, 46],
};
const lum = ([r, g, b]) => {
  const f = (c) => ((c /= 255) <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
};
const ratio = (a, b) => {
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
};
for (const [tn, tv] of Object.entries(colors))
  for (const [sn, sv] of Object.entries(surfaces))
    console.log(`${tn} on ${sn}: ${ratio(tv, sv).toFixed(2)}:1 ${ratio(tv, sv) >= 4.5 ? 'PASS' : 'FAIL'}`);
```

- [ ] **Step 2: Run it** — `node <scratchpad>/contrast.mjs`

Expected (approximately): tertiary ≈ 3.8 / 3.4 / 3.0 — FAIL on all three surfaces; secondary ≈ 5.7 / 5.1 / 4.4 — PASS on app and container, marginal FAIL on bg-header. Exact numbers from the script are authoritative.

- [ ] **Step 3: Record results in the design doc's Notes section** (append the measured ratios and a sentence noting the token decision is out of scope for this project, per spec).

- [ ] **Step 4: Commit**

```bash
git add docs/design/2026-08-09-header-voices-design.md
git commit -m "docs(design): record header-label contrast measurements"
```

---

### Task 9: Final verification sweep

- [ ] **Step 1: Grep for leftover recipes** — confirm no adopted class still declares recipe props locally:

```bash
grep -rn -E "\.(panel-title|modal-title|field-title|danger-title|group-title|block-title|pane-title|sect|kb-group-title|col-header|group-name|stat-label|meta-label|policy-legend|experimental-legend|field-status|hidden-badge|chip-prefix)\s*\{" src/lib -A6 | grep -E "font-family|font-size|letter-spacing|text-transform" ; echo "exit: $?"
```
Expected: no matches (`exit: 1`).

- [ ] **Step 2: Full local checks**

Run: `npm run lint:css && npm run check && npx vitest run`
Expected: all pass.

- [ ] **Step 3: Push and watch CI**

```bash
git push
```
Expected: Linux CI suite green on main.

- [ ] **Step 4: Hand off for visual pass** — user runs the app and eyeballs the expected diffs (spec Verification §4), with special attention to the systems-view group-name demotion.

**Follow-ups after the visual pass (not part of this plan):** the tertiary-contrast token decision (handled separately, like the vermilion amendment), and syncing the six voices to the claude.ai design-system project via DesignSync.
