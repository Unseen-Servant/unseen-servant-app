<script lang="ts">
  // The session board's surface (design §5.2): Svelte Flow over the cards
  // and lines board.ts derives from the canvas. Svelte Flow moves a card
  // while it's dragged; every gesture's end goes out as card operations,
  // and the cards are re-derived from what comes back.
  import {
    Background,
    BackgroundVariant,
    ConnectionMode,
    SvelteFlow,
    type Connection,
    type Edge,
    type Node,
  } from '@xyflow/svelte';
  import '@xyflow/svelte/dist/base.css';
  import { setContext } from 'svelte';
  import BoardFramer from './BoardFramer.svelte';
  import FrameCard from './FrameCard.svelte';
  import NoteCard from './NoteCard.svelte';
  import { CARD_ACTIONS, connectOps, frameOp, type Card, type CardActions, type CardData, type Line } from './board';
  import type { BoardOp, Side } from './types';

  export let cards: Card[];
  export let lines: Line[];
  export let dataOf: (card: Card) => CardData;
  /** What the cards can ask of the board. */
  export let actions: CardActions;
  /** Whether a card may leave the board: a note the session or the live
   *  set holds would only be put back. */
  export let removable: (card: Card) => boolean;
  /** True while the panel is visible: keys do nothing otherwise (PANELS.md). */
  export let active: boolean;
  /** Cards to frame; a new object asks again. */
  export let frame: { ids: string[] } | null = null;
  /** How far, in px, something floats over the board from its left edge
   *  (the session player): framed cards keep clear of it. */
  export let covered = 0;
  export let onOps: (ops: BoardOp[]) => void;
  export let onCardMenu: (card: Card, e: MouseEvent) => void;
  export let onLineMenu: (id: string, e: MouseEvent) => void;

  const nodeTypes = { note: NoteCard, frame: FrameCard };
  setContext(CARD_ACTIONS, actions);

  let nodes: Node[] = [];
  let edges: Edge[] = [];

  /** Cards as Svelte Flow nodes. A card under the pointer keeps where the
   *  drag has it, and the selection carries over. */
  function sync(next: Card[], data: (card: Card) => CardData) {
    const current = new Map(nodes.map((n) => [n.id, n]));
    nodes = next.map((c) => {
      const was = current.get(c.id);
      return {
        id: c.id,
        type: c.kind === 'note' ? 'note' : 'frame',
        position: was?.dragging ? was.position : { x: c.x, y: c.y },
        width: c.width,
        height: c.height,
        data: data(c),
        selected: was?.selected ?? false,
        zIndex: c.kind === 'group' ? -1 : 0,
      };
    });
  }
  $: sync(cards, dataOf);

  $: edges = lines.map((l) => ({
    id: l.id,
    source: l.source,
    target: l.target,
    sourceHandle: l.fromSide,
    targetHandle: l.toSide,
    label: l.label ?? undefined,
  }));

  const cardOf = (id: string) => cards.find((c) => c.id === id);

  function dragStop({ nodes: moved }: { nodes: Node[] }) {
    const ops = moved.flatMap((n) => {
      const card = cardOf(n.id);
      return card ? [frameOp(card, { ...n.position, width: card.width, height: card.height })] : [];
    });
    if (ops.length) onOps(ops);
  }

  /** A line drawn between two cards. Svelte Flow would add the edge
   *  itself; the board adds it from the operation instead. */
  function beforeConnect(c: Connection): false {
    const a = cardOf(c.source);
    const b = cardOf(c.target);
    if (a && b && a !== b) onOps(connectOps(a, b, (c.sourceHandle as Side) ?? undefined, (c.targetHandle as Side) ?? undefined));
    return false;
  }

  /** Delete or Backspace on a selection: lines always go, cards only when
   *  `removable` says so. The board then re-derives without them. */
  async function beforeDelete({ nodes: gone, edges: cut }: { nodes: Node[]; edges: Edge[] }) {
    const ops: BoardOp[] = [
      ...cut.map((e) => ({ op: 'remove' as const, id: e.id })),
      ...gone.filter((n) => {
        const card = cardOf(n.id);
        return card?.placed && removable(card);
      }).map((n) => ({ op: 'remove' as const, id: n.id })),
    ];
    if (ops.length) onOps(ops);
    return false;
  }

  function nodeMenu({ node, event }: { node: Node; event: MouseEvent }) {
    const card = cardOf(node.id);
    if (!card) return;
    event.preventDefault();
    onCardMenu(card, event);
  }

  function edgeMenu({ edge, event }: { edge: Edge; event: MouseEvent }) {
    event.preventDefault();
    onLineMenu(edge.id, event);
  }

  /** Backspace deletes on the board; a webview must not also take it as
   *  "go back". */
  function keepBackspace(e: KeyboardEvent) {
    const target = e.target as HTMLElement | null;
    if (e.key === 'Backspace' && !target?.closest('input, textarea, [contenteditable]')) e.preventDefault();
  }
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="board" on:keydown={keepBackspace}>
  <!-- The arrangement's keys are the table's: ↑↓ step through the plan and
       Space launches, so the board gives up moving a focused card by arrow
       (a move it wouldn't save) and Space's hold-to-pan; a drag still pans. -->
  <SvelteFlow
    bind:nodes
    bind:edges
    {nodeTypes}
    connectionMode={ConnectionMode.Loose}
    minZoom={0.2}
    maxZoom={2}
    deleteKey={active ? ['Backspace', 'Delete'] : null}
    selectionKey={active ? 'Shift' : null}
    multiSelectionKey={active ? 'Meta' : null}
    disableKeyboardA11y
    panActivationKey={null}
    zoomOnDoubleClick={false}
    attributionPosition="bottom-right"
    onnodedragstop={dragStop}
    onbeforeconnect={beforeConnect}
    onbeforedelete={beforeDelete}
    onnodecontextmenu={nodeMenu}
    onedgecontextmenu={edgeMenu}
  >
    <!-- Graph paper, the old-school dungeon map's: a faint square grid that
         scales with the zoom. -->
    <Background variant={BackgroundVariant.Lines} gap={24} />
    <BoardFramer request={frame} {covered} />
  </SvelteFlow>
</div>

<style>
  .board {
    height: 100%;
    background: var(--bg-app);
  }

  /* Svelte Flow's chrome in the app's tokens. */
  .board :global(.svelte-flow) {
    --xy-background-color: var(--bg-app);
    --xy-background-pattern-color: var(--bg-header);
    --xy-edge-stroke: var(--text-tertiary);
    --xy-edge-stroke-selected: var(--text-accent);
    --xy-edge-stroke-width: 1.5;
    --xy-connectionline-stroke: var(--text-accent);
    --xy-connectionline-stroke-width: 1.5;
    --xy-handle-background-color: var(--text-accent);
    --xy-resize-background-color: var(--text-accent);
    --xy-selection-background-color: color-mix(in srgb, var(--text-accent) 8%, transparent);
    --xy-selection-border: 1px dotted var(--text-accent);
    font-family: var(--font-body);
  }

  /* A selected card wears the accent rule; the resizer's corners carry it. */
  .board :global(.svelte-flow__node.selected > .card),
  .board :global(.svelte-flow__node.selected > .frame) {
    border-color: var(--text-accent);
  }

  .board :global(.svelte-flow__resize-control.handle) {
    width: 7px;
    height: 7px;
    border: 1px solid var(--bg-app);
    border-radius: var(--radius-cell);
  }

  .board :global(.svelte-flow__resize-control.line) {
    border-color: transparent;
  }

  /* Connection points show while the pointer is on a card. */
  .board :global(.svelte-flow__handle) {
    width: 7px;
    height: 7px;
    border: 1px solid var(--bg-app);
    border-radius: 50%;
    opacity: 0;
    transition: opacity var(--transition-fast);
  }

  .board :global(.svelte-flow__node:hover .svelte-flow__handle),
  .board :global(.svelte-flow__handle.connectingfrom) {
    opacity: 1;
  }

  /* Svelte Flow asks to keep its credit; it stays, quiet. */
  .board :global(.svelte-flow__attribution) {
    background: transparent;
    font-size: 0.65rem;
  }

  .board :global(.svelte-flow__attribution a) {
    color: var(--text-tertiary);
  }

  .board :global(.svelte-flow__edge-label) {
    padding: 0 0.3rem;
    font-size: 0.75rem;
    color: var(--text-secondary);
    background: var(--bg-app);
    border-radius: var(--radius-sm);
  }
</style>
