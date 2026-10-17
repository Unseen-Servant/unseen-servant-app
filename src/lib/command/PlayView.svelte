<script lang="ts">
  // Play (design §5.2–§5.3): the arrangement down the left, the session's
  // board in the middle. Launching a beat makes its notes the live set and
  // frames their cards; a card's key plays one note. The board's file and
  // the log are the only things written — what's live is the sidecar's.
  import { tick } from 'svelte';
  import { openUrl } from '@tauri-apps/plugin-opener';
  import type { Viewport } from '@xyflow/svelte';
  import Arrangement from './Arrangement.svelte';
  import Board from './Board.svelte';
  import CommandMenu from './CommandMenu.svelte';
  import { commandApi } from './api';
  import {
    applyOps,
    bodyOf,
    cards as boardCards,
    frameOp,
    lines as boardLines,
    type Card,
    type CardActions,
    type CardData,
  } from './board';
  import { action, divider, keyed, type MenuItem, type OpenMenu } from './menu';
  import { memberPaths, planRows, sessionNotePaths } from './prep';
  import type { BeatEntry, BoardOp, BoardView, CampaignIndex, LiveSet, NoteEntry, SessionEntry } from './types';

  export let active: boolean;
  export let campaign: string;
  export let index: CampaignIndex;
  export let session: SessionEntry;
  export let live: LiveSet | null;
  /** CommandPanel's job queue: one change at a time, errors on its line. */
  export let run: (job: () => Promise<void>) => Promise<void>;
  export let onLive: (live: LiveSet) => void;
  export let onEdit: (path: string) => void;
  export let onFollow: (name: string) => void;
  /** The session player unfolded; CommandPanel keeps it across Tab. */
  export let playerOpen: boolean;
  /** Where each session's board was left, by board key: CommandPanel's, so
   *  it outlives Tab. */
  export let boardViews: Map<string, Viewport>;
  /** A note or a beat marked spent, or not. */
  export let onSpent: (note: { name: string; path: string }, spent: boolean) => void;

  // -- the board ----------------------------------------------------------

  let view: BoardView | null = null;
  let boardError: string | null = null;
  /** The session the board was loaded for. */
  let boardFor: string | null = null;
  /** Writes under way: the sidecar's answer is adopted once none are. */
  let pending = 0;

  $: boardKey = `${campaign}\n${session.path}`;
  $: boardPath = session.path.replace(/\.md$/i, '.canvas');
  $: if (boardKey !== boardFor) void loadBoard();

  async function loadBoard() {
    const key = (boardFor = boardKey);
    try {
      const loaded = await commandApi.getBoard(campaign, session.path);
      if (boardFor === key && pending === 0) {
        const first = view === null;
        view = loaded;
        boardError = null;
        // Open where the board was left; the first time, on what's in play,
        // readable, and with nothing in play on everything.
        if (first && !boardViews.has(key)) {
          await tick();
          frameNotes(live?.notes ?? [], true);
        }
      }
    } catch (e) {
      if (boardFor === key) boardError = String(e);
    }
  }

  function apply(ops: BoardOp[]) {
    if (!view || !ops.length) return;
    const key = boardKey;
    const path = session.path;
    view = applyOps(view, ops, campaign);
    pending++;
    void run(async () => {
      try {
        const written = await commandApi.editBoard(campaign, path, ops);
        if (boardFor === key && pending === 1) view = written;
      } catch (e) {
        if (boardFor === key) void loadBoard();
        throw e;
      } finally {
        pending--;
      }
    });
  }

  $: liveNotes = new Set(live?.notes ?? []);
  $: notesByPath = new Map(index.notes.map((n) => [n.path, n]));
  /** What belongs on the board beyond what's placed: the session's notes and
   *  anything live. */
  $: wanted = new Set([...sessionNotePaths(index, session), ...liveNotes]);
  $: allCards = view ? boardCards(view, index, wanted) : [];
  $: allLines = view ? boardLines(view, allCards) : [];

  const removable = (card: Card) => card.kind !== 'note' || !card.path || !wanted.has(card.path);

  // -- what the cards show ------------------------------------------------

  /** Note bodies by path, without frontmatter. */
  const bodies = new Map<string, string>();
  const loading = new Set<string>();
  let bodiesTick = 0;

  function loadBodies(cards: Card[]) {
    const missing = cards
      .map((c) => c.path)
      .filter((p): p is string => !!p && !bodies.has(p) && !loading.has(p));
    for (const path of missing) {
      loading.add(path);
      commandApi
        .readNote(campaign, path)
        .then((note) => bodies.set(path, bodyOf(note.content)))
        .catch(() => bodies.set(path, ''))
        .finally(() => {
          loading.delete(path);
          bodiesTick++;
        });
    }
  }
  $: loadBodies(allCards);

  /** Files changed on disk: drop what the cards hold of them, and reload
   *  the board if it's one of them. */
  export function diskChanged(paths: string[]) {
    let dropped = false;
    for (const path of paths) dropped = bodies.delete(path) || dropped;
    if (dropped) loadBodies(allCards);
    if (paths.includes(boardPath) && pending === 0) void loadBoard();
  }

  const actions: CardActions = {
    launch: (card, on) => card.path && setLive(card.path, on),
    spend: (card, spent) => {
      const note = card.path ? notesByPath.get(card.path) : undefined;
      if (note) onSpent(note, spent);
    },
    edit: (card) => card.path && onEdit(card.path),
    follow: (name) => onFollow(name),
    frame: (card, f) => apply([frameOp(card, f)]),
  };

  function dataFor(lit: Set<string>, notes: Map<string, NoteEntry>, pigments: Record<string, string>, _tick: number) {
    return (card: Card): CardData => {
      const note = card.path ? notes.get(card.path) : undefined;
      return {
        card,
        name: note?.name ?? '',
        track: note?.track ?? null,
        pigment: note?.track ? (pigments[note.track] ?? null) : null,
        live: !!card.path && lit.has(card.path),
        spent: note?.spent ?? null,
        source: note?.source ?? null,
        body: card.path ? (bodies.get(card.path) ?? null) : null,
      };
    };
  }
  $: dataOf = dataFor(liveNotes, notesByPath, index.pigments, bodiesTick);

  // -- framing ------------------------------------------------------------

  let frame: { ids: string[] } | null = null;

  /** The session player sits over the board's left edge: framing keeps the
   *  cards clear of how far it reaches. */
  let player: HTMLElement | undefined;
  let playerWidth = 0;
  $: covered = player && playerWidth ? player.offsetLeft + playerWidth : 0;

  /** Frame the cards of `paths`, wherever the board has them — or, with
   *  `orAll` and no paths, the whole board. */
  function frameNotes(paths: Iterable<string>, orAll = false) {
    const idOf = new Map(Object.entries(view?.notes ?? {}).map(([id, path]) => [path, id]));
    const ids = [...paths].map((p) => idOf.get(p) ?? `auto:${p}`);
    if (ids.length || orAll) frame = { ids };
  }

  // -- the live set -------------------------------------------------------

  function setLive(path: string, on: boolean) {
    void run(async () => onLive(await commandApi.setLive(campaign, path, on)));
  }

  function launch(beat: BeatEntry) {
    void run(async () => {
      const launched = await commandApi.launch(campaign, beat.path, session.path);
      onLive(launched);
      await tick();
      frameNotes(launched.notes);
    });
  }

  function stop() {
    void run(async () => onLive(await commandApi.stop(campaign)));
  }

  // -- menus --------------------------------------------------------------

  let menu: OpenMenu | null = null;

  function cardMenu(card: Card, e: MouseEvent) {
    const items: MenuItem[] = [];
    const note = card.path ? notesByPath.get(card.path) : undefined;
    if (note) {
      const playing = liveNotes.has(note.path);
      items.push(
        action('Edit note', () => onEdit(note.path)),
        action(playing ? 'Take out of play' : 'Play', () => setLive(note.path, !playing)),
        keyed(note.spent ? 'Mark unspent' : 'Mark spent', 'command.spend', () => onSpent(note, !note.spent)),
      );
      const source = note.source;
      if (source) items.push(action('Open source', () => void openUrl(source).catch(() => {})));
    }
    if (card.placed && removable(card)) {
      if (items.length) items.push(divider);
      items.push(action('Remove from board', () => apply([{ op: 'remove', id: card.id }]), true));
    }
    if (items.length) menu = { x: e.clientX, y: e.clientY, items };
  }

  function lineMenu(id: string, e: MouseEvent) {
    menu = { x: e.clientX, y: e.clientY, items: [action('Remove line', () => apply([{ op: 'remove', id }]), true)] };
  }
