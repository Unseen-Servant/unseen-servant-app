<script lang="ts">
  // An image on the session board (#407), as Obsidian Canvas shows a
  // picture dropped on it: the image alone, fitted to the card, which moves,
  // resizes and connects like any other. One the webview can't load (gone
  // meanwhile, or outside the campaigns folder) shows its name, dashed.
  import { Handle, NodeResizer, Position } from '@xyflow/svelte';
  import { getContext } from 'svelte';
  import { CARD_ACTIONS, type CardActions, type CardData } from './board';
  import { IMAGE_SOURCE, type ImageSourceStore } from './embeds';

  export let data: CardData;
  export let selected: boolean = false;

  const actions = getContext<CardActions>(CARD_ACTIONS);
  const images = getContext<ImageSourceStore>(IMAGE_SOURCE);
  const SIDES = [
    ['top', Position.Top],
    ['right', Position.Right],
    ['bottom', Position.Bottom],
    ['left', Position.Left],
  ] as const;

  $: card = data.card;
  $: name = card.path?.split('/').pop() ?? card.text;
  $: src = card.path ? $images.file(card.path) : null;
  let failed = false;
  $: src, (failed = false);
</script>

<NodeResizer
  minWidth={40}
  minHeight={40}
  isVisible={selected}
  onResizeEnd={(_, frame) => actions.frame(card, frame)}
/>
{#each SIDES as [id, position] (id)}
  <Handle type="source" {id} {position} />
{/each}
{#if data.linking}
  <Handle type="source" id="whole" position={Position.Top} class="whole" />
{/if}
<figure class="card" class:missing={!src || failed} title={name}>
  {#if src && !failed}
    <img {src} alt={name} draggable="false" on:error={() => (failed = true)} />
  {:else}
    <figcaption>{name}</figcaption>
  {/if}
</figure>

<style>
  .card {
    width: 100%;
    height: 100%;
    margin: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--bg-vellum);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-dropdown);
    overflow: hidden;
  }

  img {
    width: 100%;
    height: 100%;
    object-fit: contain;
    display: block;
  }

  /* Names an image the webview can't show: the dashed rule of a missing
     note's card. */
  .card.missing {
    border: var(--outline-drop);
    background: var(--bg-container);
  }

  figcaption {
    padding: 0.5rem;
    font-size: 0.88rem;
    color: var(--text-secondary);
    word-break: break-word;
    text-align: center;
  }
</style>
