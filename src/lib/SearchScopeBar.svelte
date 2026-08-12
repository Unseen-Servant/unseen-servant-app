<script lang="ts">
  // Persistent readout of every narrowing the user has applied. The
  // mixer console lives in the docked FilterPanel (header cluster
  // toggle); this bar stays the readout — each chip is a
  // clear-affordance — the whole chip is the button; click to undo that
  // single narrowing without touching the others.

  import { displaySystem } from './searchScope';
  import { chordHint } from './keybindings';
  import type { CurationKey } from './searchScope';

  // Chip glyph = axis (pigment bookmark = collection, outline bookmark =
  // curation bucket, monochrome die = system); chip frame = operation
  // (purple play/solo / danger-edged mute).
  export let collectionPlays: { key: string; label: string; color: string | null }[] = [];
  export let collectionSolos: { key: string; label: string; color: string | null }[] = [];
  export let collectionMutes: { key: string; label: string; color: string | null }[] = [];
  export let collectionTrackMutes: { key: string; label: string; color: string | null }[] = [];
  export let onClearCollectionTrackMute: (key: string) => void = () => {};
  export let excludedSystems: Set<string> = new Set();
  export let soloedSystems: Set<string> = new Set();
  export let curationSolos: Set<CurationKey> = new Set();
  export let curationMutes: Set<CurationKey> = new Set();
  export let showHidden: boolean = false;
  export let hideOutOfScope: boolean = false;
  export let hideUnindexed: boolean = false;
  export let resultCount: number = 0;
  export let indexedFileCount: number = 0;
  // Master bypass. The row is the readout for what narrows a search, so
  // it has to say when nothing does — otherwise the chips claim a scope
  // the meter's denominator contradicts.
  export let scopeBypassed: boolean = false;
  export let onToggleBypass: () => void = () => {};

  // Only the narrowings bypass actually suppresses. The lens chips
  // (hidden items, focus lens, indexed-only) are display filters that
  // bypass leaves alone, so they must not summon a switch that would do
  // nothing to them.
  // Bypassed counts as bypassable so the switch can be thrown back — the
  // narrowings it suppresses are still set, they just aren't in effect.
  $: bypassable = scopeBypassed || anyBypassable;

  $: anyBypassable =
    collectionPlays.length > 0 ||
    collectionSolos.length > 0 ||
    collectionMutes.length > 0 ||
    collectionTrackMutes.length > 0 ||
    excludedSystems.size > 0 ||
    soloedSystems.size > 0 ||
    curationSolos.size > 0 ||
    curationMutes.size > 0;
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
  export let onToggleHideOutOfScope: () => void = () => {};
  export let onToggleHideUnindexed: () => void = () => {};

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
  // Folder/file solos override folder/file mutes within their axis, so
  // those mute chips would mislead and are suppressed. Playing no
  // longer suppresses them: S/M narrows within the mix, both apply.
  $: shownCollectionMutes = collectionSolos.length > 0 ? [] : collectionMutes;
  $: curationSoloList = CURATION_ORDER.filter((k) => curationSolos.has(k));
  $: curationMuteList =
    curationSoloList.length > 0 ? [] : CURATION_ORDER.filter((k) => curationMutes.has(k));
</script>

