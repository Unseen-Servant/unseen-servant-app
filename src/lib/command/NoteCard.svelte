<script lang="ts">
  // A card on the session board (design §5.2): a note read on vellum, sized
  // by the GM to show as much of it as the table needs. Its play key puts
  // the note in the live set or takes it out, as Legend Lore's key plays a
  // collection; the card itself lights in parchment while live.
  import Markdown from 'svelte-exmarkdown';
  import { gfmPlugin } from 'svelte-exmarkdown/gfm';
  import { Handle, NodeResizer, Position } from '@xyflow/svelte';
  import { openUrl } from '@tauri-apps/plugin-opener';
  import { BOOK, PLAY } from '../ui/iconPaths';
  import { getContext } from 'svelte';
  import { CARD_ACTIONS, NOTE_HREF, linkify, type CardActions, type CardData } from './board';

  export let data: CardData;
  export let selected: boolean = false;

  const actions = getContext<CardActions>(CARD_ACTIONS);
  const plugins = [gfmPlugin()];
  const SIDES = [
    ['top', Position.Top],
    ['right', Position.Right],
    ['bottom', Position.Bottom],
    ['left', Position.Left],
  ] as const;

  $: card = data.card;
  $: missing = card.kind === 'note' && card.path === null;
  $: title = data.name || card.text.split('/').pop()?.replace(/\.md$/i, '') || 'Untitled';

  /** Links in the body: a `[[link]]` opens its note, a web link the browser. */
  function click(e: MouseEvent) {
    const a = (e.target as HTMLElement).closest('a');
    if (!a) return;
    e.preventDefault();
    const href = a.getAttribute('href') ?? '';
    if (href.startsWith(NOTE_HREF)) actions.follow(decodeURIComponent(href.slice(NOTE_HREF.length)));
    else if (/^https?:/i.test(href)) void openUrl(href);
  }
</script>

<NodeResizer
  minWidth={140}
  minHeight={56}
  isVisible={selected}
  onResizeEnd={(_, frame) => actions.frame(card, frame)}
