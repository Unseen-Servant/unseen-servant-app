<script lang="ts">
  // The filter console: every row is a channel — glyph, name, S/M
  // buttons, LED count. The scope bar is the readout (engaged chips);
  // this menu is the mixer, so S/M are always visible here. Same anchor
  // pattern as the sort menu in CollectionsPanel: outside-click and
  // Escape close it.
  import { afterUpdate, tick } from 'svelte';
  import { UNTAGGED_KEY } from './searchScope';
  import type { CurationKey } from './searchScope';

  export let open: boolean = false;
  export let anchorEl: HTMLElement | undefined = undefined;

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

  // Footer [clear all]: resets every solo/mute on all axes — the same
  // action as clearing each chip in the scope bar.
  export let onClearAll: () => void = () => {};

  export let onClose: () => void = () => {};

  let menuEl: HTMLDivElement;
  let focusedIdx = 0;
  let rowEls: HTMLElement[] = [];

  // We capture whatever was focused when the menu opened (typically the
  // search input or the trigger button) so keystrokes can't leak into it
  // while the menu is open, and so Escape can hand focus back.
  let previouslyFocused: HTMLElement | null = null;

  $: handleOpenChange(open);
  async function handleOpenChange(o: boolean) {
    if (o) {
      if (!previouslyFocused) {
        previouslyFocused = (document.activeElement as HTMLElement) ?? null;
      }
      await tick();
      menuEl?.focus();
    } else {
      // Restore focus only when the close path didn't already move focus
      // somewhere meaningful (Escape leaves it inside the menu, programmatic
      // closes leave it on body). Outside-clicks land focus on whatever was
      // clicked — don't yank it back from the user.
      const ae = document.activeElement as HTMLElement | null;
      const focusInsideMenu = !!menuEl && (ae === menuEl || menuEl.contains(ae as Node));
      const focusOnBody = ae === document.body || ae === null;
      if (previouslyFocused && (focusInsideMenu || focusOnBody)) {
        previouslyFocused.focus?.();
      }
      previouslyFocused = null;
    }
  }

  function handleWindowClick(event: MouseEvent) {
    if (!open) return;
    const target = event.target as Node;
    if (anchorEl && (anchorEl === target || anchorEl.contains(target))) return;
    if (menuEl && menuEl.contains(target)) return;
    onClose();
  }

  // Re-query enabled rows after every render and apply .kb-focused. Disabled
  // rows are skipped because they carry no [data-fm] attribute — keeps the
  // keyboard cursor away from rows the user can't act on.
  function refreshRowsAndFocus() {
    if (!menuEl) {
      rowEls = [];
      return;
    }
    rowEls = Array.from(menuEl.querySelectorAll('[data-fm]')) as HTMLElement[];
    if (rowEls.length > 0) {
      focusedIdx = Math.max(0, Math.min(rowEls.length - 1, focusedIdx));
    }
    rowEls.forEach((el, i) => el.classList.toggle('kb-focused', i === focusedIdx));
  }

  // Reset cursor to the top whenever the menu opens.
  $: if (open) focusedIdx = 0;

  afterUpdate(refreshRowsAndFocus);

  function handleKey(event: KeyboardEvent) {
    if (!open) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      onClose();
      return;
    }
    const meta = event.metaKey || event.ctrlKey;
    const lk = event.key.toLowerCase();
    const bareLetter = !meta && !event.shiftKey && !event.altKey;
    const isDown = event.key === 'ArrowDown' || (bareLetter && lk === 'j');
    const isUp   = event.key === 'ArrowUp'   || (bareLetter && lk === 'k');

    if (isDown) {
      event.preventDefault();
      event.stopPropagation();
      focusedIdx = Math.min(rowEls.length - 1, focusedIdx + 1);
      refreshRowsAndFocus();
    } else if (isUp) {
      event.preventDefault();
      event.stopPropagation();
      focusedIdx = Math.max(0, focusedIdx - 1);
      refreshRowsAndFocus();
    } else if (event.key === ' ' || event.key === 'Enter') {
      // A channel row's default action is its M toggle — the same "drop
      // this from results" gesture the old checkbox carried. Rows without
      // an M button (the hidden-items label) fall back to the row itself.
      const row = rowEls[focusedIdx];
      if (row) {
        event.preventDefault();
        event.stopPropagation();
        const m = row.querySelector<HTMLElement>('[data-sm-m]');
        (m ?? row).click();
      }
    } else if (bareLetter && (lk === 's' || lk === 'm')) {
      // S / M: press the matching channel button on the focused row.
      // No-op on rows without one (S on Untagged, either on the hidden
      // row) so the keystroke doesn't fall through to the search input.
      const row = rowEls[focusedIdx];
      event.preventDefault();
      event.stopPropagation();
      row?.querySelector<HTMLElement>(lk === 's' ? '[data-sm-s]' : '[data-sm-m]')?.click();
    }
  }

  $: hasHidden = hiddenCount > 0;
  $: curationRows = [
    { key: 'collected' as CurationKey, name: 'In a collection', count: collectedCount },
    { key: 'loose' as CurationKey, name: 'Loose', count: uncollectedCount },
  ];
