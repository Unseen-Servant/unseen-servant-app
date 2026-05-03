<script lang="ts">
  // Persistent readout of every narrowing the user has applied to a search.
  // Sits above the result list so a surprising hit count ("only 2?") always
  // has a visible cause. Each chip is a clear-affordance — click to undo
  // that single narrowing without touching the others.

  export let scopeChip: { kind: 'collection' | 'file' | 'folder'; label: string; tooltip?: string } | null = null;
  export let excludedSystems: Set<string> = new Set();
  export let showHidden: boolean = false;
  export let resultCount: number = 0;
  export let indexedFileCount: number = 0;
  export let isLoading: boolean = false;
  export let onClearScope: () => void = () => {};
  export let onToggleSystemFilter: (system: string) => void = () => {};
  export let onToggleShowHidden: () => void = () => {};

  $: excludedList = Array.from(excludedSystems).sort();
  $: scopeKindLabel = scopeChip ? scopeChip.kind : 'library';
</script>

<div class="scope-bar" role="status" aria-live="polite">
  <div class="left">
    <span class="scope-readout" class:narrowed={!!scopeChip} title={scopeChip?.tooltip ?? 'Searching the entire library'}>
      <span class="scope-kind">{scopeKindLabel}:</span>
      <span class="scope-label">{scopeChip ? scopeChip.label : 'all indexed files'}</span>
      {#if scopeChip}
        <button
          type="button"
          class="chip-clear"
          on:click|stopPropagation={onClearScope}
          aria-label="Clear search scope"
          title="Clear scope"
        >×</button>
      {/if}
    </span>

    {#each excludedList as system (system)}
      <span class="chip exclusion" title="Excluded: {system}">
        <span class="chip-prefix">excl.</span>
        <span class="chip-label">{system}</span>
        <button
          type="button"
          class="chip-clear"
          on:click|stopPropagation={() => onToggleSystemFilter(system)}
          aria-label="Re-include {system}"
          title="Re-include {system}"
        >×</button>
      </span>
    {/each}

    {#if showHidden}
      <span class="chip hidden-on" title="Hidden files are visible in the tree">
        <span class="chip-label">hidden shown</span>
        <button
          type="button"
          class="chip-clear"
          on:click|stopPropagation={onToggleShowHidden}
          aria-label="Hide hidden items again"
          title="Hide them again"
        >×</button>
      </span>
    {/if}
  </div>

  <div class="right">
    {#if isLoading}
      <span class="meter">searching…</span>
    {:else}
      <span class="meter" title="Across {indexedFileCount} file{indexedFileCount === 1 ? '' : 's'} matching the active scope and filters">
        {resultCount} {resultCount === 1 ? 'hit' : 'hits'} <span class="meter-of">of {indexedFileCount} files</span>
      </span>
    {/if}
  </div>
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
    overflow: hidden;
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

  .scope-readout {
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
    padding: 0.1rem 0.4rem;
    border-radius: 3px;
    border: 1px solid transparent;
    color: var(--text-secondary);
  }

  .scope-readout.narrowed {
    border-color: var(--text-active);
    background: rgba(146, 92, 203, 0.1);
    color: var(--text-active);
  }

  .scope-kind {
    color: var(--text-tertiary);
    text-transform: uppercase;
    font-size: 0.65rem;
    letter-spacing: 0.06em;
  }

  .scope-readout.narrowed .scope-kind {
    color: var(--text-active);
    opacity: 0.75;
  }

  .scope-label {
    font-weight: 600;
    max-width: 220px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .chip {
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
    padding: 0.1rem 0.4rem;
    border-radius: 3px;
    border: 1px solid var(--border-subtle);
    background: var(--bg-container);
    color: var(--text-secondary);
    line-height: 1.2;
  }

  .chip.exclusion {
    border-color: rgba(239, 68, 68, 0.3);
    color: var(--text-secondary);
  }

  .chip-prefix {
    color: var(--text-tertiary);
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  .chip-label {
    max-width: 140px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .chip.hidden-on {
    border-color: rgba(182, 159, 129, 0.35);
    color: var(--text-accent);
  }

  .chip-clear {
    background: none;
    border: none;
    color: inherit;
    cursor: pointer;
    padding: 0 0.15rem;
    line-height: 1;
    border-radius: 2px;
    opacity: 0.7;
    transition: opacity var(--transition-fast), background var(--transition-fast);
  }

  .chip-clear:hover {
    opacity: 1;
    background: rgba(255, 255, 255, 0.06);
  }

  .chip-clear:focus-visible {
    outline: 1px solid var(--text-accent);
    outline-offset: 1px;
    opacity: 1;
  }
</style>
