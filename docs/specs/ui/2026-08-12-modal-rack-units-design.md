# Modals as Rack Units — Design

**Date:** 2026-08-12
**Status:** Code complete 2026-08-13, in 26 commits (`766cde4`..`647d7ca`).
Automated verification is green; the visual, keyboard, screen-reader,
detent and reduced-motion passes in [Verification](#verification) are
outstanding and are what close this out. Three decisions listed there need
the app running.

**Scope:** Frontend only — `src/lib/Modal.svelte`, `src/lib/ConfirmDialog.svelte`,
`src/lib/confirmStore.ts`, `src/lib/DocumentStatsModal.svelte`,
`src/lib/SettingsModal.svelte`, `src/lib/LibrarySettings.svelte`,
`src/lib/GameSystemsSettings.svelte`, `src/lib/KeyboardHelpOverlay.svelte`,
`src/lib/keybindings.ts`, `src/lib/confirmKeys.ts`, `src/app.css`. No Rust or
sidecar changes; one optional Tauri command call is discussed in
[Readout data](#readout-data). Retiring the inline two-step (open decision 1)
makes `LibrarySettings.svelte` a behaviour change, not only a restyle.

**Supersedes** the incremental proposals reviewed on 2026-08-12 (headerless
confirm, recessed Document-info well, bracketed Danger Zone controls). Those
were the right small moves; this replaces them with the structural one that
makes most of them unnecessary. It does **not** supersede
[the modal audit](2026-08-11-modal-audit-design.md), whose five adoption steps
are shipped and which this builds on.

---

### What the build turned out to be

Ordered by how much they'd cost to rediscover.

- **The keyboard model was designed for keys a human presses once.** Holding
  the delete chord on a file row committed the deletion without the prompt
  being read: the dialog opens and focuses itself within a microtask, far
  inside the macOS repeat delay, so auto-repeat keydown #2 landed on the
  focused dialog and fired the commit. It compounded — once the dialog
  closed, the `dialog[open]` guard went false and further repeats re-entered
  the delete handler on the still-focused row. The invariant now holds as one
  sentence: *the commit is reachable only from a pointer click, or from a
  keydown with `repeat === false`* — and one physical press produces exactly
  one such keydown, which was consumed raising the prompt. Its sibling lives
  in `CommitSwitch`: a held Enter on an auto-focused commit is the browser
  synthesizing one click per repeat, which no dialog handler can intercept.
- **A face is a promise, and only a commit may make it** — see
  [the rule](#a-confirmation-is-a-switch-you-throw). Nearly shipped wrong in
  two bays.
- **`ConfirmRow.from` became `value`.** Four of the rows this ships have no
  transition, so `from` named one that does not exist. The tell was in the
  doc comment, which had to apologise for the name on its own first line.
- **Contrast does not travel between surfaces.** The rail nameplate inherited
  `.ledger-label` from the scope bar, where tertiary-on-`--bg-app` is 4.72:1;
  on `--bg-header` the same pair is 3.64:1. The escape legend was worse — two
  compounding opacities put the chord at 1.79:1, below the non-text floor and
  dimmer than the `×` it replaced. Both now sit one ramp step up.
- **`flex-shrink: 0` on the nameplate** defeated the `text-overflow` rule
  three lines above it and would have pushed the escape outside the dialog
  border on any long filename. Copied from the scope bar, whose nameplate is
  a static string rather than user data.
- **`column-count` on the sheet's scroller** would have rendered four columns
  scrolling sideways — a multicol box with a definite block size spills into
  inline-direction overflow columns. Measured: 1272px of scrollWidth against
  a 640px client, with no vertical scroll at all.
- **Three modules were orphaned by this work and removed**: `inputModality.ts`
  and its test (the ring heuristic it served is gone), `ConfirmRequest.cancelLabel`,
  and `.chord-bare` (the sheet was its only consumer; menus use
  `.menu-chord.bare`). `.dialog-title` is also orphaned but **kept** pending a
  decision — see [Verification](#verification).
- **Reviews found what tests could not.** There is no jsdom here, so no
  component is unit-testable; every defect above was caught by reading,
  measuring, or mutation-testing rather than by the suite, which stayed green
  throughout at 408-411 tests.

---

## Problem

The audit fixed what was *wrong* with the modals. It did not ask whether they
were the right kind of object. They are not.

The main window is an instrument. It has a master section — nameplate, its
switch, a divider rule, then the channels (`SearchScopeBar.svelte:95`). It has
18px hardware squares where *the letter on the switch is the key that throws
it* (`app.css:329`). It has chips the source itself describes as *"the button
materialized"* (`SearchScopeBar.svelte:430`). It has a hits-over-files meter in
tabular figures, detent flashes on engage, and a colour law that separates a
mode you switched on (purple, glow) from a removal (danger tint, deliberately
no glow).

The modals inherit none of it. They are OS dialogs — titled plate, prose body,
right-aligned text buttons — painted in the app's palette. Every fix in the
audit made them *better dialogs*. None made them part of the instrument.

Two specific consequences:

- **A confirmation answers "how bad is this" with an adjective.** The one place
  it doesn't is the Danger Zone's armed label, *"Reprocess 128 files?"*, which
  the audit correctly called the best confirmation copy in the app. It is good
  because it is a readout. Nothing else got one.
- **The colour law stops at the modal boundary.** Re-indexing is an activation;
  deleting is a removal. Every S and M button in the window draws that
  distinction structurally. In a confirm dialog it is carried by a hue on a
  word.

---

## Decision

### A dialog is a rack unit

Every modal becomes a unit bracketed by two rails, both on `--bg-header` — the
plate the Header and StatusBar already share, where `StatusBar.svelte:168`
notes the two bars *"bracket the workspace as one piece of chrome"*. A modal
that brackets its own content the same way reads as a small instance of the
instrument rather than a card floating over it.

```
┌─ rail ────────────────────────────────────────┐
│ NAMEPLATE  │ …rail slot…            esc close │   --bg-header, 28px
├───────────────────────────────────────────────┤
│  bays: labelled regions, --bg-app wells       │   --bg-container, --modal-pad
├───────────────────────────────────────────────┤
│                              Commit  [ ⌫ ]    │   --bg-header, ≥28px
└───────────────────────────────────────────────┘
```

| Part | Recipe | Inherited from |
|---|---|---|
| Rail | `--bg-header`, `--statusbar-height`, hairline border | Header / StatusBar |
| Nameplate | `.ledger-label` (Almendra 0.7rem, 0.08em, uppercase, tertiary) | `SearchScopeBar` `.nameplate` |
| Divider | 1px × 12px `--border-subtle` | `SearchScopeBar` `.master-rule` |
| Bay | optional `.ledger-label` caption + content | new composition, no new values |
| Well | `--bg-app`, `--radius-well`, `--border-subtle` dividers | `--radius-well`'s own docstring (`app.css:121`) |
| Commit switch | `.sm-btn` verbatim, 18px, detent, 0.97 press tick | `app.css:329` |
| Escape | mono chord legend, `--text-tertiary` at 0.8 | `chordHint` voice |

**The nameplate drops from `.dialog-title` to `.ledger-label`.** Parchment
(`--text-accent`) is reserved for content and data; a module's name is neither.
This frees the accent voice and fixes the inversion noted during the mockup
review, where *"Delete file"* sat in the data colour above the actual question
in plain primary. A plug-in window is named for the plug-in, not the preset.

### A confirmation is a switch you throw

The commit is not a word in brackets. It is the app's 18px hardware square
carrying the key that fires it, with its label beside it as a nameplate — the
scope bar's `Scope │ B` grammar, mirrored. The pair is one `<button>`.

The colour law applies for the first time:

| Prompt | Nature | Switch dressing |
|---|---|---|
| Re-index file, Re-index all | activation | `--text-active` border, 15% wash, `--glow-active`, `detent-glow` |
| Delete anything, Reset to defaults | removal | `--text-danger` ink, 45% border, 10% wash, **no glow**, `detent-flat` |

Both recipes already exist as `.sm-btn.solo-on` / `.sm-btn.bypass-on` and
`.sm-btn.mute-on`. Nothing new is defined; the selector list grows.

**A face is a promise, and only a commit may make it.** The switch's face
carries a key, which asserts that pressing that key fires this control. So a
`CommitSwitch` may only be used where its container actually implements the
key — that is, in a unit's commit rail:

| Control | Container implements the key? | Wears |
|---|---|---|
| Confirm prompt's commit | yes — `ConfirmDialog`'s keydown (⌘⌫) or native button activation (↵) | `CommitSwitch` |
| Game system Add / Save | yes — `GameSystemsSettings.handleWindowKey` (↵ from a text input, ⌘↵ globally) | `CommitSwitch` |
| Danger Zone rows, game system Delete / Reset | **no** — they sit in a bay and raise a prompt | `ActionButton kind="confirm" danger` |

This was very nearly got wrong: an earlier draft put `CommitSwitch` in both
danger *bays*, where they would have worn `⌘⌫` and asserted
`aria-keyshortcuts="Meta+Backspace"` for a shortcut nobody implements — and in
the game-system modal, focus sits in a text input where ⌘⌫ genuinely deletes a
line, so the face would have named a key that does something else entirely.

A bay-level destructive action is not a commit; it is an action that *raises*
one. It keeps the app's existing bracketed-danger-text vocabulary.

### Cancel is a legend in the top rail

Cancel is not a peer of the commit — it is the absence of an action. It becomes
a mono chord legend reading `esc cancel`, sitting in the **top rail beside the
nameplate**, and nowhere else. It stays a real focusable `<button>`.

The rail's right slot is the **dismiss slot for every unit**, so the shell's
`×` is retired app-wide: Document info and the keyboard sheet read `esc close`
in the same position. That closes the audit's
[open decision 2](2026-08-11-modal-audit-design.md#open-decisions) outright —
the ways out are Esc, the backdrop, and one legend that *names* Esc.

Rejected: keeping the escape in the commit strip (restates the same exit twice
in one dialog — the specific note that prompted this revision), and keeping `×`
on read-only units (re-creates a split by surface, which is the fault this
whole document is about).

### The readout is the argument

Every prompt that can name its damage as a quantity does, in a `--bg-app` well
of key/value rows with `tabular-nums`:

```
FILE      Xanathar's Guide to Everything.pdf
CHUNKS    3,412  →  0
ON DISK   88.4 MB → Trash
```

Where a number would be a lie, a word stands in — *Trash*, *Loose*,
*untouched* — rendered in `--text-secondary` rather than the prompt's tone,
because those are the reassurances, not the damage.

---

## The keyboard

The mockup deferred this and it is the sharpest constraint in the design: **if
the switch face carries a key, that key must actually fire it.** Getting this
wrong reintroduces the audit's F1 (Enter committing against the user's
intent), which the audit fixed by *deleting* the dialog-level Enter handler and
warned must not come back.

Resolution, split by nature:

**Activation prompts** (`danger` unset), **raised by keyboard**. The commit
switch takes initial focus. Its face reads `↵`, and Enter is handled
**natively by the focused button** — no dialog-level listener, exactly as F1's
fix left it.

**Activation prompts raised by pointer.** Focus is *not* placed. A mouse user
who picked Re-index from a context menu never asked for a control to be
focused, and ringing one reads as a stray highlight — the rule the panes
already follow, where nothing is ringed until you navigate. Focus parks on
the dialog, so Esc works and nothing is marked. `inputModality.ts` answers
which hand raised it.

This gate was in the app before this redesign and was dropped when
`ConfirmDialog` was rebuilt — restored 2026-08-13 after the visual pass
caught it. It also removes the need for the forced `:focus` rule that F2
called for: the only programmatic focus now follows a keypress, so
`:focus-visible` matches on its own, and a plain mouse click on the switch
correctly rings nothing.

**Removal prompts** (`danger: true`). Initial focus goes to the **dialog
element itself** (`tabindex="-1"`, no visible ring — the shell already does
this when `autofocus={false}` finds nothing). Enter is therefore inert: there
is no focused button for it to activate. Tab reaches the escape legend, then
the commit.

The switch face reads the delete chord (`⌘⌫` on mac, `Del` elsewhere) and is
fired by pressing it, matched with the existing
`isDeleteChord()` (`keybindings.ts:193`) on a **dialog-scoped** `on:keydown`.

This is the strongest part of the design and the reason to accept it:

- **The key that raised the deletion is the key that commits it.** ⌘⌫ on a file
  row raises the prompt; ⌘⌫ again fires it. That is arm-then-fire in the
  keyboard domain — the transport idiom the app already teaches — and it
  generalises to prompts raised by mouse or by a footer button, where the
  switch face teaches the chord.
- **Enter can never destroy anything.** The audit's F1 safety survives without
  needing Cancel to hold focus, which matters now that Cancel is a quiet rail
  legend and focusing it would be obscure.
- The listener is on the `<dialog>`, not on `window`. The audit's note about
  `+page.svelte:2127`'s `dialog[open]` guard and
  `GameSystemsSettings.svelte:88`'s `$confirmPrompt` guard is unaffected: both
  suppress *outer* handlers while a prompt is open, which is still what we
  want.
- Confirms contain no text inputs, so there is no field for ⌘⌫ to be stolen
  from. Guard `event.isComposing` anyway, per the house rule in
  `keybindings.ts`.

A new binding is registered for the sheet: `confirm.commit`, scope `modal`.
That scope is already excluded from the cheat sheet by
`KeyboardHelpOverlay.svelte:11`, so the sheet does not grow; the binding exists
so the chord has one definition and the switch face reads it rather than
hardcoding a glyph.

---

## Store changes

`ConfirmRequest` gains optional readout rows. The store stays
presentation-free — no colours, no labels-with-defaults — per the rule the
audit set when it moved defaults into the dialog.

```ts
export interface ConfirmRow {
  label: string;            // rendered in the .ledger-label voice
  value: string;            // the figure
  to?: string;              // what it becomes, when there is a transition
  // This row's `to` is a reassurance rather than damage ("untouched",
  // "Loose"), so the dialog renders it calm instead of in the prompt's
  // tone. Semantic, not presentational: the caller states what the value
  // means, the dialog decides how that looks.
  unchanged?: boolean;
}

export interface ConfirmRequest {
  title: string;
  message?: string;
  rows?: ConfirmRow[];      // new
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
}
```

The field carrying the figure is `value`, not `from`: four of the rows this
ships have no transition at all, and `from` named one that does not exist.

`rows` is optional and `message` is unchanged, so **adoption is per call site**
and no caller is blocked on data it cannot cheaply get. A prompt with no rows
renders exactly as it does today, inside the new shell.

### Readout data

There are five prompt call sites today, and retiring the two-step (open
decision 1) adds two more. Most can fill rows from state they already hold.
The exception is delete-file (`+page.svelte:2552`), which has no chunk count. Two
options, decided in [Adoption](#adoption):

1. **Fetch it.** `get_document_stats` already exists and
   `DocumentStatsModal.svelte:26` calls it. Cost: one `await` between the
   keystroke and the prompt appearing, on a path that is currently instant.
2. **Omit the row.** Delete-file shows file name and size only. Cheaper,
   honest, and the size row still answers "how big is this".

Option 2 first. Option 1 is a follow-up worth measuring, not worth guessing at.

---

## Per-surface changes

### Confirm prompt — `ConfirmDialog.svelte`

Rebuilt on the unit. Rail nameplate + `esc cancel`; one bay holding rows and/or
the message; commit strip with the switch. `ActionButton` leaves this file.

Width stays `sm` (440px); height grows roughly 137px → 210px with rows. The
nested case (a prompt over the game-system unit) still fits a 520px Settings
modal.

### Document info — `DocumentStatsModal.svelte`

**No commit strip** — there is nothing to commit, and a unit that ends at its
last bay is one you cannot operate. That absence is the signal.

Rail: nameplate `Document`, divider, an amber lamp for "live in the index"
(amber is connectivity in this system), `esc close`.

Two bays rather than one grid: **Identity** (file, path, system) and **Index**
(chunks, pages, size, indexed). They answer different questions and only the
second changes; the current four-across grid has no room for a fifth reading
without a redesign.

The filename moves out of the title into the first readout row, where it gets
the full 560px and the same mono column as everything else about it. This
retires the truncation added in the audit's step 5 for this surface — the shell
keeps it, since a long game-system name can still overflow a rail.

The absolute timestamp leaves its `title` attribute and becomes visible beside
the relative one.

### Settings — `SettingsModal.svelte`, `LibrarySettings.svelte`

Tabs move **onto the rail** as a segmented well, reusing `.view-switch`
(`Header.svelte:233`) instead of a second underline system. Help's sub-tabs
become a second segmented well inside the first bay at the same size. This
retires the tab/sub-tab divergence the audit deferred as out of scope, and buys
back ~34px of vertical space in a 520px dialog.

The bottom rail carries *"Changes apply immediately"* and nothing else — a rail
explaining its missing commit still reads as a rail you could have operated.

Danger Zone becomes a bay: a `--text-danger`-tinted well with a row per action.
`.btn-danger` and `.btn-ghost` (`LibrarySettings.svelte:658`, `:731`) are
deleted.

### Game system edit — `GameSystemsSettings.svelte`

Rail nameplate + `esc close`; bays for Tag and Keywords; commit strip carrying
only `Save` (activation dressing). **Delete** and **Reset to defaults** move
out of the footer into a bay action row — the strip is the commit rail, and a
destructive secondary is not the unit's commit.

The two hint paragraphs collapse to the one sentence that changes behaviour
(*a folder name beats PDF content*); the rest moves to Help → Reference.

Also folds in the audit's parked nit: `GameSystemsSettings.svelte:41` runs a
redundant `tagInput.focus()` that duplicates the shell's own text-input
heuristic. (The audit recorded it at `:39`; it has drifted two lines since.)

### Keyboard sheet — `KeyboardHelpOverlay.svelte`

Scopes become bays with `.ledger-label` nameplates, two columns
(`column-count: 2` + `break-inside: avoid`), chords right-aligned against their
labels.

Bare-key chords that light a physical switch (`S M P B E X`) render as **key
caps** with a purple-tinted border; bare keys with no switch (`R A`) render as
plain caps; modifier chords stay mono text. This encodes something true —
*there is a square in the window for this key* — and needs one flag per
binding in `KEYBINDINGS`.

This is the most cuttable idea in the document. See
[Risks](#risks).

---

## Adoption

Ordered so each step leaves the tree shippable, and so the reversible parts
land before the arguable ones.

1. **The shell.** `Modal.svelte` gains named `rail` and `commit` slots, the
   `--bg-header` rails, the nameplate voice, and the escape legend; the `×` is
   deleted. Every modal adopts the rails with no behaviour change.
   `aria-labelledby` moves to the rail nameplate.
2. **The commit switch.** New `CommitSwitch.svelte` over the existing `.sm-btn`
   recipe; `ConfirmDialog` rebuilt on the unit with the keyboard model above.
   `confirmStore` unchanged at this step.
3. **The readout.** `ConfirmRow` added to the store; call sites fill rows
   where the data is already in hand.
4. **Document info** and **Game system edit** onto bays.
5. **Settings**: tabs onto the rail, sub-tabs unified, Danger Zone as a bay.
6. **Keyboard sheet**: bays, columns, key caps.

Steps 4–6 are independent of each other and of 3.

---

## Open decisions

1. ~~**Does the inline two-step survive?**~~ **Resolved 2026-08-12: no.**
   The audit's *"one doctrine, two idioms"* collapses into one idiom — every
   destructive action raises a unit, and arm-then-fire is retired.

   What forced it was counting, during implementation, what the readout well
   would actually contain. Of the eight rows planned across the call sites
   that had figures in hand: **four were identity rows** (a name, a tag),
   **three were reassurances** (`→ Loose`, `→ untouched`), and exactly **one**
   was a genuine damage transition. The flagship readout this design argues
   for — `CHUNKS 3,412 → 0` — shipped nowhere. Delete-file has no chunk count
   (`FileItem` carries only `name`/`path`/`is_dir`/`children`), and
   delete-index, where the figures are real and dramatic, never opened a
   prompt at all.

   So the well was set to grow every confirmation from ~137px to ~210px in
   order to restate strings the prompt already had. Routing the Danger Zone
   through prompts is what lets the feature make its own argument, on the one
   surface where the numbers genuinely matter:

   ```
   FILES     128     → 0
   CHUNKS    41,203  → 0
   STORAGE   2.14 GB → 0 B
   PDFs      128     → untouched
   ```

   Note the two Danger Zone rows grade differently: re-indexing rebuilds and
   destroys nothing, so it is an **activation** (purple, lit, Enter commits);
   deleting the index is a **removal** (danger tint, no glow, ⌘⌫ commits). The
   zone names the blast radius; the flag names the kind of change.

   **What is lost, recorded deliberately:** the armed label naming the damage
   (*"Reprocess 128 files?"*) was the best confirmation copy in the app. It is
   not discarded — it becomes the rows above, saying the same thing in more
   detail in the app's own tabular-figure idiom. If the prompt reads worse
   than the two-step did, that judgement belongs in the visual pass and
   reverting is one commit.
2. ~~**The stacked scrim, carried forward undecided.**~~ **Resolved
   2026-08-13** in [The Scrim: Extent and Depth](2026-08-13-scrim-extent-and-depth-design.md),
   which takes it up together with a second scrim question this design raised
   without noticing: a rack unit wears `--bg-header` rails so it reads as part
   of the instrument, and then the scrim dims the instrument. Both come down
   to what the scrim covers and how dark it is, so they are one decision.
3. **Delete-file's chunk row** — fetch or omit. Omit first; see
   [Readout data](#readout-data).
4. **The audit's open decision 1 is untouched.** Grading confirmations by
   reversibility rather than by trigger would remove the delete-file prompt
   entirely. Nothing here assumes an answer.

---

## Out of scope

- **Texture.** No gradients, inset shadows, screw heads, or brushed metal. This
  app's hardware quality lives in behaviour and semantics — the detent, the
  bypass that dims rather than hides, the lamp colours — not in material. A
  variant with rail gradients and well insets was rendered during review and
  rejected: three values, none of them tokens, and it reads as skeuomorphism
  rather than as an instrument.
- **Hold-to-commit.** Tempting given the momentary transport keys
  (`docs/specs/scope/2026-08-11-momentary-transport-design.md`), but arming
  already exists as a concept and a hold makes every deletion slow in order to
  punish a rare mistake.
- **Token values.** No colour, contrast, or type-scale changes. Every value in
  this design is an existing token or an existing recipe.
- **`LaunchSplash`**, context menus, and popovers — unchanged, as in the audit.
- **Toasts / `jobNotification`** — non-blocking, different problem.

---

## Risks

- **The switch is a genuinely different idea of what a confirmation is.** It
  commits the app to *the letter on the switch is the key that throws it* as a
  house rule rather than a scope-bar detail. If that rule is only right for the
  scope bar, the centrepiece falls and steps 2–3 should be dropped.
- **Key caps could read as busy** across ~70 rows, and the rule only pays off
  for someone who has already noticed the S/M squares in the window. Judge the
  whole sheet, not a row. Everything else in the design survives dropping them.
- **The confirm grows by ~70px.** A prompt that shows its arithmetic is a
  bigger object than one that asks a question. If it reads heavy, the well is
  the part to cut, not the rails.
- **Detent depends on DOM ancestry.** `.motion-ready` is set on
  `<main class="app-layout">` (`+page.svelte:3435`) and `<ConfirmDialog />`
  sits inside it (`:3743`). The top layer changes paint order, not ancestry, so
  the selector matches — but moving the mount outside `<main>` would silently
  kill the detent, as it would for `KeyboardHelpOverlay` (`:3801`), which is
  already outside and needs no detent.

---

## Verification

1. `npm run lint:css`, `npx svelte-check`, `npx vite build`, `npm test` all
   clean.
2. `grep -rn "rail-close\|&times;" src/lib/` returns nothing — the `×` is gone
   from every unit.
3. `grep -rn "btn-danger\|btn-ghost" src/lib/` returns nothing after step 5.
4. Unit tests on `confirmStore` for `rows` passthrough, and on the new
   `isDeleteChord` dialog path.
5. **Keyboard pass, per prompt nature** — the finding source review cannot
   settle:
   - Activation prompt: commit holds focus with a visible ring; Enter commits;
     Esc cancels.
   - Removal prompt: **Enter does nothing**; ⌘⌫ / Del commits; Esc cancels;
     Tab reaches escape then commit and back.
   - Nested: ⌘⌫ inside a prompt raised from the game-system unit must not
     reach the form underneath.
6. **Screen-reader pass** — the unit announces its rail nameplate and its rows;
   the escape legend announces as a button named Cancel/Close.
7. **Reduced-motion pass** — `detent-glow` / `detent-flat` suppressed on the
   commit switch. The existing block at `app.css:527` lists selectors
   explicitly, so the commit switch must be **added to it** — it is not
   covered for free.
8. **Visual pass by the user.** Mockups of every surface in this design:
   `https://claude.ai/code/artifact/d79814d1-f2c7-4b6e-ad6f-e09097d6c498`