</script>

<svelte:window on:click={handleWindowClick} on:keydown={handleKey} />

{#if open}
  <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
  <div
    class="filter-menu"
    bind:this={menuEl}
    on:click|stopPropagation
    tabindex="-1"
  >
    <div class="section">
      <div class="section-head">
        <span class="section-label">Hidden items</span>
        {#if hasHidden}
          <button class="reset-link" on:click={onClearHidden}>Clear</button>
        {/if}
      </div>
      <label
        class="row"
        class:row-disabled={!hasHidden}
        title={hasHidden ? 'Reveal hidden files and folders in the tree' : 'Right-click any file or folder to hide it'}
        data-fm={hasHidden ? 'row' : undefined}
      >
        <span class="row-name muted-name">Show hidden items</span>
        <span class="row-count">{hiddenCount}</span>
        <input
          class="app-checkbox"
          type="checkbox"
          checked={showHidden}
          disabled={!hasHidden}
          on:change={onToggleShowHidden}
        />
      </label>
    </div>

    {#if showCollectionFilter}
      <hr class="section-divider" />
      <div class="section">
        <div class="section-head">
          <span class="section-label">Curation</span>
        </div>
        {#each curationRows as ch (ch.key)}
          {@const soloed = curationSolos.has(ch.key)}
          {@const muted = curationMutes.has(ch.key)}
          <div class="row channel-row" class:dimmed={muted && !soloed} data-fm="row">
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
            <span class="sm">
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
      </div>
    {/if}

    {#if showSystemFilter}
      {#if systems.length > 0}
        <hr class="section-divider" />
        <div class="section">
          <div class="section-head">
            <span class="section-label">Game systems</span>
          </div>
          <div class="systems">
            {#each systems as { name, count } (name)}
              {@const soloed = soloedSystems.has(name)}
              {@const muted = excludedSystems.has(name)}
              <div class="row channel-row" class:dimmed={muted && !soloed} title={name} data-fm="row">
                <!-- Font Awesome "dice-d6" — monochrome; systems don't carry color -->
                <svg class="row-die" viewBox="0 0 640 640" fill="currentColor" aria-hidden="true">
                  <path d="M288.4 72.3C308 61.2 332 61.2 351.6 72.3L527.6 172C547.6 183.4 560 204.6 560 227.7L560 425.1C560 448.1 547.6 469.4 527.6 480.8L351.6 580.5C332 591.6 308 591.6 288.5 580.5L112.5 480.8C92.4 469.5 80 448.2 80 425.2L80 227.8C80 204.8 92.4 183.5 112.4 172.1L288.4 72.4zM166.6 219.6C157.8 216.5 147.8 219.9 142.8 228.2C137.8 236.5 139.6 246.9 146.4 253.2L149.6 255.6L299.8 345.8L299.8 494.5C299.8 505.5 308.8 514.5 319.8 514.5C330.8 514.5 339.8 505.5 339.8 494.5L339.8 345.8L490.1 255.6C499.6 249.9 502.7 237.6 497 228.2C491.3 218.8 479 215.7 469.6 221.3L319.9 311.1L170.2 221.3L166.5 219.6z"/>
                </svg>
                <span class="row-name">{name}</span>
                <span class="sm">
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
                title="Files with no game-system tag"
                data-fm="row"
              >
                <!-- Outline die: the untagged bucket is a placeholder, not an identity -->
                <svg class="row-die" viewBox="0 0 640 640" fill="none" stroke="currentColor" stroke-width="40" stroke-linejoin="round" stroke-linecap="round" aria-hidden="true">
                  <path d="M320 76 L548 206 L548 434 L320 564 L92 434 L92 206 Z"/>
                  <path d="M92 206 L320 336 L548 206"/>
                  <path d="M320 336 L320 564"/>
                </svg>
                <span class="row-name">Untagged</span>
                <span class="sm">
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
          </div>
        </div>
      {:else}
        <hr class="section-divider" />
        <div class="empty">No game systems detected yet. Index some files first.</div>
      {/if}
    {/if}

    <hr class="section-divider" />
    <div class="fm-footer">
      <button class="btn-link" on:click={onClearAll}>clear all</button>
    </div>
  </div>
{/if}

<style>
  .filter-menu {
    position: absolute;
    top: calc(100% + 4px);
    left: 0;
    background: var(--bg-focused);
    border: 1px solid var(--bg-category);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-dropdown);
    padding: 0.3rem 0 0.15rem;
    width: 260px;
    z-index: 60;
    font-family: var(--font-body);
  }
  /* The menu container holds programmatic focus so keystrokes can't leak
     into the search input. Per-row keyboard cursor is already drawn via
     `.kb-focused` on individual rows — a focus ring on the container
     itself would be redundant noise. */
  .filter-menu:focus,
  .filter-menu:focus-visible {
    outline: none;
  }

  .section {
    padding: 0.15rem 0;
  }

  .section-head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    padding: 0.35rem 0.75rem 0.15rem;
  }

  .section-label {
    font-family: var(--font-heading);
    font-size: 0.7rem;
    letter-spacing: 0.09em;
    text-transform: uppercase;
    color: var(--text-secondary);
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

  .systems {
    max-height: 12rem;
    overflow-y: auto;
  }

  .row {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.2rem 0.6rem 0.2rem 0.75rem;
    font-size: 0.85rem;
    color: var(--text-primary);
    transition: background var(--transition-fast);
  }
  .row:hover,
  .row:global(.kb-focused) {
    background: var(--bg-container);
  }
  label.row {
    cursor: pointer;
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

  .sm {
    display: inline-flex;
    gap: 0.25rem;
    flex-shrink: 0;
  }
  /* Untagged has no S — the spacer keeps the M column aligned. */
  .sm-spacer {
    width: 18px;
    flex-shrink: 0;
  }
  /* S/M button anatomy lives in app.css (.sm-btn) — shared with the
     systems-view group headers and tree folder rows. Always visible
     here: the menu IS the console, no hover-reveal. */

  /* A muted channel dims in place — removed from results, still on the
     board. Solo overrides mute, so a soloed row never dims. */
  .row.dimmed .row-name,
  .row.dimmed .row-die,
  .row.dimmed .row-count {
    opacity: 0.45;
  }

  .untagged-row {
    color: var(--text-tertiary);
  }
  .untagged-row .row-die {
    color: var(--text-tertiary);
  }

  .section-divider {
    margin: 0.3rem 0;
    border: none;
    border-top: 1px solid var(--bg-category);
  }

  .fm-footer {
    display: flex;
    justify-content: flex-end;
    padding: 0.15rem 0.6rem 0.25rem;
  }

  /* Bracketed terminal-style action, matching LibrarySettings' btn-link:
     brackets in muted color, label in accent, hover brightens. */
  .btn-link {
    background: none;
    border: none;
    padding: 0.15rem 0;
    font-family: var(--font-body);
    font-size: 0.75rem;
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
    padding: 0.5rem 0.7rem;
    font-size: 0.75rem;
    color: var(--text-tertiary);
  }
</style>
