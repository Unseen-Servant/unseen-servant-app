# Header Voices — Design

**Date:** 2026-08-09
**Status:** Complete. Implemented 2026-08-09 on main; visual pass done.
Tertiary contrast amendment landed with it (see Notes). DesignSync to the
claude.ai design project done the same day (see Notes).

## Problem

Header styling drifted into per-component variants: the same visual rank
appears at three sizes (0.9 / 0.95 / 1rem section headers), small-caps
group labels exist in five slightly different recipes, one table header
uses the body font, and one dialog title is the app's only bold header.
Every recipe is re-declared in scoped component CSS, so drift recurs.

## Decision

Six shared header classes in `src/app.css` (joining the existing Font
Utilities block), one per voice. A class bundles the full recipe —
font-family, size, letter-spacing, text-transform, line-height, default
color. Layout properties (margins, padding, flex) stay in component CSS.
Components apply the class in markup, like `font-heading` today.
Precedent: the `.sm-btn` shared button anatomy.

Raw rem values live inside the class definitions — consistent with the
tokens rule (stylelint enforces colors only) and every header number
stays in one file.

### The voices

All voices set `line-height: 1.2`. Font is Almendra unless noted.

| Class | Recipe | Use when… |
|---|---|---|
| ~~`.panel-title`~~ | *retired 2026-09-27* | Panel mastheads and the scope bar became `.nameplate` plates, which name themselves with `.ledger-label` in `--text-secondary` — the modal rail's voice, for the same reason: a module's name is not content, so it doesn't wear parchment. Cinzel, whose only job this was, was removed with it. |
| ~~`.dialog-title`~~ | *retired 2026-08-13* | Modals name themselves with `.ledger-label` on the rail; see [the rack-unit design](2026-08-12-modal-rack-units-design.md). |
| `.section-title` | 0.95rem · `--text-primary` | Titling a content section inside a surface (settings groups, help blocks). |
| `.ledger-label` | 0.7rem · 0.08em · uppercase · `--text-tertiary` | Heading a group of rows — quiet, sits below row-text size by design. |
| `.readout-label` | 0.7rem · 0.08em · uppercase · `--text-secondary` | Labeling a value — the key half of a key/value or stat pair. |
| `.micro-label` | `--font-body` · 0.65rem · 0.06em · uppercase · `--text-tertiary` | Inline annotation riding on other content (badges, chip prefixes). |

`.ledger-label` and `.readout-label` share metrics deliberately; color
carries the semantic difference (tertiary = structural grouping,
secondary = data label). Status lamps adopt `.readout-label` metrics and
override color per lamp state — color semantics stay token behavior per
the design conventions.

## Adoption map

### `.panel-title` — no visual change

- `CollectionsPanel.svelte` `.panel-title`
- `FilterPanel.svelte` `.panel-title`

### ~~`.dialog-title`~~ — retired 2026-08-13

Removed when modals became rack units. A dialog no longer wears a title in
the accent voice: parchment is reserved for content and data, and a module's
name is neither, so the rail carries `.ledger-label` instead — a silk-screened
nameplate rather than a heading. `Modal.svelte` was this class's only
consumer.

### `.section-title`

- `LibrarySettings.svelte` `.field-title` ×4 — no change
- `LibrarySettings.svelte` `.danger-title` — **0.9 → 0.95rem**; keeps
  local `--text-danger` color, padding, border
- `GeneralSettings.svelte` `.field-title` ×2 — no change
- `GettingStartedSteps.svelte` `.field-title` ×5 — no change; keeps
  local `flex: 1`, `min-width: 0`
- `KeyboardHelpOverlay.svelte` `.group-title` — no change
- `help/ReferencePane.svelte` `.block-title` ×2 — no change
- `help/AboutPane.svelte` `.block-title` ×2 — no change
- `help/GuidesPane.svelte` `.pane-title` — **1 → 0.95rem**

### `.ledger-label`

- `FilterPanel.svelte` `.sect` ×3 (one is the `sect-split` "Hidden
  items" variant) — **0.72 → 0.7rem, 0.09 → 0.08em**
- `help/ReferencePane.svelte` `.kb-group-title` — **0.78 → 0.7rem**
- `GameSystemsSettings.svelte` `.col-header` ×2 — **Crimson Text 600 →
  Almendra, 0.03 → 0.08em**; keeps local `--text-secondary` override,
  sort-button hover, column layout
- `SystemsView.svelte` `.group-name` — **0.85 → 0.7rem, 0.06 →
  0.08em**; keeps per-system `--group-color` and hover. Largest visual
  change in the project; validate in the visual pass — the single knob
  if it reads over-demoted is this class's font-size.
- `CollectionsPanel.svelte` `.empty-label` ×2 — no change (found in
  final review; recipe was byte-for-byte `.ledger-label`)

### `.readout-label` — no visual change

- `LibrarySettings.svelte` `.stat-label`, `.meta-label`, `.policy-legend`
- `GeneralSettings.svelte` `.experimental-legend`
- `help/AboutPane.svelte` `.meta-label`
- `DocumentStatsModal.svelte` `.stat-label`
- `GameSystemsSettings.svelte` `.label` ×4 (found in final review) —
  form labels keep local margin; the built-in/custom badges shared the
  same colliding selector and already rendered with this recipe, so
  they adopt too, keeping pill padding/radius and color overrides
- Lamps (keep local rest/state color overrides):
  `OllamaStatus.svelte` `.badge`, `GettingStartedSteps.svelte`
  `.field-status`

### `.micro-label`

- `SearchInspector.svelte` `.badge` — no change; pill anatomy (border,
  italic, padding) stays local
- `SearchResults.svelte` `.hidden-badge` — **0.6 → 0.65rem**; pill
  anatomy stays local
- `SearchScopeBar.svelte` `.chip-prefix` — no change

## Out of scope

- **Hero titles** — `LaunchSplash` (1.6rem) and `GettingStartedPage`
  (1.25rem): different surfaces, never co-occur.
- **Settings tabs** — `SettingsModal` `.tab-btn`: a control, not a header.
- **SystemBadge** — content identity chip with its own documented
  concept (monochrome parchment, die icon), not a label.
- **`GettingStartedSteps` `.opt`** — lowercase body-text suffix.
- Non-header text sizes (row text, descriptions, buttons).

## Notes

- `line-height: 1.2` is new on all voices (previously inherited). Mostly
  single-line headers; minor vertical-rhythm shifts are possible and are
  covered by the visual pass.
- **Contrast measured (2026-08-09, WCAG 2.1, 4.5:1 normal-text target):**
  `--text-tertiary` #6e7681 — 3.83:1 on `--bg-app`, 3.42:1 on
  `--bg-container`, 2.96:1 on `--bg-header` (FAIL on all three).
  `--text-secondary` #8b949e — 5.72:1 / 5.11:1 / 4.42:1 (PASS, PASS,
  FAIL on `--bg-header`). Small-caps labels at 0.65–0.7rem count as
  normal text. Any token change is a separate decision (as with the
  vermilion amendment), out of scope for this project.
