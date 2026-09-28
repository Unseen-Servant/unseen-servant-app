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
        <!-- Font Awesome "rectangle-list" icon (src/lib/ui/icons/rectangle-list-solid-full.svg) -->
        <svg viewBox="0 0 640 640" fill="currentColor" class="toggle-icon">
          <path d="M128 128C92.7 128 64 156.7 64 192L64 448C64 483.3 92.7 512 128 512L512 512C547.3 512 576 483.3 576 448L576 192C576 156.7 547.3 128 512 128L128 128zM224 384C224 401.7 209.7 416 192 416C174.3 416 160 401.7 160 384C160 366.3 174.3 352 192 352C209.7 352 224 366.3 224 384zM192 288C174.3 288 160 273.7 160 256C160 238.3 174.3 224 192 224C209.7 224 224 238.3 224 256C224 273.7 209.7 288 192 288zM312 232L456 232C469.3 232 480 242.7 480 256C480 269.3 469.3 280 456 280L312 280C298.7 280 288 269.3 288 256C288 242.7 298.7 232 312 232zM312 360L456 360C469.3 360 480 370.7 480 384C480 397.3 469.3 408 456 408L312 408C298.7 408 288 397.3 288 384C288 370.7 298.7 360 312 360z"/>
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
        <!-- Font Awesome "filter" icon (src/lib/ui/icons/filter-solid-full.svg) -->
        <svg viewBox="0 0 640 640" fill="currentColor" class="toggle-icon">
          <path d="M96 128C83.1 128 71.4 135.8 66.4 147.8C61.4 159.8 64.2 173.5 73.4 182.6L256 365.3L256 480C256 488.5 259.4 496.6 265.4 502.6L329.4 566.6C338.6 575.8 352.3 578.5 364.3 573.5C376.3 568.5 384 556.9 384 544L384 365.3L566.6 182.7C575.8 173.5 578.5 159.8 573.5 147.8C568.5 135.8 556.9 128 544 128L96 128z"/>
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
          <!-- Font Awesome "folder-tree" icon (src/lib/ui/icons/folder-tree-solid-full.svg) -->
          <svg viewBox="0 0 640 640" fill="currentColor" class="toggle-icon">
            <path d="M80 88C80 74.7 69.3 64 56 64C42.7 64 32 74.7 32 88L32 456C32 486.9 57.1 512 88 512L272 512L272 464L88 464C83.6 464 80 460.4 80 456L80 224L272 224L272 176L80 176L80 88zM368 288L560 288C586.5 288 608 266.5 608 240L608 144C608 117.5 586.5 96 560 96L477.3 96C468.8 96 460.7 92.6 454.7 86.6L446.1 78C437.1 69 424.9 63.9 412.2 63.9L368 64C341.5 64 320 85.5 320 112L320 240C320 266.5 341.5 288 368 288zM368 576L560 576C586.5 576 608 554.5 608 528L608 432C608 405.5 586.5 384 560 384L477.3 384C468.8 384 460.7 380.6 454.7 374.6L446.1 366C437.1 357 424.9 351.9 412.2 351.9L368 352C341.5 352 320 373.5 320 400L320 528C320 554.5 341.5 576 368 576z"/>
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
          <!-- Font Awesome "layer-group" icon (src/lib/ui/icons/layer-group-solid-full.svg) -->
          <svg viewBox="0 0 640 640" fill="currentColor" class="toggle-icon">
            <path d="M296.5 69.2C311.4 62.3 328.6 62.3 343.5 69.2L562.1 170.2C570.6 174.1 576 182.6 576 192C576 201.4 570.6 209.9 562.1 213.8L343.5 314.8C328.6 321.7 311.4 321.7 296.5 314.8L77.9 213.8C69.4 209.8 64 201.3 64 192C64 182.7 69.4 174.1 77.9 170.2L296.5 69.2zM112.1 282.4L276.4 358.3C304.1 371.1 336 371.1 363.7 358.3L528 282.4L562.1 298.2C570.6 302.1 576 310.6 576 320C576 329.4 570.6 337.9 562.1 341.8L343.5 442.8C328.6 449.7 311.4 449.7 296.5 442.8L77.9 341.8C69.4 337.8 64 329.3 64 320C64 310.7 69.4 302.1 77.9 298.2L112 282.4zM77.9 426.2L112 410.4L276.3 486.3C304 499.1 335.9 499.1 363.6 486.3L527.9 410.4L562 426.2C570.5 430.1 575.9 438.6 575.9 448C575.9 457.4 570.5 465.9 562 469.8L343.4 570.8C328.5 577.7 311.3 577.7 296.4 570.8L77.9 469.8C69.4 465.8 64 457.3 64 448C64 438.7 69.4 430.1 77.9 426.2z"/>
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
    /* No bottom rule: the plates beneath it (the dock's mastheads and the
       scope bar) sit a step darker, and that step is the edge. */
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
    cursor: default;
  }

  /* The hint is supplementary — the placeholder already says what the field
     is for — so it sits one step below the icon and placeholder voice on
     --bg-app rather than matching them. */
  /* Drawn as a key cap, like the shortcut sheet's, but kept in the tertiary
     ink: it is an idle hint, not content. */
  .search-chord {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 17px;
    height: 17px;
    padding: 0 4px;
    box-sizing: border-box;
    margin-left: 0.5rem;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    background: var(--bg-app);
    font-family: var(--font-body);
    font-size: 0.62rem;
    font-weight: 700;
    color: var(--text-tertiary);
    flex-shrink: 0;
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
