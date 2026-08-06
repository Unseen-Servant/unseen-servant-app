<script lang="ts">
  import FilterMenu from './FilterMenu.svelte';
  import { chordHint } from './keybindings';

  export let searchQuery: string = '';
  export let disabled: boolean = false;
  export let panelOpen: boolean = false;
  export let panelToggleVisible: boolean = true;
  export let scopeChip: { kind: 'collection' | 'file' | 'folder'; label: string; tooltip?: string } | null = null;
  export let filterVisible: boolean = false;
  export let excludedSystems: Set<string> = new Set();
  export let soloedSystems: Set<string> = new Set();
  export let availableSystems: { name: string; count: number }[] = [];
  export let untaggedCount: number = 0;
  export let showHidden: boolean = false;
  export let hiddenCount: number = 0;
  export let collectionFilterAvailable: boolean = false;
  export let uncategorizedFilterAvailable: boolean = false;
  export let focusFilterAvailable: boolean = false;
  export let activeContextName: string | null = null;
  export let showOnlyUncollected: boolean = false;
  export let uncollectedCount: number = 0;
  export let focusActiveCollection: boolean = false;
  export let onSubmit: (q: string) => void = () => {};
  export let onDebouncedChange: (q: string) => void = () => {};
  export let onClear: () => void = () => {};
  export let onTogglePanel: () => void = () => {};
  export let onClearScope: () => void = () => {};
  export let onToggleSystemFilter: (system: string) => void = () => {};
  export let onToggleSystemSolo: (system: string) => void = () => {};
  export let onClearSystemFilter: () => void = () => {};
  export let onToggleShowHidden: () => void = () => {};
  export let onClearHidden: () => void = () => {};
  export let onToggleShowOnlyUncollected: () => void = () => {};
  export let onToggleFocusActiveCollection: () => void = () => {};
  export let collapseAllVisible: boolean = false;
  export let collapseAllDisabled: boolean = false;
  export let onCollapseAll: () => void = () => {};
  export let viewToggleVisible: boolean = false;
  export let viewMode: 'tree' | 'systems' = 'tree';
  export let onSetViewMode: (mode: 'tree' | 'systems') => void = () => {};
  export let searchActive: boolean = false;

  let filterOpen = false;
  let filterBtn: HTMLButtonElement | undefined;

  // Indicator lights up only for non-default filter states. The default for
  // hidden items is "not shown" (showHidden = false), so the dot appears
  // when the user has flipped it on. System exclusions are dormant in tree
  // view (they're the organizing axis only in systems view) but are also
  // applied to the search backend, so they're relevant whenever search is
  // active too — exposing the filter section in both contexts keeps the
  // editor reachable wherever the exclusion is taking effect.
  // Two gates for "filters that act on file metadata, not on disk shape":
  //   - systemsFilterRelevant: game-system mute/solo. Meaningful where the
  //     organizing axis IS the system tag (systems view) or where the
  //     filter actually applies (search backend).
  //   - curationFilterRelevant: collection focus / loose-only. Same logic.
  // Both are intentionally hidden in tree view because narrowing a
  // filesystem-shaped tree by content metadata breaks the spatial mental
  // model — folders and ancestors disappear for reasons the tree itself
  // can't explain. Highlighting (e.g., active-collection highlight) is
  // the right pattern there; explicit narrow controls live elsewhere.
  $: systemsFilterRelevant = viewMode === 'systems' || searchActive;
  $: curationFilterRelevant = viewMode === 'systems' || searchActive;
  $: filterActive =
    (systemsFilterRelevant && (excludedSystems.size > 0 || soloedSystems.size > 0)) ||
    (hiddenCount > 0 && showHidden) ||
    (curationFilterRelevant && uncategorizedFilterAvailable && showOnlyUncollected) ||
    (curationFilterRelevant && focusFilterAvailable && focusActiveCollection);

  const DEBOUNCE_MS = 300;
  let debounceTimer: ReturnType<typeof setTimeout> | null = null;
  let inputEl: HTMLInputElement | null = null;

  // Two-press backspace on the scope chip: first press arms the chip
  // (visual highlight, no removal yet — gives the user a chance to back
  // out), second press clears it. Disarmed by typing, by Escape, by the
  // chip being externally cleared, or by the input losing focus.
  let scopeChipArmed = false;
  $: if (!scopeChip) scopeChipArmed = false;

  export function focus() {
    inputEl?.focus();
  }

  export function toggleFilter() {
    if (!filterVisible) return;
    filterOpen = !filterOpen;
  }

  function clearDebounce() {
    if (debounceTimer !== null) {
      clearTimeout(debounceTimer);
      debounceTimer = null;
    }
  }

  function handleInput() {
    scopeChipArmed = false;
    clearDebounce();
    const current = searchQuery;
    debounceTimer = setTimeout(() => {
      debounceTimer = null;
      onDebouncedChange(current);
    }, DEBOUNCE_MS);
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Backspace' && searchQuery === '' && scopeChip) {
      e.preventDefault();
      if (scopeChipArmed) {
        scopeChipArmed = false;
        onClearScope();
      } else {
        scopeChipArmed = true;
      }
      return;
    }
    if (e.key === 'Enter') {
      e.preventDefault();
      clearDebounce();
      onSubmit(searchQuery);
    } else if (e.key === 'Escape') {
      if (scopeChipArmed) {
        e.preventDefault();
        scopeChipArmed = false;
      } else if (searchQuery.length > 0) {
        e.preventDefault();
        clearDebounce();
        searchQuery = '';
        onClear();
      }
    }
  }

  function handleBlur() {
    scopeChipArmed = false;
  }

  function handleClear() {
    clearDebounce();
    searchQuery = '';
    onClear();
    inputEl?.focus();
  }
