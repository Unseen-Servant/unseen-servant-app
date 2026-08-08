<script lang="ts">
  // Persistent readout of every narrowing the user has applied. The
  // mixer console lives in the docked FilterPanel (header cluster
  // toggle); this bar stays the readout — each chip is a
  // clear-affordance — the whole chip is the button; click to undo that
  // single narrowing without touching the others.

  import { displaySystem } from './searchScope';
  import type { CurationKey } from './searchScope';

  // Chip glyph = axis (pigment bookmark = collection, outline bookmark =
  // curation bucket, monochrome die = system); chip frame = operation
  // (purple play/solo / danger-edged mute).
  export let collectionPlays: { key: string; label: string; color: string | null }[] = [];
  export let collectionSolos: { key: string; label: string; color: string | null }[] = [];
  export let collectionMutes: { key: string; label: string; color: string | null }[] = [];
  export let excludedSystems: Set<string> = new Set();
  export let soloedSystems: Set<string> = new Set();
  export let curationSolos: Set<CurationKey> = new Set();
  export let curationMutes: Set<CurationKey> = new Set();
  export let showHidden: boolean = false;
  export let resultCount: number = 0;
  export let indexedFileCount: number = 0;
  export let isLoading: boolean = false;
  export let searchActive: boolean = false;
  export let onClearCollectionPlay: (key: string) => void = () => {};
  export let onClearCollectionSolo: (key: string) => void = () => {};
  export let onClearCollectionMute: (key: string) => void = () => {};
  export let onToggleSystemFilter: (system: string) => void = () => {};
  export let onToggleSystemSolo: (system: string) => void = () => {};
  export let onToggleCurationSolo: (key: CurationKey) => void = () => {};
  export let onToggleCurationMute: (key: CurationKey) => void = () => {};
  export let onToggleShowHidden: () => void = () => {};

  const CURATION_LABELS: Record<CurationKey, string> = {
    collected: 'In a collection',
    loose: 'Loose',
  };
  const CURATION_ORDER: CurationKey[] = ['collected', 'loose'];

  // When anything is solo'd on an axis, mute state on that axis is
  // overridden — its mute chips would be misleading, so suppress them.
  // Only the solo chips remain to communicate the active narrowing.
  $: soloedList = Array.from(soloedSystems).sort();
  $: excludedList = soloedList.length > 0 ? [] : Array.from(excludedSystems).sort();
  $: shownCollectionMutes =
    collectionPlays.length > 0 || collectionSolos.length > 0 ? [] : collectionMutes;
  $: curationSoloList = CURATION_ORDER.filter((k) => curationSolos.has(k));
  $: curationMuteList =
    curationSoloList.length > 0 ? [] : CURATION_ORDER.filter((k) => curationMutes.has(k));
</script>