</script>

<div class="play">
  <div class="stage">
    {#if view}
      <Board
        cards={allCards}
        lines={allLines}
        {dataOf}
        {actions}
        {removable}
        {active}
        {frame}
        {covered}
        initialViewport={boardViews.get(boardKey)}
        onLeave={(viewport) => boardViews.set(boardKey, viewport)}
        onOps={apply}
        onCardMenu={cardMenu}
        onLineMenu={lineMenu}
      />
    {:else if boardError}
      <p class="board-note" role="alert">{boardError}</p>
    {/if}

    <!-- The session player, a box over the board's top-left corner. -->
    <div class="player" bind:this={player} bind:offsetWidth={playerWidth}>
      <Arrangement
        rows={planRows(index, session)}
        bind:open={playerOpen}
        {active}
        liveBeat={live?.beat ?? null}
        onLaunch={launch}
        onStop={stop}
        onFrame={(beat) => frameNotes(beat.path === live?.beat ? (live?.notes ?? []) : memberPaths(beat))}
        onEdit={(beat) => onEdit(beat.path)}
        {onSpent}
      />
    </div>

    <!-- An empty board says where its cards come from: printed in its
         corner as a legend, not a control. -->
    {#if view && !allCards.length}
      <span class="legend">Plan beats in Prep to put their notes here</span>
    {/if}
  </div>
</div>

{#if menu}
  <CommandMenu x={menu.x} y={menu.y} items={menu.items} onClose={() => (menu = null)} />
{/if}

<style>
  .play {
    flex: 1;
    min-width: 0;
    display: flex;
    min-height: 0;
  }

  .stage {
    position: relative;
    flex: 1;
    min-width: 0;
    min-height: 0;
  }

  /* Centred, clear of the session player in the corner. */
  .board-note {
    margin: 2rem;
    text-align: center;
    color: var(--text-danger);
  }

  /* The session planner's width (BeatColumn), room for a name beside the
     transport and the count. */
  .player {
    position: absolute;
    top: 0.5rem;
    left: 0.5rem;
    z-index: 5;
    width: 15rem;
    max-height: calc(100% - 1rem);
    display: flex;
    flex-direction: column;
  }

  /* In the board's corner, under the cards. */
  .legend {
    position: absolute;
    left: 0.75rem;
    bottom: 0.6rem;
    z-index: 5;
    font-size: 0.8rem;
    font-style: italic;
    color: var(--text-tertiary);
    pointer-events: none;
  }
</style>