/>
{#each SIDES as [id, position] (id)}
  <Handle type="source" {id} {position} />
{/each}

<article
  class="card"
  class:live={data.live}
  class:spent={!!data.spent}
  class:missing
  on:dblclick={() => !missing && actions.edit(card)}
>
  <header class="card-head">
    {#if !missing}
      <button
        type="button"
        class="play-key nodrag"
        class:playing={data.live}
        aria-pressed={data.live}
        title={data.live ? `Take ${title} out of play` : `Play ${title}`}
        on:click|stopPropagation={() => actions.launch(card, !data.live)}
      >
        {#if data.live}
          <span class="stop-mark" aria-hidden="true"></span>
        {:else}
          <svg viewBox="0 0 640 640" fill="currentColor" aria-hidden="true"><path d={PLAY} /></svg>
        {/if}
      </button>
    {/if}
    <span class="card-name" {title}>{title}</span>
    {#if data.track}<span class="card-track">{data.track}</span>{/if}
    {#if data.source}
      {@const source = data.source}
      <!-- Sent from Legend Lore: open the book at its page, as Legend Lore
           opens a hit. -->
      <button
        type="button"
        class="source-key nodrag"
        title="Open the source at its page"
        aria-label="Open the source"
        on:click|stopPropagation={() => void openUrl(source).catch(() => {})}
      >
        <svg viewBox="0 0 640 640" fill="currentColor" aria-hidden="true"><path d={BOOK} /></svg>
      </button>
    {/if}
    {#if !missing}
      <input
        type="checkbox"
        class="app-checkbox nodrag"
        checked={!!data.spent}
        title={data.spent ? `Spent ${data.spent}` : 'Mark spent'}
        on:change={(e) => actions.spend(card, e.currentTarget.checked)}
      />
    {/if}
  </header>
  <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
  <div class="card-body nowheel" on:click={click}>
    {#if missing}
      <p class="note-missing">Nothing is at {card.text} any more.</p>
    {:else if data.body !== null}
      <Markdown md={linkify(data.body)} {plugins} />
    {/if}
  </div>
</article>

<style>
  .card {
    width: 100%;
    height: 100%;
    display: flex;
    flex-direction: column;
    min-height: 0;
    background: var(--bg-vellum);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-dropdown);
    overflow: hidden;
    transition: border-color var(--transition-fast), opacity var(--transition-fast);
  }

  /* Live: content in play, so parchment and its glow. */
  .card.live {
    border-color: var(--text-accent);
    filter: var(--glow-accent);
  }

  /* Names a note that isn't there: the dashed rule of a missing link. */
  .card.missing {
    border: var(--outline-drop);
    background: var(--bg-container);
  }

  .card.spent .card-name,
  .card.spent .card-body {
    opacity: var(--opacity-out-of-scope);
  }

  .card.spent:hover .card-name,
  .card.spent:hover .card-body {
    opacity: var(--opacity-out-of-scope-hover);
  }

  .card-head {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.35rem 0.5rem 0.3rem;
    border-bottom: 1px solid var(--border-subtle);
  }

  .card-name {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-family: var(--font-heading);
    font-size: 1rem;
    color: var(--text-primary);
  }

  .card-track {
    flex-shrink: 0;
    font-size: 0.72rem;
    color: var(--text-tertiary);
  }

  /* Legend Lore's transport key (CollectionsPanel .tr-btn): ▶ at rest, a
     stop square lit purple while the note plays. */
  .play-key {
    flex-shrink: 0;
    width: 18px;
    height: 18px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0;
    background: transparent;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    color: var(--text-tertiary);
    cursor: pointer;
    transition: all var(--transition-fast);
  }

  .play-key svg {
    width: 9px;
    height: 9px;
    display: block;
  }

  .stop-mark {
    width: 6px;
    height: 6px;
    background: currentColor;
  }

  .play-key:hover {
    color: var(--text-secondary);
    border-color: var(--text-secondary);
  }

  .play-key:active {
    transform: scale(0.97);
  }

  .play-key.playing {
    color: var(--text-active);
    border-color: var(--text-active);
    background: color-mix(in srgb, var(--text-active) 15%, transparent);
    filter: var(--glow-active);
  }

  .source-key {
    flex-shrink: 0;
    display: inline-flex;
    align-items: center;
    padding: 0;
    background: none;
    border: none;
    color: var(--text-tertiary);
    cursor: pointer;
    transition: color var(--transition-fast);
  }

  .source-key svg {
    width: 11px;
    height: 11px;
    display: block;
  }

  .source-key:hover {
    color: var(--text-accent);
  }

  .source-key:active {
    transform: scale(0.97);
  }

  .card-body {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding: 0.4rem 0.6rem 0.5rem;
    font-size: 0.88rem;
    line-height: 1.4;
    color: var(--text-primary);
    word-break: break-word;
    cursor: default;
  }

  .note-missing {
    margin: 0;
    color: var(--text-secondary);
  }

  .card-body :global(> *:first-child) { margin-top: 0; }
  .card-body :global(> *:last-child) { margin-bottom: 0; }
  .card-body :global(p) { margin: 0.35em 0; }
  .card-body :global(:is(h1, h2, h3, h4, h5, h6)) {
    margin: 0.5em 0 0.2em;
    font-family: var(--font-heading);
    font-weight: 400;
    font-size: 1em;
    color: var(--text-secondary);
  }
  .card-body :global(:is(ul, ol)) { margin: 0.35em 0; padding-left: 1.2em; }
  .card-body :global(li) { margin: 0.1em 0; }
  .card-body :global(a) { color: var(--text-accent); cursor: pointer; }
  .card-body :global(blockquote) {
    margin: 0.4em 0;
    padding-left: 0.6em;
    border-left: 2px solid var(--border-subtle);
    color: var(--text-secondary);
  }
  .card-body :global(code) {
    font-family: var(--font-mono);
    font-size: 0.88em;
  }
  .card-body :global(table) {
    border-collapse: collapse;
    font-size: 0.9em;
  }
  .card-body :global(:is(th, td)) {
    padding: 0.15em 0.4em;
    border: 1px solid var(--border-subtle);
  }
</style>
