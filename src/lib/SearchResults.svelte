<script lang="ts">
  import { tick } from 'svelte';
  import type { SearchResultItem } from './types';
  import { pageHint } from './pdfUrl';
  import { isPathOrAncestorIn } from './selectionUtils';
  import { allWeak, tierCells, tierLabel, weakDividerIndex } from './searchTiers';
  import { displaySystem } from './searchScope';

  export let results: SearchResultItem[] = [];
  export let isLoading: boolean = false;
  // When false, shows a clear "Ollama isn't running" notice instead of
  // letting search calls fail with cryptic connection errors. Defaults
  // to true so existing usage isn't affected.
  export let ollamaRunning: boolean = true;
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
  // reserved for collections — systems are monochrome (die + parchment).
  export let collectionColorByPath: Map<string, string> = new Map();
  export let selectedIndex: number = 0;
  export let canLoadMore: boolean = false;
  export let onSelect: (index: number) => void = () => {};
  export let onLoadMore: () => void = () => {};
  export let onOpenResult: (filename: string, page?: number | null) => void = () => {};

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
  // list (e.g. ArrowDown from the search input). Selection state and focus
  // are kept in lockstep so Enter on a focused row opens the visible
  // selection without ambiguity.
  export function focusRow(index: number): void {
    const el = rowEls[index];
    el?.focus();
  }

  // Weak-tier presentation (issues #306/#310): a divider demotes trailing
  // weak results, and an all-weak list gets an explicit callout so a
  // scoped miss doesn't masquerade as a confident answer.
  $: dividerAt = weakDividerIndex(results);
  $: allResultsWeak = allWeak(results);

  function pageSpan(start: number, end: number): string {
    return pageHint(start, end);
  }

  function stripBold(s: string): string {
    return s.replace(/\*\*(.+?)\*\*/g, '$1');
  }

  function breadcrumbSegments(s: string): string[] {
    return s.split(' > ').map(stripBold).filter(Boolean);
  }

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
    onOpenResult(result.filename, result.page_start);
  }
</script>

<div
  class="search-results"
  class:dimmed={stale && results.length > 0}
  aria-busy={stale && results.length > 0}
  role="listbox"
  aria-label="Search results"
  on:scroll={handleScroll}
