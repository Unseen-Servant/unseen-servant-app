<script lang="ts">
  import { onMount, tick } from 'svelte';
  import Markdown from 'svelte-exmarkdown';
  import type { SearchResultItem } from './types';

  export let results: SearchResultItem[] = [];
  export let isLoading: boolean = false;
  export let query: string = '';
  export let error: string | null = null;
  export let indexedFileCount: number = 0;
  export let onOpenResult: (filename: string) => void = () => {};

  let expanded = new Set<number>();
  let snippetEls: (HTMLElement | null)[] = [];
  let overflowing = new Set<number>();
  let resizeObserver: ResizeObserver | null = null;

  function checkOverflow() {
    const next = new Set(overflowing);
    for (let i = 0; i < snippetEls.length; i++) {
      const el = snippetEls[i];
      if (!el) continue;
      if (!expanded.has(i)) {
        if (el.scrollHeight > el.clientHeight + 1) next.add(i);
        else next.delete(i);
      }
    }
    overflowing = next;
  }

  function reobserve() {
    if (!resizeObserver) return;
    resizeObserver.disconnect();
    for (const el of snippetEls) if (el) resizeObserver.observe(el);
  }

  onMount(() => {
    resizeObserver = new ResizeObserver(() => checkOverflow());
    reobserve();
    checkOverflow();
    return () => resizeObserver?.disconnect();
  });

  $: if (results) {
    tick().then(() => {
      reobserve();
      checkOverflow();
    });
  }

  $: if (expanded) {
    tick().then(checkOverflow);
  }

  function toggleExpand(i: number) {
    if (expanded.has(i)) {
      expanded.delete(i);
    } else {
      expanded.add(i);
    }
    expanded = expanded;
  }

  function handleOpenClick(e: MouseEvent, filename: string) {
    e.stopPropagation();
    onOpenResult(filename);
  }

  function relevancePercent(r: number): number {
    return Math.round(r * 100);
  }

  function relevanceCells(r: number): number {
    if (r <= 0) return 0;
    return Math.max(1, Math.min(5, Math.ceil(r * 5)));
  }

  function pageSpan(start: number, end: number): string {
    if (!start) return '';
    if (start === end) return `p.${start}`;
    return `pp.${start}–${end}`;
  }

  // pymupdf4llm captures headings as `## **Goblin**`, so the breadcrumb
  // text carries the bold markup. Strip for display only — the
  // embedding pipeline keeps the original (the +0.184 MRR uplift
  // from heading-prepend was measured with the asterisks present).
  function stripBold(s: string): string {
    return s.replace(/\*\*(.+?)\*\*/g, '$1');
  }

  // Chunker breadcrumbs join ancestors with " > ". Split for per-segment
  // styling and clean wrapping at separators.
  function breadcrumbSegments(s: string): string[] {
    return s.split(' > ').map(stripBold).filter(Boolean);
  }
</script>

