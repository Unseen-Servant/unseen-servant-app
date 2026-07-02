# Splash Screen Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Skip launch splash" preference (new General tab in Settings, #253) and an animated splash reveal — icon pulse, staggered title/byline fade-in, and a gentle glow (#254).

**Architecture:** Frontend-only (SvelteKit). #254 is pure CSS `@keyframes` inside `LaunchSplash.svelte`. #253 adds a `GeneralSettings.svelte` pane wired into the existing tabbed `SettingsModal.svelte`, backed by a `skipLaunchSplash` boolean persisted to `settings.json` via `@tauri-apps/plugin-store` (same pattern as `collectionsPanelOpen`). The splash visibility gate in `+page.svelte` is inverted so an opted-out user sees no flash: `showSplash` starts `false`, and `onMount` reads the pref first and only then shows the splash + starts the 1.2s timer.

**Tech Stack:** SvelteKit + TypeScript, Svelte transitions/CSS, `@tauri-apps/plugin-store`.

**Spec:** `docs/specs/splash/2026-07-02-splash-improvements-design.md`

**Testing note:** This repo unit-tests pure logic (`*.test.ts` via vitest) but does **not** test `.svelte` components. Following that established pattern, each task's automated gate is `npm run check` (svelte-check — types + props + unused-CSS) and, where behavior changes, `npm run build`. Behavioral verification is a manual smoke test in `npm run tauri dev`, run by the developer. No component-test harness is introduced.

---

## File Structure

- **Create** `src/lib/GeneralSettings.svelte` — the General settings pane. One responsibility: render app-general preferences (currently just the launch-splash control) and emit changes upward. Presentational; owns no persistence.
- **Modify** `src/lib/SettingsModal.svelte` — register the General tab (first), add two pass-through props, render `<GeneralSettings>`.
- **Modify** `src/routes/+page.svelte` — own the `skipLaunchSplash` state, load/persist it, pass it to `<SettingsModal>`, and invert the splash visibility gate in `onMount`.
- **Modify** `src/lib/LaunchSplash.svelte` — add the CSS animated reveal + reduced-motion fallback.

Tasks are ordered so every commit leaves the tree coherent and `npm run check` green: LaunchSplash (self-contained) → GeneralSettings (self-contained) → SettingsModal (props have defaults, safe before the call site passes them) → `+page.svelte` (wires state + gate).

---

## Task 1: Animated splash reveal (#254)

**Files:**
- Modify: `src/lib/LaunchSplash.svelte` (full rewrite of markup `stack` block + `<style>`)

- [ ] **Step 1: Replace the component with the animated version**

Replace the entire contents of `src/lib/LaunchSplash.svelte` with:

```svelte
<script lang="ts">
  import { fade } from 'svelte/transition';

  export let visible: boolean = true;
  export let onDismiss: () => void = () => {};

  function handleClick() {
    onDismiss();
  }
</script>

{#if visible}
  <div
    class="splash"
    role="presentation"
    on:click={handleClick}
    transition:fade={{ duration: 200 }}
  >
    <div class="stack">
      <div class="icon-wrap">
        <div class="glow" aria-hidden="true"></div>
        <img class="icon" src="/logo.svg" alt="" draggable="false" />
      </div>
      <h1 class="title font-heading">Legend Lore</h1>
      <span class="byline">Unseen Servant</span>
    </div>
  </div>
{/if}

<style>
  .splash {
    position: fixed;
    inset: 0;
    z-index: 9999;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--bg-app);
    cursor: default;
    user-select: none;
    -webkit-user-select: none;
  }

  .stack {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.6rem;
  }

  .icon-wrap {
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .glow {
    position: absolute;
    inset: -40%;
    border-radius: 50%;
    background: radial-gradient(
      circle,
      color-mix(in srgb, var(--text-accent) 45%, transparent) 0%,
      transparent 70%
    );
    opacity: 0;
    pointer-events: none;
    animation: glow-in 900ms ease-out forwards;
  }

  .icon {
    width: 96px;
    height: 96px;
    image-rendering: -webkit-optimize-contrast;
    pointer-events: none;
    animation: icon-pulse 2.4s ease-in-out infinite;
  }

  .title {
    margin: 0;
    font-size: 1.6rem;
    color: var(--text-primary);
    letter-spacing: 0.02em;
    opacity: 0;
    animation: rise-in 300ms ease-out 200ms forwards;
  }

  .byline {
    font-family: var(--font-heading, var(--font-body));
    font-size: 0.7rem;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--text-tertiary);
    opacity: 0;
    animation: rise-in 300ms ease-out 350ms forwards;
  }

  @keyframes icon-pulse {
    0%, 100% { transform: scale(1); }
    50% { transform: scale(1.04); }
  }

  @keyframes rise-in {
    from { opacity: 0; transform: translateY(6px); }
    to { opacity: 1; transform: translateY(0); }
  }

  @keyframes glow-in {
    0% { opacity: 0; }
    45% { opacity: 1; }
    100% { opacity: 0.35; }
  }

  @media (prefers-reduced-motion: reduce) {
    .icon {
      animation: none;
      transform: none;
    }
    .title,
    .byline {
      animation: none;
      opacity: 1;
      transform: none;
    }
    .glow {
      animation: none;
      opacity: 0.25;
    }
  }
</style>
```

