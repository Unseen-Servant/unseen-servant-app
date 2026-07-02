<script lang="ts">
  import Markdown from 'svelte-exmarkdown';
  import type { SearchResultItem, KnownGameSystem } from './types';
  import { pageHint } from './pdfUrl';
  import { isPathOrAncestorIn } from './selectionUtils';
  import { tierCells, tierLabel } from './searchTiers';

  export let result: SearchResultItem | null = null;
  export let hiddenPaths: Set<string> = new Set();
  export let knownSystems: KnownGameSystem[] = [];
  export let onOpenResult: (filename: string, page?: number | null) => void = () => {};

  // Tag → color lookup, matching the FileTree / SystemsView pattern.
  $: tagColors = (() => {
    const m = new Map<string, string>();
    for (const sys of knownSystems) {
      if (sys.color) m.set(sys.tag, sys.color);
    }
    return m;
  })();
  $: sysColor = result ? tagColors.get(result.game_system) ?? null : null;

  function stripBold(s: string): string {
    return s.replace(/\*\*(.+?)\*\*/g, '$1');
  }

  function breadcrumbSegments(s: string): string[] {
    return s.split(' > ').map(stripBold).filter(Boolean);
  }
</script>

<aside class="inspector" style={sysColor ? `--system-color: ${sysColor}` : ''}>
  {#if !result}
    <div class="empty">Select a result to preview.</div>
  {:else}
    {@const cells = tierCells(result.tier, result.relevance)}
    {@const label = tierLabel(result.tier, result.relevance)}
    {@const span = pageHint(result.page_start, result.page_end)}
    {@const openLabel = result.page_start ? `Open PDF at ${span}` : 'Open PDF'}
    {@const segments = result.section_heading ? breadcrumbSegments(result.section_heading) : []}

    <header class="head">
      <div class="head-text">
        <div class="meta">
          <span class="filename" title={result.source}>{result.filename}</span>
          {#if isPathOrAncestorIn(result.source, hiddenPaths)}
            <span class="badge" title="This file is hidden in the tree.">hidden</span>
          {/if}
        </div>
        <div class="sub">
          {#if result.game_system}<span>{result.game_system}</span>{/if}
          {#if span}<span class="dot">·</span><span>{span}</span>{/if}
          <span class="dot">·</span>
          <span class="gauge" role="img" aria-label={label} title={label}>
            {#each [0, 1, 2, 3, 4] as idx (idx)}
              <span class="cell" class:filled={idx < cells} aria-hidden="true"></span>
            {/each}
          </span>
          <span class="pct">{label}</span>
        </div>
      </div>
      <button
        type="button"
        class="open-btn"
        on:click={() => onOpenResult(result.filename, result.page_start)}
        title={openLabel}
        aria-label={openLabel}
      >
        <svg viewBox="0 0 640 640" fill="currentColor" aria-hidden="true">
          <path d="M384 64C366.3 64 352 78.3 352 96C352 113.7 366.3 128 384 128L466.7 128L265.3 329.4C252.8 341.9 252.8 362.2 265.3 374.7C277.8 387.2 298.1 387.2 310.6 374.7L512 173.3L512 256C512 273.7 526.3 288 544 288C561.7 288 576 273.7 576 256L576 96C576 78.3 561.7 64 544 64L384 64zM144 160C99.8 160 64 195.8 64 240L64 496C64 540.2 99.8 576 144 576L400 576C444.2 576 480 540.2 480 496L480 416C480 398.3 465.7 384 448 384C430.3 384 416 398.3 416 416L416 496C416 504.8 408.8 512 400 512L144 512C135.2 512 128 504.8 128 496L128 240C128 231.2 135.2 224 144 224L224 224C241.7 224 256 209.7 256 192C256 174.3 241.7 160 224 160L144 160z"/>
        </svg>
        <span>Open</span>
      </button>
    </header>

    <div class="body">
      {#if segments.length > 0}
        <div class="breadcrumb" aria-label="Section path">
          {#each segments as segment, idx (idx)}
            {#if idx > 0}<span class="bc-sep" aria-hidden="true">›</span>{/if}
            <span class="bc-segment">{segment}</span>
          {/each}
        </div>
      {/if}

      <div class="snippet">
        <Markdown md={result.text} />
      </div>
    </div>
  {/if}
</aside>

<style>
  .inspector {
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow: hidden;
    background: var(--bg-container);
    border-left: 1px solid var(--border-subtle);
    font-family: var(--font-body);
    color: var(--text-primary);
  }

  .empty {
    margin: auto;
    padding: 1rem;
    color: var(--text-tertiary);
    font-style: italic;
    font-size: 0.9rem;
  }

  .head {
    flex-shrink: 0;
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 0.7rem;
    padding: 1rem 1.1rem 0.6rem;
    border-bottom: 2px solid color-mix(in srgb, var(--system-color, var(--text-accent)) 40%, var(--border-subtle));
  }

  .body {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding: 0.7rem 1.1rem 1rem;
  }

  .head-text {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .meta {
    display: flex;
    align-items: baseline;
    gap: 0.5rem;
    min-width: 0;
  }

  .filename {
    font-family: var(--font-heading);
    font-size: 1.05rem;
    color: var(--text-accent);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    min-width: 0;
  }

  .badge {
    flex-shrink: 0;
    padding: 0.05rem 0.35rem;
    border: 1px solid var(--border-subtle);
    border-radius: 3px;
    font-size: 0.65rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--text-tertiary);
    font-style: italic;
  }

  .sub {
    display: flex;
    align-items: center;
    gap: 0.35rem;
    font-size: 0.8rem;
    color: var(--text-secondary);
  }

  .dot {
    color: var(--border-subtle);
  }

  .pct {
    font-variant-numeric: tabular-nums;
  }

  .gauge {
    display: inline-flex;
    gap: 2px;
    align-items: center;
  }

  .cell {
    width: 6px;
    height: 10px;
    border-radius: 1px;
    background: var(--border-subtle);
  }

  .cell.filled {
    background: var(--text-accent);
  }

  .breadcrumb {
    font-size: 0.78rem;
    color: var(--text-secondary);
    margin-bottom: 0.6rem;
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

  .snippet {
    flex: 1;
    min-height: 0;
    font-size: 0.95rem;
    color: var(--text-primary);
    line-height: 1.45;
    word-break: break-word;
  }

  .snippet :global(> *:first-child) { margin-top: 0; }
  .snippet :global(> *:last-child) { margin-bottom: 0; }
  .snippet :global(p) { margin: 0.4em 0; }
  .snippet :global(h1),
  .snippet :global(h2),
  .snippet :global(h3),
  .snippet :global(h4),
  .snippet :global(h5),
  .snippet :global(h6) {
    font-size: 1em;
    font-weight: 600;
    margin: 0.5em 0 0.25em;
  }
  .snippet :global(ul),
  .snippet :global(ol) { margin: 0.4em 0; padding-left: 1.25em; }
  .snippet :global(li) { margin: 0.1em 0; }
  .snippet :global(code) {
    font-family: var(--font-mono, ui-monospace, monospace);
    font-size: 0.9em;
    padding: 0 0.25em;
    background: var(--bg-app);
    border-radius: 2px;
  }
  .snippet :global(pre) {
    margin: 0.45em 0;
    padding: 0.4em 0.6em;
    background: var(--bg-app);
    border-radius: 3px;
    overflow-x: auto;
  }
  .snippet :global(pre code) { background: transparent; padding: 0; }
  .snippet :global(blockquote) {
    margin: 0.45em 0;
    padding-left: 0.75em;
    border-left: 2px solid var(--border-subtle);
    color: var(--text-secondary);
  }
  .snippet :global(a) { color: var(--text-accent); }
  .snippet :global(img) { max-width: 100%; height: auto; }

  .snippet :global(table) {
    display: block;
    max-width: 100%;
    overflow-x: auto;
    border-collapse: collapse;
    margin: 0.5em 0;
    font-size: 0.88em;
    border: 1px solid var(--border-subtle);
    background: var(--bg-app);
  }
  .snippet :global(thead) {
    background: var(--bg-header);
  }
  .snippet :global(th),
  .snippet :global(td) {
    border: 1px solid var(--border-subtle);
    padding: 0.25em 0.5em;
    vertical-align: top;
    text-align: left;
    white-space: normal;
  }
  .snippet :global(th) {
    font-weight: 600;
    color: var(--text-accent);
  }
  .snippet :global(td:empty),
  .snippet :global(th:empty) {
    background: rgba(0, 0, 0, 0.2);
  }
  .snippet :global(tbody tr:nth-child(even) td) {
    background: rgba(255, 255, 255, 0.02);
  }

  .open-btn {
    flex-shrink: 0;
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.3rem 0.55rem;
    background: transparent;
    border: 1px solid var(--text-accent);
    border-radius: 3px;
    color: var(--text-accent);
    font-family: var(--font-body);
    font-size: 0.8rem;
    cursor: pointer;
    transition: background var(--transition-fast), filter var(--transition-fast);
  }

  .open-btn svg {
    width: 12px;
    height: 12px;
    display: block;
  }

  .open-btn:hover {
    background: rgba(182, 159, 129, 0.08);
    filter: var(--glow-accent);
  }

  .open-btn:focus-visible {
    outline: 1px solid var(--text-accent);
    outline-offset: 2px;
  }
</style>
