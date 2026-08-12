# Momentary Transport and Master Bypass — Design

**Date:** 2026-08-11
**Status:** Implemented 2026-08-11. Awaiting a feel pass in the running
app — everything here is about tactility, which static checks cannot
judge.
**Scope:** Frontend only — `src/lib/holdLatch.ts` (new), the four panes
that dispatch transport keys, `src/routes/+page.svelte`,
`src/lib/StatusBar.svelte`, `src/lib/keybindings.ts`, `src/app.css`. No
sidecar, Rust, or persistence changes.

## Problem

The app wears a DAW's vocabulary — arm, play, mute, solo, channel strips,
LED glows, a scope *console* — but its controls behave like a web app's.
Two gaps in particular:

1. **Every toggle latches.** There was no `keyup` handler anywhere in
   `src/`. On hardware, tap latches and *hold* is momentary; that
   distinction is most of what makes a console feel like an instrument
   rather than a form.
2. **No way to hear it raw.** A GM builds a scope over a session's prep —
   collections playing, systems soloed, folders muted. When a search
   comes back thin, the question is always *"is my scope hiding it?"* and
   the only way to answer it was to dismantle the console and rebuild it.

## Decision

### Tap latches, hold is momentary

`holdLatch.ts` — press engages immediately and remembers the toggle;
release after `HOLD_MS` (250) runs the *same toggle again*, inverting back
to where it started. Release before then leaves it latched.

Reverting by re-running the toggle is the load-bearing choice: the latch
never learns what it toggled, so one implementation serves the collections
transport, the systems axis, tree rows, and filter channels. It also means
a hold is a temporary *inversion*, not a temporary *engage* — holding `M`
on an already-muted channel unmutes it for the duration. That is
consistent, and it is what a momentary switch physically does.

Applies to `S`, `M`, `P`/`Space`, and `B`. One module-level latch instance:
one pair of hands, one key held.

Rejected: snapshotting state on press and restoring it on release. Needs
per-axis knowledge of what to snapshot, and would have to be written five
times.

### Master bypass — `B`

The whole console passes through unresolved: `resolvedScopeSet` returns
null and `runSearch` skips all three narrowing axes. Tap latches, hold is
momentary, same as any transport key.

**Bypass does not clear anything.** The chips stay in the scope bar and
the lamps stay lit while the signal passes through them — that is what a
console bypass does, and it is the difference between "A/B this" and
"undo this". A `BYPASS` lamp in the status bar is the only thing saying
the visible console isn't currently doing anything.

`B` and `⌘B` (sidebar) are different actions. That is the distinction the
app's own bracket convention already teaches — *"⌘O is hold-a-modifier,
`[R]` is press-a-key"*.

**Not persisted, and deliberately not part of `ScopeConsoleState`.** It is
a momentary A/B against your own scope, not a setting; relaunching into a
silently bypassed console would be a trap.

### Detent on engage

A single bright frame when a control reaches its engaged position — 110ms,
`brightness(1.7)` decaying to rest. Engage only; releasing a switch has no
detent.

Two keyframes rather than one because `filter` is a single property: the
glow rides *inside* `detent-glow` (`brightness(1.7) var(--glow-active)`),
since animating brightness alone would drop the LED for the animation's
length. `detent-flat` serves the mute state, which carries no glow by
design (glows are reserved for activated states; a removal is not an
activation).

**Gated behind `.motion-ready`**, set after the persisted console is
restored. A CSS animation also runs when an element is *created* already
carrying the class, so without the gate every lamp the session restored
would snap on launch as though the user had just thrown it. Rare spurious
detents remain possible if a list re-keys under a control; a 110ms blip on
an already-lit lamp is an acceptable residue for a cosmetic effect.

Honours `prefers-reduced-motion` alongside the dialog animations.

## Discoverability

Two entries in the shortcut sheet: `scope.bypass`, and `scope.peek` —
which is not a chord of its own but one line teaching the idiom
(*"hold rather than tap to engage only while held"*), so the sheet doesn't
repeat it on eight labels.

## Edge cases

- **Key repeat** — every dispatch site bails on `event.repeat`, or holding
  a key would re-press the latch tens of times a second.
- **Release must always land.** `handleGlobalKeyup` is unconditional: it
  ignores every gate the keydown path applies, because a key coming back
  up must always reach the latch or a control stays stuck engaged.
- **Focus moves mid-hold** — the toggle closure captures its target, so a
  release reverts the control that was pressed, not whatever is focused
  now. `FilterPanel` captures the *button element* rather than the row for
  the same reason.
- **Window blur mid-hold** — `on:blur` cancels the hold, leaving the
  control engaged. The safe direction: the alternative reverts something
  the user can no longer see.
- **A second press while one is held** abandons the first, leaving it
  latched. Same reasoning.
- **Collections `P`/`Space`** keys the latch on the actual key pressed,
  not a literal `'p'` — either can fire it, and the release has to match
  whichever is physically held.

## Out of scope

- **Scene recall** — snapshotting and restoring whole console states.
  Filed as #365; it is a feature, not a feel change. Master bypass is the
  cheap partial answer to the same itch ("let me see past my scope for a
  second") and shipped here instead.
- **Solo-safe** — a channel that another channel's solo can't drop.
  Discussed, not built: it is per-collection persisted state plus an
  explanation burden, and wants a real need behind it first.
- **Per-collection trim** — weighting a collection's influence on ranking.
  Deliberately rejected: it is a retrieval-ranking change wearing a UI
  costume, and the eval harness has twice failed to predict real-library
  quality (BM25, reranker).
- **Momentary on mouse press.** Keyboard only for now — the buttons are
  small and hover-revealed, and a click-and-hold on an 18px target is a
  worse gesture than the key.

## Verification

1. ✅ `npm test` (394, 8 of them new against `holdLatch`: engage, tap,
   hold, key mismatch, double release, cancel, supersede),
   `npx svelte-check` 0 errors, `npm run lint:css`, `npx vite build`.
2. **Feel pass, outstanding.** Tap `S` on a row — it latches. Hold it —
   it reverts on release. Hold `B` — the library goes unscoped and the
   `BYPASS` lamp lights; release restores the exact scope.
3. **Launch check, outstanding.** Relaunch with a saved console: no lamp
   should flash. Then toggle one: it should snap.
4. **Repeat check, outstanding.** Hold a key for several seconds — the
   control must engage once, not strobe.
