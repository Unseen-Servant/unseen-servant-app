<script lang="ts">
  import { tick } from 'svelte';
  import { chord, chordHint } from './keybindings';
  import { holdsQuery, mentionAt, removeMention, searchText, viewFilter, type Mention } from './mention';

  export let searchQuery: string = '';
  export let disabled: boolean = false;
  export let panelOpen: boolean = false;
  export let panelToggleVisible: boolean = true;
  export let filterPanelOpen: boolean = false;
  export let onToggleFilterPanel: () => void = () => {};
  // Engagement lamps — lit while the panel's own narrowings are thrown,
  // open or closed. Visibility is the key's raised fill; the lamp is the mix.
  export let collectionsEngaged: boolean = false;
  export let filtersEngaged: boolean = false;
  export let onSubmit: (q: string) => void = () => {};
  export let onDebouncedChange: (q: string) => void = () => {};
  export let onClear: () => void = () => {};
  export let onFocus: () => void = () => {};
  // Fires on every focus or keystroke that leaves something to search in the
  // bar. Focus alone doesn't: an @-pick plays out over the browse view, and
  // the search view opens on the first real query.
  export let onQuery: () => void = () => {};
  export let onTogglePanel: () => void = () => {};
  export let onCollapseAll: () => void = () => {};
  export let viewToggleVisible: boolean = false;
  export let viewMode: 'tree' | 'systems' = 'tree';
  export let onSetViewMode: (mode: 'tree' | 'systems') => void = () => {};
  export let searchViewOpen: boolean = false;
  // `@` picks. The bar reports the @-word under the caret (its text after
  // the @, or null when there is none) and, while one is open, offers each
  // key to whoever plays the pick out — the collections panel — before
  // handling it itself.
  export let onMentionChange: (query: string | null) => void = () => {};
  export let onMentionKey: (event: KeyboardEvent) => boolean = () => false;

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
  let mention: Mention | null = null;
  // The query as last handed to the page, @-words stripped (and empty while
  // the bar is a / filter). Typing inside a mention leaves it unchanged, and
  // then nothing is re-searched.
  let dispatched = searchText(searchQuery);

  export function focus() {
    inputEl?.focus();
  }

  /** ⌘K: focus with the query selected, so typing replaces it. */
  export function focusAndSelect() {
    inputEl?.focus();
    inputEl?.select();
    syncMention();
  }

  function syncMention() {
    const m = focused && inputEl ? mentionAt(searchQuery, inputEl.selectionStart ?? searchQuery.length) : null;
    const query = m ? m.query : null;
    const changed = query !== (mention ? mention.query : null);
    mention = m;
    if (changed) onMentionChange(query);
  }

  /** Take the open @-word out of the bar — it was picked, or dismissed. */
  export async function consumeMention() {
    if (!mention || !inputEl) return;
    const next = removeMention(searchQuery, mention);
    searchQuery = next.value;
    await tick();
    inputEl.setSelectionRange(next.caret, next.caret);
    syncMention();
  }

  function clearDebounce() {
    if (debounceTimer !== null) {
      clearTimeout(debounceTimer);
      debounceTimer = null;
    }
  }

  function handleInput() {
    syncMention();
    if (holdsQuery(searchQuery)) onQuery();
    const current = searchText(searchQuery);
    if (current === dispatched) return;
    dispatched = current;
    clearDebounce();
    debounceTimer = setTimeout(() => {
      debounceTimer = null;
      onDebouncedChange(current);
    }, DEBOUNCE_MS);
  }

  function handleKeydown(e: KeyboardEvent) {
    // An open @-pick has first claim, and whatever it takes stops here —
    // ↓ must not drop into the results, nor Esc leave the search view.
    if (mention && !e.isComposing) {
      if (e.key === 'Escape') {
        e.preventDefault();
        e.stopPropagation();
        void consumeMention();
        return;
      }
      if (onMentionKey(e)) {
        e.preventDefault();
        e.stopPropagation();
        return;
      }
    }
    // A / filter has nothing to submit: its ↵ goes on to the page, which
    // drops it into the first match.
    if (e.key === 'Enter' && viewFilter(searchQuery) === null) {
      e.preventDefault();
      clearDebounce();
      onSubmit(searchText(searchQuery));
    }
    // Escape is handled by the page-level ladder: it steps the search
    // view closed and never clears the query — × is the only clear.
  }

  function handleClear() {
    clearDebounce();
    searchQuery = '';
    dispatched = '';
    syncMention();
    onClear();
    // Refocus only inside the search view — × on a leftover query from a
    // browse view is a tidy-up, not an entry (focus would reopen the view).
    if (searchViewOpen) inputEl?.focus();
  }
