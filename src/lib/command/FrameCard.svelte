<script lang="ts">
  // The board's other cards, as Obsidian Canvas makes them: a text card's
  // Markdown, a link's address, a group's labelled frame. Command keeps and
  // moves them; it doesn't make them.
  import Markdown from 'svelte-exmarkdown';
  import { gfmPlugin } from 'svelte-exmarkdown/gfm';
  import { Handle, NodeResizer, Position } from '@xyflow/svelte';
  import { getContext } from 'svelte';
  import { CARD_ACTIONS, linkify, type CardActions, type CardData } from './board';

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
</script>

<NodeResizer
  minWidth={80}
  minHeight={40}
  isVisible={selected}
  onResizeEnd={(_, frame) => actions.frame(card, frame)}
/>
{#if card.kind !== 'group'}
  {#each SIDES as [id, position] (id)}
    <Handle type="source" {id} {position} />
  {/each}
{/if}

<div class="frame {card.kind}">
  {#if card.kind === 'group'}
    {#if card.text}<span class="ledger-label group-label">{card.text}</span>{/if}
  {:else if card.kind === 'text'}
    <div class="text nowheel"><Markdown md={linkify(card.text)} {plugins} /></div>
  {:else if card.kind === 'link'}
    <span class="url">{card.text}</span>
  {/if}
</div>

<style>
  .frame {
    width: 100%;
    height: 100%;
    border-radius: var(--radius-md);
    overflow: hidden;
  }

  .frame.text,
  .frame.link,
  .frame.other {
    background: var(--bg-container);
    border: 1px solid var(--border-subtle);
  }

  /* A group sits behind its cards: an outline and its label, no fill. */
  .frame.group {
    border: 1px solid var(--border-subtle);
    background: color-mix(in srgb, var(--bg-container) 40%, transparent);
  }

  .group-label {
    display: block;
    padding: 0.35rem 0.6rem;
  }

  .text {
    height: 100%;
    overflow-y: auto;
    padding: 0.45rem 0.6rem;
    font-size: 0.88rem;
    line-height: 1.4;
  }

  .text :global(> *:first-child) { margin-top: 0; }
  .text :global(> *:last-child) { margin-bottom: 0; }
  .text :global(a) { color: var(--text-accent); }

  .url {
    display: block;
    padding: 0.45rem 0.6rem;
    font-family: var(--font-mono);
    font-size: 0.75rem;
    color: var(--text-accent);
    word-break: break-all;
  }
</style>