What changed vs. the original: the icon is wrapped in `.icon-wrap` with a sibling `.glow` radial halo behind it; the icon gets an infinite `icon-pulse`; title and byline start at `opacity: 0` and fade/rise in with staggered `animation-delay` (200ms / 350ms); a `prefers-reduced-motion` block disables all motion and shows everything at rest.

- [ ] **Step 2: Type/CSS check**

Run: `npm run check`
Expected: PASS — no errors, no "unused CSS selector" warnings (every selector above is used).

- [ ] **Step 3: Production build check**

Run: `npm run build`
Expected: PASS — Vite build completes.

- [ ] **Step 4: Manual smoke test**

Run `npm run tauri dev`. On launch, observe: the icon fades in with a soft glow behind it and pulses gently (a slow single "breath"); the title, then the byline, fade up a beat after the icon; after ~1.2s the whole splash fades out. Click during the splash still dismisses it immediately.

Then, with macOS **System Settings → Accessibility → Display → Reduce motion** ON, relaunch: the splash still fades in/out but the icon does not pulse, the glow is a faint static halo, and the title/byline appear without the staggered rise.

- [ ] **Step 5: Commit**

```bash
git add src/lib/LaunchSplash.svelte
git commit -m "feat(splash): animated reveal — icon pulse, staggered title, glow (#254)"
```

---

## Task 2: General settings pane component (#253)

**Files:**
- Create: `src/lib/GeneralSettings.svelte`

- [ ] **Step 1: Create the component**

Create `src/lib/GeneralSettings.svelte` with:

```svelte
<script lang="ts">
  export let skipLaunchSplash: boolean = false;
  export let onSkipLaunchSplashChange: (value: boolean) => void = () => {};

  function handleChange(e: Event & { currentTarget: HTMLSelectElement }) {
    onSkipLaunchSplashChange(e.currentTarget.value === 'skip');
  }
</script>

<div class="general-settings">
  <section class="field">
    <div class="field-head">
      <h3 class="field-title font-heading">Startup</h3>
      <p class="field-desc">How the app behaves when it launches.</p>
    </div>

    <div class="setting-row">
      <div class="setting-row-head">
        <div class="setting-row-title">Launch splash</div>
        <div class="setting-row-desc">
          Show the branded splash screen while the app starts up.
        </div>
      </div>
      <select
        class="setting-select"
        value={skipLaunchSplash ? 'skip' : 'show'}
        on:change={handleChange}
      >
        <option value="show">Show</option>
        <option value="skip">Skip</option>
      </select>
    </div>
  </section>
</div>

<style>
  .general-settings {
    padding: 1rem;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
  }

  .field-title {
    font-size: 0.95rem;
    color: var(--text-primary);
    margin: 0 0 0.35rem;
  }

  .field-desc {
    font-family: var(--font-body);
    font-size: 0.85rem;
    color: var(--text-secondary);
    line-height: 1.45;
    margin: 0;
  }

  .setting-row {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 0.75rem;
    align-items: center;
    padding: 0.4rem 0.1rem;
  }

  .setting-row-head {
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
    min-width: 0;
  }

  .setting-row-title {
    font-family: var(--font-heading, var(--font-body));
    font-size: 0.8rem;
    color: var(--text-primary);
  }

  .setting-row-desc {
    font-family: var(--font-body);
    font-size: 0.75rem;
    color: var(--text-secondary);
    line-height: 1.35;
  }

  .setting-select {
    font-family: var(--font-body);
    font-size: 0.8rem;
    padding: 0.3rem 0.5rem;
    background: var(--bg-focused);
    color: var(--text-primary);
    border: 1px solid var(--border-subtle);
    border-radius: 4px;
    cursor: pointer;
    min-width: 11rem;
  }
  .setting-select:focus {
    outline: 1px solid var(--text-accent);
    outline-offset: -1px;
  }
</style>
```

