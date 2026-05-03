<script lang="ts">
  import { tick } from 'svelte';
  import type { SearchResultItem, KnownGameSystem } from './types';
  import { pageHint } from './pdfUrl';
  import { isPathOrAncestorIn } from './selectionUtils';

  export let results: SearchResultItem[] = [];
  export let isLoading: boolean = false;
  export let query: string = '';
  export let error: string | null = null;
  export let indexedFileCount: number = 0;
  export let hiddenPaths: Set<string> = new Set();
  export let knownSystems: KnownGameSystem[] = [];
  export let selectedIndex: number = 0;
  export let onSelect: (index: number) => void = () => {};
  export let onOpenResult: (filename: string, page?: number | null) => void = () => {};

  // Tag → color lookup. Matches the pattern in FileTree.svelte and
  // SystemsView.svelte so the system color cue is consistent across views.
  $: tagColors = (() => {
    const m = new Map<string, string>();
    for (const sys of knownSystems) {
      if (sys.color) m.set(sys.tag, sys.color);
    }
    return m;
  })();
  function colorFor(tag: string): string | null {
    return tagColors.get(tag) ?? null;
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

  function relevanceCells(r: number): number {
    if (r <= 0) return 0;
    return Math.max(1, Math.min(5, Math.ceil(r * 5)));
  }

  function relevancePercent(r: number): number {
    return Math.round(r * 100);
  }

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

<div class="search-results" role="listbox" aria-label="Search results">
  {#if isLoading}
    <div class="state-msg">Searching…</div>
  {:else if error}
    <div class="state-msg state-error">{error}</div>
  {:else if results.length === 0 && query}
    {#if indexedFileCount === 0}
      <div class="state-msg">No indexed files.</div>
    {:else}
      <div class="state-msg">0 results for &ldquo;{query}&rdquo;</div>
    {/if}
  {:else}
    {#each results as result, i (i)}
      {@const cells = relevanceCells(result.relevance)}
      {@const pct = relevancePercent(result.relevance)}
      {@const span = pageSpan(result.page_start, result.page_end)}
      {@const segments = result.section_heading ? breadcrumbSegments(result.section_heading) : []}
      {@const sysColor = colorFor(result.game_system)}
      <!-- svelte-ignore a11y-click-events-have-key-events -->
      <div
        class="result-row"
        class:selected={i === selectedIndex}
        style={sysColor ? `--system-color: ${sysColor}` : ''}
        bind:this={rowEls[i]}
        on:click={() => handleRowClick(i)}
        on:dblclick={() => handleRowDblClick(i, result)}
        role="option"
        aria-selected={i === selectedIndex}
        tabindex="-1"
      >
        <span class="index" aria-hidden="true">{i + 1}</span>
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
              <span class="hidden-badge" title="This file is hidden in the tree.">hidden</span>
            {/if}
            <span class="meta-text">
              {result.filename}{result.game_system ? ` · ${result.game_system}` : ''}{span ? ` · ${span}` : ''}
            </span>
          </div>
        </div>
        <span
          class="gauge"
          role="img"
          aria-label="{pct}% match"
          title="{pct}% match"
        >
          {#each [0, 1, 2, 3, 4] as idx (idx)}
            <span class="cell" class:filled={idx < cells} aria-hidden="true"></span>
          {/each}
        </span>
      </div>
    {/each}
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

  .result-row {
    position: relative;
    display: flex;
    gap: 0.5rem;
    padding: 0.5rem 0.75rem;
    border-bottom: 1px solid var(--border-subtle);
    cursor: pointer;
    transition: background var(--transition-fast);
    align-items: flex-start;
  }

  /* DAW track-color stripe at the left edge: always-on system color,
     widens with a soft glow on selection. Falls back to parchment when
     the row's system has no color so selection still reads. */
  .result-row::before {
    content: '';
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    width: 3px;
    background: var(--system-color, transparent);
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
    width: 4px;
    background: var(--system-color, var(--text-accent));
    filter: drop-shadow(0 0 4px color-mix(in srgb, var(--system-color, var(--text-accent)) 65%, transparent));
  }

  /* Selection state is the visual cue for "current row"; click-focus on a
     tabindex=-1 row would otherwise stack a parchment focus outline on top
     when arrow keys are pressed (keyboard interaction triggers
     :focus-visible), so suppress it here. */
  .result-row:focus,
  .result-row:focus-visible {
    outline: none;
  }

  .result-row.selected .index {
    color: var(--text-accent);
  }

  .result-row.selected .gauge {
    opacity: 1;
  }

  .index {
    flex-shrink: 0;
    width: 1.2rem;
    text-align: right;
    font-family: var(--font-body);
    font-size: 0.75rem;
    font-variant-numeric: tabular-nums;
    color: var(--text-tertiary);
    line-height: 1.5;
    -webkit-user-select: none;
    user-select: none;
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
    border-radius: 3px;
    font-size: 0.6rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--text-tertiary);
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
