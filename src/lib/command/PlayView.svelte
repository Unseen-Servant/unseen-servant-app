<script lang="ts">
  // Play (design §5.2–§5.3): the arrangement down the left, the session's
  // board in the middle. Launching a beat makes its notes the live set and
  // frames their cards; a card's key plays one note. The board's file, the
  // log and the jot bar's lines in the session note are the only things
  // written — what's live is the sidecar's.
  import { tick } from 'svelte';
  import { openUrl } from '@tauri-apps/plugin-opener';
  import type { Viewport } from '@xyflow/svelte';
  import Arrangement from './Arrangement.svelte';
  import Board from './Board.svelte';
  import CommandMenu from './CommandMenu.svelte';
  import LatchKey from '../ui/LatchKey.svelte';
  import { chordHint } from '../shell/keybindings';
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
  /** A line for the session note; resolves whether it was written. */
  export let onJot: (text: string) => Promise<boolean>;
  /** The board fills the host's space, Command's bar set aside. */
  export let expanded: boolean;
  export let onExpand: (on: boolean) => void;

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

  // -- the jot bar --------------------------------------------------------

  let jot = '';
  let jotEl: HTMLTextAreaElement | undefined;

  /** Enter sends the line and clears the bar for the next; a refused line
   *  comes back, unless something new was typed meanwhile. */
  async function submitJot() {
    const text = jot.trim();
    if (!text) return;
    jot = '';
    if (!(await onJot(text)) && !jot) jot = text;
  }

  function jotKey(e: KeyboardEvent & { currentTarget: HTMLTextAreaElement }) {
    if (e.key === 'Escape') e.currentTarget.blur();
    // Enter sends: a jot is one line, however it wraps.
    else if (e.key === 'Enter' && !e.isComposing) {
      e.preventDefault();
      void submitJot();
    }
  }

  /** The bar wraps its text and is as tall as its lines, up to its
   *  max-height. Each change of the text, typed or cleared, refits it. */
  async function fitJot(_text: string) {
    await tick();
    if (!jotEl) return;
    jotEl.style.height = 'auto';
    jotEl.style.height = `${jotEl.scrollHeight + jotEl.offsetHeight - jotEl.clientHeight}px`;
  }
  $: void fitJot(jot);
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

    <!-- The expand key, in the board's top-right corner: latched and lit
         while the board fills the view, and the way back from it. -->
    <div class="expand">
      <LatchKey
        open={expanded}
        lit={expanded}
        title={expanded ? 'Back to the normal view' : 'Expand the board to fill the view'}
        label={expanded ? 'Leave the expanded board' : 'Expand the board'}
        onClick={() => onExpand(!expanded)}
      >
        <!-- Font Awesome "up-right-and-down-left-from-center" icon
             (src/lib/ui/icons/up-right-and-down-left-from-center-solid-full.svg):
             "expand" is the beat rows' frame key. -->
        <svg viewBox="0 0 640 640" fill="currentColor" aria-hidden="true">
          <path d="M408 64L552 64C565.3 64 576 74.7 576 88L576 232C576 241.7 570.2 250.5 561.2 254.2C552.2 257.9 541.9 255.9 535 249L496 210L409 297C399.6 306.4 384.4 306.4 375.1 297L343.1 265C333.7 255.6 333.7 240.4 343.1 231.1L430.1 144.1L391.1 105.1C384.2 98.2 382.2 87.9 385.9 78.9C389.6 69.9 398.3 64 408 64zM232 576L88 576C74.7 576 64 565.3 64 552L64 408C64 398.3 69.8 389.5 78.8 385.8C87.8 382.1 98.1 384.2 105 391L144 430L231 343C240.4 333.6 255.6 333.6 264.9 343L296.9 375C306.3 384.4 306.3 399.6 296.9 408.9L209.9 495.9L248.9 534.9C255.8 541.8 257.8 552.1 254.1 561.1C250.4 570.1 241.7 576 232 576z" />
        </svg>
      </LatchKey>
    </div>

    <!-- The jot bar, in the board's bottom corner: a line at the end of
         the session note, which the key beside it (and ⌘O) opens. -->
    <div class="jot">
      <textarea
        class="jot-bar"
        rows="1"
        bind:this={jotEl}
        bind:value={jot}
        placeholder="Write to session notes…"
        aria-label="Add a line to the session note"
        spellcheck="false"
        on:keydown={jotKey}
      ></textarea>
      <button
        type="button"
        class="note-key"
        title={'Open the session note' + chordHint('command.sessionNote')}
        aria-label="Open the session note"
        on:click={() => onEdit(session.path)}
      >
        <!-- Font Awesome "pen-to-square" icon (src/lib/ui/icons/pen-to-square-solid-full.svg):
             the session menu's Edit session note. -->
        <svg viewBox="0 0 640 640" fill="currentColor" aria-hidden="true">
          <path d="M535.6 85.7C513.7 63.8 478.3 63.8 456.4 85.7L432 110.1L529.9 208L554.3 183.6C576.2 161.7 576.2 126.3 554.3 104.4L535.6 85.7zM236.4 305.7C230.3 311.8 225.6 319.3 222.9 327.6L193.3 416.4C190.4 425 192.7 434.5 199.1 441C205.5 447.5 215 449.7 223.7 446.8L312.5 417.2C320.7 414.5 328.2 409.8 334.4 403.7L496 241.9L398.1 144L236.4 305.7zM160 128C107 128 64 171 64 224L64 480C64 533 107 576 160 576L416 576C469 576 512 533 512 480L512 384C512 366.3 497.7 352 480 352C462.3 352 448 366.3 448 384L448 480C448 497.7 433.7 512 416 512L160 512C142.3 512 128 497.7 128 480L128 224C128 206.3 142.3 192 160 192L256 192C273.7 192 288 177.7 288 160C288 142.3 273.7 128 256 128L160 128z" />
        </svg>
      </button>
    </div>
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

  /* Level with the session player's plate across the board. */
  .expand {
    position: absolute;
    top: 0.5rem;
    right: 0.5rem;
    z-index: 5;
  }

  /* The bar and, beside it, the key that opens what it writes to, level
     with the bar's last line as it grows up from the corner. */
  .jot {
    position: absolute;
    left: 0.5rem;
    bottom: 0.5rem;
    z-index: 5;
    max-width: calc(100% - 1rem);
    display: flex;
    align-items: flex-end;
    gap: 0.3rem;
  }

  /* Wider than the session player, for a sentence. One line is the app's
     row height, which the key matches (0.85rem × 1.3 + padding + border);
     longer text wraps and the bar grows (fitJot), then scrolls. */
  .jot-bar {
    flex: 0 1 auto;
    width: 20rem;
    min-width: 0;
    min-height: 1.65rem;
    max-height: 9rem;
    box-sizing: border-box;
    display: block;
    padding: 0.21rem 0.45rem;
    resize: none;
    overflow-y: auto;
    background: var(--bg-container);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    font-family: var(--font-body);
    font-size: 0.85rem;
    line-height: 1.3;
    color: var(--text-primary);
  }

  /* As Legend Lore's search bar. */
  .jot-bar::placeholder {
    color: var(--text-secondary);
    font-style: italic;
  }

  .jot-bar:focus {
    outline: none;
    border-color: var(--text-accent);
  }

  /* A square well the bar's height, drawn as the bar is; hover brightens
     its ink and edge as the spend key's does, never a glow. */
  .note-key {
    flex: 0 0 auto;
    width: 1.65rem;
    height: 1.65rem;
    box-sizing: border-box;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0;
    background: var(--bg-container);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    color: var(--text-tertiary);
    cursor: pointer;
    transition: all var(--transition-fast);
  }

  .note-key:hover,
  .note-key:focus-visible {
    color: var(--text-secondary);
    border-color: var(--text-secondary);
    outline: none;
  }

  .note-key:active {
    transform: scale(0.97);
  }

  .note-key svg {
    width: 12px;
    height: 12px;
  }
</style>
