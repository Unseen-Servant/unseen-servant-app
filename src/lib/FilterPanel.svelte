<script lang="ts">
  // The filter panel: the mixer console for the unified S/M model,
  // docked in the left pane as the collections panel's sibling. Every
  // row is a channel — glyph, name, S/M buttons, LED count. The scope
  // bar stays the readout: engaging S/M here materializes a chip there,
  // and clearing a chip resets the row. Unlike the old dropdown console,
  // S/M are hover-revealed like the tree's folder rows — the panel is
  // furniture, not a popover.
  import { afterUpdate } from 'svelte';
  import { computeFilterRows, stepFilterRow } from './filterRows';
  import { materializeKey } from './paneFocus';
  import { UNTAGGED_KEY } from './searchScope';
  import type { CurationKey } from './searchScope';

  // DAW-style filter state for game systems.
  //   - excludedSystems: muted rows (M lit). Empty = nothing muted.
  //   - soloedSystems:   solo'd rows. When non-empty, mute is overridden:
  //                      only solo'd systems pass, regardless of which
  //                      rows are muted. This matches Logic Pro / Ableton.
  //                      Untagged files don't pass under solos.
  export let excludedSystems: Set<string> = new Set();
  export let soloedSystems: Set<string> = new Set();
  export let onToggleSystem: (system: string) => void = () => {};
  export let onToggleSolo: (system: string) => void = () => {};

  // Available systems (with counts) — typically gameSystemStats from +page.
  export let systems: { name: string; count: number }[] = [];

  // Count of indexed files with no game-system tag. Rendered as a
  // mute-only "Untagged" channel (key: UNTAGGED_KEY) so muting a real
  // system doesn't silently drop untagged files from search (issue #307).
  // No solo button — solo means "focus on these systems" and untagged
  // files never pass under solos; an 18px spacer keeps the column honest.
  export let untaggedCount: number = 0;

  // Whether the Game systems section is meaningful in the current context.
  // System tags are the organizing axis of the systems view, so we only
  // expose the filter there — in tree view it's a foreign content filter
  // over a filesystem-shaped structure.
  export let showSystemFilter: boolean = true;

  // Hidden items section. `hiddenCount` is the number of explicitly-hidden
  // paths (folders count as 1 each — descendants are implicit). The row
  // toggles `showHidden`; when count is 0 the row is disabled. This row
  // keeps its checkbox — it reveals, it doesn't narrow.
  export let showHidden: boolean = false;
  export let hiddenCount: number = 0;
  export let onToggleShowHidden: () => void = () => {};
  export let onClearHidden: () => void = () => {};

  // Focus lens (spec: scope doctrine) — hide out-of-scope rows on the
  // browsing surfaces (tree, systems view). Console surfaces — this
  // panel, the collections panel, the scope bar — never hide.
  export let hideOutOfScope: boolean = false;
  export let onToggleHideOutOfScope: () => void = () => {};

  // "Hide unindexed items" — the bulk gesture for material scope can't
  // speak about, sibling to per-item hide. Spec: docs/specs/scope/
  // 2026-08-09-hide-unindexed-design.md.
  export let hideUnindexed: boolean = false;
  export let onToggleHideUnindexed: () => void = () => {};

  // Where this pane's caret is. null means no cursor is drawn — which is now
  // distinct from not holding the keyboard, see `active`.
  export let focusedRow: string | null = null;
  // This panel owns the arrow keys. A click anywhere in it activates the pane
  // without ringing a row; the first arrow then materializes the caret. Until
  // this existed the panel had no mouse entry point at all — Cmd+Alt+↓ was
  // the only way in.
  export let active = false;
  export let onActivate: () => void = () => {};
  // Where that first arrow lands, remembered by the page.
  export let lastFocusedRow: string | null = null;
  export let onFocusRow: (key: string | null) => void = () => {};

  // Curation section: two channels over the collected/loose domain,
  // the third narrowing axis (same union/intersect/solo-overrides-mute
  // semantics as systems and collections). Soloing Collected is the old
  // "show only collection"; soloing Loose is the old "show only loose";
  // nothing engaged = show all. The parent gates the section via
  // `showCollectionFilter`.
  export let showCollectionFilter: boolean = false;
  export let collectedCount: number = 0;
  export let uncollectedCount: number = 0;
  export let curationSolos: Set<CurationKey> = new Set();
  export let curationMutes: Set<CurationKey> = new Set();
  export let onToggleCurationSolo: (key: CurationKey) => void = () => {};
  export let onToggleCurationMute: (key: CurationKey) => void = () => {};

  // Masthead [clear all]: resets every solo/mute on all axes — the same
  // action as clearing each chip in the scope bar.
  export let onClearAll: () => void = () => {};

  let panelEl: HTMLElement;

  // The navigable row set, derived not queried. Order is the j/k order.
  $: rows = computeFilterRows({
    hasHidden,
    showCollectionFilter,
    showSystemFilter,
    systems,
    untaggedCount,
  });

  function rowElByKey(key: string): HTMLElement | null {
    return panelEl?.querySelector<HTMLElement>(`[data-fm-key="${CSS.escape(key)}"]`) ?? null;
  }

  // The panel body scrolls, and the cursor no longer moves DOM focus, so
  // nothing scrolls it into view for us any more.
  let lastScrolled: string | null = null;
  afterUpdate(() => {
    if (!focusedRow) { lastScrolled = null; return; }
    if (focusedRow === lastScrolled) return;
    lastScrolled = focusedRow;
    rowElByKey(focusedRow)?.scrollIntoView({ block: 'nearest' });
  });

  /** Claim the pane, restoring `preferred` when that row still exists. */
  export function claim(preferred: string | null) {
    if (rows.length === 0) return;
    const target = preferred && rows.some((r) => r.key === preferred) ? preferred : rows[0].key;
    onFocusRow(target);
  }

  // Window-level and gated on the token — the same shape CollectionsPanel
  // uses, so exactly one pane responds to a keystroke.
  function handleWindowKey(event: KeyboardEvent) {
    if (!active) return;
    if (event.isComposing) return;
    // Yield to popovers and modals that own the keyboard while open.
    if (document.querySelector('.sort-menu, .dropdown, .context-menu')) return;
    if (document.querySelector('dialog[open]')) return;
    const target = event.target as HTMLElement | null;
    if (target?.matches('input, textarea, [contenteditable="true"]')) return;

    const meta = event.metaKey || event.ctrlKey;
    const lk = event.key.toLowerCase();
    const bareLetter = !meta && !event.shiftKey && !event.altKey;
    const isDown = event.key === 'ArrowDown' || (bareLetter && lk === 'j');
    const isUp   = event.key === 'ArrowUp'   || (bareLetter && lk === 'k');

    if (event.key === 'Escape') {
      // Release the pane. Not a close — the panel is docked furniture whose
      // open state is persisted, and the header toggle is its close
      // affordance. Matches CollectionsPanel's onFocusCollection(null).
      event.preventDefault();
      onFocusRow(null);
      return;
    }
    // Active with no caret (the pane was claimed by a click on its chrome):
    // the first arrow places the caret rather than stepping, so it lands *on*
    // the restored row instead of one past it.
    if (focusedRow === null && (isDown || isUp)) {
      event.preventDefault();
      onFocusRow(materializeKey(rows.map((r) => r.key), lastFocusedRow, isDown ? 1 : -1));
      return;
    }
    if (isDown) {
      event.preventDefault();
      onFocusRow(stepFilterRow(rows, focusedRow, 1));
      return;
    }
    if (isUp) {
      event.preventDefault();
      onFocusRow(stepFilterRow(rows, focusedRow, -1));
      return;
    }
    if (event.key === 'Home' && !meta && rows.length > 0) {
      event.preventDefault();
      onFocusRow(rows[0].key);
      return;
    }
    if (event.key === 'End' && !meta && rows.length > 0) {
      event.preventDefault();
      onFocusRow(rows[rows.length - 1].key);
      return;
    }

    // Everything below acts on the caret's row, which the branches above are
    // the only way to create. Escape stays above so it can still release an
    // active pane that never grew one.
    if (focusedRow === null) return;

    if (event.key === ' ' || event.key === 'Enter') {
      // A channel row's default action is its M toggle. A view row has no
      // M — its own control is the only button, so click that.
      event.preventDefault();
      const el = rowElByKey(focusedRow);
      const m = el?.querySelector<HTMLElement>('[data-sm-m]');
      (m ?? el?.querySelector<HTMLElement>('[data-fm-action]'))?.click();
      return;
    }
    if (bareLetter && (lk === 's' || lk === 'm')) {
      event.preventDefault();
      rowElByKey(focusedRow)
        ?.querySelector<HTMLElement>(lk === 's' ? '[data-sm-s]' : '[data-sm-m]')
        ?.click();
    }
  }

  $: hasHidden = hiddenCount > 0;
  $: curationRows = [
    { key: 'collected' as CurationKey, name: 'In a collection', count: collectedCount },
    { key: 'loose' as CurationKey, name: 'Loose', count: uncollectedCount },
  ];
