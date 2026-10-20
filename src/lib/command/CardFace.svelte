<script lang="ts">
  // A note card's face (design §5.2): its note read on vellum, under a head
  // that reads as a row. The board's cards wear it (NoteCard) and so does
  // the card tray's hand (CardTray). Its play key puts the note in the live
  // set or takes it out, as Legend Lore's key plays a collection; on the
  // board the card itself lights in parchment while live.
  import Markdown from 'svelte-exmarkdown';
  import { gfmPlugin } from 'svelte-exmarkdown/gfm';
  import { openUrl } from '@tauri-apps/plugin-opener';
  import { BOOK, PLAY } from '../ui/iconPaths';
  import SpendKey from './SpendKey.svelte';
  import { getContext } from 'svelte';
  import type { Plugin } from 'svelte-exmarkdown';
  import { CARD_ACTIONS, NOTE_HREF, linkify, type CardActions, type CardData } from './board';
  import { IMAGE_SOURCE, embedImages, rehypeEmbeds, type ImageSourceStore } from './embeds';

  export let data: CardData;
  /** In the card tray, where every card is live: it doesn't light, and the
   *  outline is the board card's. */
  export let held = false;

  const actions = getContext<CardActions>(CARD_ACTIONS);
  const images = getContext<ImageSourceStore>(IMAGE_SOURCE);

  $: card = data.card;
  let plugins: Plugin[];
  $: plugins = [gfmPlugin(), { rehypePlugin: [rehypeEmbeds, $images, card.path] }];
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

<article
  class="card"
  data-path={missing ? null : card.path}
  class:live={data.live && !held}
  class:outlined={data.outlined && !held}
  class:spent={!!data.spent}
  class:missing
  on:dblclick={() => !missing && actions.edit(card)}
>
  <!-- The title first; then its track, and its keys at the end, as a
       row's transport sits at its end: play, then spent. -->
  <header class="card-head" class:pigmented={!!data.pigment} style:--pigment={data.pigment}>
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
      <SpendKey spent={data.spent} name={title} onToggle={() => actions.spend(card, !data.spent)} />
    {/if}
  </header>
  <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
  <div class="card-body nowheel" on:click={click}>
    {#if missing}
      <p class="note-missing">Nothing is at {card.text} any more.</p>
    {:else if data.body !== null}
      <Markdown md={linkify(embedImages(data.body))} {plugins} />
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

  /* Its card in the tray is pointed at: a ring clear of the card, apart
     from the live rule it may already wear. */
  .card.outlined {
    outline: 1px solid var(--text-accent);
    outline-offset: 4px;
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

  /* The track's pigment fills the head, as it fills the track's plate in
     Prep (TrackGrid .nameplate.pigmented), in ink, bold as there. */
  .card-head.pigmented {
    background: var(--pigment);
    --key-ground: var(--bg-container);
  }

  /* Its keys keep the plain head's ground, as a pigmented plate's count
     badge does (TrackGrid .nameplate.pigmented .count), so the pigment
     doesn't show through their wells. */
  .card-head.pigmented .play-key {
    background: var(--key-ground);
  }

  .card-head.pigmented .play-key.playing {
    background: color-mix(in srgb, var(--text-active) 15%, var(--bg-container));
  }

  .card-head.pigmented .card-name {
    color: var(--text-inverse);
    font-weight: 700;
  }

  .card-head.pigmented .source-key {
    color: color-mix(in srgb, var(--text-inverse) 70%, transparent);
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

  /* The track in a well like the keys beside it, on their ground, bold:
     a plate's label set into the head. */
  .card-track {
    flex-shrink: 0;
    display: inline-flex;
    align-items: center;
    height: 18px;
    padding: 0 0.35rem;
    background: var(--key-ground, transparent);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    font-size: 0.72rem;
    font-weight: 700;
    line-height: 1;
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
  /* An embedded image, no wider than the card (#407). */
  .card-body :global(img) { max-width: 100%; height: auto; }
  /* An embed naming nothing: its name, dashed as a missing link is. */
  .card-body :global(.embed-missing) {
    color: var(--text-secondary);
    text-decoration: underline dashed;
    text-decoration-color: var(--text-accent);
    text-underline-offset: 3px;
  }
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
