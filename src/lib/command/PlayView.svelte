<script lang="ts">
  // Play (design §5.2–§5.3): the arrangement down the left, the session's
  // board in the middle. Launching a beat makes its notes the live set and
  // frames their cards; a card's key plays one note; typing finds any note
  // in the campaign to play. The board's file and the log are the only
  // things written — what's live is the sidecar's.
  import { tick } from 'svelte';
  import { openUrl } from '@tauri-apps/plugin-opener';
  import ActionButton from '../ui/ActionButton.svelte';
  import { menuSlotHeld } from '../shell/menuSlot';
  import Arrangement from './Arrangement.svelte';
  import Board from './Board.svelte';
  import CommandMenu from './CommandMenu.svelte';
  import InlineName from './InlineName.svelte';
  import { commandApi } from './api';
  import {
    applyOps,
    bodyOf,
    cards as boardCards,
    findNotes,
    frameOp,
    lines as boardLines,
    type Card,
    type CardActions,
    type CardData,
  } from './board';
  import { action, divider, type MenuItem, type OpenMenu } from './menu';
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
  export let onSpent: (note: NoteEntry, spent: boolean) => void;

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
        // Open on what's in play, readable; nothing in play, on everything.
        if (first) {
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

  function dataFor(lit: Set<string>, notes: Map<string, NoteEntry>, _tick: number) {
    return (card: Card): CardData => {
      const note = card.path ? notes.get(card.path) : undefined;
      return {
        card,
        name: note?.name ?? '',
        track: note?.track ?? null,
        live: !!card.path && lit.has(card.path),
        spent: note?.spent ?? null,
        source: note?.source ?? null,
        body: card.path ? (bodies.get(card.path) ?? null) : null,
      };
    };
  }
  $: dataOf = dataFor(liveNotes, notesByPath, bodiesTick);

  // -- framing ------------------------------------------------------------

  let frame: { ids: string[] } | null = null;

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

  let capturing = false;

  function capture(name: string) {
    capturing = false;
    void run(async () => onLive((await commandApi.capture(campaign, session.path, name)).live));
  }

  function jot(text: string) {
    void run(async () => void (await commandApi.jot(campaign, session.path, text)));
  }

  $: liveBeat = live?.beat ? (index.beats.find((b) => b.path === live!.beat) ?? null) : null;

  // -- finding a note to play ---------------------------------------------

  let finding: string | null = null;
  let findAt = 0;
  let findInput: HTMLInputElement | undefined;
  $: matches = finding ? findNotes(index, finding) : [];
  $: if (findAt >= matches.length) findAt = 0;

  function onKeydown(e: KeyboardEvent) {
    if (!active || finding !== null || menu || capturing || menuSlotHeld()) return;
    // A dialog's keys are its own (CommandPanel); ? opens the shortcut sheet.
    if (document.querySelector('dialog[open]')) return;
    if (e.metaKey || e.ctrlKey || e.altKey || e.key.length !== 1 || e.key === ' ' || e.key === '?') return;
    const target = e.target as HTMLElement | null;
    if (target?.closest('input, textarea, select, [contenteditable], .cm-editor')) return;
    e.preventDefault();
    finding = e.key;
    findAt = 0;
    void tick().then(() => findInput?.focus());
  }

  function playFound(note: NoteEntry | undefined) {
    finding = null;
    if (!note) return;
    if (!liveNotes.has(note.path)) setLive(note.path, true);
    void tick().then(() => frameNotes([note.path]));
  }

  function findKeydown(e: KeyboardEvent) {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      const step = e.key === 'ArrowDown' ? 1 : -1;
      if (matches.length) findAt = (findAt + step + matches.length) % matches.length;
    } else if (e.key === 'Enter') {
      e.preventDefault();
      playFound(matches[findAt]);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      finding = null;
    }
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
        action(note.spent ? 'Mark unspent' : 'Mark spent', () => onSpent(note, !note.spent)),
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

<svelte:window on:keydown={onKeydown} />

<div class="play">
  <Arrangement
    rows={planRows(index, session)}
    log={session.log}
    liveBeat={live?.beat ?? null}
    onLaunch={launch}
    onShow={(beat) => frameNotes(memberPaths(beat))}
    onEdit={(beat) => onEdit(beat.path)}
    onJot={jot}
  />

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
        onOps={apply}
        onCardMenu={cardMenu}
        onLineMenu={lineMenu}
      />
    {:else if boardError}
      <p class="board-note" role="alert">{boardError}</p>
    {/if}

    <div class="transport">
      {#if capturing}
        <div class="capture-name">
          <InlineName
            placeholder="Name the beat"
            label="Capture the live set as a beat"
            onCommit={capture}
            onCancel={() => (capturing = false)}
          />
        </div>
      {:else if live?.notes.length}
        <span class="live-lamp" aria-hidden="true"></span>
        <span class="live-what">{liveBeat?.name ?? 'improvised'}</span>
        <span class="live-count">{live.notes.length}</span>
        <ActionButton label="frame" title="Frame the live cards" onClick={() => frameNotes(live?.notes ?? [])} />
        <ActionButton label="capture" title="Keep the live set as a new beat after this one" onClick={() => (capturing = true)} />
        <ActionButton label="stop" title="Take every note out of play" onClick={stop} />
      {:else if view && !allCards.length}
        <span class="hint">Plan beats in Prep, or type a note's name to play it.</span>
      {:else}
        <span class="hint">Nothing in play — launch a beat, or type a note's name.</span>
      {/if}
    </div>

    {#if finding !== null}
      <div class="find">
        {#if matches.length}
          <ul class="matches" role="listbox" aria-label="Notes to play">
            {#each matches as note, i (note.path)}
              <li
                role="option"
                aria-selected={i === findAt}
                class="match"
                class:current={i === findAt}
                class:playing={liveNotes.has(note.path)}
                on:mousedown|preventDefault={() => playFound(note)}
              >
                <span class="match-name">{note.name}</span>
                {#if note.track}<span class="match-track">{note.track}</span>{/if}
              </li>
            {/each}
          </ul>
        {/if}
        <label class="find-line">
          <span class="ledger-label">play</span>
          <input
            bind:this={findInput}
            bind:value={finding}
            on:keydown={findKeydown}
            on:blur={() => (finding = null)}
            spellcheck="false"
            aria-label="Find a note to play"
          />
        </label>
      </div>
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

  .board-note {
    margin: 2rem;
    color: var(--text-danger);
  }

  /* The transport strip floats over the board's top edge. */
  .transport {
    position: absolute;
    top: 0.5rem;
    left: 0.5rem;
    z-index: 5;
    display: flex;
    align-items: baseline;
    gap: 0.5rem;
    max-width: calc(100% - 1rem);
    padding: 0.25rem 0.6rem;
    background: var(--bg-container);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-dropdown);
    font-size: 0.85rem;
  }

  /* Amber is a lamp: something is live at the table. */
  .live-lamp {
    align-self: center;
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--text-connected);
    filter: var(--glow-accent);
  }

  .live-what {
    font-family: var(--font-heading);
    color: var(--text-primary);
  }

  .live-count {
    font-size: 0.75rem;
    font-variant-numeric: tabular-nums;
    color: var(--text-tertiary);
  }

  .hint {
    color: var(--text-tertiary);
  }

  .capture-name {
    width: 16rem;
  }

  .find {
    position: absolute;
    left: 0.5rem;
    bottom: 0.5rem;
    z-index: 6;
    width: min(22rem, calc(100% - 1rem));
    background: var(--bg-container);
    border: 1px solid var(--text-accent);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-dropdown);
  }

  .matches {
    margin: 0;
    padding: 0.25rem;
    list-style: none;
    border-bottom: 1px solid var(--border-subtle);
  }

  .match {
    display: flex;
    align-items: baseline;
    gap: 0.5rem;
    padding: 0.15rem 0.45rem;
    border-radius: var(--radius-sm);
    font-size: 0.9rem;
    cursor: pointer;
  }

  .match.current {
    background: var(--bg-focused);
  }

  .match.playing .match-name {
    color: var(--text-accent);
  }

  .match-name {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .match-track {
    flex-shrink: 0;
    font-size: 0.75rem;
    color: var(--text-tertiary);
  }

  .find-line {
    display: flex;
    align-items: baseline;
    gap: 0.5rem;
    padding: 0.3rem 0.55rem;
  }

  .find-line input {
    flex: 1;
    min-width: 0;
    padding: 0;
    background: none;
    border: none;
    outline: none;
    font-family: var(--font-body);
    font-size: 0.95rem;
    color: var(--text-primary);
  }
</style>
