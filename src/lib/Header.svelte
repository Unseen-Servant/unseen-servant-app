<script lang="ts">
  import { chord, chordHint } from './keybindings';

  export let searchQuery: string = '';
  export let disabled: boolean = false;
  export let panelOpen: boolean = false;
  export let panelToggleVisible: boolean = true;
  export let filterPanelOpen: boolean = false;
  export let onToggleFilterPanel: () => void = () => {};
  export let onSubmit: (q: string) => void = () => {};
  export let onDebouncedChange: (q: string) => void = () => {};
  export let onClear: () => void = () => {};
  export let onFocus: () => void = () => {};
  export let onTogglePanel: () => void = () => {};
  export let onCollapseAll: () => void = () => {};
  export let viewToggleVisible: boolean = false;
  export let viewMode: 'tree' | 'systems' = 'tree';
  export let onSetViewMode: (mode: 'tree' | 'systems') => void = () => {};
  export let searchViewOpen: boolean = false;

  // The switch always marks the browse view you came from — while the search
  // view is up that mark dims rather than clearing, so the view you'd return
  // to stays readable. Repeating a segment only means "do it again" when you
  // are actually in that view; from search both segments are plain exits.
  $: repeatsTree = !searchViewOpen && viewMode === 'tree';
  $: repeatsSystems = !searchViewOpen && viewMode === 'systems';

  const DEBOUNCE_MS = 300;
  let debounceTimer: ReturnType<typeof setTimeout> | null = null;
  let inputEl: HTMLInputElement | null = null;
  let focused = false;

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
    }
    // Escape is handled by the page-level ladder: it steps the search
    // view closed and never clears the query — × is the only clear.
  }

  function handleClear() {
    clearDebounce();
    searchQuery = '';
    onClear();
    // Refocus only inside the search view — × on a leftover query from a
    // browse view is a tidy-up, not an entry (focus would reopen the view).
    if (searchViewOpen) inputEl?.focus();
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
      <button
        class="panel-toggle"
        class:active={filterPanelOpen}
        on:click={onToggleFilterPanel}
        title={(filterPanelOpen ? 'Hide filter panel' : 'Show filter panel') + chordHint('filter.toggle')}
        aria-label="Toggle filter panel"
        aria-pressed={filterPanelOpen}
      >
        <!-- Faders — three channel lines with offset knobs punched out of
             the header background -->
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" class="toggle-icon">
          <path d="M5 4v16M12 4v16M19 4v16"/>
          <circle class="knob" cx="5" cy="15" r="2.6"/>
          <circle class="knob" cx="12" cy="8" r="2.6"/>
          <circle class="knob" cx="19" cy="12" r="2.6"/>
        </svg>
      </button>
    {/if}
    {#if viewToggleVisible}
      <!-- View switch — a picker, not a mode: one view is always on, so the
           current segment sits on a raised fill instead of lighting purple.
           Repeating the tree action collapses the whole tree. While the
           search view is up the current segment dims and both act as exits. -->
      <div class="view-switch" role="group" aria-label="Library view">
        <button
          class="view-segment"
          class:current={viewMode === 'tree'}
          class:dimmed={searchViewOpen}
          on:click={() => (repeatsTree ? onCollapseAll() : onSetViewMode('tree'))}
          title={(repeatsTree ? 'Tree view — again collapses all' : 'Tree view') + chordHint('view.tree')}
          aria-label="Tree view"
          aria-pressed={viewMode === 'tree'}
        >
          <!-- List tree — folder hierarchy -->
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="toggle-icon">
            <path d="M21 6H9M21 12h-8M21 18h-8" />
            <path d="M4 4v4c0 1.1.9 2 2 2h3" />
            <path d="M4 8v8c0 1.1.9 2 2 2h3" />
          </svg>
        </button>
        <button
          class="view-segment"
          class:current={viewMode === 'systems'}
          class:dimmed={searchViewOpen}
          on:click={() => { if (!repeatsSystems) onSetViewMode('systems'); }}
          title={'Shelve by system' + chordHint('view.systems')}
          aria-label="Shelve by system"
          aria-pressed={viewMode === 'systems'}
        >
          <!-- Layered stack — shelve by system -->
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="toggle-icon">
            <path d="M12 2 L22 7 L12 12 L2 7 Z" />
            <path d="M2 12 L12 17 L22 12" />
            <path d="M2 17 L12 22 L22 17" />
          </svg>
        </button>
      </div>
    {/if}
  </div>
  <div class="search-wrapper" class:disabled>
    <span class="search-icon" aria-hidden="true">⌕</span>
    <!-- The search field only ever holds the query — narrowings (solos
         and mutes on either axis) live as chips in the scope bar. -->
    <input
      bind:this={inputEl}
      bind:value={searchQuery}
      class="search-input"
      type="text"
      placeholder="Search your library…"
      {disabled}
      on:input={handleInput}
      on:keydown={handleKeydown}
      on:focus={() => { focused = true; onFocus(); }}
      on:blur={() => (focused = false)}
      aria-label="Search library"
    />
    <!-- One trailing slot, and a query outranks the hint: × shows whenever
         there is something to clear, focused or not, so a query left behind
         in a browse view stays clearable without entering search first. The
         focus-chord hint fills the slot only while it is idle — unfocused and
         empty — and stays out when the bar is disabled and the chord is a
         no-op. -->
    {#if searchQuery.length > 0}
      <button
        class="clear-btn"
        type="button"
        on:click={handleClear}
        aria-label="Clear search"
      >&times;</button>
    {:else if !focused && !disabled}
      <span class="search-chord" aria-hidden="true">{chord('search.focus')}</span>
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

  /* Tighter cluster for icon-button siblings — keeps the panel toggles
     and the view switch close while preserving header gap to the search
     wrapper. */
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

  /* View switch — two-segment picker in its own darker well against the
     header. The current segment reads as a raised fill, never purple. */
  .view-switch {
    display: flex;
    gap: 2px;
    padding: 2px;
    background: var(--bg-app);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-well);
  }
  .view-segment {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 22px;
    background: transparent;
    border: none;
    border-radius: var(--radius-md);
    color: var(--text-tertiary);
    cursor: pointer;
    padding: 0;
    transition: all var(--transition-fast);
  }
  .view-segment:hover {
    color: var(--text-primary);
  }
  .view-segment.current {
    background: var(--bg-header);
    color: var(--text-primary);
  }
  /* Search takes over the pane but not the picker: the segment you came from
     keeps its raised fill at half lift and steps down one notch in the text
     ramp. Still brighter than its idle sibling, so "last view consulted"
     stays legible without competing with the results. */
  .view-segment.current.dimmed {
    background: color-mix(in srgb, var(--bg-header) 55%, var(--bg-app));
    color: var(--text-secondary);
  }

  .toggle-icon {
    width: 14px;
    height: 14px;
    display: block;
  }
  /* Fader knobs are punched out of the header so the channel line reads
     as passing behind them. */
  .toggle-icon .knob {
    fill: var(--bg-header);
  }

  .search-wrapper {
    display: flex;
    align-items: center;
    flex: 1;
    height: calc(var(--header-height) - 10px);
    padding: 0 0.7rem;
    /* Recessed into the header at the same depth as the panels and views
       below it, and as the .view-switch well alongside it — both header
       inlays read as cut out of the plate rather than laid on it. */
    background: var(--bg-app);
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

  /* The hint is supplementary — the placeholder already says what the field
     is for — so it sits one step below the icon and placeholder voice on
     --bg-app rather than matching them. */
  .search-chord {
    padding-left: 0.5rem;
    font-family: var(--font-mono);
    font-size: 0.7rem;
    color: var(--text-tertiary);
    white-space: nowrap;
    -webkit-user-select: none;
    user-select: none;
  }

  /* × (U+00D7), not ✕ (U+2715): the bundled Crimson Text maps the former and
     not the latter, so ✕ dropped through to a system fallback and rendered in
     a face nothing else in the app uses. Every other dismiss — modal close,
     status-bar note, scope chips — is already this glyph. It draws lighter
     than ✕ did at the same size, hence the step up; as a math operator it
     sits on the mid-line, so it optically centres without nudging. */
  .clear-btn {
    background: transparent;
    border: none;
    color: var(--text-secondary);
    font-size: 1.05rem;
    cursor: pointer;
    padding: 0 0.25rem;
    margin-left: 0.25rem;
    line-height: 1;
    transition: color var(--transition-fast);
  }

  .clear-btn:hover {
    color: var(--text-primary);
  }
</style>