</script>

<header class="header">
  <div class="header-controls">
    {#if panelToggleVisible}
      <button
        class="panel-toggle"
        class:active={panelOpen}
        on:click={onTogglePanel}
        title={(panelOpen ? 'Hide collections panel' : 'Show collections panel') + chordHint('sidebar.toggle')}
        aria-label="Toggle collections panel"
        aria-pressed={panelOpen}
      >
        <!-- Font Awesome "table-columns" icon (static/icons/table-columns-solid-full.svg) -->
        <svg viewBox="0 0 640 640" fill="currentColor" class="toggle-icon">
          <path d="M96 160C96 124.7 124.7 96 160 96L480 96C515.3 96 544 124.7 544 160L544 480C544 515.3 515.3 544 480 544L160 544C124.7 544 96 515.3 96 480L96 160zM160 224L160 480L288 480L288 224L160 224zM480 224L352 224L352 480L480 480L480 224z"/>
        </svg>
      </button>
    {/if}
    {#if viewToggleVisible}
      <button
        class="panel-toggle"
        class:active={viewMode === 'systems'}
        on:click={() => onSetViewMode(viewMode === 'systems' ? 'tree' : 'systems')}
        title={(viewMode === 'systems' ? 'Switch to tree view' : 'Shelve by system') + chordHint('view.toggle')}
        aria-label="Toggle view mode"
        aria-pressed={viewMode === 'systems'}
      >
        <!-- Layered stack — group by tag -->
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="toggle-icon">
          <path d="M12 2 L22 7 L12 12 L2 7 Z" />
          <path d="M2 12 L12 17 L22 12" />
          <path d="M2 17 L12 22 L22 17" />
        </svg>
      </button>
    {/if}
    {#if collapseAllVisible}
      <button
        class="panel-toggle"
        on:click={onCollapseAll}
        disabled={collapseAllDisabled}
        title="Collapse all folders"
        aria-label="Collapse all folders"
      >
        <!-- Double chevron up — collapse all -->
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" class="toggle-icon">
          <polyline points="17 11 12 6 7 11" />
          <polyline points="17 18 12 13 7 18" />
        </svg>
      </button>
    {/if}
    {#if filterVisible}
      <div class="filter-anchor">
        <button
          class="panel-toggle filter-btn"
          class:active={filterOpen}
          class:has-filter={filterActive}
          on:click|stopPropagation={() => { filterOpen = !filterOpen; }}
          bind:this={filterBtn}
          title={`Filter library${chordHint('filter.toggle')}`}
          aria-label="Filter library"
          aria-haspopup="menu"
          aria-expanded={filterOpen}
        >
          <!-- Font Awesome "filter" — viewBox padded so the glyph density
               matches the 640-viewBox panel-toggle icon next to it. -->
          <svg viewBox="-64 -64 640 640" fill="currentColor" class="toggle-icon">
            <path d="M3.9 22.9C10.5 8.9 24.5 0 40 0L472 0c15.5 0 29.5 8.9 36.1 22.9s4.6 30.5-5.2 42.5L320 290.7 320 448c0 12.1-6.8 23.2-17.7 28.6s-23.8 4.3-33.5-3l-64-48c-8.1-6-12.8-15.5-12.8-25.6l0-109.3L9 65.4C-.7 53.4-2.8 36.8 3.9 22.9z"/>
          </svg>
          {#if filterActive}<span class="filter-dot" aria-hidden="true"></span>{/if}
        </button>
        <FilterMenu
          open={filterOpen}
          anchorEl={filterBtn}
          {excludedSystems}
          {soloedSystems}
          systems={availableSystems}
          {untaggedCount}
          showSystemFilter={systemsFilterRelevant}
          onToggleSystem={onToggleSystemFilter}
          onToggleSolo={onToggleSystemSolo}
          onClearSystems={onClearSystemFilter}
          {showHidden}
          {hiddenCount}
          {onToggleShowHidden}
          {onClearHidden}
          showCollectionFilter={collectionFilterAvailable && curationFilterRelevant}
          {uncategorizedFilterAvailable}
          {focusFilterAvailable}
          {activeContextName}
          {showOnlyUncollected}
          {uncollectedCount}
          {focusActiveCollection}
          {onToggleShowOnlyUncollected}
          {onToggleFocusActiveCollection}
          onClose={() => { filterOpen = false; }}
        />
      </div>
    {/if}
  </div>
  <div class="search-wrapper" class:disabled>
    <span class="search-icon" aria-hidden="true">⌕</span>
    {#if scopeChip}
      <span
        class="scope-chip"
        class:armed={scopeChipArmed}
        title={scopeChip.tooltip ?? `${scopeChip.kind}: ${scopeChip.label}`}
      >
        <span class="scope-kind">in {scopeChip.kind}:</span>
        <span class="scope-label">{scopeChip.label}</span>
        <button
          type="button"
          class="scope-clear"
          on:click|stopPropagation={onClearScope}
          aria-label="Clear search scope"
        >✕</button>
      </span>
    {/if}
    <input
      bind:this={inputEl}
      bind:value={searchQuery}
      class="search-input"
      type="text"
      placeholder="Search your library…"
      {disabled}
      on:input={handleInput}
      on:keydown={handleKeydown}
      on:blur={handleBlur}
      aria-label="Search library"
    />
    {#if searchQuery.length > 0}
      <button
        class="clear-btn"
        type="button"
        on:click={handleClear}
        aria-label="Clear search"
      >✕</button>
    {/if}
  </div>
</header>

<style>
  .header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    height: var(--header-height);
    padding: 0 0.5rem;
    background: var(--bg-header);
    border-bottom: 1px solid var(--border-subtle);
    flex-shrink: 0;
  }

  /* Tighter cluster for icon-button siblings — keeps the panel toggle,
     filter, and collapse-all close while preserving header gap to the
     search wrapper. */
  .header-controls {
    display: flex;
    align-items: center;
    gap: 0.15rem;
    flex-shrink: 0;
  }

  .panel-toggle {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    background: transparent;
    border: 1px solid transparent;
    border-radius: var(--radius-md);
    color: var(--text-secondary);
    cursor: pointer;
    padding: 0;
    transition: all var(--transition-fast);
    flex-shrink: 0;
  }
  .panel-toggle:hover {
    color: var(--text-primary);
  }
  .panel-toggle.active {
    color: var(--text-active);
  }
  .panel-toggle.active .toggle-icon {
    filter: var(--glow-active);
  }
  .panel-toggle:disabled {
    color: var(--text-tertiary);
    cursor: not-allowed;
  }
  .panel-toggle:disabled:hover {
    color: var(--text-tertiary);
  }
  .panel-toggle:disabled .toggle-icon {
    filter: none;
  }
  .toggle-icon {
    width: 14px;
    height: 14px;
    display: block;
  }

  .filter-anchor {
    position: relative;
    flex-shrink: 0;
  }
  .filter-btn {
    position: relative;
  }
  .filter-btn.has-filter {
    color: var(--text-accent);
  }
  .filter-btn.has-filter .toggle-icon {
    filter: var(--glow-accent);
  }
  .filter-dot {
    position: absolute;
    top: 4px;
    right: 4px;
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--text-active);
  }

  .search-wrapper {
    display: flex;
    align-items: center;
    flex: 1;
    height: calc(var(--header-height) - 10px);
    padding: 0 0.7rem;
    background: var(--bg-container);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-lg);
    transition: border-color var(--transition-fast);
  }

  .search-wrapper:focus-within {
    border-color: var(--text-accent);
  }

  .search-wrapper.disabled {
    opacity: 0.5;
  }

  .search-icon {
    color: var(--text-secondary);
    font-size: 1rem;
    margin-right: 0.4rem;
    -webkit-user-select: none;
    user-select: none;
  }

  .search-input {
    flex: 1;
    min-width: 0;
    height: 100%;
    background: transparent;
    border: none;
    outline: none;
    color: var(--text-primary);
    font-family: var(--font-body);
    font-size: 0.9rem;
  }

  .search-input::placeholder {
    color: var(--text-secondary);
    font-style: italic;
  }

  .search-input:disabled {
    cursor: not-allowed;
  }

  .clear-btn {
    background: transparent;
    border: none;
    color: var(--text-secondary);
    font-size: 0.85rem;
    cursor: pointer;
    padding: 0 0.25rem;
    margin-left: 0.25rem;
    line-height: 1;
    transition: color var(--transition-fast);
  }

  .clear-btn:hover {
    color: var(--text-primary);
  }

  .scope-chip {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    max-width: 240px;
    padding: 0.1rem 0.25rem 0.1rem 0.4rem;
    margin-right: 0.4rem;
    background: rgba(146, 92, 203, 0.12);
    border: 1px solid var(--text-active);
    border-radius: var(--radius-sm);
    color: var(--text-active);
    font-size: 0.75rem;
    line-height: 1.2;
    flex-shrink: 0;
    min-width: 0;
    transition: background var(--transition-fast), filter var(--transition-fast);
  }

  /* First Backspace on the empty input arms the chip — visual signal that
     the next Backspace will clear the scope. Type, Escape, click away, or
     external clear all disarm. */
  .scope-chip.armed {
    background: rgba(146, 92, 203, 0.32);
    filter: var(--glow-active);
  }
  .scope-kind {
    color: var(--text-secondary);
    flex-shrink: 0;
  }
  .scope-label {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    min-width: 0;
    font-weight: 600;
  }
  .scope-clear {
    background: none;
    border: none;
    color: var(--text-active);
    cursor: pointer;
    font-size: 0.75rem;
    padding: 0 0.15rem;
    line-height: 1;
    border-radius: 2px;
    flex-shrink: 0;
  }
  .scope-clear:hover {
    background: rgba(146, 92, 203, 0.2);
  }
</style>
