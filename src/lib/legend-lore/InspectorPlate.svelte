<script lang="ts">
  import type { SearchResultItem } from './types';
  import { bookTitle, pageCitation, pageHint } from './pdfUrl';
  import { breadcrumbSegments, isAllCaps } from './breadcrumb';
  import { displaySystem, UNTAGGED_KEY } from './searchScope';
  import { SHIELD } from '../ui/iconPaths';
  import { m } from '../paraglide/messages';

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

<!-- The inspector's plate, level with the scope bar across the split seam:
     the source (book and system, in the row's voice), the full section
     path, and the one action — so the text below gets the pane's whole
     height. -->
<div class="inspector-plate nameplate">
  {#if result}
    <!-- One baseline for the source and the path: centring each in its
         own box let Crimson and Almendra drift a pixel apart. The plate
         centres the row as a whole. -->
    <div class="line">
    <!-- Capped, so a long filename can't crowd the path; the book takes
         the ellipsis and the system stays whole. -->
    <span class="source" title={result.source}>
      <span class="source-book">{bookTitle(result.filename)}</span>
      {#if result.game_system === UNTAGGED_KEY}
        <span class="source-system">{displaySystem(result.game_system)}</span>
      {:else if result.game_system}
        <span class="source-system">
          <svg class="source-shield" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round" aria-hidden="true">
            <path d={SHIELD}/>
          </svg>
          {result.game_system}
        </span>
      {/if}
    </span>
    <span class="rule" aria-hidden="true"></span>
    <nav class="path" aria-label={m.lore_plate_section_path()} title={segments.join(' › ') || undefined}>
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
    </div>
    <!-- The printed page leads, as on the row; the physical one stays in
         the tooltip for PDF viewers, which count from the cover. -->
    <button
      type="button"
      class="plate-btn"
      on:click={() => result && onOpenResult(result.source, result.filename, result.page_start)}
      title={span && cite !== span ? m.lore_plate_open_pdf_at({ span }) : undefined}
    >{cite ? m.lore_plate_open_at({ cite }) : m.lore_plate_open()}</button>
  {/if}
</div>

<style>
  /* Padded to the inspector body's inset, so the path starts over the
     text it names. No left border: the list column's is the one seam. */
  .inspector-plate {
    flex: 1;
    min-width: 0;
    display: flex;
    align-items: center;
    gap: 0.6rem;
    padding: 0.3rem 0.9rem 0.3rem 1.1rem;
    font-family: var(--font-body);
  }

  /* The book and system as the result row sets them: one secondary
     voice at 0.75rem. */
  .line {
    flex: 1;
    min-width: 0;
    display: flex;
    align-items: baseline;
    gap: 0.6rem;
  }

  .source {
    flex: 0 0 auto;
    max-width: 10rem;
    display: flex;
    align-items: baseline;
    gap: 0.4rem;
    overflow: hidden;
    white-space: nowrap;
    font-size: 0.75rem;
    color: var(--text-secondary);
  }

  .source-book {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .source-system {
    flex-shrink: 0;
  }

  /* On the text's baseline, a pixel down — SystemBadge's recipe; centring
     in the line box set it low against Crimson's high-riding glyphs. */
  .source-shield {
    width: 9px;
    height: 9px;
    margin-right: 0.25rem;
    vertical-align: -1px;
  }

  /* The scope bar's master rule, between the source and the path. */
  .rule {
    flex-shrink: 0;
    align-self: center;
    width: 1px;
    height: 12px;
    background: var(--bg-category);
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
    font-size: 0.8rem;
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
