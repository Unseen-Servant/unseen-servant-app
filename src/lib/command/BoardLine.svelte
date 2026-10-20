<script lang="ts">
  // A line on the board: Svelte Flow's curve, with its label drawn here so
  // a double-click names it in place (board toolbar design §3.4). Enter or
  // a click away keeps the name, Escape backs out, and an emptied name
  // takes the label off.
  import { BaseEdge, EdgeLabel, getBezierPath, type Position } from '@xyflow/svelte';
  import { getContext } from 'svelte';
  import { CARD_ACTIONS, type CardActions } from './board';

  export let id: string;
  export let sourceX: number;
  export let sourceY: number;
  export let targetX: number;
  export let targetY: number;
  export let sourcePosition: Position;
  export let targetPosition: Position;
  /** The line's label, and whether it's being named (Board). */
  export let data: Record<string, unknown> | undefined = undefined;
  export let interactionWidth: number | undefined = undefined;

  $: label = typeof data?.label === 'string' ? data.label : null;
  $: editing = data?.editing === true;

  const actions = getContext<CardActions>(CARD_ACTIONS);

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

<BaseEdge {id} {path} {interactionWidth} />
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
