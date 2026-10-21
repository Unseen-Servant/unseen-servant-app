<script lang="ts">
  import { tick } from 'svelte';
  import Markdown, { type Plugin } from 'svelte-exmarkdown';
  import { gfmPlugin } from 'svelte-exmarkdown/gfm';
  import type { SearchResultItem } from './types';
  import { bookTitle, pageCitation } from './pdfUrl';
  import { findMatchedRange, splitAround, type MatchedParts } from './matchedSpan';
  import { queryTerms, rehypeMarkTerms } from './snippetHits';

  // No header of its own: the selected row names the book and system, and
  // the InspectorPlate above the pane carries the section path and [open].
  export let result: SearchResultItem | null = null;
  export let query: string = '';
  export let onOpenResult: (source: string, filename: string, page?: number | null) => void = () => {};

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

  // Where each query hit sits on the track, in px from its top. Empty
  // when there's nothing to scroll.
  let hitTicks: number[] = [];

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

  function measureLane() {
    if (!bodyEl || bodyEl.scrollHeight <= bodyEl.clientHeight) {
      mark = null;
      hitTicks = [];
      return;
    }
    const scale = bodyEl.clientHeight / bodyEl.scrollHeight;
    const origin = bodyEl.getBoundingClientRect().top - bodyEl.scrollTop;
    const trackY = (el: Element) => (el.getBoundingClientRect().top - origin) * scale;
    mark = matchEl
      ? { top: trackY(matchEl), height: Math.max(3, matchEl.offsetHeight * scale) }
      : null;
    // A tick is 2px; hits closer than that on the track would stack into
    // a smear, so one tick stands for them all.
    const ticks: number[] = [];
    for (const el of bodyEl.querySelectorAll('.hit')) {
      const y = Math.round(trackY(el));
      if (ticks.length === 0 || y - ticks[ticks.length - 1] >= 3) ticks.push(y);
    }
    hitTicks = ticks;
  }

  function followResizes(node: HTMLElement) {
    const observer = new ResizeObserver(() => {
      centreMatch();
      measureLane();
    });
    observer.observe(node);
    return { destroy: () => observer.disconnect() };
  }

  $: if (result && matchEl) {
    followMatch = true;
    tick().then(() => {
      centreMatch();
      measureLane();
    });
  }
  // Hits move with the result, and with the query's terms under it.
  $: if (result && mdPlugins) tick().then(measureLane);
</script>

<aside class="inspector">
  {#if !result}
    <div class="empty">Select a result to preview.</div>
  {:else}
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
      {#if hitTicks.length > 0}
        <!-- Every query hit on the scrollbar track, the way find-in-page
             marks them. Pointer-transparent: the thumb under them drags. -->
        <div class="hit-ticks" aria-hidden="true">
          {#each hitTicks as y (y)}
            <span class="hit-tick" style="top: {y}px"></span>
          {/each}
        </div>
      {/if}
      {#if mark}
        <!-- The match's place in the section, an edge down the track's
             inner side; the thumb already shows where the reader is.
             Clicking it goes back. -->
        <button
          type="button"
          class="match-mark"
          style="top: {mark.top}px; height: {mark.height}px"
          title="Back to the match"
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
    /* Vellum: warmer and lighter than the list's ground, and not the
       plate's grey, so the text reads as its own surface under the plate.
       Tables, code and the hit lane recess to --bg-app. No left border:
       the list pane's right border is the one seam. */
    background: var(--bg-vellum);
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

  /* The hit lane: the scrollbar widened from app.css's 8px to 14px and
     recessed into --bg-app off the vellum, so it reads as its own strip —
     an overview of the section. The ticks and the match edge below are
     laid over it at that width. */
  .body::-webkit-scrollbar {
    width: 14px;
  }

  .body::-webkit-scrollbar-track {
    background: var(--bg-app);
    border-left: 1px solid var(--border-subtle);
  }

  /* Inset 2px so the lane's edge shows around it. No hover step: this
     rule outranks the global one, which darkens the thumb. */
  .body::-webkit-scrollbar-thumb {
    background: var(--bg-category);
    background-clip: padding-box;
    border: 2px solid transparent;
    border-radius: var(--radius-md);
  }

  .hit-ticks {
    position: absolute;
    top: 0;
    right: 0;
    bottom: 0;
    width: 14px;
    pointer-events: none;
  }

  /* Parchment, as the hits in the text. Clear of the match edge. */
  .hit-tick {
    position: absolute;
    left: 5px;
    right: 2px;
    height: 2px;
    border-radius: var(--radius-cell);
    background: var(--text-accent);
  }

  /* Parchment, as the match's margin rule, on the lane's inner edge. A
     transparent border takes the target out to where the ticks start;
     on hover it widens to 8px, so it's easy to hit once found. */
  .match-mark {
    position: absolute;
    left: calc(100% - 14px);
    width: 5px;
    padding: 0;
    border: none;
    border-right: 2px solid transparent;
    background: var(--text-accent);
    background-clip: padding-box;
    border-radius: var(--radius-cell);
    cursor: pointer;
    transition: filter var(--transition-fast), width var(--transition-fast);
  }

  .match-mark:hover {
    width: 8px;
    border-right-width: 0;
    filter: brightness(1.25);
  }

  .match-mark:focus-visible {
    outline: 1px solid var(--text-accent);
    outline-offset: 1px;
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
</style>
