# Modals & Confirmations — Audit and Design

**Date:** 2026-08-11
**Status:** In progress. **Steps 1 and 2 implemented 2026-08-11** (F1–F4,
F9, and the entry point); awaiting the visual/keyboard pass in
[Verification](#verification). Steps 3–5 not started. Remaining findings
are code-level, not validated in the running app.
**Scope:** Frontend only — `src/lib/Modal.svelte`,
`src/lib/ConfirmDialog.svelte`, `src/lib/ActionButton.svelte`,
`src/lib/SettingsModal.svelte`, `src/lib/DocumentStatsModal.svelte`,
`src/lib/KeyboardHelpOverlay.svelte`, `src/lib/GameSystemsSettings.svelte`,
`src/lib/LibrarySettings.svelte`, `src/routes/+page.svelte`, `src/app.css`.
No sidecar or Rust changes. (One dependency removal touches `package.json`
— see [Notes](#notes).)

## Inventory

| Surface | Implementation | Callers |
|---|---|---|
| `Modal.svelte` | shared native `<dialog>` shell | Settings, Document info, Keyboard shortcuts, Add/Edit game system |
| `ConfirmDialog.svelte` | its **own** `<dialog>`, bypasses the shell | Delete collection — 1 call site (`+page.svelte:3664`) |
| Tauri `confirm()` | **native OS dialog** | Re-index file (`+page.svelte:2417`), delete file/folder (`+page.svelte:2488`) |
| Inline arm-then-fire | two-step button, no dialog | Danger Zone: re-index all, delete index (`LibrarySettings.svelte:335`, `:376`) |
| *(none)* | fires immediately | Delete custom system, Reset to defaults (`GameSystemsSettings.svelte:118`, `:128`) |

`LaunchSplash.svelte` is a full-screen overlay, not a dialog, and is out of
scope. Context menus (`ContextMenu`, `SystemTagMenu`, the collections sort
menu) are popovers with their own documented vocabulary — also out of scope.

## Problem

Five idioms answer the same question ("are you sure?"), and one of them is
the operating system. The split is not by risk, cost, or reversibility — it
is by which file the handler happens to live in:

- ⌘⌫ on a file-tree row raises a **macOS system dialog** (system font,
  system buttons, system colors). ⌘⌫ on a collections row raises the
  **in-app** one. Same chord, same gesture, two chrome systems — added by
  the same commit that unified the binding (84f7af7).
- Deleting a **collection** — cheap and reversible, its own message says
  *"nothing in your library is deleted"* — asks. Deleting a **custom game
  system** and resetting a built-in override — both unrecoverable — do not.
- The native dialog is the only place in the app that hands the user to OS
  chrome. Everything the design conventions establish (serif type, no
  filled rectangles, danger as a hue swap) is absent there.

The cause of the native-dialog reach is ergonomic, not aesthetic. Raising
the in-app dialog today costs a page-level state variable plus a
conditional block in the template (`pendingDeleteCollection` +
`+page.svelte:3664-3673`). `await confirm(…)` is one line. The second
author took the one-liner, correctly.

## Decision

### One doctrine, two idioms

**Modal confirm** when the trigger leaves nothing on screen to press again
— a keystroke or a context-menu item. The user's pointer is nowhere near a
control; the dialog is what gives them something to aim at.

**Inline arm-then-fire** when a persistent control raised the action — the
Danger Zone rows. Re-pressing the same control is a stronger commitment
gesture than clicking a button that just appeared under the cursor, and it
matches the arm-then-play idiom the collections transport already teaches.

**Native `confirm()` is retired.** No third idiom, no OS chrome.

| Action | Today | Under the doctrine |
|---|---|---|
| Delete file/folder | native | modal confirm |
| Re-index file | native | modal confirm |
| Delete collection | modal confirm | unchanged |
| Delete custom game system | none | modal confirm |
| Reset built-in to defaults | none | modal confirm |
| Re-index all files | inline two-step | unchanged (restyled — F8) |
| Delete the index | inline two-step | unchanged (restyled — F8) |

### The missing entry point

A store plus a single mounted dialog, so raising a confirm costs one
`await`:

```ts
// src/lib/confirmStore.ts  — named for the notificationStore.ts precedent
export interface ConfirmRequest {
  title: string;
  message?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
}
export const confirmPrompt: {
  subscribe: …;                                   // ConfirmRequest | null
  request(req: ConfirmRequest): Promise<boolean>;
  answer(value: boolean): void;                   // the dialog's only input
};
```

`+page.svelte` mounts one propless `<ConfirmDialog>` driven by the store
and drops `pendingDeleteCollection` and its conditional block. Call sites
read `if (!(await confirmPrompt.request({ … }))) return;` — the same shape
the native call has now, which is the point: nothing about the ergonomics
should push a future handler back toward the OS.

Label defaults (`Confirm` / `Cancel`) live in the dialog, not the store —
the store stays presentation-free, so its whole surface is the promise
lifecycle and all of it is unit-testable.

Rejected: a `<ConfirmDialog>` per call site (what we have; it is why the
tree diverged), and a generic imperative `mount()` helper (Svelte 4
component-API churn for one dialog).

## Findings

### P0 — Behavior and access

**F1 · Enter commits even when Cancel is focused.**
`ConfirmDialog.svelte:38` handles Enter at dialog level and always calls
`onConfirm()`, whatever holds focus. Fifteen lines above, `:22-25` explains
that danger prompts auto-focus Cancel so *"pressing Enter on muscle memory
shouldn't commit a permanent action"* — the Enter handler defeats exactly
that. Tab to Cancel, press Enter, the collection is gone.
*Fix:* let the focused button take Enter natively (buttons already
activate on Enter). Keep an explicit Enter shortcut only for non-danger
prompts, or scope it to when focus is on the dialog element itself.

**F2 · The safety focus is probably invisible.**
Chromium does not paint `:focus-visible` on a programmatic `.focus()` when
the preceding interaction was a mouse click — which is exactly how a
context-menu delete arrives. So on danger prompts Cancel *is* focused but
does not *look* focused, and the whole F1 safety mechanism is unreadable.
*Fix:* force the ring on the auto-focused button inside dialogs rather
than relying on the `:focus-visible` heuristic. Verify in the app; this is
the one finding whose premise is engine behavior rather than source.

**F3 · ConfirmDialog has no accessible name.**
`Modal.svelte:90` sets `aria-label={title}`; `ConfirmDialog.svelte:54` sets
nothing, so a screen reader announces an unnamed dialog and the message
text is not associated with it.
*Fix:* `aria-labelledby` on `.title`, `aria-describedby` on `.message`.

### P1 — Design system violations

**F4 · ConfirmDialog wears different chrome than every other modal.**
It predates the shell and never adopted it. Six divergences, all in
`ConfirmDialog.svelte:78-92`:

| Property | ConfirmDialog | `Modal.svelte` |
|---|---|---|
| background | `--bg-focused` | `--bg-container` |
| border | `--bg-category` (a *background* token) | `--border-subtle` |
| shadow | `--shadow-dropdown` | `--shadow-modal` |
| radius | raw `6px` | `var(--radius-lg)` |
| backdrop | `rgba(0,0,0,0.5)` | `rgba(0,0,0,0.6)` |
| header | none; title floats in body | `.modal-header` plate |

A modal at dropdown elevation with a brighter-than-normal border is a
distinct surface the design system never declared. The raw `6px` is
`--radius-well` spelled out.
*Fix:* rebuild ConfirmDialog on `Modal.svelte`
(`width="min(420px, 90vw)"`). All six close at once, and F3 comes free
(the shell already names its dialog). Fallback if the header plate reads
wrong on a two-line prompt: align the six values by hand.

**F5 · Two reds in one button row.**
In a danger prompt the Confirm is `--text-danger` at rest
(`app.css:260`) and Cancel — `kind="discard"` — turns `--text-danger` on
hover (`app.css:254`). Hovering Cancel makes it look like the destructive
one. Both buttons red, opposite meanings, same row.
*Fix:* suppress the discard→danger hover when the dialog is `danger`;
hover to `--text-primary` instead. Danger red marks one thing at a time.

**F6 · "✓ Delete".**
`ActionButton.svelte:26` always draws Font Awesome *circle-check* for
`kind="confirm"`, so destructive confirms get a checkmark next to the word
Delete.
*Fix:* an icon override for danger confirms (*trash* or
*triangle-exclamation*), or no icon — color and label already carry it.

**F7 · Filled rectangle buttons in the Danger Zone.**
CLAUDE.md, Design Conventions: *"No filled-rectangle buttons: actions are
text or icons that gain color, glow, or brackets. Danger is a hue swap
(`--text-danger`), not a new shape."* Three violations:

- `LibrarySettings.svelte:664` `.btn-danger-solid` — solid `--text-danger`
  fill, `--bg-container` text. The armed step of both Danger Zone rows.
- `LibrarySettings.svelte:659` `.btn-danger-outline:hover` — fills solid
  red on hover.
- `GameSystemsSettings.svelte:445` `.btn-delete:hover` — same, with
  `--text-inverse` text.

*Fix:* the armed destructive state already has a house recipe —
`.sm-btn.mute-on` (`app.css:318-322`): `--text-danger` glyph,
`color-mix(… --text-danger 45%, transparent)` border,
`color-mix(… 10%, transparent)` wash, no fill, and deliberately no glow
(glows are reserved for activated states; a removal is not an activation).
Reusing it makes "armed to destroy" one look across the mute button and
the Danger Zone with zero new vocabulary. The rest of the two-step is
already good — the armed label changing to *"Delete 128 files?"* is the
best confirmation copy in the app and should be kept.
Also `LibrarySettings.svelte:675` `.danger-zone` uses raw `6px`
(`--radius-well`).

**F8 · Three button vocabularies in one modal footer.**
`GameSystemsSettings.svelte:217-230` puts bordered `.btn` rectangles
(*Reset to defaults*, *Delete*) beside icon+text `ActionButton`s
(*Discard*, *Add/Save*) — two shapes, two type sizes, one row, ~4rem apart.
*Fix:* all four become ActionButtons. *Reset to defaults* needs a neutral
text-only variant of `ActionButton` (no icon, `--text-secondary`,
brightens on hover), which is also the right home for any future
"tertiary" modal action.

**F9 · Risk grading is inverted.** See [Problem](#problem). Closed by the
doctrine table; listed here because it is a behavior change, not a restyle,
and needs the F-numbered entry for the adoption map.

### P2 — Polish

**F10 · The cheat sheet drops the bracket convention.**
`app.css:448-457` brackets one-character chords in menus because *"a bare R
reads as a stray capital and a bare '.' barely reads at all"*.
`KeyboardHelpOverlay.svelte:57` renders `chord(entry.id)` plain, so the
menu shows `[R]` and the overlay — the surface whose entire job is teaching
the bindings — shows `R`. `isBareKeyChord()` already exists
(`keybindings.ts:164`).
*Fix:* bracket bare chords in the overlay. The overlay's louder treatment
(`--text-primary`, 0.85rem vs the menu's `--text-secondary`, 0.7rem) is
correct and stays — there the chord *is* the content.

**F11 · Document info is titled "Info" and its stat grid is cramped.**
`DocumentStatsModal.svelte:62` titles the dialog `"Info"` while the
filename — the actual subject — is repeated in the body. The stat block is
five equal columns in a 560px modal (`:119-126`), and SYSTEM holds a
comma-joined list of game systems in a fifth of that width; multi-system
files will wrap or clip.
*Fix:* filename as the dialog title (needs `text-overflow: ellipsis` added
to `.dialog-title` or a local override — the voice class sets no
truncation), and SYSTEM promoted out of the grid to its own full-width row
under the four numeric cells.

**F12 · Modal geometry is four ad-hoc strings.**
`min(640px, 90vw)` ×2, `min(560px, 90vw)`, `min(440px, 90vw)`, plus
`min(520px, 80vh)` / `min(640px, 80vh)` heights, each written at the call
site. Nothing stops the next modal landing 30px off its neighbour. Body
padding has drifted the same way: `1rem` (KeyboardHelpOverlay,
SettingsModal panes) vs `1rem 1.25rem 1.25rem` (DocumentStatsModal).
*Fix:* a `size="sm" | "md" | "lg"` prop on `Modal` backed by tokens, and
one `--modal-pad`. Precedent: the menu geometry block in `app.css:139-148`.

**F13 · Modals snap in; the splash fades.**
Neither dialog has an entry transition, though `--transition-fast` /
`--transition-normal` exist and `LaunchSplash` fades. A 150ms backdrop fade
plus a 0.98→1 scale on the panel matches the press-tick language the
conventions already name. `prefers-reduced-motion` is honoured in exactly
one component today (`SearchScopeBar.svelte:363`) — this is the moment to
make it a global rule rather than a second local one.

**F14 · The close affordance is a text `&times;`.**
`Modal.svelte:97` — the `×` character at 1.4rem in a serif face, where
every other icon in the app is a Font Awesome SVG. Optical weight and
baseline do not match the icon set. Its hover also runs
`--text-secondary → --text-primary`, one step brighter than the rest of
the chrome.
*Fix:* FA *xmark* at 14px, `--text-tertiary → --text-secondary` on hover.

**F15 · The scrim is duplicated with a stylelint escape hatch per file.**
`Modal.svelte:130-133` and `ConfirmDialog.svelte:89-92`: two `::backdrop`
rules, two `stylelint-disable` comments, two different alphas.
*Fix:* one global `dialog::backdrop` rule in `app.css` with a
`--scrim-modal` token and a single disable comment. Both existing comments
claim `::backdrop` cannot see `:root` tokens — that was true when written,
but `::backdrop` inheritance changed in both engines since; worth
re-testing on the current WKWebView/WebView2 pair, because if it inherits
now the escape hatch disappears entirely rather than being centralised.

**F16 · Nits.**
- `Modal.svelte:90` `aria-label={title}` duplicates the visible title;
  `aria-labelledby` on the title span cannot drift from it.
- `Modal.svelte:142-143` hardcodes `8px` twice for the header's top
  corners where `--radius-lg` is that value. Stylelint enforces colors
  only, so radius drift is unpoliced everywhere.
- `ConfirmDialog.svelte:28-32` restores focus on destroy but does not
  clear `returnTarget`; `Modal.svelte:69-74` does. Harmless (the component
  is dying) but the two implementations differ for no reason — moot once
  F4 merges them.
- Disabled cursor is `not-allowed` in `LibrarySettings.svelte:650` and
  `:566`, `default` in `app.css:252` `.action-btn:disabled`.

## Adoption map

Ordered so each step leaves the tree shippable.

1. ~~**`confirmStore.ts` + ConfirmDialog rebuilt on `Modal.svelte`**~~ —
   F1, F2, F3, F4, and the entry point. **Done 2026-08-11.** Landed as
   described, plus three shell additions that steps 2–5 can rely on:
   - `Modal` gained `describedBy` (F3's `aria-describedby`) and now
     honours a `[data-autofocus]` element inside its content, outranking
     the text-input heuristic. The child *declaring* its focus target and
     the shell *performing* the focus is what removes the race: there is
     one `.focus()` call, made after `showModal()` and a `tick()`.
   - `ActionButton` gained `initialFocus`, which renders that attribute.
     Needed because the component lists its attributes explicitly rather
     than spreading `$$restProps`, and Modal queries the DOM.
   - F1's fix is a deletion: no dialog-level Enter handler at all. The
     focused button activates on Enter natively, so *where focus sits is
     the whole of the chord's meaning* — which is what made auto-focusing
     Cancel meaningful in the first place.
2. ~~**Retire the native dialog**~~ — F9. **Done 2026-08-11.** All four
   sites route through `confirmPrompt.request`; `@tauri-apps/plugin-dialog`
   is uninstalled. Three things the plan did not anticipate:
   - **Re-index is not `danger`.** Rebuilding chunks destroys nothing, so
     it keeps focus on Confirm and Enter rips through it. The doctrine's
     danger flag turns out to grade *destructiveness*, not *importance* —
     worth holding to as more prompts arrive.
   - **The game-system prompts stack on an open modal.** `showModal()` on
     a dialog outside the open one promotes it above in the top layer, so
     the edit modal stays visible behind its own prompt and focus returns
     to the button that raised it. Nesting is the reason to check this
     specifically in the visual pass.
   - **Stacking exposed a second instance of F1.**
     `GameSystemsSettings.handleWindowKey` is a *window* listener, and
     window keydown still fires behind an open dialog, so ⌘Enter in the
     prompt would have saved the form underneath. Guarded on
     `$confirmPrompt`. The generic `dialog[open]` guard at
     `+page.svelte:2080` cannot help a component whose own modal is the
     open dialog — any future component-level key handler that coexists
     with a modal needs this check.
3. **Danger vocabulary** — F5, F6, F7, F8. `ActionButton` gains a danger
   icon override and a neutral variant; Danger Zone and the GameSystems
   footer adopt them; `.btn-danger-solid`, `.btn-danger-outline`,
   `.btn`/`.btn-delete`/`.btn-reset` are deleted.
4. **Shell polish** — F12, F13, F14, F15, F16. Size and padding tokens,
   scrim token, xmark SVG, entry transition behind a global
   `prefers-reduced-motion` rule, radius tokens.
5. **Content** — F10, F11. Overlay brackets; Document info title and
   layout.

Steps 3–5 are independent of each other and of 1–2.

## Out of scope

- **Context menus and popovers** (`ContextMenu`, `SystemTagMenu`,
  collections sort menu) — non-modal, own vocabulary, documented in
  `docs/design/2026-08-09-menu-affordances-design.md`.
- **`LaunchSplash`** — a full-screen overlay with no dismissal decision to
  make; its hero title is already excluded by the header-voices doc.
- **Settings tab and sub-tab navigation** (`SettingsModal.svelte:161-221`)
  — controls inside a modal, not modal chrome. They are internally
  consistent.
- **Token values themselves.** No color, contrast, or type-scale changes
  are proposed. F7 reuses an existing recipe; F12/F15 add geometry and
  scrim tokens whose values are the ones already in the code.
- **Toasts / `jobNotification`** — non-blocking, different problem.

## Open decisions

1. **The doctrine's boundary** (modal vs inline). The rule proposed is
   "did a persistent control raise it?" An alternative worth naming: grade
   by *reversibility* instead — delete-file moves to Trash and is
   recoverable, delete-index is not. That would push delete-file toward no
   confirmation at all, which is a bigger behavior change than this audit
   should decide on its own.
2. ~~**F4's fallback.**~~ Primary path shipped: the confirm prompt wears
   the full shell, header plate and all. Two consequences to judge in the
   visual pass rather than in the abstract — (a) whether the plate reads
   right above a one-or-two-line question, and (b) the shell's × is now a
   fourth way to cancel, alongside the Cancel button, Esc, and the
   backdrop. Four dismissals against one commit is arguably correct for a
   destructive prompt; if it reads as clutter, a `header={false}` variant
   is the fallback, not a second dialog implementation.
3. **F11's title.** Filename-as-title needs truncation on `.dialog-title`,
   which is a shared voice class — local override, or amend the voice?

## Verification

Checked items were run against step 1 on 2026-08-11.

1. ✅ `npm run lint:css` and `npx svelte-check` pass (0 errors), plus
   `npx vite build` and `npm test` (381 passing, 6 of them new against
   `confirmStore`: promise lifecycle, idle answers, and the supersede
   case).
2. ✅ `grep -rn "plugin-dialog" src/ package.json` returns nothing.
3. ✅ `grep -rln "showModal" src/lib/` — `Modal.svelte` is the only
   `.showModal()` caller (the other two hits are a comment and
   GameSystems' local `showModal` boolean).
4. Grep confirms no remaining `background: var(--text-danger)` or
   `.btn-danger-solid` after step 3.
5. **Outstanding for step 1** — keyboard pass on the confirm prompt: Esc
   cancels; Tab cycles inside; Enter on a focused Cancel **cancels**
   (F1); the auto-focused button shows a ring when the prompt was raised
   by mouse (F2). F2's premise is engine behavior, so this is the one
   step-1 fix that source review cannot settle.
6. **Outstanding** — screen-reader pass: the prompt announces its title
   and its message (F3).
7. **Outstanding for step 2** — the nested case: Delete or Reset inside
   the game-system edit modal must raise the prompt *above* it, leave it
   visible behind, return focus to the button that raised it on cancel,
   and not save the form on ⌘Enter while the prompt is up.
8. Visual pass by the user. Expected diffs — **step 1:** the confirm
   prompt moves from the focused surface to the container surface, gains
   the header plate and modal-depth shadow, and widens slightly
   (320–480px → 420px). **Step 2:** deleting a file or folder and
   re-indexing one file now show that prompt instead of an OS dialog; two
   new prompts appear in game-system editing. **Later steps:** Danger Zone
   armed state loses its red fill, GameSystems footer becomes one button
   family, overlay chords gain brackets, modals fade in.

## Notes

- **`@tauri-apps/plugin-dialog` uninstalled** in step 2 — `confirm` was
  its only JS import. The Rust side stays and must: the folder picker is a
  Rust command using `DialogExt` (`src-tauri/src/lib.rs:393`), registered
  at `:1692`. **`"dialog:default"` in
  `src-tauri/capabilities/default.json:21` was deliberately left in
  place.** Capabilities gate the JS→Rust bridge and nothing crosses it
  now, so it is very likely droppable — but the only thing it can break is
  the folder picker, at runtime, in a way no test or type-check catches.
  Least-privilege tidying is not worth that on its own; fold it into a
  release where `npm run tauri build` is being exercised locally anyway.
- **The `dialog[open]` guard stays correct.** `+page.svelte:2080` bails
  out of the global keydown handler whenever a native dialog is open,
  because keydown still bubbles through the focused dialog even though the
  page is inert. Moving more confirmations into `<dialog>` widens what
  that guard covers, which is the desired direction — but it means the
  guard is now load-bearing for the delete flows too, and F1's fix must
  not reintroduce a window-level Enter listener.
- **F7's recipe reuse is the whole point of the finding.** The Danger Zone
  two-step is good interaction design that happens to be painted in the
  one shape the conventions forbid. The fix is a restyle, not a redesign —
  resist turning it into a modal.
- The header-voices pass already touched `ConfirmDialog.svelte` (dropped
  `font-weight: 600` from `.title`) and `LibrarySettings.svelte`
  `.danger-title`, so both files' *type* is current; only their surface,
  shape, and behavior lag. Step 1 retired `ConfirmDialog`'s local `.title`
  entirely — the shell's header now carries `.dialog-title`, so that voice
  adoption is inherited rather than re-declared.
- **Noticed in passing, not touched:** `GameSystemsSettings.svelte:39`
  runs `$: if (showModal && tagInput) tagInput.focus();`, duplicating what
  the shell already does — `Modal`'s text-input heuristic finds the same
  input. Pre-existing and harmless (both focus the same element), but it
  is a second focus call of exactly the kind `[data-autofocus]` exists to
  avoid. Fold it into step 4 if that step touches the file.
