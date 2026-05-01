<script lang="ts">
  export let searchQuery: string = '';
  export let isSearching: boolean = false;
  export let disabled: boolean = false;
  export let panelOpen: boolean = false;
  export let panelToggleVisible: boolean = true;
  export let scopeChip: { kind: 'collection' | 'file' | 'folder'; label: string; tooltip?: string } | null = null;
  export let onSubmit: (q: string) => void = () => {};
  export let onDebouncedChange: (q: string) => void = () => {};
  export let onClear: () => void = () => {};
  export let onTogglePanel: () => void = () => {};
  export let onClearScope: () => void = () => {};

  const DEBOUNCE_MS = 300;
  let debounceTimer: ReturnType<typeof setTimeout> | null = null;
  let inputEl: HTMLInputElement | null = null;

  export function focus() {
    inputEl?.focus();
  }

  function clearDebounce() {
    if (debounceTimer !== null) {
      clearTimeout(debounceTimer);
      debounceTimer = null;
    }
  }

  function handleInput() {
    clearDebounce();
    const current = searchQuery;
    debounceTimer = setTimeout(() => {
      debounceTimer = null;
      onDebouncedChange(current);
    }, DEBOUNCE_MS);
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter') {
      e.preventDefault();
      clearDebounce();
      onSubmit(searchQuery);
    } else if (e.key === 'Escape' && searchQuery.length > 0) {
      e.preventDefault();
      clearDebounce();
      searchQuery = '';
      onClear();
    }
  }

  function handleClear() {
    clearDebounce();
    searchQuery = '';
    onClear();
    inputEl?.focus();
  }
</script>

<header class="header">
  {#if panelToggleVisible}
    <button
      class="panel-toggle"
      class:active={panelOpen}
      on:click={onTogglePanel}
      title={panelOpen ? 'Hide collections panel' : 'Show collections panel'}
      aria-label="Toggle collections panel"
      aria-pressed={panelOpen}
    >
      <!-- Font Awesome "table-columns" icon (static/icons/table-columns-solid-full.svg) -->
      <svg viewBox="0 0 640 640" fill="currentColor" class="toggle-icon">
        <path d="M96 160C96 124.7 124.7 96 160 96L480 96C515.3 96 544 124.7 544 160L544 480C544 515.3 515.3 544 480 544L160 544C124.7 544 96 515.3 96 480L96 160zM160 224L160 480L288 480L288 224L160 224zM480 224L352 224L352 480L480 480L480 224z"/>
      </svg>
    </button>
  {/if}
  <div class="search-wrapper" class:disabled>
    <span class="search-icon" aria-hidden="true">⌕</span>
    {#if scopeChip}
      <span
        class="scope-chip"
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
      aria-label="Search library"
    />
    {#if isSearching}
      <span class="spinner" aria-label="Searching">⟳</span>
    {/if}
    {#if searchQuery.length > 0 && !isSearching}
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

  .panel-toggle {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 4px;
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
    color: var(--text-accent);
  }
  .toggle-icon {
    width: 14px;
    height: 14px;
    display: block;
  }

  .search-wrapper {
    display: flex;
    align-items: center;
    flex: 1;
    height: calc(var(--header-height) - 10px);
    padding: 0 0.5rem;
    background: var(--bg-container);
    border: 1px solid var(--border-subtle);
    border-radius: 4px;
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

  .spinner {
    color: var(--text-accent);
    font-size: 0.9rem;
    margin-left: 0.4rem;
    animation: spin 1s linear infinite;
    -webkit-user-select: none;
    user-select: none;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
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
    border-radius: 3px;
    color: var(--text-active);
    font-size: 0.75rem;
    line-height: 1.2;
    flex-shrink: 0;
    min-width: 0;
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