</script>

<header class="header">
  <div class="header-controls">
    {#if panelToggleVisible}
      <!-- Panel keys — hardware latches in their own well. Open is the
           raised fill the view switch uses (a view, not a mode); the LED
           under each icon is the only purple, and it answers for the mix. -->
      <div class="panel-keys" role="group" aria-label="Panels">
        <div class="key-well">
          <button
            class="panel-key"
            class:open={panelOpen}
            on:click={onTogglePanel}
            title={(panelOpen ? 'Hide collections panel' : 'Show collections panel') + chordHint('sidebar.toggle')}
            aria-label="Toggle collections panel"
            aria-pressed={panelOpen}
          >
            <!-- Font Awesome "gem" icon (src/lib/ui/icons/gem-solid-full.svg) -->
            <svg viewBox="0 0 640 640" fill="currentColor" class="toggle-icon">
              <path d="M180.7 97.8C185.2 91.7 192.4 88 200 88L440 88C447.6 88 454.8 91.6 459.3 97.8L571.3 249.8C578.1 259 577.4 271.7 569.8 280.2L337.8 536.2C333.3 541.2 326.8 544.1 320 544.1C313.2 544.1 306.8 541.2 302.2 536.2L70.2 280.2C62.5 271.7 61.9 259 68.7 249.8L180.7 97.8zM219.2 137.6C215.9 140.1 215 144.6 217.1 148.1L274.5 243.8L127.3 256C123.2 256.3 120 259.8 120 264C120 268.2 123.2 271.6 127.3 272L319.3 288C319.7 288 320.2 288 320.6 288L512.6 272C516.7 271.7 519.9 268.2 519.9 264C519.9 259.8 516.7 256.4 512.6 256L365.4 243.7L422.8 148.1C424.9 144.6 424 140 420.7 137.6C417.4 135.2 412.8 135.6 410 138.6L320 236.2L229.9 138.6C227.1 135.6 222.5 135.2 219.2 137.6z"/>
            </svg>
            <span class="lamp" class:lit={collectionsEngaged} aria-hidden="true"></span>
          </button>
        </div>
        <div class="key-well">
          <button
            class="panel-key"
            class:open={filterPanelOpen}
            on:click={onToggleFilterPanel}
            title={(filterPanelOpen ? 'Hide filter panel' : 'Show filter panel') + chordHint('filter.toggle')}
            aria-label="Toggle filter panel"
            aria-pressed={filterPanelOpen}
          >
            <!-- Font Awesome "filter" icon (src/lib/ui/icons/filter-solid-full.svg) -->
            <svg viewBox="0 0 640 640" fill="currentColor" class="toggle-icon">
              <path d="M96 128C83.1 128 71.4 135.8 66.4 147.8C61.4 159.8 64.2 173.5 73.4 182.6L256 365.3L256 480C256 488.5 259.4 496.6 265.4 502.6L329.4 566.6C338.6 575.8 352.3 578.5 364.3 573.5C376.3 568.5 384 556.9 384 544L384 365.3L566.6 182.7C575.8 173.5 578.5 159.8 573.5 147.8C568.5 135.8 556.9 128 544 128L96 128z"/>
            </svg>
            <span class="lamp" class:lit={filtersEngaged} aria-hidden="true"></span>
          </button>
        </div>
      </div>
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
          title={repeatsTree ? `Tree view — again collapses all${chordHint('tree.collapseAll')}` : `Tree view${chordHint('view.toggle')}`}
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
          title={'Shelve by system' + chordHint('view.toggle')}
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
    <!-- Font Awesome "magnifying-glass" icon (src/lib/ui/icons/magnifying-glass-solid-full.svg) -->
    <svg class="search-icon" viewBox="0 0 640 640" fill="currentColor" aria-hidden="true">
      <path d="M480 272C480 317.9 465.1 360.3 440 394.7L566.6 521.4C579.1 533.9 579.1 554.2 566.6 566.7C554.1 579.2 533.8 579.2 521.3 566.7L394.7 440C360.3 465.1 317.9 480 272 480C157.1 480 64 386.9 64 272C64 157.1 157.1 64 272 64C386.9 64 480 157.1 480 272zM272 416C351.5 416 416 351.5 416 272C416 192.5 351.5 128 272 128C192.5 128 128 192.5 128 272C128 351.5 192.5 416 272 416z"/>
    </svg>
    <!-- The search field only ever holds the query — narrowings (solos
         and mutes on either axis) live as chips in the scope bar. An
         @-word is on its way to becoming one: it is never searched. Nor is
         a bar that leads with /: that is a name filter on the browse view. -->
    <input
      bind:this={inputEl}
      bind:value={searchQuery}
      class="search-input"
      type="text"
      placeholder="Search the library, @ a collection, / to filter…"
      {disabled}
      on:input={handleInput}
      on:keydown={handleKeydown}
      on:keyup={syncMention}
      on:click={syncMention}
      on:focus={() => { focused = true; onFocus(); if (holdsQuery(searchQuery)) onQuery(); syncMention(); }}
      on:blur={() => { focused = false; syncMention(); }}
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

  /* Tighter cluster for the two wells — keeps the panel keys and the view
     switch close while preserving header gap to the search wrapper. */
  .header-controls {
    display: flex;
    align-items: center;
    gap: 0.3rem;
    flex-shrink: 0;
  }

  /* Each panel key sits in its own well, cut like the view switch's, with
     the header plate showing between them: these latch independently
     rather than picking one of two. At rest a key is flush with the well
     floor; open, it comes up on the raised fill. */
  .panel-keys {
    display: flex;
    gap: 0.3rem;
  }
  .key-well {
    display: flex;
    padding: 2px;
    background: var(--bg-app);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-well);
  }
  .panel-key {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 3px;
    width: 26px;
    height: 22px;
    background: transparent;
    border: none;
    border-radius: var(--radius-md);
    color: var(--text-tertiary);
    cursor: pointer;
    padding: 0;
    transition: all var(--transition-fast);
    flex-shrink: 0;
  }
  .panel-key:hover {
    color: var(--text-primary);
  }
  .panel-key:active {
    transform: scale(0.97);
  }
  .panel-key.open {
    background: var(--bg-header);
    color: var(--text-primary);
  }
  .panel-key .toggle-icon {
    width: 12px;
    height: 12px;
  }
  /* The LED: a dark slot at rest, so the key reads as hardware with a lamp
     that is off rather than a key with no lamp. Lit, it takes the transport's
     purple and glow. */
  .lamp {
    width: 10px;
    height: 2px;
    border-radius: var(--radius-sm);
    background: var(--border-subtle);
    transition: background var(--transition-fast);
  }
  .panel-key.open .lamp {
    background: var(--bg-app);
  }
  .lamp.lit,
  .panel-key.open .lamp.lit {
    background: var(--text-active);
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

  /* Same 12px box as the header's other Font Awesome glyphs. */
  .search-icon {
    width: 12px;
    height: 12px;
    flex-shrink: 0;
    color: var(--text-secondary);
    margin-right: 0.4rem;
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
