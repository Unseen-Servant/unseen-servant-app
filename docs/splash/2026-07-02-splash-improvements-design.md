# Splash Screen Improvements — Design

**Date:** 2026-07-02
**Issues:** [#253](https://github.com/Unseen-Servant/unseen-legend-lore/issues/253) (skip-splash preference), [#254](https://github.com/Unseen-Servant/unseen-legend-lore/issues/254) (animated reveal)
**Status:** Approved

## Summary

Two independent improvements to the launch splash, deferred from the original
splash brainstorm (PR #246):

1. **#253** — Let users skip the launch splash entirely, via a new **General**
   tab in the Settings modal.
2. **#254** — Make the splash feel alive with an animated reveal: an icon pulse,
   a staggered fade-in of the title and byline, and a gentle glow behind the icon.

Both are polish, not fixes. The current splash already does its job.

## Current state

- `src/lib/LaunchSplash.svelte` — a fixed full-screen overlay with a centered
  stack: icon (`/logo.svg`), `<h1>` title "Legend Lore", and a "Unseen Servant"
  byline. Enter/exit is a plain `svelte/transition` `fade` (200ms). No internal
  animation; icon and title appear as one static composition.
- `src/routes/+page.svelte`
  - `let showSplash = true;` (line ~170) — splash renders immediately on mount.
  - `onMount` starts a 1.2s `setTimeout` that sets `showSplash = false`.
  - Click or first keypress dismisses early (`dismissSplash`).
  - Settings persist via `@tauri-apps/plugin-store` (`settings.json`), ad-hoc
    keys, read in `onMount` and written with `store.set(...)` + `store.save()`
    (see `togglePanel` and `collectionsPanelOpen` for the established pattern).
- `src/lib/SettingsModal.svelte` — tabbed modal. `tabs` array drives a
  `<nav class="tab-nav">`; body switches on `activeTab`. Existing tabs:
  Library, Game Systems, Help. The Help tab has its own sub-tabs (Guides,
  Reference, About).
- Settings controls use `<select>` dropdowns inside `.setting-row` blocks
  (`LibrarySettings.svelte`), **not** toggle switches — consistent with the
  app's old-school aesthetic.

Note: #253's original text suggested placing the toggle in `Settings → Help →
About` "alongside 'Hide help shortcut in status bar'." That preference does not
actually exist, and the decision here is to use a dedicated **General** tab
instead. This design supersedes the issue text on placement.

## #253 — Skip launch splash

### The async-load wrinkle

The skip preference lives in `settings.json`, which loads **asynchronously** in
`onMount`. The splash currently renders immediately (`showSplash = true`), so
reading the pref and then hiding the splash would show it for a frame or two
followed by the 200ms fade-out — a visible flicker for a user who opted out.

**Resolution:** invert the visibility gate.

- Change the initial state to `let showSplash = false;` (nothing shown at first).
- In `onMount`, read the skip pref **first**, before the sidecar-failure and
  settings/`loadFiles` work. If skip is off (default), set `showSplash = true`
  and start the existing 1.2s timer. If skip is on, do nothing — the splash
  never appears.

The splash then fades **in** a few milliseconds late instead of instantly. This
is imperceptible: the window background is already `var(--bg-app)` — the same
dark color as the splash — so there is no visual discontinuity, just a dark
screen the icon fades into. When skip is on there is zero flash.

Rejected alternative: mirroring the pref into synchronous `localStorage` so
`showSplash` can initialize synchronously. Adds a second persistence layer for
no meaningful gain — the late fade-in is already flash-free.

### State and persistence (`+page.svelte`)

- New state: `let skipLaunchSplash = false;` (default: splash shows).
- Load in `onMount` alongside the other prefs, using the existing
  `parseBoolean(await store.get('skipLaunchSplash'))` pattern.
- New handler `onSkipLaunchSplashChange(value: boolean)`:
  - Sets `skipLaunchSplash = value`.
  - Persists via `load('settings.json')` → `store.set('skipLaunchSplash', value)`
    → `store.save()`, wrapped in try/catch and logging on failure — identical to
    `togglePanel`.
- The pref only affects the **next** launch. The splash is already dismissed by
  the time the user can open Settings, so no live re-show logic is needed.

### General tab (`SettingsModal.svelte`)

- New component `src/lib/GeneralSettings.svelte`:
  - Props: `skipLaunchSplash: boolean` and
    `onSkipLaunchSplashChange: (value: boolean) => void`.
  - One `.setting-row` (reusing the LibrarySettings row structure):
    - Title: "Launch splash"
    - Desc: "Show the branded splash while the app starts up."
    - Control: a `<select>` with options **Show** (`false`) / **Skip** (`true`),
      matching the existing dropdown idiom. `on:change` calls
      `onSkipLaunchSplashChange(e.currentTarget.value === 'skip')`.
- Wire into `SettingsModal.svelte`:
  - Add `'general'` to the `activeTab` / `initialTab` type unions.
  - Add `{ id: 'general', label: 'General' }` as the **first** entry in `tabs`
    (order: General, Library, Game Systems, Help).
  - Add the two new props (`skipLaunchSplash`, `onSkipLaunchSplashChange`) and
    pass them to `<GeneralSettings>` in a new `{:else if activeTab === 'general'}`
    branch.
  - `+page.svelte` passes the state and handler into `<SettingsModal>`.

## #254 — Animated reveal

All animation lives in `LaunchSplash.svelte` as pure CSS `@keyframes` on the
existing markup. The container keeps its `transition:fade`. Because the child
elements mount with the container, their CSS animations start immediately;
`animation-delay` produces the stagger. The splash is visible ~1.2s (plus a
200ms fade-out), so reveal animations complete within ~900ms, leaving a brief
settled moment before dismissal.

- **Icon pulse (looping):** `scale(1.0) → 1.04 → 1.0`, ease-in-out, ~2.4s cycle,
  `infinite`. One slow "breath" plays while the splash is up.
- **Title + byline stagger:** each fades in with a slight upward translate
  (~6px → 0). Title delayed ~200ms, byline ~350ms after mount, each over ~300ms.
  The icon reads first, then the wordmark settles in beneath it.
- **Glow:** a radial glow element behind the icon (e.g. an absolutely-positioned
  `radial-gradient` div, or a `filter: drop-shadow` on the icon). It fades in
  with the icon (0 → peak over ~400ms) and eases down to a low settled opacity by
  ~900ms — "a gentle glow that fades to match the dark splash background." Uses an
  accent-tinted color drawn from the existing theme variables; kept subtle.

### Reduced motion

Wrap all of the above in `@media (prefers-reduced-motion: reduce)` overrides:
- Icon: `animation: none;` (no pulse), `transform: none;`.
- Title/byline: `animation: none;`, `opacity: 1; transform: none;` (appear at
  rest, no stagger).
- Glow: `animation: none;` and either hidden or held at a low static opacity.

The container `fade` is retained in all cases — it is a simple opacity
transition and not motion-sensitive.

## Out of scope

- No changes to dismissal behavior (click / first keypress still dismiss).
- No changes to the 1.2s duration.
- No live preview of the splash from the General tab.
- The nonexistent "Hide help shortcut in status bar" preference from #253's text
  is not created.

## Testing

- **Frontend build/type check:** `npm run build` / `svelte-check` stays green
  with the new component and props.
- **Manual (local, per project convention):**
  - Fresh launch shows the animated splash (pulse + stagger + glow), then it
    fades out after ~1.2s.
  - Setting **General → Launch splash → Skip**, then relaunching, shows no splash
    and no flash.
  - Switching back to **Show** restores the splash on next launch.
  - With OS "reduce motion" on, the splash appears without pulse/stagger/glow but
    still fades in and out.
- No sidecar or Rust changes; existing pytest/rust suites are unaffected.
