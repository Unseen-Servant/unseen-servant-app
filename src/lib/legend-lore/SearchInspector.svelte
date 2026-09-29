<script lang="ts">
  import { tick } from 'svelte';
  import Markdown, { type Plugin } from 'svelte-exmarkdown';
  import { gfmPlugin } from 'svelte-exmarkdown/gfm';
  import type { SearchResultItem, KnownGameSystem } from './types';
  import { bookTitle, pageCitation, pageHint } from './pdfUrl';
  import { findMatchedRange, splitAround, type MatchedParts } from './matchedSpan';
  import { isPathOrAncestorIn } from './selectionUtils';
  import { displaySystem, UNTAGGED_KEY } from './searchScope';
  import { breadcrumbSegments, isAllCaps } from './breadcrumb';
  import { queryTerms, rehypeMarkTerms } from './snippetHits';
  import { chordHint } from '../shell/keybindings';
  import SystemBadge from './SystemBadge.svelte';
  import SystemTagMenu from './SystemTagMenu.svelte';

  export let result: SearchResultItem | null = null;
  export let query: string = '';
  export let hiddenPaths: Set<string> = new Set();
  export let knownSystems: KnownGameSystem[] = [];
  export let gameSystemMap: Map<string, string[]> = new Map();
  export let onOpenResult: (source: string, filename: string, page?: number | null) => void = () => {};
  export let onSetGameSystems: (path: string, tags: string[]) => void = () => {};

  // Tag-editor menu shared with FileTree; left-aligned under the badge.
  let tagMenu: SystemTagMenu | undefined;

  // Rulebook pages are half tables — without GFM they render as pipe soup.
  // Query terms light the way they do on the rows.
  let mdPlugins: Plugin[];
  $: mdPlugins = [gfmPlugin(), { rehypePlugin: [rehypeMarkTerms, queryTerms(query)] }];

  // The marked passage, for scrolling it into view.
  let matchEl: HTMLElement | null = null;
  let bodyEl: HTMLElement | null = null;

  // Where the match sits on the scrollbar track, in px from its top.
  // Null when there's no match or nothing to scroll.
  let mark: { top: number; height: number } | null = null;

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
  // Centring once isn't enough: tables, fonts and pane widths can settle
  // after the scroll and slide the match off-centre (seen landing at the
  // bottom edge). So the view follows the match through any resize until
  // the reader takes the scroll themselves.
  let followMatch = false;

  function centreMatch() {
    if (followMatch) matchEl?.scrollIntoView({ block: 'center' });
  }

  function releaseMatch() {
    followMatch = false;
  }

  /** Scroll back to the match and follow it again, as on selection. */
  export function returnToMatch() {
    followMatch = true;
    centreMatch();
  }

  function measureMark() {
    if (!bodyEl || !matchEl || bodyEl.scrollHeight <= bodyEl.clientHeight) {
      mark = null;
      return;
    }
    const scale = bodyEl.clientHeight / bodyEl.scrollHeight;
    const y =
      matchEl.getBoundingClientRect().top -
      bodyEl.getBoundingClientRect().top +
      bodyEl.scrollTop;
    mark = {
      top: y * scale,
      height: Math.max(3, matchEl.offsetHeight * scale),
    };
  }

  function followResizes(node: HTMLElement) {
    const observer = new ResizeObserver(() => {
      centreMatch();
      measureMark();
    });
    observer.observe(node);
    return { destroy: () => observer.disconnect() };
  }

  $: if (result && matchEl) {
    followMatch = true;
    tick().then(() => {
      centreMatch();
      measureMark();
    });
  }
  $: if (!matchEl) mark = null;

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
</script>