<div class="scope-bar">
  <div class="left">
    {#each collectionPlays as chip (chip.key)}
      <button
        type="button"
        class="chip solo"
        on:click|stopPropagation={() => onClearCollectionPlay(chip.key)}
        title="Stop {chip.label}"
        aria-label="Stop {chip.label}"
      >
        <span class="chip-prefix">play</span>
        {#if chip.color}
          <!-- Bookmark ribbon — the collection axis keeps its pigment -->
          <svg class="chip-mark" viewBox="0 0 24 24" fill={chip.color} aria-hidden="true">
            <path d="M5 2h14v20l-7-5.2L5 22z"/>
          </svg>
        {:else}
          <!-- No pigment — outline ribbon, same grammar as the panel -->
          <svg class="chip-mark" viewBox="0 0 24 24" fill="none" stroke="var(--text-tertiary)" stroke-width="2.2" stroke-linejoin="round" aria-hidden="true">
            <path d="M6 3h12v18l-6-4.4L6 21z"/>
          </svg>
        {/if}
        <span class="chip-label">{chip.label}</span>
        <span class="chip-clear" aria-hidden="true">×</span>
      </button>
    {/each}

    {#each collectionSolos as chip (chip.key)}
      <button
        type="button"
        class="chip solo"
        on:click|stopPropagation={() => onClearCollectionSolo(chip.key)}
        title="Stop soloing {chip.label}"
        aria-label="Stop soloing {chip.label}"
      >
        <span class="chip-prefix">solo</span>
        {#if chip.color}
          <!-- Bookmark ribbon — the collection axis keeps its pigment -->
          <svg class="chip-mark" viewBox="0 0 24 24" fill={chip.color} aria-hidden="true">
            <path d="M5 2h14v20l-7-5.2L5 22z"/>
          </svg>
        {:else}
          <!-- No pigment — outline ribbon, same grammar as the panel -->
          <svg class="chip-mark" viewBox="0 0 24 24" fill="none" stroke="var(--text-tertiary)" stroke-width="2.2" stroke-linejoin="round" aria-hidden="true">
            <path d="M6 3h12v18l-6-4.4L6 21z"/>
          </svg>
        {/if}
        <span class="chip-label">{chip.label}</span>
        <span class="chip-clear" aria-hidden="true">×</span>
      </button>
    {/each}

    {#each curationSoloList as key (key)}
      <button
        type="button"
        class="chip solo"
        on:click|stopPropagation={() => onToggleCurationSolo(key)}
        title="Stop soloing {CURATION_LABELS[key]}"
        aria-label="Stop soloing {CURATION_LABELS[key]}"
      >
        <span class="chip-prefix">solo</span>
        {#if key === 'collected'}
          <!-- Outline bookmark — the curation bucket, not a specific collection -->
          <svg class="chip-mark" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round" aria-hidden="true">
            <path d="M6 3h12v18l-6-4.4L6 21z"/>
          </svg>
        {/if}
        <span class="chip-label">{CURATION_LABELS[key]}</span>
        <span class="chip-clear" aria-hidden="true">×</span>
      </button>
    {/each}

    {#each soloedList as system (system)}
      <button
        type="button"
        class="chip solo"
        on:click|stopPropagation={() => onToggleSystemSolo(system)}
        title="Stop soloing {displaySystem(system)}"
        aria-label="Stop soloing {displaySystem(system)}"
      >
        <span class="chip-prefix">solo</span>
        <!-- Font Awesome "dice-d6" — monochrome; it marks the axis, the frame marks the operation -->
        <svg class="chip-die" viewBox="0 0 640 640" fill="currentColor" aria-hidden="true">
          <path d="M288.4 72.3C308 61.2 332 61.2 351.6 72.3L527.6 172C547.6 183.4 560 204.6 560 227.7L560 425.1C560 448.1 547.6 469.4 527.6 480.8L351.6 580.5C332 591.6 308 591.6 288.5 580.5L112.5 480.8C92.4 469.5 80 448.2 80 425.2L80 227.8C80 204.8 92.4 183.5 112.4 172.1L288.4 72.4zM166.6 219.6C157.8 216.5 147.8 219.9 142.8 228.2C137.8 236.5 139.6 246.9 146.4 253.2L149.6 255.6L299.8 345.8L299.8 494.5C299.8 505.5 308.8 514.5 319.8 514.5C330.8 514.5 339.8 505.5 339.8 494.5L339.8 345.8L490.1 255.6C499.6 249.9 502.7 237.6 497 228.2C491.3 218.8 479 215.7 469.6 221.3L319.9 311.1L170.2 221.3L166.5 219.6z"/>
        </svg>
        <span class="chip-label">{displaySystem(system)}</span>
        <span class="chip-clear" aria-hidden="true">×</span>
      </button>
    {/each}

    {#each shownCollectionMutes as chip (chip.key)}
      <button
        type="button"
        class="chip exclusion"
        on:click|stopPropagation={() => onClearCollectionMute(chip.key)}
        title="Unmute {chip.label}"
        aria-label="Unmute {chip.label}"
      >
        <span class="chip-prefix">mute</span>
        {#if chip.color}
          <!-- Bookmark ribbon — dims with the chip ("removed, still recognizable") -->
          <svg class="chip-mark" viewBox="0 0 24 24" fill={chip.color} aria-hidden="true">
            <path d="M5 2h14v20l-7-5.2L5 22z"/>
          </svg>
        {:else}
          <!-- No pigment — outline ribbon, same grammar as the panel -->
          <svg class="chip-mark" viewBox="0 0 24 24" fill="none" stroke="var(--text-tertiary)" stroke-width="2.2" stroke-linejoin="round" aria-hidden="true">
            <path d="M6 3h12v18l-6-4.4L6 21z"/>
          </svg>
        {/if}
        <span class="chip-label">{chip.label}</span>
        <span class="chip-clear" aria-hidden="true">×</span>
      </button>
    {/each}

    {#each curationMuteList as key (key)}
      <button
        type="button"
        class="chip exclusion"
        on:click|stopPropagation={() => onToggleCurationMute(key)}
        title="Unmute {CURATION_LABELS[key]}"
        aria-label="Unmute {CURATION_LABELS[key]}"
      >
        <span class="chip-prefix">mute</span>
        {#if key === 'collected'}
          <svg class="chip-mark" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round" aria-hidden="true">
            <path d="M6 3h12v18l-6-4.4L6 21z"/>
          </svg>
        {/if}
        <span class="chip-label">{CURATION_LABELS[key]}</span>
        <span class="chip-clear" aria-hidden="true">×</span>
      </button>
    {/each}

    {#each excludedList as system (system)}
      <button
        type="button"
        class="chip exclusion"
        on:click|stopPropagation={() => onToggleSystemFilter(system)}
        title="Unmute {displaySystem(system)}"
        aria-label="Unmute {displaySystem(system)}"
      >
        <span class="chip-prefix">mute</span>
        <!-- Font Awesome "dice-d6" — monochrome; dims with the chip ("removed, still recognizable") -->
        <svg class="chip-die" viewBox="0 0 640 640" fill="currentColor" aria-hidden="true">
          <path d="M288.4 72.3C308 61.2 332 61.2 351.6 72.3L527.6 172C547.6 183.4 560 204.6 560 227.7L560 425.1C560 448.1 547.6 469.4 527.6 480.8L351.6 580.5C332 591.6 308 591.6 288.5 580.5L112.5 480.8C92.4 469.5 80 448.2 80 425.2L80 227.8C80 204.8 92.4 183.5 112.4 172.1L288.4 72.4zM166.6 219.6C157.8 216.5 147.8 219.9 142.8 228.2C137.8 236.5 139.6 246.9 146.4 253.2L149.6 255.6L299.8 345.8L299.8 494.5C299.8 505.5 308.8 514.5 319.8 514.5C330.8 514.5 339.8 505.5 339.8 494.5L339.8 345.8L490.1 255.6C499.6 249.9 502.7 237.6 497 228.2C491.3 218.8 479 215.7 469.6 221.3L319.9 311.1L170.2 221.3L166.5 219.6z"/>
        </svg>
        <span class="chip-label">{displaySystem(system)}</span>
        <span class="chip-clear" aria-hidden="true">×</span>
      </button>
    {/each}

    {#if showHidden}
      <button
        type="button"
        class="chip hidden-on"
        on:click|stopPropagation={onToggleShowHidden}
        title="Hide them again"
        aria-label="Hide hidden items again"
      >
        <span class="chip-label">hidden shown</span>
        <span class="chip-clear" aria-hidden="true">×</span>
      </button>
    {/if}
  </div>

  {#if searchActive}
    <div class="right" role="status" aria-live="polite">
      {#if isLoading}
        <span class="meter searching">
          Searching<span class="searching-dots" aria-hidden="true"><span>.</span><span>.</span><span>.</span></span>
        </span>
      {:else}
        <span class="meter" title="Across {indexedFileCount} file{indexedFileCount === 1 ? '' : 's'} matching the active scope and filters">
          {resultCount} {resultCount === 1 ? 'hit' : 'hits'} <span class="meter-of">of {indexedFileCount} files</span>
        </span>
      {/if}
    </div>
  {/if}
</div>

<style>
  .scope-bar {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.3rem 0.75rem;
    background: var(--bg-app);
    border-bottom: 1px solid var(--border-subtle);
    font-family: var(--font-body);
    font-size: 0.75rem;
    color: var(--text-secondary);
    flex-shrink: 0;
  }

  .left {
    display: flex;
    align-items: center;
    gap: 0.35rem;
    flex: 1;
    min-width: 0;
    flex-wrap: wrap;
  }

  .right {
    flex-shrink: 0;
    color: var(--text-tertiary);
    font-variant-numeric: tabular-nums;
  }

  .meter-of {
    color: var(--text-tertiary);
    opacity: 0.75;
  }

  /* Active-search readout: accent-coloured and bolder than the muted
     resting "X hits" so users notice a re-search has kicked off when
     stale results are still on screen. */
  .meter.searching {
    color: var(--text-active);
    font-weight: 600;
    letter-spacing: 0.02em;
  }

  /* Three dots whose opacity cycles in stagger — a typewriter "..."
     animation, intentionally low-fi to stay in keeping with the
     terminal/desktop aesthetic. Fixed width so the layout doesn't
     jitter as dots fade. */
  .searching-dots {
    display: inline-block;
    width: 1em;
    text-align: left;
    margin-left: 0.05em;
  }
  .searching-dots > span {
    display: inline-block;
    animation: searching-dot 1.2s infinite ease-in-out;
  }
  .searching-dots > span:nth-child(2) { animation-delay: 0.18s; }
  .searching-dots > span:nth-child(3) { animation-delay: 0.36s; }

  @keyframes searching-dot {
    0%, 100% { opacity: 0.25; }
    50% { opacity: 1; }
  }

  @media (prefers-reduced-motion: reduce) {
    .searching-dots > span {
      animation: none;
      opacity: 1;
    }
  }

  .chip {
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
    padding: 0.1rem 0.4rem;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
    background: var(--bg-container);
    color: var(--text-secondary);
    line-height: 1.2;
  }

  /* Mute chips wear the lit M button's dressing — 45% danger border,
     10% danger wash, danger ink. The chip is the button materialized,
     as the solo chip is the S button's purple. Mirrors .sm-btn.mute-on. */
  .chip.exclusion {
    border-color: color-mix(in srgb, var(--text-danger) 45%, transparent);
    background: color-mix(in srgb, var(--text-danger) 10%, transparent);
    color: var(--text-danger);
  }
  .chip.exclusion .chip-prefix {
    color: var(--text-danger);
    opacity: 0.75;
  }

  /* Solo chips use the active accent so they read as a positive
     focus state, not a removal. Mirrors the solo button in the
     filter menu. */
  .chip.solo {
    border-color: var(--text-active);
    background: color-mix(in srgb, var(--text-active) 12%, transparent);
    color: var(--text-active);
  }
  .chip.solo .chip-prefix {
    color: var(--text-active);
    opacity: 0.75;
  }

  .chip-prefix {
    color: var(--text-tertiary);
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  .chip-die,
  .chip-mark {
    width: 11px;
    height: 11px;
    flex-shrink: 0;
  }

  /* Removed, still recognizable — the exclusion's glyph dims to 60%. */
  .chip.exclusion .chip-die,
  .chip.exclusion .chip-mark {
    opacity: 0.6;
  }

  .chip-label {
    max-width: 140px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .chip.hidden-on {
    border-color: color-mix(in srgb, var(--text-accent) 35%, transparent);
    color: var(--text-accent);
  }

  /* The whole chip is the clear button; the × is just a glyph. Hover
     signals removal: grey fill step, label struck through, × at full
     opacity in danger ("color on intent", like the discard action-btn). */
  .chip {
    cursor: pointer;
    transition: background var(--transition-fast);
    /* button reset (font shorthand would zero the chips' line-height): */
    font: inherit;
    line-height: 1.2;
    text-align: left;
  }

  .chip:hover {
    background: var(--bg-focused);
  }

  .chip:hover .chip-label {
    text-decoration: line-through;
  }

  .chip:hover .chip-clear {
    opacity: 1;
    color: var(--text-danger);
  }

  .chip-clear {
    padding: 0 0.15rem;
    line-height: 1;
    opacity: 0.7;
    transition: opacity var(--transition-fast), color var(--transition-fast);
  }
</style>
