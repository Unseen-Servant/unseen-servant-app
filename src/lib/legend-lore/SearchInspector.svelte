<script lang="ts">
  import { tick } from 'svelte';
  import Markdown from 'svelte-exmarkdown';
  import { gfmPlugin } from 'svelte-exmarkdown/gfm';
  import type { SearchResultItem, KnownGameSystem } from './types';
  import { pageCitation, pageHint } from './pdfUrl';
  import { findMatchedRange, splitAround, type MatchedParts } from './matchedSpan';
  import { isPathOrAncestorIn } from './selectionUtils';
  import { tierCells, tierLabel } from './searchTiers';
  import { displaySystem, UNTAGGED_KEY } from './searchScope';
  import SystemBadge from './SystemBadge.svelte';
  import SystemTagMenu from './SystemTagMenu.svelte';

  export let result: SearchResultItem | null = null;
  export let hiddenPaths: Set<string> = new Set();
  export let knownSystems: KnownGameSystem[] = [];
  export let gameSystemMap: Map<string, string[]> = new Map();
  export let onOpenResult: (source: string, filename: string, page?: number | null) => void = () => {};
  export let onSetGameSystems: (path: string, tags: string[]) => void = () => {};

  // Tag-editor menu shared with FileTree; left-aligned under the badge.
  let tagMenu: SystemTagMenu | undefined;

  // Rulebook pages are half tables — without GFM they render as pipe soup.
  const mdPlugins = [gfmPlugin()];

  // The marked passage, for scrolling it into view.
  let matchEl: HTMLElement | null = null;

  $: tags = (result && gameSystemMap.get(result.source)) || [];

  // `text` is the whole assembled section now (roadmap 2.5), so the hit
  // has to be marked inside it. Null when the unit can't be located —
  // the section then renders undivided.
  $: parts = result ? matchedParts(result) : null;

  function matchedParts(r: SearchResultItem): MatchedParts | null {
    const range = findMatchedRange(r.text, r.matched_text, r.chunk_text);
    return range ? splitAround(r.text, range) : null;
  }

  // A section can run several screens; the hit is often below the fold.
  // Same tick-then-scroll shape as the result list's row scrolling.
  $: if (result) {
    tick().then(() => matchEl?.scrollIntoView({ block: 'center' }));
  }

  function toggleSystem(tag: string) {
    if (!result) return;
    const next = tags.includes(tag)
      ? tags.filter((t) => t !== tag)
      : [...tags, tag];
    onSetGameSystems(result.source, next);
  }

  function clearSystem() {
    if (!result) return;
    onSetGameSystems(result.source, []);
  }

  function stripBold(s: string): string {
    return s.replace(/\*\*(.+?)\*\*/g, '$1');
  }

  function breadcrumbSegments(s: string): string[] {
    return s.split(' > ').map(stripBold).filter(Boolean);
  }
</script>

