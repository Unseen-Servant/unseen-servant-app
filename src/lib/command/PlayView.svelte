<script lang="ts">
  // Play (design §5.2–§5.3): the session's board, the arrangement over its
  // corner and the card tray under it. Launching a beat makes its notes the
  // live set, frames their cards and deals them to the tray; a card's key
  // plays one note. The board's file and the jot bar's lines in the
  // session note are the only things written — what's live is the
  // sidecar's.
  import { onDestroy, onMount, setContext, tick } from 'svelte';
  import { writable } from 'svelte/store';
  import type { Viewport } from '@xyflow/svelte';
  import Arrangement from './Arrangement.svelte';
  import Board from './Board.svelte';
  import BoardTools from './BoardTools.svelte';
  import CardFace from './CardFace.svelte';
  import CardTray from './CardTray.svelte';
  import CommandMenu from './CommandMenu.svelte';
  import LatchKey from '../ui/LatchKey.svelte';
  import { confirmPrompt } from '../shell/confirmStore';
  import { bindKeys, type KeyContext } from '../shell/keys';
  import { chord, chordHint } from '../shell/keybindings';
  import { commandApi } from './api';
  import {
    CARD,
    CARD_ACTIONS,
    GAP,
    applyOps,
    bodyKey,
    bodyOf,
    cards as boardCards,
    frameOp,
    handOf,
    imageCard,
    lines as boardLines,
    newId,
    placeAll,
    standSpread,
    type Card,
    type CardActions,
    type CardData,
    type Tool,
  } from './board';
  import { inverse } from './boardUndo';
  import { IMAGE_SOURCE, type ImageSource } from './embeds';
  import { action, divider, keyed, type MenuItem, type OpenMenu } from './menu';
  import { beatGroups, memberPaths, planRows, sessionNotePaths } from './prep';
  import type { BeatEntry, BoardOp, BoardView, CampaignIndex, LiveSet, NoteEntry, SessionEntry } from './types';
  import { m } from '../paraglide/messages';

  export let active: boolean;
  export let campaign: string;
  export let index: CampaignIndex;
  export let session: SessionEntry;
  export let live: LiveSet | null;
  /** Where the cards' images load from (#407). */
  export let images: ImageSource;
  /** CommandPanel's job queue: one change at a time, errors on its line. */
  export let run: (job: () => Promise<void>) => Promise<void>;
  export let onLive: (live: LiveSet) => void;
  export let onEdit: (path: string) => void;
  export let onFollow: (name: string) => void;
  /** The session player unfolded; CommandPanel keeps it across Tab. */
  export let playerOpen: boolean;
  /** The card tray unfolded, the same. */
  export let trayOpen: boolean;
  /** Where each session's board was left, by board key: CommandPanel's, so
   *  it outlives Tab. */
  export let boardViews: Map<string, Viewport>;
  /** Each session's board as last drawn, by board key, the same: Tab back
   *  draws it at once, and the sidecar's answer follows. */
  export let boards: Map<string, BoardView>;
  /** What the note cards show, without frontmatter, by bodyKey:
   *  CommandPanel's, so Tab back to Play doesn't read every note again. It
   *  drops what changes on disk. */
  export let bodies: Map<string, string>;
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
  /** Each gesture's way back, last on top; and the ways forward again
   *  (board toolbar design §4). */
  let undos: BoardOp[][] = [];
  let redos: BoardOp[][] = [];
  /** The toolbar's tool, and the text card, frame or line being edited in
   *  place (§3). */
  let tool: Tool = 'select';
  let editing: string | null = null;

  $: boardKey = `${campaign}\n${session.path}`;
  $: boardPath = session.path.replace(/\.md$/i, '.canvas');
  $: if (boardKey !== boardFor) {
    // Undo is this board's, for this visit (board toolbar design §4).
    undos = [];
    redos = [];
    editing = null;
    standing = [];
    view = boards.get(boardKey) ?? view;
    void loadBoard();
  }

  /** Draw the board for `key`, and keep it for Tab back. */
  function show(key: string, next: BoardView) {
    view = next;
    boards.set(key, next);
  }

  async function loadBoard() {
    const key = (boardFor = boardKey);
    try {
      const loaded = await commandApi.getBoard(campaign, session.path);
      if (boardFor === key && pending === 0) {
        const first = view === null;
        show(key, loaded);
        boardError = null;
        // Open where the board was left; the first time, on what's in play,
        // readable, and with nothing in play on everything.
        if (first && !boardViews.has(key)) {
          await tick();
          frameBeat(index.beats.find((b) => b.path === live?.beat), live?.notes ?? [], true);
        }
      }
    } catch (e) {
      if (boardFor === key) boardError = String(e);
    }
  }

  // -- undo (board toolbar design §4) -------------------------------------

  const HISTORY = 100;

  function undo() {
    const back = undos.at(-1);
    if (!back) return;
    undos = undos.slice(0, -1);
    apply(back, 'undo');
  }

  function redo() {
    const again = redos.at(-1);
    if (!again) return;
    redos = redos.slice(0, -1);
    apply(again, 'redo');
  }

  /** Change the board: draw it at once, write it, and keep the way back —
   *  on the undo stack, or on redo's while undoing. */
  function apply(change: BoardOp[], as: 'gesture' | 'undo' | 'redo' = 'gesture') {
    if (!view || !change.length) return;
    const ops = placeAll(allCards, change);
    const back = inverse(view, ops, campaign);
    if (as === 'undo') redos = [...redos, back];
    else undos = [...undos, back].slice(-HISTORY);
    if (as === 'gesture') redos = [];
    const key = boardKey;
    const path = session.path;
    show(key, applyOps(view, ops, campaign));
    pending++;
    void run(async () => {
      try {
        const written = await commandApi.editBoard(campaign, path, ops);
        if (boardFor === key && pending === 1) show(key, written);
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
  /** The session's notes by beat, as Arrange frames them: the order the
   *  cards not yet placed are laid out in too. */
  $: groups = beatGroups(index, session);
  $: allCards = view ? boardCards(view, index, wanted, groups.map((g) => g.notes)) : [];
  $: allLines = view ? boardLines(view, allCards) : [];

  const removable = (card: Card) => (card.kind !== 'note' && card.kind !== 'image') || !card.path || !wanted.has(card.path);

  // -- what the cards show ------------------------------------------------

  /** Bodies being read, by bodyKey. */
  const loading = new Set<string>();
  let bodiesTick = 0;

  function loadBodies(cards: Card[]) {
    const missing = cards
      .flatMap((c) => (c.kind === 'note' ? [c.path] : []))
      .filter((p): p is string => !!p && !bodies.has(bodyKey(campaign, p)) && !loading.has(bodyKey(campaign, p)));
    for (const path of missing) {
      const key = bodyKey(campaign, path);
      loading.add(key);
      commandApi
        .readNote(campaign, path)
        .then((note) => bodies.set(key, bodyOf(note.content)))
        .catch(() => bodies.set(key, ''))
        .finally(() => {
          loading.delete(key);
          bodiesTick++;
        });
    }
  }
  $: loadBodies(allCards);

  /** Files changed on disk, their bodies already dropped (CommandPanel):
   *  read again what the cards show, and reload the board if it's one of
   *  them. */
  export function diskChanged(paths: string[]) {
    loadBodies(allCards);
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
    begin: (id) => (editing = id),
    finish: (id, fields) => {
      if (editing === id) editing = null;
      if (fields) apply([{ op: 'set', id, ...fields }]);
    },
    remove: (id) => apply([{ op: 'remove', id }]),
    set: (ids, fields) => apply(ids.map((id) => ({ op: 'set', id, ...fields }))),
  };

  // -- the toolbar (board toolbar design §3) -------------------------------

  let board: Board | undefined;

  /** A tool's card is made, and opens for its text or name. */
  function create(op: BoardOp) {
    apply([op]);
    editing = op.id;
    tool = 'select';
  }

  const TOOL_KEYS: Record<string, Tool> = { v: 'select', h: 'hand', d: 'note', t: 'text', n: 'sticky', l: 'line', f: 'frame' };

  /** The whole board in view, clear of the session player (⌥1). */
  const fitAll = () => (frame = { ids: [] });

  /** Arrange by beat (board toolbar design §6): the sidecar works out the
   *  layout, applied as one step that undo takes back, then the whole
   *  board is shown. */
  async function arrange() {
    const go = await confirmPrompt.request({
      title: m.command_play_arrange_title(),
      message: m.command_play_arrange_message({ frame: 'Throughout', undo: chord('command.boardUndo') }),
      confirmLabel: m.command_play_arrange_confirm(),
    });
    if (!go) return;
    void run(async () => {
      apply(await commandApi.arrangeBoard(campaign, session.path));
      await tick();
      fitAll();
    });
  }

  /** Images dropped from Finder (#407): each copied onto the campaign's
   *  shelf, since the campaign is the unit, then placed where they fell,
   *  one under another, as one step undo takes back. */
  function dropImages(files: File[], at: { x: number; y: number }) {
    void run(async () => {
      const ops: BoardOp[] = [];
      let y = at.y;
      for (const file of files) {
        const path = await commandApi.addImage(campaign, file.name, await file.arrayBuffer());
        const size = await sizeOf(file);
        ops.push({ op: 'place', id: newId(), path, x: Math.round(at.x), y: Math.round(y), ...size });
        y += size.height + GAP;
      }
      apply(ops);
    });
  }

  /** A dropped image's card size, from the image itself; a card's when the
   *  webview can't read it. */
  async function sizeOf(file: File) {
    try {
      const bitmap = await createImageBitmap(file);
      const size = imageCard(bitmap.width, bitmap.height);
      bitmap.close();
      return size;
    } catch {
      return { ...CARD };
    }
  }

  /** The board's keys, Miro's letters (§3.5), dispatched while Command has
   *  the keyboard (keys.ts). Bound ahead of the session player's, which
   *  this view mounts after binding, so Esc puts down an armed tool, then
   *  the standing cards, before it lets go of a beat. */
  function boardKeys(e: KeyboardEvent, ctx: KeyContext): boolean {
    if (menu || e.isComposing || ctx.menu || ctx.typing) return false;
    const mod = e.metaKey || e.ctrlKey;
    const key = e.key.toLowerCase();
    if (mod && !e.altKey && (key === 'z' || key === 'g')) {
      if (key === 'z') (e.shiftKey ? redo : undo)();
      else if (e.shiftKey) board?.unframeSelection();
      else board?.frameSelection();
      return true;
    }
    if (mod && !e.altKey && !e.shiftKey && key === 'd') {
      board?.duplicate();
      return true;
    }
    // ⇧⌘F fills the rack with the board, and brings the view back. F for
    // fill; ⌘F stays Legend Lore's filters.
    if (mod && !e.altKey && e.shiftKey && key === 'f') {
      onExpand(!expanded);
      return true;
    }
    // By the key's place: ⌥ turns "1" into "¡" on a Mac. ⌥1 the whole
    // board, ⌥2 the selection, ⌥3 the live cards — the beat's frame when
    // it has one, as launching it shows.
    if (e.altKey && !mod && !e.shiftKey && /^Digit[123]$/.test(e.code)) {
      if (e.code === 'Digit1') fitAll();
      else if (e.code === 'Digit2') {
        const ids = board?.selectedIds() ?? [];
        if (ids.length) frame = { ids };
      } else if (live) {
        frameBeat(index.beats.find((b) => b.path === live?.beat), live.notes);
      }
      return true;
    }
    if (mod || e.altKey || e.shiftKey) return false;
    if (e.key === 'Escape' && tool !== 'select') {
      tool = 'select';
      return true;
    }
    if (e.key === 'Escape' && putBack()) return true;
    const next = TOOL_KEYS[key];
    if (!next) return false;
    if (!e.repeat) tool = next;
    return true;
  }

  const unbindKeys = bindKeys(boardKeys, { tool: 'command' });
  onDestroy(unbindKeys);
  // The tray's cards ask what the board's do.
  setContext(CARD_ACTIONS, actions);
  // The board's cards and the tray's find their images here.
  const imageSource = writable(images);
  $: imageSource.set(images);
  setContext(IMAGE_SOURCE, imageSource);

  /** The live set's cards, for the tray. */
  $: hand = handOf(allCards, live?.notes ?? []);
  $: liveBeatName = live?.beat ? (index.beats.find((b) => b.path === live?.beat)?.name ?? null) : null;
  /** The note whose tray card is pointed at: its board card is outlined. */
  let pointed: string | null = null;

  function dataFor(
    lit: Set<string>,
    notes: Map<string, NoteEntry>,
    pigments: Record<string, string>,
    outlined: string | null,
    editingId: string | null,
    linking: boolean,
    _tick: number,
  ) {
    return (card: Card): CardData => {
      const note = card.path ? notes.get(card.path) : undefined;
      return {
        card,
        name: note?.name ?? '',
        track: note?.track ?? null,
        pigment: note?.track ? (pigments[note.track] ?? null) : null,
        live: !!card.path && lit.has(card.path),
        playable: !!note,
        spent: note?.spent ?? null,
        source: note?.source ?? null,
        body: card.path ? (bodies.get(bodyKey(campaign, card.path)) ?? null) : null,
        outlined: !!card.path && card.path === outlined,
        editing: card.id === editingId,
        linking,
      };
    };
  }
  $: dataOf = dataFor(liveNotes, notesByPath, index.pigments, pointed, editing, tool === 'line', bodiesTick);

  // -- framing ------------------------------------------------------------

  let frame: { ids: string[] } | null = null;

  /** The session player sits over the board's left edge: framing keeps the
   *  cards clear of how far it reaches. */
  let player: HTMLElement | undefined;
  let playerWidth = 0;
  $: covered = player && playerWidth ? player.offsetLeft + playerWidth : 0;

  /** Standing cards keep clear of the session player on the left and the
   *  rail on the right, and stand above the jot bar in the corner, as it
   *  grows with its text. */
  let stageWidth = 0;
  let jotHeight = 0;
  let rail: HTMLElement | undefined;
  let railWidth = 0;
  $: clearance = {
    left: covered,
    right: rail && railWidth ? stageWidth - rail.offsetLeft : 0,
  };

  /** Frame the cards of `paths`, wherever the board has them — or, with
   *  `orAll` and no paths, the whole board. */
  function frameNotes(paths: Iterable<string>, orAll = false) {
    const idOf = new Map(Object.entries({ ...view?.notes, ...view?.images }).map(([id, path]) => [path, id]));
    const ids = [...paths].map((p) => idOf.get(p) ?? `auto:${p}`);
    if (ids.length || orAll) frame = { ids };
  }

  /** Frame a beat: the frame named after it, as Arrange makes one, so a
   *  note it shares with a beat across the board doesn't pull the view out
   *  to both (board toolbar design §6); else the cards of `paths`. */
  function frameBeat(beat: BeatEntry | undefined, paths: Iterable<string>, orAll = false) {
    const name = beat?.name.trim().toLowerCase();
    const named = name
      ? view?.nodes.find((n) => n.type === 'group' && typeof n.label === 'string' && n.label.trim().toLowerCase() === name)
      : undefined;
    if (named) frame = { ids: [named.id] };
    else frameNotes(paths, orAll);
  }

  // -- the live set -------------------------------------------------------

  function setLive(path: string, on: boolean) {
    void run(async () => onLive(await commandApi.setLive(campaign, path, on)));
  }

  function launch(beat: BeatEntry) {
    void run(async () => {
      const launched = await commandApi.launch(campaign, beat.path);
      onLive(launched);
      await tick();
      frameBeat(beat, launched.notes);
    });
  }

  function stop() {
    void run(async () => onLive(await commandApi.stop(campaign)));
  }

  /** The card tray's order, dragged. */
  function orderLive(notes: string[]) {
    return run(async () => onLive(await commandApi.orderLive(campaign, notes)));
  }

  // -- standing cards -----------------------------------------------------

  /** The notes whose cards stand in the middle of the dimmed board, from a
   *  right-click on one in the tray or on the board. */
  let standing: string[] = [];
  $: stood = handOf(allCards, standing);
  /** A launch or a stop puts them back. */
  let standBeat: string | null = null;
  $: if ((live?.beat ?? null) !== standBeat) {
    standBeat = live?.beat ?? null;
    standing = [];
  }

  /** A note's or an image's card stands up; another has its menu. */
  const standable = (card: Card) => (card.kind === 'note' || card.kind === 'image') && !!card.path;

  /** A right-click stands a card up, or puts it back. */
  function stand(card: Card) {
    const path = card.path;
    if (!path) return;
    standing = standing.includes(path) ? standing.filter((p) => p !== path) : [...standing, path];
  }

  /** Esc, or a click on the dimmed board, puts every card back. False
   *  with none standing. */
  function putBack(): boolean {
    if (!stood.length) return false;
    standing = [];
    return true;
  }

  /** Each standing card's own height at the columns' width, from its
   *  unseen copy (measure), as its note or its picture loads. */
  let natural = new Map<string, number>();
  let stageHeight = 0;
  let rem = 16;
  onMount(() => (rem = parseFloat(getComputedStyle(document.documentElement).fontSize) || rem));
  /** In columns across the board's middle, from the stand's 0.5rem top to
   *  a gap above the jot bar: a reading measure down to 22rem, and a card
   *  cut to share an overfull column keeps its head and three lines. */
  $: spread = standSpread(
    stood.map((c) => natural.get(c.path ?? '') ?? 0),
    { width: stageWidth, height: stageHeight - 1.5 * rem - jotHeight, ...clearance },
    { min: 22 * rem, max: 28 * rem, gap: 0.5 * rem, least: 6.5 * rem },
  );

  function measure(el: HTMLElement, path: string) {
    const seen = new ResizeObserver(([entry]) => (natural = new Map(natural).set(path, entry.contentRect.height)));
    seen.observe(el);
    return {
      destroy() {
        seen.disconnect();
        natural.delete(path);
        natural = natural;
      },
    };
  }

  /** A right-click on a board card: a note's or an image's stands it up,
   *  as the tray's do; another's opens its menu, but not with Hand, which
   *  changes nothing on the board. */
  function boardMenu(card: Card, e: MouseEvent) {
    if (standable(card)) stand(card);
    else if (tool !== 'hand') cardMenu(card, e);
  }

  // -- menus --------------------------------------------------------------

  let menu: OpenMenu | null = null;

  function cardMenu(card: Card, e: MouseEvent) {
    const items: MenuItem[] = [];
    if (card.kind === 'text') items.push(action(m.command_play_edit_text(), () => (editing = card.id)));
    if (card.kind === 'group') items.push(action(m.command_play_rename_frame(), () => (editing = card.id)));
    if (card.kind === 'text' || card.kind === 'group') {
      items.push(keyed(m.command_play_duplicate(), 'command.boardDuplicate', () => board?.duplicate([card.id])));
    }
    if (card.placed && removable(card)) {
      if (items.length) items.push(divider);
      const label = card.kind === 'group' ? m.command_play_remove_frame() : m.command_play_remove_card();
      items.push(action(label, () => apply([{ op: 'remove', id: card.id }]), true));
    }
    if (items.length) menu = { x: e.clientX, y: e.clientY, items };
  }

  function lineMenu(id: string, e: MouseEvent) {
    menu = {
      x: e.clientX,
      y: e.clientY,
      items: [
        action(m.command_play_line_label(), () => (editing = id)),
        divider,
        action(m.command_play_remove_line(), () => apply([{ op: 'remove', id }]), true),
      ],
    };
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

  /** ⌘J: the caret in the bar, from the editor too. */
  export function focusJot() {
    jotEl?.focus();
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
  <div class="stage" bind:clientWidth={stageWidth} bind:clientHeight={stageHeight}>
    {#if view}
      <Board
        cards={allCards}
        lines={allLines}
        {index}
        {dataOf}
        {actions}
        {removable}
        {active}
        {frame}
        {covered}
        initialViewport={boardViews.get(boardKey)}
        onLeave={(viewport) => boardViews.set(boardKey, viewport)}
        onOps={(ops) => apply(ops)}
        onCardMenu={boardMenu}
        onPress={() => (menu = null)}
        onLineMenu={lineMenu}
        {tool}
        {editing}
        onCreate={create}
        onToolDone={() => (tool = 'select')}
        onDropImages={dropImages}
        bind:this={board}
      />
    {:else if boardError}
      <p class="board-note" role="alert">{boardError}</p>
    {/if}

    {#if stood.length}
      <!-- The board under the standing cards, dimmed as a sheet dims its
           window; a click on it puts them back, as Esc does. The session
           player, the rail and the jot bar stay lit over it. -->
      <!-- svelte-ignore a11y_click_events_have_key_events -->
      <div class="scrim" role="presentation" on:click={putBack}></div>
      <!-- Each standing card at the columns' width and its own height,
           unseen, for the spread to measure. -->
      <div class="measure" style:width="{spread.width}px" aria-hidden="true">
        {#each stood as card (card.id)}
          <div use:measure={card.path ?? ''}><CardFace data={dataOf(card)} held /></div>
        {/each}
      </div>
      <!-- The standing cards in columns across the board's middle, each
           its note's height up to the board's (standSpread). -->
      <div class="stand">
        {#each stood as card, i (card.id)}
          {@const box = spread.boxes[i]}
          <div
            class="standing"
            role="presentation"
            data-path={card.path}
            style:left="{box.x}px"
            style:top="{box.y}px"
            style:width="{spread.width}px"
            style:height="{box.height}px"
            on:contextmenu|preventDefault={() => stand(card)}
          >
            <CardFace data={dataOf(card)} held />
          </div>
        {/each}
      </div>
    {/if}

    <!-- The session player, a box over the board's top-left corner. -->
    <div class="player" bind:this={player} bind:offsetWidth={playerWidth}>
      <Arrangement
        rows={planRows(index, session)}
        bind:open={playerOpen}
        liveBeat={live?.beat ?? null}
        onLaunch={launch}
        onStop={stop}
        onFrame={(beat) => frameBeat(beat, beat.path === live?.beat ? (live?.notes ?? []) : memberPaths(beat))}
        onEdit={(beat) => onEdit(beat.path)}
        {onSpent}
      />
    </div>

    <!-- The expand key, in the board's top-right corner: latched and lit
         while the board fills the view, and the way back from it. The
         toolbar hangs under it. -->
    <div class="rail" bind:this={rail} bind:offsetWidth={railWidth}>
      <LatchKey
        open={expanded}
        lit={expanded}
        title={(expanded ? m.command_play_expand_back() : m.command_play_expand_title()) + chordHint('command.boardFill')}
        label={expanded ? m.command_play_expand_leave() : m.command_play_expand()}
        onClick={() => onExpand(!expanded)}
      >
        <!-- Font Awesome "up-right-and-down-left-from-center" icon
             (src/lib/ui/icons/up-right-and-down-left-from-center-solid-full.svg):
             "expand" is the beat rows' frame key. -->
        <svg viewBox="0 0 640 640" fill="currentColor" aria-hidden="true">
          <path d="M408 64L552 64C565.3 64 576 74.7 576 88L576 232C576 241.7 570.2 250.5 561.2 254.2C552.2 257.9 541.9 255.9 535 249L496 210L409 297C399.6 306.4 384.4 306.4 375.1 297L343.1 265C333.7 255.6 333.7 240.4 343.1 231.1L430.1 144.1L391.1 105.1C384.2 98.2 382.2 87.9 385.9 78.9C389.6 69.9 398.3 64 408 64zM232 576L88 576C74.7 576 64 565.3 64 552L64 408C64 398.3 69.8 389.5 78.8 385.8C87.8 382.1 98.1 384.2 105 391L144 430L231 343C240.4 333.6 255.6 333.6 264.9 343L296.9 375C306.3 384.4 306.3 399.6 296.9 408.9L209.9 495.9L248.9 534.9C255.8 541.8 257.8 552.1 254.1 561.1C250.4 570.1 241.7 576 232 576z" />
        </svg>
      </LatchKey>
      {#if view}
        <BoardTools
          {tool}
          onTool={(t) => (tool = t)}
          canUndo={undos.length > 0}
          canRedo={redos.length > 0}
          onUndo={undo}
          onRedo={redo}
          onFit={fitAll}
          canArrange={groups.length > 0}
          onArrange={() => void arrange()}
        />
      {/if}
    </div>

    <!-- The jot bar, in the board's bottom corner (⌘J): a line at the end
         of the session note, which the key beside it (and ⇧⌘J) opens. -->
    <div class="jot" bind:offsetHeight={jotHeight}>
      <textarea
        class="jot-bar"
        rows="1"
        bind:this={jotEl}
        bind:value={jot}
        placeholder={m.command_play_jot_placeholder()}
        aria-label={m.command_play_jot_label()}
        spellcheck="false"
        on:keydown={jotKey}
      ></textarea>
      <button
        type="button"
        class="note-key"
        title={m.command_play_open_note() + chordHint('command.sessionNote')}
        aria-label={m.command_play_open_note()}
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

  {#if hand.length}
    <CardTray
      cards={hand}
      {dataOf}
      beat={liveBeatName}
      bind:open={trayOpen}
      onPoint={(path) => (pointed = path)}
      onOrder={orderLive}
      onStand={stand}
    />
  {/if}
</div>

{#if menu}
  <CommandMenu x={menu.x} y={menu.y} items={menu.items} onClose={() => (menu = null)} />
{/if}

<style>
  /* The board, then the card tray docked under it. */
  .play {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    min-height: 0;
  }

  .stage {
    position: relative;
    flex: 1;
    min-width: 0;
    min-height: 0;
  }

  /* Under the player, the rail and the jot bar. */
  .scrim {
    position: absolute;
    inset: 0;
    z-index: 4;
    background: var(--scrim-board);
  }

  /* Laid out, so it measures, but never seen nor in the stage's way. */
  .measure {
    position: absolute;
    top: 0;
    left: 0;
    height: 0;
    overflow: hidden;
    visibility: hidden;
    pointer-events: none;
  }

  /* Over the scrim, from the board's top to its foot, where the spread
     sets the cards. A click between them falls to the dimmed board, which
     puts them back. */
  .stand {
    position: absolute;
    inset: 0.5rem 0;
    z-index: 5;
    pointer-events: none;
  }

  .standing {
    position: absolute;
    display: flex;
    flex-direction: column;
    pointer-events: auto;
  }

  .standing :global(.card) {
    flex: 1 1 auto;
    border-color: var(--text-accent);
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

  /* Level with the session player's plate across the board; the toolbar
     under the expand key, on the same edge. */
  .rail {
    position: absolute;
    top: 0.5rem;
    right: 0.5rem;
    z-index: 5;
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 0.4rem;
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
