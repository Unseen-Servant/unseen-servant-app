<script context="module" lang="ts">
  import { STICKY_COLOR } from './board';

  /** A new sticky's colour: the last the selection bar gave a text card,
   *  for as long as the app runs (board toolbar design §3.2). */
  let lastSticky = STICKY_COLOR;
</script>

<script lang="ts">
  // The session board's surface (design §5.2): Svelte Flow over the cards
  // and lines board.ts derives from the canvas. Svelte Flow moves a card
  // while it's dragged; every gesture's end goes out as card operations,
  // and the cards are re-derived from what comes back. The toolbar's tool
  // (board toolbar design §3) decides what a click or a drag does: Hand
  // pans over the cards, Note asks for a note to place where the board is
  // clicked, Text, Sticky and Frame make one there, Line draws from
  // anywhere on a card. With Select, the selection bar floats over
  // selected text cards, stickies and frames, or over a selected line.
  import {
    Background,
    BackgroundVariant,
    ConnectionMode,
    NodeToolbar,
    SvelteFlow,
    type Connection,
    type Viewport,
    type Edge,
    type Node,
    type XYPosition,
  } from '@xyflow/svelte';
  import '@xyflow/svelte/dist/base.css';
  import { setContext } from 'svelte';
  import { writable } from 'svelte/store';
  import BoardBar from './BoardBar.svelte';
  import BoardFramer from './BoardFramer.svelte';
  import BoardLine from './BoardLine.svelte';
  import BoardNoteField from './BoardNoteField.svelte';
  import BoardPointer from './BoardPointer.svelte';
  import FrameCard from './FrameCard.svelte';
  import ImageCard from './ImageCard.svelte';
  import NoteCard from './NoteCard.svelte';
  import {
    BAR_LINE,
    CARD,
    CARD_ACTIONS,
    NEW_FRAME,
    STICKY,
    TEXT_CARD,
    around,
    connectOps,
    duplicateOps,
    frameDepths,
    frameOp,
    inside,
    newId,
    paint,
    type Card,
    type CardActions,
    type CardData,
    type Line,
    type Tool,
  } from './board';
  import { IMAGE } from './embeds';
  import type { BoardOp, CampaignIndex, Side } from './types';

  export let cards: Card[];
  export let lines: Line[];
  /** The campaign, whose notes the Note tool places. */
  export let index: CampaignIndex;
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
  /** Where the viewport opens: where the board was left (PlayView). */
  export let initialViewport: Viewport | undefined = undefined;
  /** The viewport as the board closes, to open there again. */
  export let onLeave: (viewport: Viewport) => void;
  export let onOps: (ops: BoardOp[]) => void;
  export let onCardMenu: (card: Card, e: MouseEvent) => void;
  export let onLineMenu: (id: string, e: MouseEvent) => void;
  export let tool: Tool;
  /** The card or line being edited in place: a line shows its field. */
  export let editing: string | null;
  /** What a tool made, to open for editing at once. */
  export let onCreate: (op: BoardOp) => void;
  /** The tool did its one thing: back to Select, as Miro's do. */
  export let onToolDone: () => void;
  /** Images dropped from Finder, and where on the board they fell (#407). */
  export let onDropImages: (files: File[], at: XYPosition) => void;

  const nodeTypes = { note: NoteCard, image: ImageCard, frame: FrameCard };
  const edgeTypes = { line: BoardLine };
  setContext(CARD_ACTIONS, actions);

  let nodes: Node[] = [];
  let edges: Edge[] = [];
  /** Cards to select once they're drawn: a duplicate's copies. */
  let choose: Set<string> | null = null;

  /** Cards as Svelte Flow nodes. A card under the pointer keeps where the
   *  drag has it, and the selection carries over. */
  function sync(next: Card[], data: (card: Card) => CardData) {
    const current = new Map(nodes.map((n) => [n.id, n]));
    const depths = frameDepths(next);
    const picking = choose && next.some((c) => choose!.has(c.id)) ? choose : null;
    if (picking) choose = null;
    nodes = next.map((c) => {
      const was = current.get(c.id);
      return {
        id: c.id,
        type: c.kind === 'note' || c.kind === 'image' ? c.kind : 'frame',
        position: was && (was.dragging || carried.has(c.id)) ? was.position : { x: c.x, y: c.y },
        width: c.width,
        height: c.height,
        data: data(c),
        selected: picking ? picking.has(c.id) : (was?.selected ?? false),
        zIndex: depths.get(c.id) ?? 0,
      };
    });
  }
  $: sync(cards, dataOf);

  /** Lines as Svelte Flow edges, the selection carried over as the cards'
   *  is, so the selection bar stays while a line is restyled. */
  function syncEdges(next: Line[], editingId: string | null) {
    const chosen = new Set(edges.filter((e) => e.selected).map((e) => e.id));
    edges = next.map((l) => ({
      id: l.id,
      source: l.source,
      target: l.target,
      sourceHandle: l.fromSide,
      targetHandle: l.toSide,
      type: 'line',
      selected: chosen.has(l.id),
      data: { label: l.label, color: l.color, fromEnd: l.fromEnd, toEnd: l.toEnd, editing: l.id === editingId },
    }));
  }
  $: syncEdges(lines, editing);

  const cardOf = (id: string) => cards.find((c) => c.id === id);

  // -- the selection bar (board toolbar design §3.3) ------------------------

  /** The line that wears the bar: the selection, when it's one line. */
  const barLine = writable<string | null>(null);
  setContext(BAR_LINE, barLine);

  $: byId = new Map(cards.map((c) => [c.id, c]));
  $: chosenCards = nodes.filter((n) => n.selected);
  $: chosenLines = edges.filter((e) => e.selected);
  /** The cards that wear the bar: a selection of text cards, stickies and
   *  frames, and nothing else. A note card's head already wears its
   *  track's pigment. */
  $: barCards =
    tool === 'select' &&
    !chosenLines.length &&
    chosenCards.length &&
    chosenCards.every((n) => ['text', 'group'].includes(byId.get(n.id)?.kind ?? ''))
      ? chosenCards.map((n) => n.id)
      : [];
  $: barLine.set(tool === 'select' && !chosenCards.length && chosenLines.length === 1 ? chosenLines[0].id : null);
  /** The colour the bar's cards share, as drawn; undefined when they differ. */
  $: barColor = (() => {
    const drawn = new Set(barCards.map((id) => paint(byId.get(id)?.color ?? null)));
    return drawn.size === 1 ? [...drawn][0] : undefined;
  })();

  /** The bar's pick. A text card given a pigment is a sticky, and the next
   *  sticky takes it. */
  function recolour(ids: string[], color: string | null) {
    actions.set(ids, { color });
    if (color && ids.some((id) => byId.get(id)?.kind === 'text')) lastSticky = color;
  }

  // -- a frame carries what's inside it (board toolbar design §4) ----------

  /** The cards a dragged frame carries, each where it started. */
  let carried = new Map<string, XYPosition>();
  /** Each dragged frame where it started. */
  let lifted = new Map<string, XYPosition>();

  function dragStart({ nodes: dragged }: { nodes: Node[] }) {
    carried = new Map();
    lifted = new Map();
    const moving = new Set(dragged.map((n) => n.id));
    for (const n of dragged) {
      const frame = cardOf(n.id);
      if (frame?.kind !== 'group') continue;
      lifted.set(n.id, { x: frame.x, y: frame.y });
      for (const c of inside(cards, frame)) if (!moving.has(c.id)) carried.set(c.id, { x: c.x, y: c.y });
    }
  }

  function drag({ nodes: dragged }: { nodes: Node[] }) {
    const lead = dragged.find((n) => lifted.has(n.id));
    if (!lead || !carried.size) return;
    const start = lifted.get(lead.id)!;
    const dx = lead.position.x - start.x;
    const dy = lead.position.y - start.y;
    nodes = nodes.map((n) => {
      const from = carried.get(n.id);
      return from ? { ...n, position: { x: from.x + dx, y: from.y + dy } } : n;
    });
  }

  function dragStop({ nodes: moved }: { nodes: Node[] }) {
    const at = new Map(moved.map((n) => [n.id, n.position]));
    for (const n of nodes) if (carried.has(n.id)) at.set(n.id, n.position);
    carried = new Map();
    lifted = new Map();
    const ops = [...at].flatMap(([id, position]) => {
      const card = cardOf(id);
      return card ? [frameOp(card, { ...position, width: card.width, height: card.height })] : [];
    });
    if (ops.length) onOps(ops);
  }

  const SIDE_IDS: string[] = ['top', 'right', 'bottom', 'left'];
  /** A handle's side; the Line tool's whole-card handle has none, so the
   *  line faces the way the cards do (board.ts facing). */
  const sideOf = (handle: string | null | undefined) =>
    handle && SIDE_IDS.includes(handle) ? (handle as Side) : undefined;

  /** A line drawn between two cards. Svelte Flow would add the edge
   *  itself; the board adds it from the operation instead. */
  function beforeConnect(c: Connection): false {
    const a = cardOf(c.source);
    const b = cardOf(c.target);
    if (a && b && a !== b) onOps(connectOps(a, b, sideOf(c.sourceHandle), sideOf(c.targetHandle)));
    return false;
  }

  // -- images dropped from Finder (#407) -----------------------------------

  /** Only a drag carrying files lands here: Finder's. The app's own drags
   *  carry none, and native drag and drop stays off, so this is the page's
   *  own drop. */
  const carriesFiles = (e: DragEvent) => !!e.dataTransfer?.types.includes('Files');

  function dragOver(e: DragEvent) {
    if (!carriesFiles(e)) return;
    e.preventDefault();
    e.dataTransfer!.dropEffect = 'copy';
  }

  function drop(e: DragEvent) {
    if (!carriesFiles(e)) return;
    e.preventDefault();
    const files = [...(e.dataTransfer?.files ?? [])].filter((f) => IMAGE.test(f.name));
    if (files.length) onDropImages(files, toBoard({ x: e.clientX, y: e.clientY }));
  }

  // -- the toolbar's Text, Sticky and Frame --------------------------------

  let toBoard: (point: XYPosition) => XYPosition = (point) => point;
  let overlay: HTMLElement | undefined;
  /** A press under way with a making tool, in the window's coordinates. */
  let drawn: { x0: number; y0: number; x1: number; y1: number } | null = null;
  $: making = tool === 'note' || tool === 'text' || tool === 'sticky' || tool === 'frame';

  function press(e: PointerEvent) {
    if (e.button !== 0) return;
    overlay?.setPointerCapture(e.pointerId);
    drawn = { x0: e.clientX, y0: e.clientY, x1: e.clientX, y1: e.clientY };
  }

  function stretch(e: PointerEvent) {
    if (drawn) drawn = { ...drawn, x1: e.clientX, y1: e.clientY };
  }

  /** A click makes the tool's card there; a frame can be dragged to size. */
  function release() {
    if (!drawn) return;
    const d = drawn;
    drawn = null;
    const a = toBoard({ x: Math.min(d.x0, d.x1), y: Math.min(d.y0, d.y1) });
    const b = toBoard({ x: Math.max(d.x0, d.x1), y: Math.max(d.y0, d.y1) });
    const at = { x: Math.round(a.x), y: Math.round(a.y) };
    const sized = Math.abs(d.x1 - d.x0) > 4 || Math.abs(d.y1 - d.y0) > 4;
    const id = newId();
    if (tool === 'note') {
      const r = overlay!.getBoundingClientRect();
      const left = Math.min(d.x0 - r.left, r.width - FIELD_WIDTH);
      const top = d.y0 - r.top;
      naming = { at, left: Math.max(0, left), top, up: top > r.height - FIELD_ROOM };
    } else if (tool === 'frame') {
      const size = sized
        ? { width: Math.max(80, Math.round(b.x - a.x)), height: Math.max(40, Math.round(b.y - a.y)) }
        : NEW_FRAME;
      onCreate({ op: 'add', id, type: 'group', ...at, ...size });
    } else if (tool === 'sticky') {
      onCreate({ op: 'add', id, type: 'text', text: '', color: lastSticky, ...at, ...STICKY });
    } else {
      onCreate({ op: 'add', id, type: 'text', text: '', ...at, ...TEXT_CARD });
    }
  }

  /** The rectangle being drawn, in the overlay's own coordinates. */
  $: sketch =
    drawn && overlay && tool === 'frame'
      ? (() => {
          const r = overlay.getBoundingClientRect();
          return {
            left: Math.min(drawn.x0, drawn.x1) - r.left,
            top: Math.min(drawn.y0, drawn.y1) - r.top,
            width: Math.abs(drawn.x1 - drawn.x0),
            height: Math.abs(drawn.y1 - drawn.y0),
          };
        })()
      : null;

  // -- the toolbar's Note ---------------------------------------------------

  /** The Note tool's field, where the board was clicked: on the board, and
   *  over it in px. Its list opens upward near the board's foot. */
  let naming: { at: XYPosition; left: number; top: number; up: boolean } | null = null;
  $: if (tool !== 'note') naming = null;
  /** The field's width, and the room its list needs below it. */
  const FIELD_WIDTH = 14 * 16;
  const FIELD_ROOM = 360;

  /** The picked note's card goes where the board was clicked: one already
   *  on the board moves there, as a note has one card per board. */
  function placeNote(path: string) {
    if (!naming) return;
    const { at } = naming;
    naming = null;
    const card = cards.find((c) => c.kind === 'note' && c.path === path);
    onOps([card ? frameOp(card, { ...at, width: card.width, height: card.height }) : { op: 'place', id: newId(), path, ...at, ...CARD }]);
    onToolDone();
  }

  /** The selected cards, for framing them in view (⌥2). */
  export function selectedIds(): string[] {
    return nodes.filter((n) => n.selected).map((n) => n.id);
  }

  /** ⌘D, or a card menu's Duplicate: copies of the text cards, stickies
   *  and frames among `ids`, beside them, selected in their stead. Copies
   *  set down out of view are framed, as ⌥2 would. */
  export function duplicate(ids: string[] = selectedIds()) {
    const ops = duplicateOps(cards, lines, ids);
    const copies = ops.flatMap((o) => (o.op === 'add' ? [o] : []));
    if (!copies.length) return;
    choose = new Set(copies.map((o) => o.id));
    onOps(ops);
    const r = boardEl.getBoundingClientRect();
    const a = toBoard({ x: r.left, y: r.top });
    const b = toBoard({ x: r.right, y: r.bottom });
    const seen = copies.every((o) => o.x >= a.x && o.y >= a.y && o.x + o.width <= b.x && o.y + o.height <= b.y);
    if (!seen) request = { ids: [...choose] };
  }

  /** What the framer frames: the board's asks (`frame`), or the copies. */
  let request: { ids: string[] } | null = null;
  $: request = frame;
  let boardEl: HTMLElement;

  /** ⌘G: a frame around the selected cards, its name field open. */
  export function frameSelection() {
    const chosen = nodes.flatMap((n) => (n.selected ? (cardOf(n.id) ?? []) : []));
    if (chosen.length) onCreate({ op: 'add', id: newId(), type: 'group', ...around(chosen) });
  }

  /** ⇧⌘G: the selected frames go, and their cards stay. */
  export function unframeSelection() {
    const ops = nodes.flatMap((n) =>
      n.selected && cardOf(n.id)?.kind === 'group' ? [{ op: 'remove' as const, id: n.id }] : [],
    );
    if (ops.length) onOps(ops);
  }

  /** A double-click on a line names it. */
  function lineClick({ edge, event }: { edge: Edge; event: MouseEvent }) {
    if (event.detail === 2 && tool === 'select') actions.begin(edge.id);
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
<div
  class="board"
  class:hand={tool === 'hand'}
  class:linking={tool === 'line'}
  bind:this={boardEl}
  on:keydown={keepBackspace}
  on:dragover={dragOver}
  on:drop={drop}
>
  <!-- The arrangement's keys are the table's: ↑↓ step through the plan and
       Space launches, so the board gives up moving a focused card by arrow
       (a move it wouldn't save) and Space's hold-to-pan; a drag still pans. -->
  <SvelteFlow
    bind:nodes
    bind:edges
    {nodeTypes}
    {edgeTypes}
    nodesDraggable={tool === 'select'}
    elementsSelectable={tool === 'select'}
    connectionMode={ConnectionMode.Loose}
    {initialViewport}
    minZoom={0.2}
    maxZoom={2}
    deleteKey={active ? ['Backspace', 'Delete'] : null}
    selectionKey={active ? 'Shift' : null}
    multiSelectionKey={active ? 'Meta' : null}
    disableKeyboardA11y
    panActivationKey={null}
    zoomOnDoubleClick={false}
    attributionPosition="bottom-right"
    onnodedragstart={dragStart}
    onnodedrag={drag}
    onnodedragstop={dragStop}
    onbeforeconnect={beforeConnect}
    onconnectend={() => tool === 'line' && onToolDone()}
    onedgeclick={lineClick}
    onbeforedelete={beforeDelete}
    onnodecontextmenu={nodeMenu}
    onedgecontextmenu={edgeMenu}
  >
    <!-- Graph paper, the old-school dungeon map's: a faint square grid that
         scales with the zoom. -->
    <Background variant={BackgroundVariant.Lines} gap={24} />
    <BoardFramer {request} {covered} {onLeave} />
    <BoardPointer bind:toBoard />
    <NodeToolbar nodeId={barCards} isVisible={barCards.length > 0} class="bar-holder">
      <BoardBar color={barColor} onColor={(c) => recolour(barCards, c)} />
    </NodeToolbar>
  </SvelteFlow>
  {#if making}
    <!-- Over the cards, under the board's keys and boxes: a making tool's
         click lands here, not on a card. -->
    <div
      class="overlay"
      bind:this={overlay}
      role="presentation"
      on:pointerdown={press}
      on:pointermove={stretch}
      on:pointerup={release}
    >
      {#if sketch}
        <div class="sketch" style:left="{sketch.left}px" style:top="{sketch.top}px" style:width="{sketch.width}px" style:height="{sketch.height}px"></div>
      {/if}
    </div>
  {/if}
  {#if naming}
    <BoardNoteField
      {index}
      left={naming.left}
      top={naming.top}
      up={naming.up}
      onPick={placeNote}
      onCancel={(putDown) => {
        naming = null;
        if (putDown) onToolDone();
      }}
    />
  {/if}
</div>

<style>
  .board {
    position: relative;
    height: 100%;
    background: var(--bg-app);
  }

  /* Hand: every drag pans, over the cards and lines too. */
  .board.hand :global(.svelte-flow__node),
  .board.hand :global(.svelte-flow__edge),
  .board.hand :global(.svelte-flow__edge-label) {
    pointer-events: none;
  }

  .board.hand :global(.svelte-flow__pane) {
    cursor: grab;
  }

  .board.linking :global(.svelte-flow__node) {
    cursor: crosshair;
  }

  /* The Line tool's handle: the whole card, unseen, so a line starts and
     lands anywhere on it. */
  .board :global(.svelte-flow__handle.whole) {
    inset: 0;
    width: 100%;
    height: 100%;
    transform: none;
    border: none;
    border-radius: 0;
    background: transparent;
    opacity: 0;
    cursor: crosshair;
  }

  /* A frame sits far back in the stack (frameDepths), and Svelte Flow sets
     its bar there too: the bar floats over every card. (The class takes
     the place of Svelte Flow's own.) */
  .board :global(.bar-holder) {
    z-index: 2000 !important;
  }

  .overlay {
    position: absolute;
    inset: 0;
    z-index: 4;
    cursor: crosshair;
  }

  /* The frame being drawn: a frame's own rule, dashed while it's
     prospective (the app's "not yet real"). */
  .sketch {
    position: absolute;
    border: 1px dashed var(--text-accent);
    border-radius: var(--radius-md);
    pointer-events: none;
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
