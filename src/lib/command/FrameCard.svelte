<script lang="ts">
  // The board's other cards, as Obsidian Canvas makes them and the board's
  // toolbar does: a text card's Markdown (a sticky when it has a colour), a
  // link's address, a group's labelled frame. A double-click edits a text
  // card's text or a frame's name in place (board toolbar design §3.4); a
  // text card emptied there leaves the board.
  import Markdown from 'svelte-exmarkdown';
  import { gfmPlugin } from 'svelte-exmarkdown/gfm';
  import { Handle, NodeResizer, Position } from '@xyflow/svelte';
  import { getContext } from 'svelte';
  import RenameField from '../ui/RenameField.svelte';
  import { CARD_ACTIONS, linkify, paint, type CardActions, type CardData } from './board';
  import { m } from '../paraglide/messages';

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
  $: tint = paint(card.color);

  function focus(field: HTMLTextAreaElement) {
    field.focus();
    field.setSelectionRange(field.value.length, field.value.length);
  }

  /** A click away or Escape keeps the text, as Miro's do; emptied, the card goes. */
  function finishText(field: HTMLTextAreaElement) {
    const text = field.value;
    if (!text.trim()) {
      actions.finish(card.id);
      actions.remove(card.id);
    } else {
      actions.finish(card.id, text === card.text ? undefined : { text });
    }
  }

  function textKey(e: KeyboardEvent & { currentTarget: HTMLTextAreaElement }) {
    if (e.key === 'Escape' && !e.isComposing) {
      e.preventDefault();
      e.currentTarget.blur();
    }
  }
</script>

<NodeResizer
  minWidth={80}
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

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
  class="frame {card.kind}"
  class:sticky={card.kind === 'text' && !!tint}
  class:tinted={card.kind === 'group' && !!tint}
  style:--tint={tint}
  on:dblclick={() => card.kind === 'text' && actions.begin(card.id)}
>
  {#if card.kind === 'group'}
    {#if data.editing}
      <div class="group-label nodrag">
        <RenameField
          value={card.text}
          label={m.command_frame_name()}
          placeholder={m.command_frame_name_placeholder()}
          onCommit={(label) => actions.finish(card.id, { label })}
          onCancel={() => actions.finish(card.id)}
        />
      </div>
    {:else}
      <!-- svelte-ignore a11y_no_static_element_interactions -->
      <span class="ledger-label group-label" on:dblclick={() => actions.begin(card.id)}>{card.text}</span>
    {/if}
  {:else if card.kind === 'text'}
    {#if data.editing}
      <textarea
        class="text-field nodrag nowheel"
        value={card.text}
        aria-label={m.command_frame_text()}
        spellcheck="false"
        use:focus
        on:keydown={textKey}
        on:blur={(e) => finishText(e.currentTarget)}
      ></textarea>
    {:else}
      <div class="text nowheel"><Markdown md={linkify(card.text)} {plugins} /></div>
    {/if}
  {:else if card.kind === 'link'}
    <span class="url">{card.text}</span>
  {/if}
</div>

<style>
  .frame {
    width: 100%;
    height: 100%;
    box-sizing: border-box;
    border-radius: var(--radius-md);
    overflow: hidden;
  }

  .frame.link,
  .frame.other {
    background: var(--bg-container);
    border: 1px solid var(--border-subtle);
  }

  /* Text sits on the board's paper, unboxed, with a rule only while
     selected (Board); a sticky is a pigment wash. */
  .frame.text {
    border: 1px solid transparent;
  }

  .frame.text.sticky {
    background: color-mix(in srgb, var(--tint) 28%, var(--bg-container));
    border-color: color-mix(in srgb, var(--tint) 45%, var(--border-subtle));
  }

  /* A group sits behind its cards: an outline and its label, no fill. */
  .frame.group {
    border: 1px solid var(--border-subtle);
    background: color-mix(in srgb, var(--bg-container) 40%, transparent);
  }

  .frame.group.tinted {
    background: color-mix(in srgb, var(--tint) 10%, transparent);
    border-color: color-mix(in srgb, var(--tint) 45%, var(--border-subtle));
  }

  /* A row's height whether named or not, so an unnamed frame's band
     still takes the double-click that names it. */
  .group-label {
    display: block;
    box-sizing: border-box;
    min-height: 1.65rem;
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

  /* The text as typed, in the card's own place and voice. */
  .text-field {
    width: 100%;
    height: 100%;
    box-sizing: border-box;
    display: block;
    padding: 0.45rem 0.6rem;
    resize: none;
    background: transparent;
    border: none;
    outline: none;
    font-family: var(--font-body);
    font-size: 0.88rem;
    line-height: 1.4;
    color: var(--text-primary);
  }

  .url {
    display: block;
    padding: 0.45rem 0.6rem;
    font-family: var(--font-mono);
    font-size: 0.75rem;
    color: var(--text-accent);
    word-break: break-all;
  }
</style>
