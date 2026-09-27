<script lang="ts">
  // Persistent readout of every narrowing the user has applied. The
  // mixer console lives in the docked FilterPanel (header cluster
  // toggle); this bar stays the readout — each chip is a
  // clear-affordance — the whole chip is the button; click to undo that
  // single narrowing without touching the others.

  import { displaySystem } from './searchScope';
  import { chordHint } from '../shell/keybindings';
  import type { CurationKey } from './searchScope';
  import { RIBBON_FILLED, RIBBON_OUTLINE, SHIELD, SHIELD_FESS } from '../ui/iconPaths';

  // Chip glyph = axis (pigment bookmark = collection, outline bookmark =
  // curation bucket, monochrome shield = system); chip frame = operation
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

<div class="scope-bar nameplate">
  <div class="left" class:bypassed={scopeBypassed}>
    <!-- The master section: a nameplate and the bypass switch, both
         permanent. The bar used to render empty until something narrowed,
         which made it a hairline nobody could learn anything from — and a
         bypass that only appears once engaged teaches nobody it exists.
         The switch is the same 18px hardware square the S and M buttons
         use, labelled with its own chord: the letter on the switch is the
         key that throws it. -->
    <span class="scope-name panel-title">Scope</span>
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
            <path d={RIBBON_FILLED}/>
          </svg>
        {:else}
          <!-- No pigment — outline ribbon, same grammar as the panel -->
          <svg class="chip-mark" viewBox="0 0 24 24" fill="none" stroke="var(--text-tertiary)" stroke-width="2.2" stroke-linejoin="round" aria-hidden="true">
            <path d={RIBBON_OUTLINE}/>
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
            <path d={RIBBON_FILLED}/>
          </svg>
        {:else}
          <svg class="chip-mark" viewBox="0 0 24 24" fill="none" stroke="var(--text-tertiary)" stroke-width="2.2" stroke-linejoin="round" aria-hidden="true">
            <path d={RIBBON_OUTLINE}/>
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
            <path d={RIBBON_FILLED}/>
          </svg>
        {:else}
          <!-- No pigment — outline ribbon, same grammar as the panel -->
          <svg class="chip-mark" viewBox="0 0 24 24" fill="none" stroke="var(--text-tertiary)" stroke-width="2.2" stroke-linejoin="round" aria-hidden="true">
            <path d={RIBBON_OUTLINE}/>
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
            <path d={RIBBON_OUTLINE}/>
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
        <!-- Active shield (with its fess) — monochrome; it marks the axis, the frame marks the operation -->
        <svg class="chip-die" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round" aria-hidden="true">
          <path d={SHIELD}/>
          <path d={SHIELD_FESS}/>
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
            <path d={RIBBON_FILLED}/>
          </svg>
        {:else}
          <!-- No pigment — outline ribbon, same grammar as the panel -->
          <svg class="chip-mark" viewBox="0 0 24 24" fill="none" stroke="var(--text-tertiary)" stroke-width="2.2" stroke-linejoin="round" aria-hidden="true">
            <path d={RIBBON_OUTLINE}/>
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
            <path d={RIBBON_OUTLINE}/>
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
        <!-- Shield — monochrome; dims with the chip ("removed, still recognizable") -->
        <svg class="chip-die" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round" aria-hidden="true">
          <path d={SHIELD}/>
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
    /* A chip is the tallest thing the row carries — taller than the 18px
       switch that sets the resting height — so the row has to be built
       for it from the start. Otherwise the first chip thickened the bar
       and shoved the tree below it down a couple of pixels. The chip
       wears this height and the row reserves it: 1.2 line-height on the
       0.75rem body text, plus 0.1rem padding and a 1px border per side. */
    --chip-height: calc(1.1rem + 2px);
    /* Pins to the top of the scrolling tree/systems container; inert in
       search mode, whose flex column doesn't scroll. z-index keeps the
       rows' positioned affordances beneath (fixed dropdowns sit higher). */
    position: sticky;
    top: 0;
    z-index: 2;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    /* A nameplate like the dock's panel mastheads (.nameplate supplies the
       plate). No bottom rule: the plate's grey parts it from the rows
       scrolling beneath. */
    padding: 0.3rem 0.75rem;
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
    /* Room for a chip whether or not one is there. Wrapping to a second
       line still grows the bar — that is a real change of state; a chip
       appearing on the line already on screen is not. */
    min-height: var(--chip-height);
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
    height: var(--chip-height);
    padding: 0.1rem 0.4rem;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
    background: var(--bg-container);
    color: var(--text-secondary);
    line-height: 1.2;
  }

  /* Names the region whether or not anything is in it. Same voice the
     other row-group headings wear. */
  .scope-name {
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
     a dip rather than a strobe. Only the narrowing chips (solo/play and
     mute frames) dip — the view-switch chips (hidden shown, indexed
     only, lens on) are display filters bypass leaves alone, and dimming
     a switch that is still doing its job would claim otherwise. */
  .left .chip {
    transition: background var(--transition-fast), opacity var(--transition-fast);
  }
  .left.bypassed .chip.solo,
  .left.bypassed .chip.exclusion {
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
     opacity in danger ("color on intent"). */
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
