<script lang="ts">
  import type { SearchResultItem } from './types';
  import { bookTitle, pageCitation, pageHint } from './pdfUrl';
  import { breadcrumbSegments, isAllCaps } from './breadcrumb';

  export let result: SearchResultItem | null = null;
  export let onOpenResult: (source: string, filename: string, page?: number | null) => void = () => {};

  $: segments = result?.section_heading ? breadcrumbSegments(result.section_heading) : [];
  // A section-less hit is named by its book, as on its row.
  $: title = segments.length > 0 ? segments[segments.length - 1] : result ? bookTitle(result.filename) : '';
  $: ancestors = segments.slice(0, -1);
  $: span = result ? pageHint(result.page_start, result.page_end) : null;
  $: cite = result
    ? pageCitation(result.page_start, result.page_end, result.page_label_start, result.page_label_end)
    : null;
</script>

<!-- The inspector's plate, level with the scope bar across the split seam.
     The selected row already names the book and its system; the plate
     keeps what the row can't — the full section path — and the one action,
     so the text below gets the pane's whole height. -->
<div class="inspector-plate nameplate">
  {#if result}
    <nav class="path" aria-label="Section path" title={segments.join(' › ') || undefined}>
      <!-- One line, and the title keeps its full width: only the
           ancestors give way, each taking its own ellipsis. A title wider
           than the plate fills it with its own and the ancestors drop out.
           No shrink ratios — WebKit didn't honour them. -->
      {#if ancestors.length > 0}
        <span class="path-head">
          {#each ancestors as segment, idx (idx)}
            <span class="segment">{segment}</span>
            <span class="sep" aria-hidden="true">›</span>
          {/each}
        </span>
      {/if}
      <h2 class="title" class:caps={segments.length > 0 && isAllCaps(title)}>{title}</h2>
    </nav>
    <!-- The printed page leads, as on the row; the physical one stays in
         the tooltip for PDF viewers, which count from the cover. -->
    <button
      type="button"
      class="plate-btn"
      on:click={() => result && onOpenResult(result.source, result.filename, result.page_start)}
      title={span && cite !== span ? `Open PDF at ${span}` : undefined}
    >{cite ? `open ${cite}` : 'open'}</button>
  {/if}
</div>

<style>
  /* Padded to the inspector body's inset, so the path starts over the
     text it names. */
  .inspector-plate {
    flex: 1;
    min-width: 0;
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.3rem 0.9rem 0.3rem 1.1rem;
    border-left: 1px solid var(--border-subtle);
    font-family: var(--font-body);
  }

  .path {
    flex: 1;
    min-width: 0;
    display: flex;
    align-items: baseline;
    overflow: hidden;
    white-space: nowrap;
  }

  /* Every ancestor in small caps, in the plate's label voice — not only
     the ones the book set in capitals, which left the path half shouting
     and half not. The title keeps the row's rule. */
  .path-head {
    display: flex;
    align-items: baseline;
    flex: 0 1 auto;
    min-width: 0;
    overflow: hidden;
    font-size: 0.75rem;
    font-variant-caps: all-small-caps;
    letter-spacing: 0.04em;
    color: var(--text-secondary);
  }

  .segment {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  /* Path separator: a single guillemet in the body serif. */
  .sep {
    flex-shrink: 0;
    margin: 0 0.3rem;
    color: var(--text-tertiary);
    -webkit-user-select: none;
    user-select: none;
  }

  /* The leaf, a heading: primary, not the data parchment. */
  .title {
    flex: 0 0 auto;
    max-width: 100%;
    margin: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    font-family: var(--font-heading);
    font-size: 0.875rem;
    font-weight: 400;
    color: var(--text-primary);
  }

  /* Small caps for capitalised headings — see SearchResults.svelte .caps */
  .caps {
    font-variant-caps: all-small-caps;
    letter-spacing: 0.04em;
  }

  .plate-btn {
    flex-shrink: 0;
    white-space: nowrap;
    font-variant-numeric: tabular-nums;
  }
</style>