<aside class="inspector">
  {#if !result}
    <div class="empty">Select a result to preview.</div>
  {:else}
    {@const span = pageHint(result.page_start, result.page_end)}
    {@const cite = pageCitation(
      result.page_start,
      result.page_end,
      result.page_label_start,
      result.page_label_end
    )}
    {@const segments = result.section_heading ? breadcrumbSegments(result.section_heading) : []}

    <!-- The selected row already carries the gauge and the book line; the
         header keeps what the row can't: the full section path, pinned
         above the body so it stays in view while the match is centred. -->
    <header class="head">
      <div class="head-text">
        <div class="meta">
          <span class="filename" title={result.source}>{bookTitle(result.filename)}</span>
          {#if result.game_system === UNTAGGED_KEY}
            <span class="sysname">untagged</span>
          {:else if result.game_system}
            <button class="sys-btn" on:click={(e) => tagMenu?.toggle(e)} aria-label="Edit game system tags">
              <SystemBadge tag={displaySystem(result.game_system)} />
            </button>
          {/if}
          {#if isPathOrAncestorIn(result.source, hiddenPaths)}
            <span class="badge micro-label" title="This file is hidden in the tree.">hidden</span>
          {/if}
        </div>
        {#if segments.length > 0}
          <div class="breadcrumb" aria-label="Section path">
            <!-- Each separator rides with the segment after it, so a wrap
                 never leaves one hanging at a line end. -->
            {#each segments as segment, idx (idx)}
              <span class="bc-item">
                {#if idx > 0}<span class="bc-sep" aria-hidden="true">›</span>{/if}
                <span class="bc-segment" class:caps={isAllCaps(segment)}>{segment}</span>
              </span>
            {/each}
          </div>
        {/if}
      </div>
      <!-- The printed page leads, as on the row; the physical one stays in
           the tooltip for PDF viewers, which count from the cover. -->
      <button
        type="button"
        class="open-btn"
        on:click={() => onOpenResult(result.source, result.filename, result.page_start)}
        title={span && cite !== span ? `Open PDF at ${span}` : undefined}
      >{cite ? `open ${cite}` : 'open'}</button>
    </header>

    <SystemTagMenu
      bind:this={tagMenu}
      {knownSystems}
      {tags}
      onToggleSystem={toggleSystem}
      onClear={clearSystem}
    />

    <div class="body-frame">
      <!-- Wheel, a scrollbar drag or a key hands the scroll to the reader;
           the listeners only observe, so the body stays a plain region. -->
      <!-- svelte-ignore a11y_no_static_element_interactions -->
      <div
        class="body"
        bind:this={bodyEl}
        use:followResizes
        on:wheel|passive={releaseMatch}
        on:pointerdown={releaseMatch}
        on:keydown={releaseMatch}
      >
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
                title={`Open ${bookTitle(twin.filename)}${twinCite ? ` at ${twinCite}` : ''}`}
                on:click={() => onOpenResult(twin.source, twin.filename, twin.page_start)}
              >
                {bookTitle(twin.filename)}{twinCite ? ` · ${twinCite}` : ''}
              </button>
            {/each}
          </div>
        {/if}

        <div class="snippet" use:followResizes>
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
      {#if mark}
        <!-- The match's place in the section, drawn on the scrollbar track
             the way find-in-page marks are; the thumb already shows where
             the reader is. Clicking it goes back. -->
        <button
          type="button"
          class="match-mark"
          style="top: {mark.top}px; height: {mark.height}px"
          title={`Back to the match${chordHint('results.toMatch')}`}
          aria-label="Back to the match"
          on:click={returnToMatch}
        ></button>
      {/if}
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

  .body-frame {
    position: relative;
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
  }

  .body {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding: 0.7rem 1.1rem 1rem;
  }

  /* Laid over the scrollbar track, the width app.css gives
     ::-webkit-scrollbar. Parchment, as the match's margin rule. */
  .match-mark {
    position: absolute;
    right: 0;
    width: 8px;
    padding: 0;
    border: none;
    border-radius: var(--radius-cell);
    background: var(--text-accent);
    cursor: pointer;
    transition: filter var(--transition-fast);
  }

  .match-mark:hover {
    filter: brightness(1.25);
  }

  .match-mark:focus-visible {
    outline: 1px solid var(--text-accent);
    outline-offset: 1px;
  }

  .head-text {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
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

  /* Tagged files carry the system badge; "untagged" stays plain text —
     no pill, no dropdown trigger beyond what the tree already offers. */
  .sysname {
    flex-shrink: 0;
    font-size: 0.8rem;
    color: var(--text-secondary);
  }

  .sys-btn {
    flex-shrink: 0;
    display: inline-flex;
    padding: 0;
    background: none;
    border: none;
    cursor: pointer;
  }

  .sys-btn:hover :global(.game-system-badge) {
    border-color: var(--text-accent);
  }

  .breadcrumb {
    font-size: 0.78rem;
    color: var(--text-secondary);
    line-height: 1.35;
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    column-gap: 0.3rem;
    row-gap: 0.1rem;
  }

  .bc-item {
    display: flex;
    align-items: baseline;
    gap: 0.3rem;
    min-width: 0;
  }

  .bc-segment {
    word-break: break-word;
  }

  .bc-item:last-child .bc-segment {
    color: var(--text-primary);
  }

  /* Small caps for capitalised headings — see SearchResults.svelte .caps */
  .caps {
    font-variant-caps: all-small-caps;
    letter-spacing: 0.04em;
  }

  /* Path separator — see SearchResults.svelte .bc-sep */
  .bc-sep {
    color: var(--text-tertiary);
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

  /* The unit that actually matched, inside the section around it: a
     margin rule only. A wash tinted everything under it, tables included,
     and blurred where the unit started and stopped. */
  .matched {
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

  /* Prose keeps a reading measure on a wide pane; tables stay free to
     take the width their columns need. */
  .snippet :global(:is(p, ul, ol, blockquote, h1, h2, h3, h4, h5, h6)) {
    max-width: 68ch;
  }

  /* Query terms in the data colour, as on the rows — no fill, no glow. */
  .snippet :global(.hit) {
    color: var(--text-accent);
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

  /* Block (for the horizontal scroll) but sized to the cells, so the
     border hugs the table instead of boxing empty space beside it. */
  .snippet :global(table) {
    display: block;
    width: fit-content;
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

  /* Bracketed text, parchment like the plate controls: opening the book
     is an action on content, not a mode, so not the modal purple. The
     brackets sit a step quieter and light with the label on hover. */
  .open-btn {
    flex-shrink: 0;
    padding: 0.1rem 0;
    background: none;
    border: none;
    color: var(--text-accent);
    font-family: var(--font-body);
    font-size: 0.85rem;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
    cursor: pointer;
    transition: filter var(--transition-fast), transform var(--transition-fast);
  }

  .open-btn::before,
  .open-btn::after {
    color: var(--text-secondary);
    transition: color var(--transition-fast);
  }

  .open-btn::before {
    content: '[';
    margin-right: 0.15rem;
  }

  .open-btn::after {
    content: ']';
    margin-left: 0.15rem;
  }

  .open-btn:hover {
    filter: brightness(1.25);
  }

  .open-btn:hover::before,
  .open-btn:hover::after {
    color: var(--text-accent);
  }

  .open-btn:active {
    transform: scale(0.97);
  }

  .open-btn:focus-visible {
    outline: 1px solid var(--text-accent);
    outline-offset: 2px;
  }
</style>
