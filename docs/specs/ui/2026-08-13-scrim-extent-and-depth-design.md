# The Scrim: Extent and Depth — Design

**Date:** 2026-08-13
**Status:** Implemented 2026-08-13 (`7773913`, `c709707`, `cd1adff`, `3c0cf53`).
Automated verification green at 416 tests. The visual passes in
[Verification](#verification) are outstanding, and one risk below was not
measurable here and is recorded as a hypothesis rather than a finding.
**Scope:** Frontend only — `src/app.css`, `src/lib/Modal.svelte`,
`src/lib/dialogStack.ts` *(new)*, `src/routes/+page.svelte`. No Rust or
sidecar changes.

**Follows** [Modals as Rack Units](2026-08-12-modal-rack-units-design.md),
which is code complete. This closes that design's open decision 2 and the
question it left implicit: the rack-unit work decided what a modal *is*, and
never revisited what the scrim behind it covers.

---

## Problem

Two complaints, one cause. The scrim is a single full-viewport black at a
single alpha, and it was never asked to be anything else.

### It dims the instrument the modal is quoting

A rack unit wears `--bg-header` rails specifically because the Header and
StatusBar *"bracket the workspace as one piece of chrome"*
(`StatusBar.svelte:168`). The whole argument for the rails is that a modal
should read as a small instance of the instrument rather than a card
floating over it.

Then the scrim dims the instrument. The modal quotes a frame that is, at
that moment, 60% dark.

There is a functional cost on top of the aesthetic one. **That chrome is
live.** The StatusBar carries the sidecar lamp, MCP activity, the sync
spinner, job notifications and errors; the Header carries the connection
state and the view switch. Some of it bears directly on the prompt in front
of it — *Re-index all files* is exactly the moment you want to see whether a
sync is already running. The scrim hides the answer to the question the
prompt raises.

### It extinguishes the modal a stacked prompt is about

`showModal()` puts a dialog in the top layer, and each dialog paints its own
`::backdrop` immediately beneath itself. With two open:

```
   page                    ← dimmed twice: 1 − (0.4 × 0.4) = 84% dark
   backdrop 1  (0.6)
   Settings modal          ← dimmed once by backdrop 2: 60% dark
   backdrop 2  (0.6)       ← sits BETWEEN the two dialogs
   confirm prompt          ← undimmed
```

The second backdrop darkens **the modal underneath**, which is the context
the prompt is asking about: *Delete the index* is a question about what
Settings is displaying. Sixty percent is not "inactive", it is nearly gone.

Retiring the inline two-step made this reachable from Settings as well as
from the game-system editor, so it now happens on the app's most-visited
modal rather than a rare one.

---

## Decision

### The scrim covers the workspace, not the frame

```css
dialog::backdrop {
  top: var(--header-height);
  bottom: var(--statusbar-height);
}
```

`::backdrop` is a viewport-covering fixed box; insetting it to the region
between the two chrome bars leaves them unscrimmed. The heights are already
tokens and already drive the bars themselves, so the edges cannot drift
apart.

### The frame dims itself, one step, and says why

Leaving the chrome at full brightness would be worse than scrimming it. The
page behind an open dialog is **inert**: a bright, apparently-live Header
whose buttons do nothing is a false affordance, and a click there does not
even dismiss the dialog.

So the chrome takes the app's existing dim for *present but not available* —
`--opacity-out-of-scope` (0.45), the same value the scope console's bypass
uses on the principle that *"the point of a bypass is to see what you are
bypassing"*. Present, legible, obviously not for pressing. No new token, no
new vocabulary.

The net effect is the one being asked for: the modal sits **inside** the
instrument's frame rather than over the whole app, and the lamps stay
readable.

### A stacked dialog scrims lighter

```css
:root, dialog::backdrop {
  --scrim-modal: rgba(0, 0, 0, 0.6);
  --scrim-modal-stacked: rgba(0, 0, 0, 0.35);
}
dialog.stacked::backdrop { background: var(--scrim-modal-stacked); }
```

At 0.35 the modal underneath stays clearly legible as context while still
reading as inactive, and the two layers keep a visible separation.

Rejected: **no scrim at all** for a stacked dialog. It maximises legibility
underneath, but nothing then marks the lower modal as inert — two undimmed
modals read as equally live, which is the opposite of what stacking means.
Rejected: **leaving 0.6**, which is the status quo the complaint is about.

Note the declaration sits on `:root, dialog::backdrop` rather than `:root`
alone. That is not decoration — whether `::backdrop` inherits custom
properties from its originating element is engine-version dependent, and a
`var()` that fails to resolve yields *no background*, i.e. a missing scrim
rather than a fallback one. The rack-unit work already learned this; the new
token joins the existing declaration rather than starting a second one.

### Both facts come from one store

CSS cannot ask "am I the second dialog open?", and it should not have to
guess "is any dialog open?" either. A four-line store answers both:

```ts
// src/lib/dialogStack.ts
export const openDialogs = createDialogStack();   // subscribe + register() + release()
```

`register()` returns whether a dialog was *already* open, which is the whole
reason it is a function rather than a bare counter — that boolean is the only
way a dialog can know it is stacked.

`Modal.svelte` already owns the open/close lifecycle in `sync()`. On show it
reads the count *before* incrementing — a non-zero value means this dialog is
stacked, which sets `class="stacked"` for the lighter scrim — and decrements
on close and on destroy. `+page.svelte` sets `class:dialog-open={$openDialogs > 0}`
on `<main class="app-layout">`, which is where the Header and StatusBar live.

Two properties matter and both are testable, which is worth something in a
repo with no jsdom: the count never goes negative, and it survives a dialog
that unmounts without closing — `DocumentStatsModal` is destroyed by
`{#if statsModalPath}` rather than by flipping `visible`, which is exactly
the case that leaked focus restoration once before.

Rejected: `:has(dialog[open])`. This app ships on WKWebView and WebView2 with
no `minimumSystemVersion` pinned, and it has already been bitten once by
assuming `::backdrop` behaviour was uniform across engines. The state is
cheap and certain; the selector is neither.

---

## What this does not fix

**The page still composites to 84% under two dialogs.** That is unchanged and
correct — the page *is* two layers away. What changes is that the modal
between them is legible and the frame around them is lit, which is what
carries orientation.

**The dialog stays centred in the viewport**, not in the workspace. With a
40px header and a 28px status bar the difference is 6px of vertical offset.
Not worth overriding the UA's `margin: auto` centring and the positioning
edge cases that come with it.

---

## Risks

- **Backdrop-click-to-dismiss is still unverified, and this change makes the
  answer matter more.** An attempt to measure it failed: the harness available
  here renders local files as static snapshots rather than live pages, so no
  result was obtained. Recording that rather than a guess dressed as data.

  What is *reasoned*, and should be treated as a hypothesis until someone
  clicks: `::backdrop` generates a box but no DOM node, and the reason
  `e.target === dialogEl` is the canonical backdrop-click idiom is that
  browsers dispatch clicks in the backdrop region to the dialog element
  itself. If that holds, insetting the backdrop shrinks its box and therefore
  its hit region, so after this change the scrimmed workspace should still
  dismiss and the chrome strips should not — which is the behaviour we want,
  since those strips are deliberately outside the scrim and should not read as
  backdrop.

  Three outcomes and what each means, for whoever runs it:
  - **Neither region dismisses** — backdrop dismissal never worked and the
    audit's claim was wrong. Correct the audit; do not add the behaviour here,
    that is its own decision.
  - **Both regions dismiss** — the chrome strip is acting as backdrop, which
    is wrong. Restrict `handleClick` to the scrimmed region.
  - **Only the scrimmed region dismisses** — correct as shipped; record it and
    delete this risk.
- **Insetting `::backdrop` needs checking in both engines.** Ordinary
  positioning on a well-specified pseudo-element should be uniform, but this
  is the same class of assumption that failed before. Check WKWebView and
  WebView2, not just one.
- **Dimming chrome creates a stacking context** on `.header` and `.statusbar`.
  Neither has positioned descendants that escape its bounds — the Header's
  dropdowns are fixed-position and rendered elsewhere — but confirm the sort
  menu and any tooltip still paint correctly with a dialog open.
- **`LaunchSplash` is unaffected**: it is a full-screen overlay, not a
  `<dialog>`, and paints no backdrop.

---

## Verification

1. `npm run lint:css`, `npx svelte-check`, `npx vitest run`, `npm run build`
   all clean.
2. Unit tests on `dialogStack`: increments and decrements symmetrically,
   never goes negative, and a destroy-without-close still releases its count.
3. **Visual pass** — open any modal: the Header and StatusBar stay visible at
   one dim step, the workspace behind is scrimmed, and the modal reads as
   sitting inside the frame. Check that a lit sidecar lamp and a running sync
   spinner are still legible.
4. **Stacked pass** — Settings ▸ Library ▸ Delete index. The Settings modal
   behind the prompt must stay readable; the chrome must not double-dim.
5. **Dismissal pass** — settle the backdrop-click question above, and confirm
   Esc and the rail's escape legend are unaffected.
6. **Stacked-count pass** — open Document info (which unmounts rather than
   closing), confirm the chrome un-dims afterwards. A leaked count would
   leave the app permanently dimmed, which is the worst failure mode here and
   the reason the store is tested.
