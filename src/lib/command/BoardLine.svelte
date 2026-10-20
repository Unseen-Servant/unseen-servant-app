<script lang="ts">
  // A line on the board: Svelte Flow's curve, in its colour, with its
  // arrowheads and its label drawn here so a double-click names it in
  // place (board toolbar design §3.4). Enter or a click away keeps the
  // name, Escape backs out, and an emptied name takes the label off. The
  // selected line wears the selection bar over its middle (§3.3).
  import { BaseEdge, EdgeLabel, EdgeToolbar, getBezierPath, type Position } from '@xyflow/svelte';
  import { getContext } from 'svelte';
  import type { Readable } from 'svelte/store';
  import BoardBar from './BoardBar.svelte';
  import { BAR_LINE, CARD_ACTIONS, arrowhead, paint, type CardActions } from './board';
  import type { Side } from './types';

  export let id: string;
  export let sourceX: number;
  export let sourceY: number;
  export let targetX: number;
  export let targetY: number;
  export let sourcePosition: Position;
  export let targetPosition: Position;
  /** The line's label, colour and ends, and whether it's being named
   *  (Board). */
  export let data: Record<string, unknown> | undefined = undefined;
  export let interactionWidth: number | undefined = undefined;

  $: label = typeof data?.label === 'string' ? data.label : null;
  $: editing = data?.editing === true;
  $: color = paint(typeof data?.color === 'string' ? data.color : null);
  $: ends = { fromEnd: data?.fromEnd === 'arrow' ? 'arrow' : 'none', toEnd: data?.toEnd === 'arrow' ? 'arrow' : 'none' } as const;
  /** A pigment takes the place of the line's ink; selected, it wears the
   *  accent as any line does. */
  $: ink = color ? `--xy-edge-stroke: ${color}` : undefined;

  const actions = getContext<CardActions>(CARD_ACTIONS);
  const barLine = getContext<Readable<string | null>>(BAR_LINE);

  let path = '';
  let labelX = 0;
  let labelY = 0;
  $: [path, labelX, labelY] = getBezierPath({ sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition });

  let cancelled = false;

  function focus(input: HTMLInputElement) {
    cancelled = false;
    // Once EdgeLabel's portal has moved the label into place: moving a
    // focused field drops its focus.
    requestAnimationFrame(() => {
      input.focus();
      input.select();
    });
  }

  function finish(input: HTMLInputElement) {
    const name = input.value.trim();
    if (cancelled || name === (label ?? '')) actions.finish(id);
    else actions.finish(id, { label: name || null });
  }

  function key(e: KeyboardEvent & { currentTarget: HTMLInputElement }) {
    if (e.isComposing) return;
    if (e.key === 'Escape') cancelled = true;
    if (e.key === 'Enter' || e.key === 'Escape') {
      e.preventDefault();
      e.currentTarget.blur();
    }
  }
</script>

<BaseEdge {id} {path} {interactionWidth} style={ink} />
{#if ends.toEnd === 'arrow'}
  <path class="arrowhead" d={arrowhead(targetX, targetY, targetPosition as Side)} style={ink} />
{/if}
{#if ends.fromEnd === 'arrow'}
  <path class="arrowhead" d={arrowhead(sourceX, sourceY, sourcePosition as Side)} style={ink} />
{/if}
{#if $barLine === id && !editing}
  <EdgeToolbar x={labelX} y={labelY} alignY="bottom" isVisible>
    <div class="lift">
      <BoardBar
        {color}
        onColor={(c) => actions.set([id], { color: c })}
        {ends}
        onEnds={(e) => actions.set([id], e)}
        onLabel={() => actions.begin(id)}
      />
    </div>
  </EdgeToolbar>
{/if}
{#if editing}
  <EdgeLabel x={labelX} y={labelY} class="nodrag nopan">
    <input
      class="line-name"
      value={label ?? ''}
      placeholder="Label…"
      aria-label="The line's label"
      spellcheck="false"
      use:focus
      on:keydown={key}
      on:blur={(e) => finish(e.currentTarget)}
    />
  </EdgeLabel>
{:else if label}
  <EdgeLabel x={labelX} y={labelY} selectEdgeOnClick ondblclick={() => actions.begin(id)}>{label}</EdgeLabel>
{/if}

<style>
  .arrowhead {
    fill: var(--xy-edge-stroke);
  }

  :global(.svelte-flow__edge.selected) .arrowhead {
    fill: var(--xy-edge-stroke-selected);
  }

  /* Clear of the label at the line's middle; the gap lets the pointer
     through to the line. */
  .lift {
    padding-bottom: 0.9rem;
    pointer-events: none;
  }

  .lift > :global(*) {
    pointer-events: auto;
  }

  /* The label's own size and voice (Board's .svelte-flow__edge-label), as
     a field. */
  .line-name {
    width: 10rem;
    padding: 0 0.3rem;
    font-family: var(--font-body);
    font-size: 0.75rem;
    color: var(--text-primary);
    background: var(--bg-app);
    border: 1px solid var(--text-accent);
    border-radius: var(--radius-sm);
    outline: none;
  }
</style>