<aside class="inspector">
  {#if !result}
    <div class="empty">Select a result to preview.</div>
  {:else}
    {@const cells = tierCells(result.tier, result.relevance)}
    {@const label = tierLabel(result.tier, result.relevance)}
    {@const span = pageHint(result.page_start, result.page_end)}
    {@const cite = pageCitation(
      result.page_start,
      result.page_end,
      result.page_label_start,
      result.page_label_end
    )}
    {@const openLabel = result.page_start ? `Open PDF at ${span}` : 'Open PDF'}
    {@const segments = result.section_heading ? breadcrumbSegments(result.section_heading) : []}

    <header class="head">
      <div class="head-text">
        <div class="meta">
          <span class="filename" title={result.source}>{result.filename}</span>
          {#if isPathOrAncestorIn(result.source, hiddenPaths)}
            <span class="badge micro-label" title="This file is hidden in the tree.">hidden</span>
          {/if}
        </div>
        <div class="sub">
          {#if result.game_system === UNTAGGED_KEY}
            <span class="sysname">untagged</span>
          {:else if result.game_system}
            <button class="sys-btn" on:click={(e) => tagMenu?.toggle(e)} aria-label="Edit game system tags">
              <SystemBadge tag={displaySystem(result.game_system)} />
            </button>
          {/if}
          {#if cite}
            <span class="dot">·</span>
            <!-- The printed page leads; the physical one stays in reach
                 for PDF viewers, which count from the cover. -->
            <span title={!span || cite === span ? undefined : `PDF ${span}`}>{cite}</span>
          {/if}
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
        on:click={() => onOpenResult(result.source, result.filename, result.page_start)}
        title={openLabel}
        aria-label={openLabel}
      >
        <svg viewBox="0 0 640 640" fill="currentColor" aria-hidden="true">
          <path d="M384 64C366.3 64 352 78.3 352 96C352 113.7 366.3 128 384 128L466.7 128L265.3 329.4C252.8 341.9 252.8 362.2 265.3 374.7C277.8 387.2 298.1 387.2 310.6 374.7L512 173.3L512 256C512 273.7 526.3 288 544 288C561.7 288 576 273.7 576 256L576 96C576 78.3 561.7 64 544 64L384 64zM144 160C99.8 160 64 195.8 64 240L64 496C64 540.2 99.8 576 144 576L400 576C444.2 576 480 540.2 480 496L480 416C480 398.3 465.7 384 448 384C430.3 384 416 398.3 416 416L416 496C416 504.8 408.8 512 400 512L144 512C135.2 512 128 504.8 128 496L128 240C128 231.2 135.2 224 144 224L224 224C241.7 224 256 209.7 256 192C256 174.3 241.7 160 224 160L144 160z"/>
        </svg>
        <span>Open</span>
      </button>
    </header>

    <SystemTagMenu
      bind:this={tagMenu}
      {knownSystems}
      {tags}
      onToggleSystem={toggleSystem}
      onClear={clearSystem}
    />

    <div class="body">
      {#if segments.length > 0}
        <div class="breadcrumb" aria-label="Section path">
          {#each segments as segment, idx (idx)}
            {#if idx > 0}<span class="bc-sep" aria-hidden="true">›</span>{/if}
            <span class="bc-segment">{segment}</span>
          {/each}
        </div>
      {/if}

      {#if result.also_in.length > 0}
        <!-- Cross-edition twins collapsed into this result (roadmap 2.3).
             Each opens its own book at its own page. -->
        <div class="also-in">
          <span class="micro-label">also in</span>
          {#each result.also_in as twin, idx (idx)}
            {@const twinCite = pageCitation(
              twin.page_start,
              twin.page_end,
              twin.page_label_start,
              twin.page_label_end
            )}
            <button
              type="button"
              class="also-chip"
              title={`Open ${twin.filename}${twinCite ? ` at ${twinCite}` : ''}`}
              on:click={() => onOpenResult(twin.source, twin.filename, twin.page_start)}
            >
              {twin.filename}{twinCite ? ` · ${twinCite}` : ''}
            </button>
          {/each}
        </div>
      {/if}

      <div class="snippet">
        {#if parts}
          <!-- Three documents, not one: the range is snapped to whole
               Markdown blocks so a table straddling it stays renderable. -->
          {#if parts.before}
            <Markdown md={parts.before} plugins={mdPlugins} />
          {/if}
          {#if parts.match}
            <div class="matched" bind:this={matchEl}>
              <Markdown md={parts.match} plugins={mdPlugins} />
            </div>
          {/if}
          {#if parts.after}
            <Markdown md={parts.after} plugins={mdPlugins} />
          {/if}
        {:else}
          <Markdown md={result.text} plugins={mdPlugins} />
        {/if}
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
    border-bottom: 1px solid var(--border-subtle);
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
    border-radius: var(--radius-sm);
    font-style: italic;
  }

  .sub {
    display: flex;
    align-items: center;
    gap: 0.35rem;
    font-size: 0.8rem;
    color: var(--text-secondary);
  }

  /* Tagged files carry the system badge; "untagged" stays plain text —
     no pill, no dropdown trigger beyond what the tree already offers. */
  .sysname {
    color: var(--text-secondary);
  }

  .sys-btn {
    display: inline-flex;
    padding: 0;
    background: none;
    border: none;
    cursor: pointer;
  }

  .sys-btn:hover :global(.game-system-badge) {
    border-color: var(--text-accent);
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

  .also-in {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.3rem;
    margin-bottom: 0.6rem;
  }

  /* The SystemBadge tint recipe — the one 20% color-mix identity wash.
     Hover brightens the border only; no glow, no new hue. */
  .also-chip {
    min-width: 0;
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    padding: 0.1rem 0.4rem;
    border: 1px solid transparent;
    border-radius: var(--radius-sm);
    background: color-mix(in srgb, var(--text-accent) 20%, transparent);
    color: var(--text-accent);
    font-family: var(--font-body);
    font-size: 0.75rem;
    cursor: pointer;
    transition: border-color var(--transition-fast);
  }

  .also-chip:hover {
    border-color: var(--text-accent);
  }

  .also-chip:focus-visible {
    outline: 1px solid var(--text-accent);
    outline-offset: 2px;
  }

  /* The unit that actually matched, inside the section around it. */
  .matched {
    background: color-mix(in srgb, var(--text-accent) 14%, transparent);
    border-left: 2px solid var(--text-accent);
    padding-left: 0.5rem;
  }

  .matched :global(> *:first-child) { margin-top: 0; }
  .matched :global(> *:last-child) { margin-bottom: 0; }

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
    font-family: var(--font-mono);
    font-size: 0.9em;
    padding: 0 0.25em;
    background: var(--bg-app);
    border-radius: 2px;
  }
  .snippet :global(pre) {
    margin: 0.45em 0;
    padding: 0.4em 0.6em;
    background: var(--bg-app);
    border-radius: var(--radius-sm);
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
    /* stylelint-disable-next-line declaration-property-value-allowed-list -- neutral 20% black recess for empty table cells */
    background: rgba(0, 0, 0, 0.2);
  }
  .snippet :global(tbody tr:nth-child(even) td) {
    /* stylelint-disable-next-line declaration-property-value-allowed-list -- neutral 2% white zebra stripe */
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
    border-radius: var(--radius-sm);
    color: var(--text-accent);
    font-family: var(--font-body);
    font-size: 0.8rem;
    cursor: pointer;
    transition: background var(--transition-fast);
  }

  .open-btn svg {
    width: 12px;
    height: 12px;
    display: block;
  }

  /* Grey step only — glows are reserved for activated states, and hover
     never introduces hue (see Design Conventions in CLAUDE.md). */
  .open-btn:hover {
    background: var(--bg-focused);
  }

  .open-btn:focus-visible {
    outline: 1px solid var(--text-accent);
    outline-offset: 2px;
  }
</style>