<div class="search-results">
  {#if isLoading}
    <div class="state-msg">Searching…</div>
  {:else if error}
    <div class="state-msg state-error">Search failed: {error}</div>
  {:else if results.length === 0 && query}
    {#if indexedFileCount === 0}
      <div class="state-msg">Index some files to enable search.</div>
    {:else}
      <div class="state-msg">No results for "{query}".</div>
    {/if}
  {:else}
    {#each results as result, i (i)}
      {@const pct = relevancePercent(result.relevance)}
      {@const cells = relevanceCells(result.relevance)}
      <div
        class="result-row"
        class:expanded={expanded.has(i)}
        on:click={() => toggleExpand(i)}
        on:keydown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleExpand(i); } }}
        role="button"
        tabindex="0"
      >
        <span class="chevron" aria-hidden="true">{expanded.has(i) ? '⌄' : '›'}</span>
        <div class="result-body">
          {#if result.section_heading}
            {@const segments = breadcrumbSegments(result.section_heading)}
            {#if segments.length > 0}
              <div class="breadcrumb" aria-label="Section path">
                {#each segments as segment, idx (idx)}
                  {#if idx > 0}<span class="bc-sep" aria-hidden="true">›</span>{/if}
                  <span class="bc-segment">{segment}</span>
                {/each}
              </div>
            {/if}
          {/if}
          <div class="snippet-wrap">
            <div
              class="snippet"
              class:clamped={!expanded.has(i)}
              bind:this={snippetEls[i]}
            >
              <Markdown md={result.text} />
            </div>
            {#if !expanded.has(i) && overflowing.has(i)}
              <span class="more-hint" aria-hidden="true">more…</span>
            {/if}
          </div>
          <div class="meta-row">
            <span class="meta-text">
              {result.filename} · {result.game_system}{pageSpan(result.page_start, result.page_end) ? ` · ${pageSpan(result.page_start, result.page_end)}` : ''}
            </span>
          </div>
        </div>
        <div class="result-aside">
          <button
            type="button"
            class="open-icon-btn"
            title="Open PDF"
            aria-label="Open PDF"
            on:click={(e) => handleOpenClick(e, result.filename)}
            on:keydown|stopPropagation
          >
            <!-- Font Awesome "arrow-up-right-from-square" icon (static/icons/arrow-up-right-from-square-solid-full.svg) -->
            <svg class="open-icon" viewBox="0 0 640 640" fill="currentColor" aria-hidden="true">
              <path d="M384 64C366.3 64 352 78.3 352 96C352 113.7 366.3 128 384 128L466.7 128L265.3 329.4C252.8 341.9 252.8 362.2 265.3 374.7C277.8 387.2 298.1 387.2 310.6 374.7L512 173.3L512 256C512 273.7 526.3 288 544 288C561.7 288 576 273.7 576 256L576 96C576 78.3 561.7 64 544 64L384 64zM144 160C99.8 160 64 195.8 64 240L64 496C64 540.2 99.8 576 144 576L400 576C444.2 576 480 540.2 480 496L480 416C480 398.3 465.7 384 448 384C430.3 384 416 398.3 416 416L416 496C416 504.8 408.8 512 400 512L144 512C135.2 512 128 504.8 128 496L128 240C128 231.2 135.2 224 144 224L224 224C241.7 224 256 209.7 256 192C256 174.3 241.7 160 224 160L144 160z"/>
            </svg>
          </button>
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
      </div>
    {/each}
  {/if}
</div>

<style>
  .search-results {
    display: flex;
    flex-direction: column;
    padding: 0.25rem 0;
  }

  .state-msg {
    padding: 2rem 1rem;
    text-align: center;
    color: var(--text-secondary);
    font-family: var(--font-body);
    font-style: italic;
  }

  .state-error {
    color: var(--text-danger);
    font-style: normal;
  }

  .result-row {
    display: flex;
    gap: 0.5rem;
    padding: 0.6rem 0.75rem;
    border-bottom: 1px solid var(--border-subtle);
    cursor: pointer;
    transition: background var(--transition-fast);
  }

  .result-row:hover {
    background: var(--bg-focused);
  }

  .result-row:focus-visible {
    outline: 1px solid var(--text-accent);
    outline-offset: -1px;
  }

  .chevron {
    flex-shrink: 0;
    width: 1rem;
    color: var(--text-secondary);
    font-size: 1rem;
    line-height: 1.3;
    -webkit-user-select: none;
    user-select: none;
  }

  .result-body {
    flex: 1;
    min-width: 0;
  }

  .snippet {
    font-family: var(--font-body);
    font-size: 0.95rem;
    color: var(--text-primary);
    line-height: 1.4;
    word-break: break-word;
  }

  .snippet :global(> *:first-child) { margin-top: 0; }
  .snippet :global(> *:last-child) { margin-bottom: 0; }
  .snippet :global(p) { margin: 0.35em 0; }
  .snippet :global(h1),
  .snippet :global(h2),
  .snippet :global(h3),
  .snippet :global(h4),
  .snippet :global(h5),
  .snippet :global(h6) {
    font-size: 1em;
    font-weight: 600;
    margin: 0.4em 0 0.2em;
  }
  .snippet :global(ul),
  .snippet :global(ol) { margin: 0.35em 0; padding-left: 1.25em; }
  .snippet :global(li) { margin: 0.1em 0; }
  .snippet :global(code) {
    font-family: var(--font-mono, ui-monospace, monospace);
    font-size: 0.9em;
    padding: 0 0.25em;
    background: var(--bg-container);
    border-radius: 2px;
  }
  .snippet :global(pre) {
    margin: 0.4em 0;
    padding: 0.4em 0.6em;
    background: var(--bg-container);
    border-radius: 3px;
    overflow-x: auto;
  }
  .snippet :global(pre code) { background: transparent; padding: 0; }
  .snippet :global(blockquote) {
    margin: 0.4em 0;
    padding-left: 0.75em;
    border-left: 2px solid var(--border-subtle);
    color: var(--text-secondary);
  }
  .snippet :global(a) { color: var(--text-accent); }
  .snippet :global(img) { max-width: 100%; height: auto; }

  .snippet.clamped {
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  .breadcrumb {
    font-family: var(--font-body);
    font-size: 0.78rem;
    color: var(--text-secondary);
    margin-bottom: 0.3rem;
    line-height: 1.35;
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    column-gap: 0.3rem;
    row-gap: 0.1rem;
  }

  .bc-segment {
    word-break: break-word;
  }

  .bc-segment:last-child {
    color: var(--text-primary);
  }

  .bc-sep {
    color: var(--border-subtle);
    -webkit-user-select: none;
    user-select: none;
  }

  .snippet-wrap {
    position: relative;
  }

  .more-hint {
    position: absolute;
    right: 0;
    bottom: 0;
    font-family: var(--font-body);
    font-size: 0.8rem;
    font-style: italic;
    color: var(--text-secondary);
    background: linear-gradient(to right, transparent, var(--bg-focused) 40%);
    padding: 0 0.15rem 0 2rem;
    line-height: 1.4;
    pointer-events: none;
    visibility: hidden;
  }

  .result-row:hover .more-hint,
  .result-row:focus-visible .more-hint {
    visibility: visible;
  }

  .meta-row {
    margin-top: 0.35rem;
    font-family: var(--font-body);
    font-size: 0.8rem;
    color: var(--text-secondary);
  }

  .meta-text {
    display: block;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .result-aside {
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    justify-content: space-between;
    gap: 0.4rem;
  }

  .gauge {
    display: inline-flex;
    gap: 2px;
    flex-shrink: 0;
    align-items: center;
    opacity: 0.85;
    transition: opacity var(--transition-fast);
  }

  .result-row:hover .gauge {
    opacity: 1;
  }

  .cell {
    width: 6px;
    height: 10px;
    border-radius: 1px;
    background: var(--border-subtle);
    transition: background var(--transition-fast);
  }

  .cell.filled {
    background: var(--text-accent);
  }

  .open-icon-btn {
    flex-shrink: 0;
    background: transparent;
    border: none;
    padding: 0.15rem;
    color: var(--text-secondary);
    cursor: pointer;
    border-radius: 3px;
    line-height: 0;
    visibility: hidden;
    transition: color var(--transition-fast), background var(--transition-fast);
  }

  .result-row:hover .open-icon-btn,
  .open-icon-btn:focus-visible {
    visibility: visible;
  }

  .open-icon-btn:hover {
    color: var(--text-accent);
    background: var(--bg-container);
  }

  .open-icon-btn:focus-visible {
    outline: 1px solid var(--text-accent);
    outline-offset: 1px;
  }

  .open-icon {
    width: 14px;
    height: 14px;
    display: block;
  }
</style>