</script>

<svelte:window on:keydown={handleWindowKey} />

<!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
<aside class="filter-panel" bind:this={panelEl} on:mousedown={onActivate}>
  <header class="panel-head">
    <span class="panel-title">Filters</span>
    <button class="btn-link" on:click={onClearAll}>clear all</button>
  </header>

  <div class="panel-body">
    {#if showCollectionFilter}
      <div class="sect ledger-label">Curation</div>
      {#each curationRows as ch (ch.key)}
        {@const soloed = curationSolos.has(ch.key)}
        {@const muted = curationMutes.has(ch.key)}
        <div
          class="row channel-row"
          class:soloed
          class:dimmed={muted && !soloed}
          class:kb-focused={focusedRow === `curation:${ch.key}`}
          data-fm-key="curation:{ch.key}"
        >
          {#if ch.key === 'collected'}
            <!-- Outline bookmark — same ribbon as the chip bookmarks, unfilled:
                 the channel is the curation bucket, not a specific collection -->
            <svg class="row-die" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round" aria-hidden="true">
              <path d="M6 3h12v18l-6-4.4L6 21z"/>
            </svg>
          {:else}
            <span class="row-die" aria-hidden="true"></span>
          {/if}
          <span class="row-name">{ch.name}</span>
          <span class="sm" class:engaged={soloed || muted}>
            <button
              type="button"
              class="sm-btn"
              class:solo-on={soloed}
              data-sm-s
              on:click|stopPropagation={() => onToggleCurationSolo(ch.key)}
              aria-pressed={soloed}
              title={ch.key === 'collected'
                ? (soloed ? 'Stop soloing collected files' : 'Solo collected files (show only collection)')
                : (soloed ? 'Stop soloing loose files' : 'Solo loose files (show only loose)')}
            >S</button>
            <button
              type="button"
              class="sm-btn"
              class:mute-on={muted}
              data-sm-m
              on:click|stopPropagation={() => onToggleCurationMute(ch.key)}
              aria-pressed={muted}
              title={ch.key === 'collected'
                ? (muted ? 'Unmute collected files' : 'Mute collected files')
                : (muted ? 'Unmute loose files' : 'Mute loose files')}
            >M</button>
          </span>
          <span class="row-count">{ch.count}</span>
        </div>
      {/each}
    {/if}

    {#if showSystemFilter}
      <div class="sect ledger-label">Game systems</div>
      {#if systems.length > 0}
        {#each systems as { name, count } (name)}
          {@const soloed = soloedSystems.has(name)}
          {@const muted = excludedSystems.has(name)}
          <div
            class="row channel-row"
            class:soloed
            class:dimmed={muted && !soloed}
            class:kb-focused={focusedRow === `system:${name}`}
            title={name}
            data-fm-key="system:{name}"
          >
            <!-- Font Awesome "dice-d6" — monochrome; systems don't carry color -->
            <svg class="row-die" viewBox="0 0 640 640" fill="currentColor" aria-hidden="true">
              <path d="M288.4 72.3C308 61.2 332 61.2 351.6 72.3L527.6 172C547.6 183.4 560 204.6 560 227.7L560 425.1C560 448.1 547.6 469.4 527.6 480.8L351.6 580.5C332 591.6 308 591.6 288.5 580.5L112.5 480.8C92.4 469.5 80 448.2 80 425.2L80 227.8C80 204.8 92.4 183.5 112.4 172.1L288.4 72.4zM166.6 219.6C157.8 216.5 147.8 219.9 142.8 228.2C137.8 236.5 139.6 246.9 146.4 253.2L149.6 255.6L299.8 345.8L299.8 494.5C299.8 505.5 308.8 514.5 319.8 514.5C330.8 514.5 339.8 505.5 339.8 494.5L339.8 345.8L490.1 255.6C499.6 249.9 502.7 237.6 497 228.2C491.3 218.8 479 215.7 469.6 221.3L319.9 311.1L170.2 221.3L166.5 219.6z"/>
            </svg>
            <span class="row-name">{name}</span>
            <span class="sm" class:engaged={soloed || muted}>
              <button
                type="button"
                class="sm-btn"
                class:solo-on={soloed}
                data-sm-s
                on:click|stopPropagation={() => onToggleSolo(name)}
                aria-pressed={soloed}
                aria-label={soloed ? `Stop soloing ${name}` : `Solo ${name}`}
                title={soloed ? `Stop soloing ${name} (S)` : `Solo ${name} (S)`}
              >S</button>
              <button
                type="button"
                class="sm-btn"
                class:mute-on={muted}
                data-sm-m
                on:click|stopPropagation={() => onToggleSystem(name)}
                aria-pressed={muted}
                aria-label={muted ? `Unmute ${name}` : `Mute ${name}`}
                title={muted ? `Unmute ${name} (M)` : `Mute ${name} (M)`}
              >M</button>
            </span>
            <span class="row-count">{count}</span>
          </div>
        {/each}
        {#if untaggedCount > 0}
          {@const muted = excludedSystems.has(UNTAGGED_KEY)}
          <div
            class="row channel-row untagged-row"
            class:dimmed={muted}
            class:kb-focused={focusedRow === `system:${UNTAGGED_KEY}`}
            title="Files with no game-system tag"
            data-fm-key="system:{UNTAGGED_KEY}"
          >
            <!-- Outline die: the untagged bucket is a placeholder, not an identity -->
            <svg class="row-die" viewBox="0 0 640 640" fill="none" stroke="currentColor" stroke-width="40" stroke-linejoin="round" stroke-linecap="round" aria-hidden="true">
              <path d="M320 76 L548 206 L548 434 L320 564 L92 434 L92 206 Z"/>
              <path d="M92 206 L320 336 L548 206"/>
              <path d="M320 336 L320 564"/>
            </svg>
            <span class="row-name">Untagged</span>
            <span class="sm" class:engaged={muted}>
              <span class="sm-spacer" aria-hidden="true"></span>
              <button
                type="button"
                class="sm-btn"
                class:mute-on={muted}
                data-sm-m
                on:click|stopPropagation={() => onToggleSystem(UNTAGGED_KEY)}
                aria-pressed={muted}
                aria-label={muted ? 'Unmute untagged files' : 'Mute untagged files'}
                title={muted ? 'Unmute untagged files (M)' : 'Mute untagged files (M)'}
              >M</button>
            </span>
            <span class="row-count">{untaggedCount}</span>
          </div>
        {/if}
      {:else}
        <div class="empty">No game systems detected yet. Index some files first.</div>
      {/if}
    {/if}

    <!-- View-visibility switches last: they say what the tree shows, not
         what search sees, so they sit below the narrowing axes. -->
    <div class="sect sect-split ledger-label">
      <span>Hidden items</span>
      {#if hasHidden}
        <button class="reset-link" on:click={onClearHidden}>Clear</button>
      {/if}
    </div>
    <div
      class="row"
      class:row-disabled={!hasHidden}
      class:kb-focused={focusedRow === 'view:showHidden'}
      title={hasHidden ? 'Reveal hidden files and folders in the tree' : 'Right-click any file or folder to hide it'}
      data-fm-key="view:showHidden"
    >
      <span class="row-name muted-name">Show hidden items</span>
      <span class="row-count">{hiddenCount}</span>
      <button
        type="button"
        class="app-checkbox"
        role="checkbox"
        aria-checked={showHidden}
        aria-label="Show hidden items"
        disabled={!hasHidden}
        data-fm-action
        on:click|stopPropagation={onToggleShowHidden}
      ></button>
    </div>

    <div
      class="row lens-row"
      class:kb-focused={focusedRow === 'view:hideUnindexed'}
      title="Hide files and folders the library knows nothing about — not indexed, not selected for indexing"
      data-fm-key="view:hideUnindexed"
    >
      <span class="row-name muted-name">Hide unindexed items</span>
      <button
        type="button"
        class="app-checkbox lens-checkbox"
        role="checkbox"
        aria-checked={hideUnindexed}
        aria-label="Hide unindexed items"
        data-fm-action
        on:click|stopPropagation={onToggleHideUnindexed}
      ></button>
    </div>

    <div
      class="row lens-row"
      class:kb-focused={focusedRow === 'view:hideOutOfScope'}
      title="Hide dimmed out-of-scope rows in the tree and systems view"
      data-fm-key="view:hideOutOfScope"
    >
      <span class="row-name muted-name">Hide out-of-scope items</span>
      <button
        type="button"
        class="app-checkbox lens-checkbox"
        role="checkbox"
        aria-checked={hideOutOfScope}
        aria-label="Hide out-of-scope items"
        data-fm-action
        on:click|stopPropagation={onToggleHideOutOfScope}
      ></button>
    </div>
  </div>
</aside>

<style>
  .filter-panel {
    display: flex;
    flex-direction: column;
    min-height: 0;
    background: var(--bg-app);
    font-family: var(--font-body);
    overflow: hidden;
  }
  .panel-head {
    display: flex;
    align-items: baseline;
    gap: 0.5rem;
    padding: 0.6rem 0.75rem 0.4rem;
    flex-shrink: 0;
  }
  .panel-body {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding-bottom: 0.4rem;
  }

  /* Quiet small-caps section headers — ledger voice, like the tree.
     No rule under them. */
  .sect {
    padding: 0.6rem 0.25rem 0.15rem 0.75rem;
  }

  .row {
    display: flex;
    align-items: center;
    gap: 0.45rem;
    padding: 0.28rem 0.75rem 0.28rem 1.1rem;
    font-size: 0.85rem;
    color: var(--text-primary);
    /* Reserved for the solo rule so engaging S doesn't shift layout. */
    border-left: 3px solid transparent;
    transition: background var(--transition-fast);
  }
  .row:hover {
    background: var(--bg-container);
  }
  /* Keyboard focus rings rather than fills, so the caret stays visible
     on a soloed row instead of losing the background to it. */
  .row.kb-focused {
    box-shadow: var(--ring-focus);
  }
  .row-disabled {
    color: var(--text-tertiary);
    cursor: default;
  }
  .row-disabled:hover {
    background: transparent;
  }
  .row-disabled .row-count {
    color: var(--text-tertiary);
  }
  /* Section head variant with a right-aligned reset link. */
  .sect-split {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    padding-right: 0.75rem;
  }

  /* Soloed channel — the tree's own soloed-collection treatment:
     parchment wash + purple rule on the reserved border. */
  .row.soloed {
    background: color-mix(in srgb, var(--text-accent) 8%, transparent);
    border-left-color: var(--text-active);
  }

  .row-die {
    width: 0.8rem;
    height: 0.8rem;
    flex-shrink: 0;
    color: var(--text-secondary);
  }

  .row-name {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .muted-name {
    color: var(--text-secondary);
  }
  .row-disabled .muted-name {
    color: var(--text-tertiary);
  }

  .reset-link {
    background: none;
    border: none;
    color: var(--text-tertiary);
    font-family: var(--font-body);
    font-size: 0.7rem;
    padding: 0;
    cursor: pointer;
    transition: color var(--transition-fast);
  }
  .reset-link:hover {
    color: var(--text-secondary);
  }

  /* LED count readout — same inverted 18px box as the systems-view group
     count (filled, borderless, tabular digits). */
  .row-count {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    height: 18px;
    min-width: 18px;
    padding: 0 0.3rem;
    border-radius: var(--radius-sm);
    background: color-mix(in srgb, var(--text-tertiary) 18%, transparent);
    color: var(--text-secondary);
    font-size: 0.65rem;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    line-height: 1;
    flex-shrink: 0;
  }

  /* S/M cluster — hidden at rest, revealed on row hover or keyboard
     focus, always visible while engaged. Same reveal grammar as the
     tree's folder rows; button anatomy is the shared .sm-btn in app.css. */
  .sm {
    display: inline-flex;
    gap: 0.25rem;
    flex-shrink: 0;
    opacity: 0;
    transition: opacity var(--transition-fast);
  }
  .row:hover .sm,
  .row:focus-within .sm,
  .row.kb-focused .sm,
  .sm.engaged {
    opacity: 1;
  }
  /* Untagged has no S — the spacer keeps the M column aligned. */
  .sm-spacer {
    width: 18px;
    flex-shrink: 0;
  }

  /* A muted channel dims in place — removed from results, still on the
     board. Solo overrides mute, so a soloed row never dims. */
  .row.dimmed .row-name,
  .row.dimmed .row-die,
  .row.dimmed .row-count {
    opacity: var(--opacity-out-of-scope);
  }

  .untagged-row {
    color: var(--text-tertiary);
  }
  .untagged-row .row-die {
    color: var(--text-tertiary);
  }

  /* Bracketed terminal-style action, matching LibrarySettings' btn-link:
     brackets in muted color, label in accent, hover brightens. */
  .btn-link {
    margin-left: auto;
    background: none;
    border: none;
    padding: 0;
    font-family: var(--font-body);
    font-size: 0.72rem;
    color: var(--text-accent);
    cursor: pointer;
    transition: filter var(--transition-fast);
  }
  .btn-link::before,
  .btn-link::after {
    color: var(--text-secondary);
  }
  .btn-link::before {
    content: '[';
    margin-right: 0.15rem;
  }
  .btn-link::after {
    content: ']';
    margin-left: 0.15rem;
  }
  .btn-link:hover {
    filter: brightness(1.25);
  }

  .empty {
    padding: 0.3rem 0.75rem 0.5rem 1.1rem;
    font-size: 0.75rem;
    color: var(--text-tertiary);
  }

  /* The lens is a mode the user switched on — checked wears purple,
     not the parchment content accent. */
  .lens-checkbox:checked {
    background-color: var(--text-active);
    border-color: var(--text-active);
  }
</style>
