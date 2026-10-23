<script lang="ts">
  import { tick } from 'svelte';
  import type { SearchResultItem } from './types';
  import { bookTitle, pageCitation } from './pdfUrl';
  import { breadcrumbSegments, isAllCaps } from './breadcrumb';
  import { isPathOrAncestorIn } from './selectionUtils';
  import { allWeak, GAUGE_CELLS, tierCells, tierLabel } from './searchTiers';
  import { markSnippet, queryTerms } from './snippetHits';
  import { displaySystem, UNTAGGED_KEY } from './searchScope';
  import { SHIELD } from '../ui/iconPaths';
  import type { KnownGameSystem } from './types';
  import SystemTagMenu from './SystemTagMenu.svelte';
  import { hoverLive } from '../ui/inputModality';
  import { grab } from '../ui/grab';
  import { writeTreePathsTransfer, clearTreePathsPayload, type TreePathsPayload } from './dragPayload';
  import { m } from '../paraglide/messages';

  export let results: SearchResultItem[] = [];
  export let isLoading: boolean = false;
  // When false, shows a clear "Ollama isn't running" notice instead of
  // letting search calls fail with cryptic connection errors. Defaults
  // to true so existing usage isn't affected.
  export let ollamaRunning: boolean = true;
  // Ollama is probed through the sidecar, so a down sidecar comes first.
  export let sidecarConnected: boolean = true;
  // True only when a fresh search is in flight — i.e., the displayed
  // rows belong to an older query than the one currently committed.
  // Dims the rows so they read as stale, distinguishes from "load more"
  // pagination where the existing rows are still authoritative.
  export let stale: boolean = false;
  export let query: string = '';
  export let error: string | null = null;
  export let indexedFileCount: number = 0;
  // True when the whole library has nothing indexed — distinct from a
  // scope narrowed down to zero files, which reads as "Nothing in scope."
  export let libraryEmpty: boolean = false;
  export let hiddenPaths: Set<string> = new Set();
  // File path → collection pigment, resolved by the parent. Color is
  // reserved for collections — systems are monochrome (shield + parchment).
  export let collectionColorByPath: Map<string, string> = new Map();
  // Weak matches fade back unless the General setting turns it off.
  export let dimWeak: boolean = true;
  export let selectedIndex: number = 0;
  export let canLoadMore: boolean = false;
  export let onSelect: (index: number) => void = () => {};
  export let onLoadMore: () => void = () => {};
  export let onOpenResult: (source: string, filename: string, page?: number | null) => void = () => {};
  // The browse views' row affordances, reaching the results: rows are
  // drag sources for the collections panel (same page-stashed payload
  // contract as the tree), carry the shared context menu, and — while a
  // collection is armed — a filing checkbox. Search stays a browsing
  // surface with a selection, so clicking a row still selects (the
  // inspector is how you judge a book before filing it); the checkbox
  // and X are the filing gestures.
  export let onBeginDrag: (path: string, name: string, isDir: boolean) => TreePathsPayload | null =
    () => null;
  export let onContextMenu: (event: MouseEvent, result: SearchResultItem) => void = () => {};
  export let curating: boolean = false;
  export let collectionPaths: Set<string> = new Set();
  export let onCollectionAdd: (paths: string[]) => void = () => {};
  export let onCollectionRemove: (paths: string[]) => void = () => {};
  // The selected row's system badge edits its book's tags, with the menu
  // FileTree uses; left-aligned under the badge.
  export let knownSystems: KnownGameSystem[] = [];
  export let gameSystemMap: Map<string, string[]> = new Map();
  export let onSetGameSystems: (path: string, tags: string[]) => void = () => {};

  let tagMenu: SystemTagMenu | undefined;

  $: selectedSource = results[selectedIndex]?.source ?? null;
  $: selectedTags = (selectedSource && gameSystemMap.get(selectedSource)) || [];

  function toggleSystem(tag: string) {
    if (!selectedSource) return;
    const next = selectedTags.includes(tag)
      ? selectedTags.filter((t) => t !== tag)
      : [...selectedTags, tag];
    onSetGameSystems(selectedSource, next);
  }

  function clearSystem() {
    if (!selectedSource) return;
    onSetGameSystems(selectedSource, []);
  }

  // Scroll-near-bottom triggers an upstream fetch for more results. The
  // parent's canLoadMore prop reflects the actual load gate (not searching,
  // not at cap, backend hasn't said it's empty), so we just have to detect
  // proximity here. 80px from the bottom is enough lead time for the next
  // batch to arrive before the user runs out of rows.
  function handleScroll(e: Event) {
    if (!canLoadMore) return;
    const el = e.currentTarget as HTMLElement;
    if (el.scrollTop + el.clientHeight >= el.scrollHeight - 80) {
      onLoadMore();
    }
  }

  let rowEls: (HTMLElement | null)[] = [];

  // Scroll the selected row into view whenever selection changes — pairs
  // with arrow-key navigation in +page.svelte.
  $: if (results.length > 0 && selectedIndex >= 0) {
    tick().then(() => {
      const el = rowEls[selectedIndex];
      if (el) el.scrollIntoView({ block: 'nearest' });
    });
  }

  // Imperative handle for the parent so it can move keyboard focus into the
  // list (e.g. after Enter in the search input). Selection state and focus
  // are kept in lockstep so Enter on a focused row opens the visible
  // selection without ambiguity.
  export function focusRow(index: number): void {
    const el = rowEls[index];
    el?.focus();
  }

  // Weak-tier presentation (issues #306/#310): weak rows are dimmed in
  // place, and an all-weak list gets an explicit callout so a scoped miss
  // doesn't masquerade as a confident answer.
  $: terms = queryTerms(query);
  const gaugeCells = Array.from({ length: GAUGE_CELLS }, (_, idx) => idx);
  $: allResultsWeak = allWeak(results);

  // Snippet preview: strip markdown markers and collapse whitespace so the
  // single-line row stays scannable. The full markdown still renders in the
  // inspector — this is just a glyph for the row.
  function snippetPreview(text: string): string {
    return text
      .replace(/```[\s\S]*?```/g, ' ')
      .replace(/`([^`]+)`/g, '$1')
      .replace(/!\[[^\]]*\]\([^)]*\)/g, '')
      .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
      .replace(/[*_~>#]/g, '')
      .replace(/\s+/g, ' ')
      .trim();
  }

  function handleRowClick(i: number) {
    onSelect(i);
  }

  function handleRowDblClick(i: number, result: SearchResultItem) {
    onSelect(i);
    onOpenResult(result.source, result.filename, result.page_start);
  }

  // Capture-phase press recording, mirroring SystemsView: the row itself
  // is the drag source, so a drag begun on the filing checkbox must be
  // refused — stopPropagation on the checkbox can't do it (drag
  // initiation isn't propagation-based).
  let pressedControl = false;
  function recordPressTarget(event: MouseEvent) {
    pressedControl = !!(event.target as HTMLElement | null)?.closest('.app-checkbox');
  }

  function handleDragStart(event: DragEvent, result: SearchResultItem) {
    if (pressedControl) {
      event.preventDefault();
      return;
    }
    const payload = onBeginDrag(result.source, result.filename, false);
    if (!payload || !event.dataTransfer) {
      event.preventDefault();
      return;
    }
    writeTreePathsTransfer(event.dataTransfer, payload);
  }

  function handleRowMouseDown(event: MouseEvent, i: number, result: SearchResultItem) {
    if (event.button === 2) {
      event.preventDefault();
      event.stopPropagation();
      // The menu acts on the row under the pointer — select it first so
      // the inspector and the menu agree about which book is meant.
      onSelect(i);
      onContextMenu(event, result);
    }
  }

  function handleCheckboxClick(event: MouseEvent, result: SearchResultItem) {
    event.stopPropagation();
    if (collectionPaths.has(result.source)) onCollectionRemove([result.source]);
    else onCollectionAdd([result.source]);
  }
</script>

<div
  class="search-results"
  class:dimmed={stale && results.length > 0}
  class:hover-live={$hoverLive}
  aria-busy={stale && results.length > 0}
  role="listbox"
  aria-label={m.lore_results_label()}
  on:scroll={handleScroll}
>
  {#if !sidecarConnected && results.length === 0}
    <div class="state-msg state-warn">
      {m.lore_results_no_sidecar()}
    </div>
  {:else if !ollamaRunning && results.length === 0}
    <div class="state-msg state-warn">
      {m.lore_results_no_ollama()}
    </div>
  {:else if isLoading && results.length === 0}
    <div class="state-msg">{m.lore_results_searching()}</div>
  {:else if error}
    <div class="state-msg state-error">{error}</div>
  {:else if results.length === 0 && query}
    {#if indexedFileCount === 0}
      <div class="state-msg">{libraryEmpty ? m.lore_results_no_indexed() : m.lore_results_nothing_in_scope()}</div>
    {:else}
      <div class="state-msg">{m.lore_results_none_for({ query })}</div>
    {/if}
  {:else if results.length === 0}
    <!-- Search view opened from an empty bar (first use, or after ×) -->
    <div class="state-msg">{m.lore_results_type_to_search()}</div>
  {:else}
    {#if allResultsWeak}
      <div class="weak-callout" role="status">
        {m.lore_results_all_weak()}
      </div>
    {/if}
    {#each results as result, i (i)}
      {@const cells = tierCells(result.tier, result.relevance)}
      {@const label = tierLabel(result.tier, result.relevance)}
      <!-- The printed page, as the inspector cites it — the number the
           reader turns to, not the PDF's index from the cover. -->
      {@const span = pageCitation(
        result.page_start,
        result.page_end,
        result.page_label_start,
        result.page_label_end
      )}
      {@const segments = result.section_heading ? breadcrumbSegments(result.section_heading) : []}
      <!-- Section first: the row is titled by what matched, the leaf
           heading, under a source line naming the book and its system —
           the one place the search view names them. A section-less hit is
           titled by its book instead. The full path is the title's
           tooltip, and the inspector plate's for the selected row. -->
      {@const leaf = segments[segments.length - 1] ?? null}
      {@const book = bookTitle(result.filename)}
      {@const selected = i === selectedIndex}
      {@const title = leaf ?? book}
      {@const collColor = collectionColorByPath.get(result.source) ?? null}
      <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-noninteractive-element-interactions -->
      <div
        class="result-row"
        class:selected={i === selectedIndex}
        class:weak={dimWeak && result.tier === 'weak'}
        style={collColor ? `--collection-color: ${collColor}` : ''}
        bind:this={rowEls[i]}
        use:grab
        on:dragstart={(e) => handleDragStart(e, result)}
        on:dragend={clearTreePathsPayload}
        on:click={() => handleRowClick(i)}
        on:dblclick={() => handleRowDblClick(i, result)}
        on:mousedown|capture={recordPressTarget}
        on:mousedown={(e) => handleRowMouseDown(e, i, result)}
        role="option"
        aria-selected={i === selectedIndex}
        tabindex="-1"
      >
        {#if curating}
          <button
            class="app-checkbox collecting row-checkbox"
            on:click={(e) => handleCheckboxClick(e, result)}
            on:mousedown|stopPropagation
            on:dblclick|stopPropagation
            role="checkbox"
            aria-label={m.lore_results_add_to_collection({ name: result.filename })}
            aria-checked={collectionPaths.has(result.source)}
          ></button>
        {/if}
        <!-- The rank, with the relevance meter under it, so the meters
             line up as a column down the list. -->
        <span class="lead">
          <span class="index-cell" aria-hidden="true">{i + 1}</span>
          <span
            class="gauge"
            role="img"
            aria-label={label}
            title={label}
          >
            {#each gaugeCells as idx (idx)}
              <span class="cell" class:filled={idx < cells} aria-hidden="true"></span>
            {/each}
          </span>
        </span>
        <div class="row-body">
          <!-- The source strip over the title, like a track's name over its
               clip. On the selected row the system is also the trigger for
               the book's tags — the inspector has no header left to carry
               it — but it looks the same as on every row: no pill, it only
               brightens on hover. "untagged" stays plain text. -->
          <div class="source-line">
            {#if isPathOrAncestorIn(result.source, hiddenPaths)}
              <span class="hidden-badge micro-label" title={m.lore_results_hidden_title()}>{m.lore_results_hidden()}</span>
            {/if}
            {#if leaf}
              <span class="source-book">{book}</span>
            {/if}
            {#if result.game_system === UNTAGGED_KEY}
              <span class="source-system">{displaySystem(result.game_system)}</span>
            {:else if result.game_system && selected}
              <button
                type="button"
                class="source-system sys-btn"
                aria-label={m.lore_results_edit_tags({ book })}
                on:click={(e) => tagMenu?.toggle(e)}
                on:mousedown|stopPropagation
                on:dblclick|stopPropagation
              >
                <svg class="source-shield" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round" aria-hidden="true">
                  <path d={SHIELD}/>
                </svg>
                {result.game_system}
              </button>
            {:else if result.game_system}
              <span class="source-system">
                <svg class="source-shield" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round" aria-hidden="true">
                  <path d={SHIELD}/>
                </svg>
                {result.game_system}
              </span>
            {/if}
            {#if span}
              <span class="row-page">{span}</span>
            {/if}
          </div>
          <div class="title-line" title={segments.length > 0 ? segments.join(' › ') : undefined}>
            <span class="row-title" class:caps={leaf !== null && isAllCaps(leaf)}>{title}</span>
          </div>
          <!-- The row shows why it matched: `text` is the whole section
               now, whose opening line is rarely the hit (roadmap 2.5). -->
          <div class="snippet">{#each markSnippet(snippetPreview(result.matched_text || result.text), terms) as part, idx (idx)}{#if part.hit}<span class="hit">{part.text}</span>{:else}{part.text}{/if}{/each}</div>
          {#if result.also_in.length > 0}
            <!-- Cross-edition twins folded into this row (roadmap 2.3);
                 the inspector lists and opens them. -->
            <div class="also-row">
              <span class="also-chip" title={result.also_in.map((a) => bookTitle(a.filename)).join(', ')}>
                {m.lore_results_editions({ count: result.also_in.length })}
              </span>
            </div>
          {/if}
        </div>
      </div>
    {/each}
    {#if isLoading && !stale && results.length > 0}
      <div class="loading-more" aria-live="polite">{m.lore_results_loading_more()}</div>
    {/if}
  {/if}
</div>

<SystemTagMenu
  bind:this={tagMenu}
  {knownSystems}
  tags={selectedTags}
  onToggleSystem={toggleSystem}
  onClear={clearSystem}
/>

<style>
  .search-results {
    display: flex;
    flex-direction: column;
    padding: 0.25rem 0;
    height: 100%;
    overflow-y: auto;
  }

  .state-msg {
    padding: 0.6rem 0.75rem;
    color: var(--text-secondary);
    font-family: var(--font-body);
    font-size: 0.85rem;
  }

  .state-error {
    color: var(--text-danger);
  }

  .state-warn {
    color: var(--text-accent);
  }

  .loading-more {
    padding: 0.5rem 0.75rem 0.75rem;
    color: var(--text-tertiary);
    font-family: var(--font-body);
    font-size: 0.75rem;
    font-style: italic;
    text-align: center;
  }

  .result-row {
    position: relative;
    display: flex;
    gap: 0.5rem;
    padding: 0.5rem 0.75rem;
    border-bottom: 1px solid var(--border-subtle);
    cursor: pointer;
    transition: background var(--transition-fast), opacity var(--transition-fast);
    align-items: flex-start;
    /* Rows are drag sources, like the tree's; the inspector keeps the
       selectable full text. */
    -webkit-user-select: none;
    user-select: none;
  }

  /* Filing checkbox while a collection is armed — colour comes from the
     shared .app-checkbox.collecting recipe. Nudged to the index cell's
     optical line, since the row aligns flex-start. */
  .row-checkbox {
    flex-shrink: 0;
    margin-top: 1.1rem;
  }

  /* Stale-results state: a new search is in flight against a different
     query, but the previous rows are still rendered. Fade them so the
     reader registers "this is what you were looking at, the new answer
     is on the way" without losing scroll position or layout. */
  .search-results.dimmed .result-row {
    opacity: 0.35;
    pointer-events: none;
  }

  /* Selection stripe at the left edge: collection pigment with a soft
     glow, parchment fallback when the file is in no colored collection.
     The per-row collection cue lives on the index cell instead. */
  .result-row::before {
    content: '';
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    width: 4px;
    background: transparent;
    transition: width var(--transition-fast), filter var(--transition-fast), background var(--transition-fast);
    pointer-events: none;
  }

  /* Hover paints only while the pointer drives ($hoverLive): an arrow
     scrolls rows under a resting pointer, and :hover would light the one
     that slid beneath it beside the selected row. */
  .hover-live .result-row:hover {
    background: var(--bg-container);
  }

  /* Selection here *is* the keyboard cursor (selectedIndex, arrow-driven),
     so it takes the row focus ring rather than a state fill. The stripe,
     the inverted index cell and the lit gauge below carry the rest. */
  .result-row.selected {
    box-shadow: var(--ring-focus);
  }

  .result-row.selected::before {
    background: var(--collection-color, var(--text-accent));
    filter: drop-shadow(0 0 4px color-mix(in srgb, var(--collection-color, var(--text-accent)) 65%, transparent));
  }

  /* Selection state is the visual cue for "current row"; click-focus on a
     tabindex=-1 row would otherwise stack a parchment focus outline on top
     when arrow keys are pressed (keyboard interaction triggers
     :focus-visible), so suppress it here. */
  .result-row:focus,
  .result-row:focus-visible {
    outline: none;
  }

  .result-row.selected .index-cell {
    background: var(--collection-color, var(--text-accent));
    color: var(--text-inverse);
  }

  .result-row.selected .gauge {
    opacity: 1;
  }

  /* Weak-tier results stay listed (recall) but read as demoted. Selection
     restores full opacity so keyboard navigation stays legible. */
  .result-row.weak {
    opacity: 0.55;
  }

  .result-row.weak.selected,
  .hover-live .result-row.weak:hover {
    opacity: 1;
  }

  .weak-callout {
    margin: 0.35rem 0.5rem;
    padding: 0.35rem 0.5rem;
    font-size: 0.8rem;
    font-style: italic;
    color: var(--text-tertiary);
    border: 1px dashed var(--border-subtle);
    border-radius: 2px;
  }

  .lead {
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.3rem;
    /* Level with the title line, under the source strip. */
    margin-top: 1.1rem;
  }

  .index-cell {
    width: 1.35rem;
    height: 1.15rem;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: 2px;
    /* Gilt folio numerals: Almendra, and parchment rather than grey when
       no collection claims the file. A collection's pigment still wins, so
       the colour↔collection mapping the panel teaches survives. Almendra's
       figures are proportional; the fixed cell width keeps the column
       aligned all the same. */
    font-family: var(--font-heading);
    font-size: 0.8rem;
    line-height: 1;
    background: color-mix(in srgb, var(--collection-color, var(--text-accent)) 15%, transparent);
    color: var(--collection-color, var(--text-accent));
    -webkit-user-select: none;
    user-select: none;
  }

  .row-body {
    flex: 1;
    min-width: 0;
  }

  /* The source strip: the book, then its system, one voice for both, and
     the printed page at the far edge. The book gives way to a narrow pane;
     the system and page stay. */
  .source-line {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    min-width: 0;
    margin-bottom: 0.05rem;
    font-family: var(--font-body);
    line-height: 1.3;
    white-space: nowrap;
  }

  .source-book {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    font-size: 0.75rem;
    color: var(--text-secondary);
  }

  .source-system {
    flex-shrink: 0;
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
    font-size: 0.75rem;
    color: var(--text-secondary);
  }

  .source-shield {
    width: 9px;
    height: 9px;
  }

  /* The selected row's system, as a trigger: unstyled so it reads the
     same as every row's. Hover brightens — no glow, no new hue. */
  .sys-btn {
    padding: 0;
    background: none;
    border: none;
    font-family: var(--font-body);
    cursor: pointer;
    transition: filter var(--transition-fast);
  }

  .sys-btn:hover {
    filter: brightness(1.35);
  }

  .sys-btn:focus-visible {
    outline: 1px solid var(--text-accent);
    outline-offset: 2px;
  }

  .title-line {
    min-width: 0;
    font-family: var(--font-body);
    line-height: 1.3;
  }

  .row-title {
    display: block;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 0.95rem;
    font-weight: 600;
    color: var(--text-primary);
  }

  /* The printed page, as the inspector cites it. */
  .row-page {
    flex-shrink: 0;
    margin-left: auto;
    font-size: 0.75rem;
    font-variant-numeric: tabular-nums;
    color: var(--text-secondary);
  }

  /* Headings set in capitals in the source sit level with mixed-case
     ones instead of shouting over them. */
  .caps {
    font-variant-caps: all-small-caps;
    letter-spacing: 0.04em;
  }

  /* A step down from the title, so the query terms stand out in it. */
  .snippet {
    font-family: var(--font-body);
    font-size: 0.85rem;
    color: var(--text-secondary);
    line-height: 1.35;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  /* The selected row opens its snippet to two lines — the one row whose
     reason for matching the reader is weighing. */
  .result-row.selected .snippet {
    display: -webkit-box;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    white-space: normal;
  }

  /* Query terms in the data colour — parchment, no fill, no glow. */
  .hit {
    color: var(--text-accent);
  }

  .hidden-badge {
    flex-shrink: 0;
    padding: 0.05rem 0.35rem;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    font-style: italic;
  }

  .also-row {
    margin-top: 0.2rem;
  }

  /* The SystemBadge tint recipe — identity fills are the one 20%
     color-mix wash. Data, so parchment; no glow (not an active state). */
  .also-chip {
    display: inline-block;
    padding: 0.05rem 0.4rem;
    border-radius: var(--radius-sm);
    background: color-mix(in srgb, var(--text-accent) 20%, transparent);
    color: var(--text-accent);
    font-family: var(--font-body);
    font-size: 0.7rem;
    white-space: nowrap;
  }

  .gauge {
    display: inline-flex;
    gap: 2px;
    opacity: 0.7;
    transition: opacity var(--transition-fast);
  }

  .hover-live .result-row:hover .gauge {
    opacity: 1;
  }

  /* Flatter than tall under the rank cell, so the pair reads as one
     column mark. */
  .cell {
    width: 5px;
    height: 6px;
    border-radius: var(--radius-cell);
    background: var(--border-subtle);
    transition: background var(--transition-fast);
  }

  .cell.filled {
    background: var(--text-accent);
  }
</style>