The class names and style values are copied from `LibrarySettings.svelte` so the pane visually matches the other tabs. The `.field-head` wrapper is a plain (unstyled) div, mirroring `LibrarySettings`; it needs no CSS rule.

- [ ] **Step 2: Type/CSS check**

Run: `npm run check`
Expected: PASS. (svelte-check type-checks the new standalone component; the `Event & { currentTarget: HTMLSelectElement }` handler signature and the default-valued props resolve cleanly. No unused-CSS warnings.)

- [ ] **Step 3: Commit**

```bash
git add src/lib/GeneralSettings.svelte
git commit -m "feat(settings): add GeneralSettings pane with launch-splash control (#253)"
```

---

## Task 3: Register the General tab in SettingsModal (#253)

**Files:**
- Modify: `src/lib/SettingsModal.svelte`

- [ ] **Step 1: Import the new pane**

In the imports block (after line 9, `import AboutPane from './help/AboutPane.svelte';`), add:

```svelte
  import GeneralSettings from './GeneralSettings.svelte';
```

- [ ] **Step 2: Add the two pass-through props**

Immediately after line 41 (`export let initialHelpSubTab: ... = 'guides';`), add:

```svelte
  export let skipLaunchSplash: boolean = false;
  export let onSkipLaunchSplashChange: (value: boolean) => void = () => {};
```

- [ ] **Step 3: Add `'general'` to the tab type unions**

Change the `initialTab` prop declaration (line 40) from:

```svelte
  export let initialTab: 'library' | 'game-systems' | 'help' = 'library';
```

to:

```svelte
  export let initialTab: 'general' | 'library' | 'game-systems' | 'help' = 'library';
```

And change the `activeTab` declaration (line 43) from:

```svelte
  let activeTab: 'library' | 'game-systems' | 'help' = initialTab;
```

to:

```svelte
  let activeTab: 'general' | 'library' | 'game-systems' | 'help' = initialTab;
```

- [ ] **Step 4: Add the tab button as the first entry**

Change the `tabs` array (lines 50-54) from:

```svelte
  const tabs = [
    { id: 'library' as const, label: 'Library' },
    { id: 'game-systems' as const, label: 'Game Systems' },
    { id: 'help' as const, label: 'Help' },
  ];
```

to:

```svelte
  const tabs = [
    { id: 'general' as const, label: 'General' },
    { id: 'library' as const, label: 'Library' },
    { id: 'game-systems' as const, label: 'Game Systems' },
    { id: 'help' as const, label: 'Help' },
  ];
```

- [ ] **Step 5: Render the pane as the first body branch**

Change the start of the tab-body conditional (line 77) from:

```svelte
      {#if activeTab === 'game-systems'}
```

to:

```svelte
      {#if activeTab === 'general'}
        <GeneralSettings {skipLaunchSplash} {onSkipLaunchSplashChange} />
      {:else if activeTab === 'game-systems'}
```

Leave the rest of the `{:else if}` chain unchanged.

- [ ] **Step 6: Type/CSS check**

Run: `npm run check`
Expected: PASS. The existing `<SettingsModal>` call site in `+page.svelte` does not yet pass the new props — that is fine because both have default values. `initialTab='general'` is now assignable.

- [ ] **Step 7: Commit**

```bash
git add src/lib/SettingsModal.svelte
git commit -m "feat(settings): register General tab first in SettingsModal (#253)"
```

---

## Task 4: Wire state, persistence, and the splash gate in +page.svelte (#253)

**Files:**
- Modify: `src/routes/+page.svelte`

This task owns all `+page.svelte` changes together so the tree stays coherent: the `skipLaunchSplash` state, its load (which also gates the splash), the persist handler, and the props passed to `<SettingsModal>`.

- [ ] **Step 1: Add the state variable and flip the splash default**

Change line 170 from:

```svelte
  let showSplash = true;
```

to:

```svelte
  let showSplash = false;
  let skipLaunchSplash = false;
```

(`splashTimer` on the next line is unchanged.)

- [ ] **Step 2: Update the `initialTab` type to include `'general'`**

Change line 172 from:

```svelte
  let settingsInitialTab: 'library' | 'game-systems' | 'help' = 'library';
```

to:

```svelte
  let settingsInitialTab: 'general' | 'library' | 'game-systems' | 'help' = 'library';
```

(This keeps the local variable's type compatible with the widened `SettingsModal` prop. The existing `'library'` default is unchanged.)

- [ ] **Step 3: Replace the unconditional splash timer with the pref-gated version**

The current `onMount` begins (lines 456-460) with:

```svelte
  onMount(async () => {
    splashTimer = setTimeout(() => {
      showSplash = false;
      splashTimer = null;
    }, 1200);
```

Replace those lines with:

```svelte
  onMount(async () => {
    // Decide splash visibility from the persisted preference BEFORE showing it.
    // Reading first (and defaulting to "show" on any error) means users who
    // opted out never see a flash — the window background is already --bg-app,
    // so the splash just fades in a few ms late instead of flashing out.
    try {
      const splashStore = await load('settings.json');
      skipLaunchSplash = parseBoolean(await splashStore.get('skipLaunchSplash')) ?? false;
    } catch {
      skipLaunchSplash = false;
    }
    if (!skipLaunchSplash) {
      showSplash = true;
      splashTimer = setTimeout(() => {
        showSplash = false;
        splashTimer = null;
      }, 1200);
    }
```

The rest of `onMount` (the `sidecar://failed` listener, the settings `load('settings.json')` block, etc.) is unchanged. `load('settings.json')` returns a cached handle, so calling it again later in `onMount` is cheap and safe.

- [ ] **Step 4: Add the persist handler**

Add this function next to `togglePanel` (which is around line 2518). Place it directly above `async function togglePanel() {`:

```svelte
  async function handleSkipLaunchSplashChange(value: boolean) {
    skipLaunchSplash = value;
    try {
      const store = await load('settings.json');
      await store.set('skipLaunchSplash', value);
      await store.save();
    } catch (e) {
      console.log('Could not persist skipLaunchSplash:', e);
    }
  }
```

- [ ] **Step 5: Pass the new props to `<SettingsModal>`**

In the `<SettingsModal ... />` block (starts at line 3084), add these two props. Put them right after the `initialHelpSubTab={settingsInitialHelpSubTab}` line (line 3088):

```svelte
  skipLaunchSplash={skipLaunchSplash}
  onSkipLaunchSplashChange={handleSkipLaunchSplashChange}
```

- [ ] **Step 6: Type/CSS check**

Run: `npm run check`
Expected: PASS. `parseBoolean` is already imported and used elsewhere in this file (e.g. `collectionsPanelOpen`); `load` is imported at line 9.

- [ ] **Step 7: Production build check**

Run: `npm run build`
Expected: PASS.

- [ ] **Step 8: Manual smoke test**

Run `npm run tauri dev`:
1. Fresh launch shows the animated splash, then it fades out after ~1.2s.
2. Open **Settings** — the **General** tab is first and selected-by-default styling matches the others. It shows **Launch splash: Show**.
3. Set it to **Skip**. Fully quit and relaunch the app: **no splash appears, and there is no flash** — the window opens straight to the app on the dark background.
4. Open **Settings → General**, confirm it still reads **Skip** (persistence survived restart). Set it back to **Show**, relaunch: the animated splash returns.

- [ ] **Step 9: Commit**

```bash
git add src/routes/+page.svelte
git commit -m "feat(splash): skip-launch-splash preference + flash-free gate (#253)"
```

---

## Final verification

- [ ] **Full check + build + existing tests green**

```bash
npm run check && npm run build && npm run test
```
Expected: all PASS. `npm run test` (vitest) covers the pure-logic suites and is unaffected by these UI changes — running it confirms nothing regressed.

- [ ] **Confirm both issues are satisfied**
  - #253: General tab (first) with a Show/Skip launch-splash dropdown; persists across restarts; opted-out launch is flash-free.
  - #254: icon pulse + staggered title/byline + glow on launch; degrades to a plain fade under `prefers-reduced-motion`.