>
  {#if !ollamaRunning && results.length === 0}
    <div class="state-msg state-warn">
      Ollama isn&rsquo;t running. Start it to search.
    </div>
  {:else if isLoading && results.length === 0}
    <div class="state-msg">Searching&hellip;</div>
  {:else if error}
    <div class="state-msg state-error">{error}</div>
  {:else if results.length === 0 && query}
    {#if indexedFileCount === 0}
      <div class="state-msg">{libraryEmpty ? 'No indexed files.' : 'Nothing in scope.'}</div>
    {:else}
      <div class="state-msg">0 results for &ldquo;{query}&rdquo;</div>
    {/if}
  {:else if results.length === 0}
    <!-- Search view opened from an empty bar (first use, or after ✕) -->
    <div class="state-msg">Type to search your library.</div>
  {:else}
    {#if allResultsWeak}
      <div class="weak-callout" role="status">
        No strong matches &mdash; the content may be outside the current scope.
      </div>
    {/if}
    {#each results as result, i (i)}
      {@const cells = tierCells(result.tier, result.relevance)}
      {@const label = tierLabel(result.tier, result.relevance)}
      {@const span = pageSpan(result.page_start, result.page_end)}
      {@const segments = result.section_heading ? breadcrumbSegments(result.section_heading) : []}
      {@const collColor = collectionColorByPath.get(result.source) ?? null}
      {#if i === dividerAt}
        <div class="weak-divider" role="separator">weak matches</div>
      {/if}
      <!-- svelte-ignore a11y-click-events-have-key-events -->
      <div
        class="result-row"
        class:selected={i === selectedIndex}
        class:weak={result.tier === 'weak'}
        style={collColor ? `--collection-color: ${collColor}` : ''}
        bind:this={rowEls[i]}
        on:click={() => handleRowClick(i)}
        on:dblclick={() => handleRowDblClick(i, result)}
        role="option"
        aria-selected={i === selectedIndex}
        tabindex="-1"
      >
        <span class="index-cell" aria-hidden="true">{i + 1}</span>
        <div class="row-body">
          {#if segments.length > 0}
            <div class="breadcrumb">
              {#each segments as segment, idx (idx)}
                {#if idx > 0}<span class="bc-sep" aria-hidden="true">›</span>{/if}
                <span class="bc-segment">{segment}</span>
              {/each}
            </div>
          {/if}
          <div class="snippet">{snippetPreview(result.text)}</div>
          <div class="meta-row">
            {#if isPathOrAncestorIn(result.source, hiddenPaths)}
              <span class="hidden-badge micro-label" title="This file is hidden in the tree.">hidden</span>
            {/if}
            <span class="meta-text">
              {result.filename}{result.game_system ? ` · ${displaySystem(result.game_system)}` : ''}{span ? ` · ${span}` : ''}
            </span>
          </div>
        </div>
        <span
          class="gauge"
          role="img"
          aria-label={label}
          title={label}
        >
          {#each [0, 1, 2, 3, 4] as idx (idx)}
            <span class="cell" class:filled={idx < cells} aria-hidden="true"></span>
          {/each}
        </span>
      </div>
    {/each}
    {#if isLoading && !stale && results.length > 0}
      <div class="loading-more" aria-live="polite">loading more…</div>
    {/if}
  {/if}
</div>

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

  .result-row:hover {
    background: var(--bg-focused);
  }

  .result-row.selected {
    background: var(--bg-focused);
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
  .result-row.weak:hover {
    opacity: 1;
  }

  .weak-divider {
    margin: 0.35rem 0 0.15rem;
    padding: 0 0.5rem;
    font-size: 0.7rem;
    font-variant: small-caps;
    letter-spacing: 0.08em;
    color: var(--text-tertiary);
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .weak-divider::before,
  .weak-divider::after {
    content: '';
    flex: 1;
    border-top: 1px solid var(--border-subtle);
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

  .index-cell {
    flex-shrink: 0;
    width: 1.35rem;
    height: 1.15rem;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: 2px;
    font-family: var(--font-body);
    font-size: 0.7rem;
    font-variant-numeric: tabular-nums;
    background: color-mix(in srgb, var(--collection-color, var(--text-tertiary)) 20%, transparent);
    color: var(--collection-color, var(--text-tertiary));
    -webkit-user-select: none;
    user-select: none;
    margin-top: 0.05rem;
  }

  .row-body {
    flex: 1;
    min-width: 0;
  }

  .breadcrumb {
    font-family: var(--font-body);
    font-size: 0.75rem;
    color: var(--text-secondary);
    margin-bottom: 0.15rem;
    line-height: 1.3;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .bc-segment {
    word-break: keep-all;
  }

  .bc-segment:last-child {
    color: var(--text-primary);
  }

  .bc-sep {
    color: var(--border-subtle);
    -webkit-user-select: none;
    user-select: none;
    margin: 0 0.25rem;
  }

  .snippet {
    font-family: var(--font-body);
    font-size: 0.9rem;
    color: var(--text-primary);
    line-height: 1.35;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .meta-row {
    margin-top: 0.2rem;
    font-family: var(--font-body);
    font-size: 0.75rem;
    color: var(--text-secondary);
    display: flex;
    align-items: center;
    gap: 0.4rem;
    min-width: 0;
  }

  .meta-text {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .hidden-badge {
    flex-shrink: 0;
    padding: 0.05rem 0.35rem;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    font-style: italic;
  }

  .gauge {
    display: inline-flex;
    gap: 2px;
    flex-shrink: 0;
    align-items: center;
    opacity: 0.7;
    transition: opacity var(--transition-fast);
    margin-top: 0.2rem;
  }

  .result-row:hover .gauge {
    opacity: 1;
  }

  .cell {
    width: 5px;
    height: 9px;
    border-radius: 1px;
    background: var(--border-subtle);
    transition: background var(--transition-fast);
  }

  .cell.filled {
    background: var(--text-accent);
  }
</style>