<div class="scope-bar">
  <div class="left" class:bypassed={scopeBypassed}>
    <!-- The master section: a nameplate and the bypass switch, both
         permanent. The bar used to render empty until something narrowed,
         which made it a hairline nobody could learn anything from — and a
         bypass that only appears once engaged teaches nobody it exists.
         The switch is the same 18px hardware square the S and M buttons
         use, labelled with its own chord: the letter on the switch is the
         key that throws it. -->
    <span class="nameplate ledger-label">Scope</span>
    <button
      type="button"
      class="sm-btn"
      class:bypass-on={scopeBypassed}
      disabled={!bypassable}
      aria-pressed={scopeBypassed}
      on:click|stopPropagation={onToggleBypass}
      title={!bypassable
        ? 'Nothing to bypass yet — solo or mute something first'
        : scopeBypassed
          ? `Scope bypassed — every indexed file is in scope. Restore it${chordHint('scope.bypass')}`
          : `Bypass the scope — every indexed file back in scope, without clearing anything${chordHint('scope.bypass')}`}
    >B</button>
    <span class="master-rule" aria-hidden="true"></span>

    {#if !bypassable && !searchActive}
      <!-- Only when the meter isn't showing: with a search active and no
           scope engaged, both would report the same total. -->
      <span class="resting">all {indexedFileCount} files</span>
    {/if}
    {#each collectionPlays as chip (chip.key)}
      <button
        type="button"
        class="chip solo"
        on:click|stopPropagation={() => onClearCollectionPlay(chip.key)}
        title="Stop {chip.label}"
        aria-label="Stop {chip.label}"
      >
        <span class="chip-prefix micro-label">play</span>
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

    {#each collectionTrackMutes as chip (chip.key)}
      <button
        type="button"
        class="chip exclusion"
        on:click|stopPropagation={() => onClearCollectionTrackMute(chip.key)}
        title="Unmute {chip.label}"
        aria-label="Unmute {chip.label}"
      >
        <span class="chip-prefix micro-label">mute</span>
        {#if chip.color}
          <!-- Bookmark ribbon — the collection keeps its pigment even muted -->
          <svg class="chip-mark" viewBox="0 0 24 24" fill={chip.color} aria-hidden="true">
            <path d="M5 2h14v20l-7-5.2L5 22z"/>
          </svg>
        {:else}
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
        <span class="chip-prefix micro-label">solo</span>
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
        <span class="chip-prefix micro-label">solo</span>
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
        <span class="chip-prefix micro-label">solo</span>
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
        <span class="chip-prefix micro-label">mute</span>
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
        <span class="chip-prefix micro-label">mute</span>
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
        <span class="chip-prefix micro-label">mute</span>
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

    {#if hideUnindexed}
      <button
        type="button"
        class="chip indexed-only"
        on:click|stopPropagation={onToggleHideUnindexed}
        title="Show unindexed items again"
        aria-label="Show unindexed items again"
      >
        <span class="chip-label">indexed only</span>
        <span class="chip-clear" aria-hidden="true">×</span>
      </button>
    {/if}

    {#if hideOutOfScope}
      <button
        type="button"
        class="chip lens-on"
        on:click|stopPropagation={onToggleHideOutOfScope}
        title="Show out-of-scope items again"
        aria-label="Show out-of-scope items again"
      >
        <span class="chip-label">lens on</span>
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
        <!-- Under bypass the denominator is the whole library, so the
             tooltip must stop claiming the scope produced it. -->
        <span
          class="meter"
          title={scopeBypassed
            ? `Across all ${indexedFileCount} indexed file${indexedFileCount === 1 ? '' : 's'} — the scope is bypassed`
            : `Across ${indexedFileCount} file${indexedFileCount === 1 ? '' : 's'} matching the active scope and filters`}
        >
          {resultCount} {resultCount === 1 ? 'hit' : 'hits'} <span class="meter-of">of {indexedFileCount} files</span>
        </span>
      {/if}
    </div>
  {/if}
</div>

<style>
  .scope-bar {
    /* Pins to the top of the scrolling tree/systems container; inert in
       search mode, whose flex column doesn't scroll. z-index keeps the
       rows' positioned affordances beneath (fixed dropdowns sit higher). */
    position: sticky;
    top: 0;
    z-index: 2;
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

  /* Names the region whether or not anything is in it. Same voice the
     other row-group headings wear. */
  .nameplate {
    flex-shrink: 0;
  }

  /* Divides master from channels — the switch above the strip, not the
     first chip in it. */
  .master-rule {
    width: 1px;
    height: 12px;
    background: var(--border-subtle);
    flex-shrink: 0;
  }

  /* What the bar says when nothing narrows: the count the search would
     run against. Quiet — it is the absence of state, not state. */
  .resting {
    color: var(--text-tertiary);
    opacity: 0.75;
    font-style: italic;
  }

  /* Dimmed, not hidden: the point of a bypass is to see what you are
     bypassing. Reuses the app's single out-of-scope dim step rather than
     inventing a second one, and transitions so a momentary hold reads as
     a dip rather than a strobe. */
  .left .chip {
    transition: background var(--transition-fast), opacity var(--transition-fast);
  }
  .left.bypassed .chip {
    opacity: var(--opacity-out-of-scope);
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

  /* Both are modes the user switched on, so both wear purple. A shared
     rule rather than a reused class name — "lens-on" would misname the
     unindexed chip, which is not the focus lens. */
  .chip.lens-on,
  .chip.indexed-only {
    border-color: color-mix(in srgb, var(--text-active) 35%, transparent);
    color: var(--text-active);
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