- **Tertiary contrast amendment (2026-08-09, follow-up decision):**
  `--text-tertiary` brightened one step to **#7d8590**
  (`oklch(0.614 0.019 256.3)`, from `oklch(0.563 …)` — hue and chroma
  held, ΔL +0.05, the same step size as the vermilion amendment's
  0.579 → 0.630). `--text-secondary` **unchanged**. Re-measured:
  tertiary now 4.71:1 on `--bg-app` (PASS), 4.21:1 on `--bg-container`,
  3.64:1 on `--bg-header`, 3.44:1 on `--bg-focused`.

  Three findings drove it, and they are worth not re-deriving:

  1. **Measure against surfaces the token actually meets.** The
     `--bg-header` column above is a hypothetical pairing: no
     tertiary or secondary *text* sits on `--bg-header` anywhere in
     the app. Its only text use is the `<thead>` of extracted tables
     in `SearchInspector` snippets, which inherit `--text-primary`
     (8.80:1). `Header.svelte` `.view-segment` looks like a
     counter-example but its well is `--bg-app`, and the `.current`
     segment that does take `--bg-header` switches to
     `--text-primary`. Secondary's lone recorded failure was against
     that surface, so it needed no change. The real surfaces for
     tertiary text are `--bg-app` and `--bg-container` at rest, plus
     `--bg-focused` on row hover/keyboard focus.
  2. **The precedent is narrower than "brighten until AA."** Commit
     1e6e730 brightened vermilion to clear 4.5:1 *on `--bg-app`
     specifically* and left it at 4.13:1 on `--bg-container` and
     3.57:1 on `--bg-header`. The house rule is: clear AA on the
     surface the color lives on, accept the rest, record it. The new
     tertiary profile (4.71 / 4.21 / 3.64 / 3.44) is deliberately the
     same shape as the accepted vermilion profile.
  3. **Full AA on `--bg-container` would cost the voice system.**
     Tertiary needs ≥ #828b96 (`oklch(0.633 …)`) to reach 4.55:1
     there — which compresses the tertiary→secondary OKLCH gap from
     0.099 to 0.029. `.ledger-label` and `.readout-label` are
     byte-identical apart from that color, so the gap *is* the
     distinction. At #7d8590 the gap is 0.049 — half the original but
     still 3× the `--bg-header`/`--bg-focused` delta (0.016) that
     reads as two distinct surfaces today. That is where the line was
     drawn.

  The token is used at ~55 sites, not just the two label voices —
  meta text, empty states, icon strokes, dashed drop targets — so the
  edit is app-wide "dim chrome gets one step brighter", and belongs in
  a visual pass. Residual known gaps, accepted: tertiary text on
  `--bg-container` (4.21:1) and on hovered/focused rows
  (`--bg-focused`, 3.44:1). Both clear the 3:1 non-text threshold, and
  the content there is quiet by design (grip glyphs, disabled rows,
  weak-result callouts).
- Several components carry a pointless `var(--font-heading,
  var(--font-body))` fallback; adopting the shared classes removes those
  declarations as a side effect.
- **DesignSync done (2026-08-09), baseline commit 5b40f7f.** New card
  `foundations/header-voices.html`; the six voices, the font utilities,
  the shared `.sm-btn` and `--text-tertiary` #7d8590 added to
  `assets/tokens.css`. Adoption propagated to the systems-view,
  filter-panel, forms, search-results, scope-bar and collections-panel
  cards. Two contradictions surfaced and were corrected against code:
  the collections-panel card had stale pigment names (Ochre / Orpiment /
  Aegean, Verdigris on the wrong hue — `PIGMENTS` in `palette.ts` is
  authoritative), and `collection-colors.html` still cited danger as
  #cf4232 instead of the amended #e15342. Ledger in the project's
  `github.md`.

## Verification

1. `npm run lint:css` and `npx svelte-check` pass.
2. Grep confirms no component still declares font-family / font-size /
   letter-spacing / text-transform for the adopted header classes.
3. Contrast check done and recorded (see Notes).
4. Visual pass by the user in the running app. Expected visible diffs:
   GuidesPane title −0.05rem, danger title +0.05rem, ConfirmDialog
   unbolded, col-header font swap, sect/kb-group converge on 0.7rem,
   group-name demotion, hidden-badge +0.05rem.
