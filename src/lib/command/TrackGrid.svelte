<script lang="ts">
  // The Prep grid (design §5.1): one column per track, every note in it,
  // subfolders as groups. A click selects a note, as a row in Legend Lore,
  // and a double-click opens it; while a beat is armed, the click also puts
  // it in the beat or takes it out. Right-click for rename, spent, move and
  // trash. The empty row at the foot of each column and the ghost at the
  // end of the grid name a new note or track in place. A column's nameplate
  // drags to reorder the tracks and renames on a double-click, as a
  // collection's row does in Legend Lore; a note's row drags between rows
  // to reorder its group or to move there, or onto another column.
  //
  // Each row's slot, Ableton's square lit as a splash lamp, reads the
  // session at a glance: lit parchment for a note in the selected beat,
  // half-lit for one some other planned beat holds, dark otherwise.
  // A spent note dims and carries a check.
  import { onDestroy } from 'svelte';
  import InlineName from './InlineName.svelte';
  import RenameField from '../ui/RenameField.svelte';
  import { hoverLive } from '../ui/inputModality';
  import CommandMenu from './CommandMenu.svelte';
  import { action, choice, divider, heading, keyed, type OpenMenu } from './menu';
  import { PIGMENTS } from '../legend-lore/palette';
  import { draggedNote, endNoteDrag, isNoteDrag, startNoteDrag } from './noteDrag';
  import { planMoveTo } from './prep';
  import type { Column, NoteGroup } from './columns';
  import type { NoteEntry } from './types';

  export let cols: Column[];
  /** Each track's pigment, by name. */
  export let pigments: Record<string, string>;
  export let openPath: string | null;
  /** Notes in the lit beat. */
  export let members: Set<string>;
  /** The lit beat, by name, for the plates' readout. */
  export let litBeatName: string | null;
  /** Notes some beat of the session's plan holds. */
  export let inSession: Set<string>;
  /** The live set, while there is one: notes outside it dim, as Legend
   *  Lore's tree does while a collection plays. */
  export let liveNotes: Set<string> | null;
  /** A beat is armed: a click also toggles membership. */
  export let armed: boolean;
  export let onToggleMember: (note: NoteEntry) => void;
  export let onSpent: (note: NoteEntry, spent: boolean) => void;
  export let ambiguous: (name: string) => boolean;
  export let onOpen: (note: NoteEntry) => void;
  /** The note last clicked: Legend Lore's focused row. */
  export let selectedPath: string | null;
  export let onSelect: (note: NoteEntry) => void;
  export let onCreateNote: (track: string, name: string) => void;
  /** Resolves the reason a rename was refused, or null when it took. */
  export let onRenameNote: (note: NoteEntry, name: string) => Promise<string | null>;
  /** Move a note to a track or a group's folder; dropped between rows
   *  there, `order` is that folder's notes by name, with it in place. */
  export let onMoveNote: (note: NoteEntry, folder: string, order?: string[]) => void;
  export let onTrashNote: (note: NoteEntry) => void;
  export let onRevealNote: (note: NoteEntry) => void;
  export let onCreateTrack: (name: string) => void;
  export let onRenameTrack: (track: string, name: string) => Promise<string | null>;
  export let onTrashTrack: (column: Column) => void;
  export let onRevealTrack: (track: string) => void;
  /** The tracks by name, in the order they were dragged into. */
  export let onReorderTracks: (order: string[]) => void;
  export let onPigmentTrack: (track: string, pigment: string | null) => void;
  /** A folder's notes by name, in the order they were dragged into. */
  export let onReorderNotes: (folder: string, names: string[]) => void;

  /** How many of each track's notes the lit beat holds, for its plate. */
  $: inBeat = new Map(
    cols.map((c) => [c.track, c.groups.reduce((n, g) => n + g.notes.filter((x) => members.has(x.path)).length, 0)]),
  );

  let creatingIn: string | null = null;
  let creatingTrack = false;
  let renamingPath: string | null = null;
  let renamingTrack: string | null = null;
  let menu: OpenMenu | null = null;

  // Hover latched on pointerenter, as Legend Lore's rows (FileTree).
  let hovered: string | null = null;
  function leave(path: string) {
    if (hovered === path) hovered = null;
  }

  /** R on the selected note: renamed in its row, if it's one of the grid's. */
  export function rename(path: string) {
    if (cols.some((c) => c.groups.some((g) => g.notes.some((n) => n.path === path)))) renamingPath = path;
  }

  // A right-click selects the row, as it focuses one in Legend Lore, so the
  // menu's keys act on what it opened on.
  function noteMenu(e: MouseEvent, note: NoteEntry) {
    onSelect(note);
    const others = cols.map((c) => c.track).filter((t) => t !== note.track);
    menu = {
      x: e.clientX,
      y: e.clientY,
      items: [
        action(note.spent ? 'Mark unspent' : 'Mark spent', () => onSpent(note, !note.spent)),
        divider,
        heading('move to'),
        ...others.map((t) => action(t, () => onMoveNote(note, t))),
        action('Shelf', () => onMoveNote(note, 'Shelf')),
        divider,
        keyed('Rename', 'command.rename', () => (renamingPath = note.path)),
        action('Show in Finder', () => onRevealNote(note)),
        action('Move to Trash', () => onTrashNote(note), true),
      ],
    };
  }

  // -- dragging onto the grid ---------------------------------------------
  //
  // Two drags reach it, told apart by their private types (a dragover can
  // read nothing else). A track, from its nameplate, reorders as Legend
  // Lore's collections do: over a column, the pointer's half picks the side
  // it lands on; past the last, the end. A note, from a row here or on the
  // shelf, lands between rows the same way, the pointer's half of a row
  // picking the side: among its own group's it reorders them, among any
  // other group's, in this column or another, it moves to that folder in
  // that place, an order the campaign keeps. Dropped elsewhere on another
  // track's column, it moves to that track.
  const TRACK_MIME = 'application/x-command-track';
  const isTrackDrag = (e: DragEvent) =>
    Array.from(e.dataTransfer?.types ?? []).some((t) => t.toLowerCase() === TRACK_MIME);

  let draggingTrack: string | null = null;
  /** Where the dragged track lands: before column `dropAt`, or after the last. */
  let dropAt: number | null = null;
  /** The track a dragged note would move to. */
  let noteInto: string | null = null;

  /** Where a note dragged among a group's rows lands: before row `at`, or
   *  after the last. */
  interface NoteSlot {
    note: NoteEntry;
    group: NoteGroup;
    at: number;
  }
  let noteSlot: NoteSlot | null = null;
  $: lineBefore = noteSlot && noteSlot.at < noteSlot.group.notes.length ? noteSlot.group.notes[noteSlot.at].path : null;
  $: lineAfter = noteSlot && noteSlot.at === noteSlot.group.notes.length ? noteSlot.group.notes[noteSlot.at - 1].path : null;

  function startTrackDrag(e: DragEvent, track: string) {
    draggingTrack = track;
    if (!e.dataTransfer) return;
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData(TRACK_MIME, track);
  }

  // Any drag's end, the shelf's too, reaches the window.
  function endDrag() {
    draggingTrack = null;
    dropAt = null;
    noteInto = null;
    noteSlot = null;
    stopScrolling();
  }

  // The webview doesn't scroll the grid under a drag, so the grid does: a
  // track or note held near either edge scrolls it that way, faster the
  // nearer the edge, until the pointer moves off, the drag ends or there's
  // no more. A note over a column scrolls that column the same way, by its
  // top and bottom, to reach the rows it can land among.
  const EDGE = 48;
  const MAX_STEP = 12;
  let gridEl: HTMLDivElement;
  let pointerX: number | null = null;
  let pointerY: number | null = null;
  let scrolling = 0;

  /** The scroll a pointer at `at` asks of a box from `start` to `end`. */
  function edgeStep(at: number, start: number, end: number): number {
    const near = (gap: number) => Math.max(1, Math.round(MAX_STEP * (1 - Math.max(gap, 0) / EDGE)));
    if (at - start < EDGE) return -near(at - start);
    if (end - at < EDGE) return near(end - at);
    return 0;
  }

  function scrollStep() {
    let moved = false;
    if (pointerX !== null && pointerY !== null) {
      const grid = gridEl.getBoundingClientRect();
      const left = gridEl.scrollLeft;
      const step = edgeStep(pointerX, grid.left, grid.right);
      if (step !== 0) gridEl.scrollLeft += step;
      const list = draggingTrack ? null : listOf(columnAt(pointerX));
      const top = list?.scrollTop;
      if (list) {
        const box = list.getBoundingClientRect();
        const down = edgeStep(pointerY, box.top, box.bottom);
        if (down !== 0) list.scrollTop += down;
      }
      moved = gridEl.scrollLeft !== left || list?.scrollTop !== top;
      // The rows moved under a still pointer: what's lit follows.
      if (moved) aim(pointerX, pointerY);
    }
    scrolling = moved ? requestAnimationFrame(scrollStep) : 0;
  }

  function stopScrolling() {
    pointerX = null;
    pointerY = null;
    cancelAnimationFrame(scrolling);
    scrolling = 0;
  }

  onDestroy(stopScrolling);

  /** The column under `x`, by index; past the last track, `cols.length`. */
  function columnAt(x: number): number {
    const columns = Array.from(gridEl.children);
    for (let i = 0; i < cols.length; i++) {
      if (x < columns[i].getBoundingClientRect().right) return i;
    }
    return cols.length;
  }

  /** Where a track dropped at `x` lands: before the column under it, or
   *  after it past its middle; past the last track, at the end. */
  function slotAt(x: number): number {
    const i = columnAt(x);
    if (i === cols.length) return i;
    const box = gridEl.children[i].getBoundingClientRect();
    return x >= box.left + box.width / 2 ? i + 1 : i;
  }

  /** The track a note dropped at `x` moves to: the column's under it, if
   *  that's not where the note already is. */
  function noteTarget(note: NoteEntry | null, x: number): string | null {
    const track = cols[columnAt(x)]?.track ?? null;
    return note && track !== note.track ? track : null;
  }

  /** The rows' list of column `i`; none past the last track. */
  const listOf = (i: number) => gridEl.children[i]?.querySelector<HTMLElement>('.notes') ?? null;

  /** Where a note dropped at (x, y) lands among the rows of the group
   *  under it: before the row under it or, past that row's middle, after
   *  it. Away from a group's rows, nowhere. */
  function noteSlotAt(note: NoteEntry | null, x: number, y: number): NoteSlot | null {
    const i = columnAt(x);
    const list = listOf(i);
    if (!note || !list) return null;
    // Rows scrolled out of the list still have boxes, under the nameplate.
    const shown = list.getBoundingClientRect();
    if (y < shown.top || y >= shown.bottom) return null;
    const boxes = new Map(
      Array.from(list.querySelectorAll<HTMLElement>('[data-path]'), (r) => [r.dataset.path, r.getBoundingClientRect()]),
    );
    for (const group of cols[i].groups) {
      const rows = group.notes.map((n) => boxes.get(n.path));
      // A row being renamed has no box: its group takes no drop.
      if (rows.some((r) => !r)) continue;
      const first = rows[0]!;
      const last = rows[rows.length - 1]!;
      if (y < first.top || y >= last.bottom) continue;
      const at = rows.findIndex((b) => y < b!.top + b!.height / 2);
      return { note, group, at: at < 0 ? rows.length : at };
    }
    return null;
  }

  /** Light what a drop at (x, y) would do: between rows, the line; on the
   *  rest of another track's column, the column. */
  function aim(x: number, y: number) {
    if (draggingTrack) dropAt = slotAt(x);
    else {
      const note = draggedNote();
      noteSlot = noteSlotAt(note, x, y);
      noteInto = noteSlot ? null : noteTarget(note, x);
    }
  }

  function overGrid(e: DragEvent) {
    const track = !!draggingTrack && isTrackDrag(e);
    if (!track && !(isNoteDrag(e) && draggedNote())) return;
    pointerX = e.clientX;
    pointerY = e.clientY;
    if (!scrolling) scrolling = requestAnimationFrame(scrollStep);
    aim(e.clientX, e.clientY);
    if (!track && noteInto === null && noteSlot === null) return;
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
  }

  function dropOnGrid(e: DragEvent) {
    const dragged = draggingTrack;
    const note = isNoteDrag(e) ? draggedNote() : null;
    const slot = noteSlotAt(note, e.clientX, e.clientY);
    const into = slot ? null : noteTarget(note, e.clientX);
    const at = slotAt(e.clientX);
    endDrag();
    if (dragged && isTrackDrag(e)) {
      e.preventDefault();
      const order = cols.map((c) => c.track);
      const from = order.indexOf(dragged);
      const to = at > from ? at - 1 : at;
      if (from < 0 || to === from) return;
      order.splice(to, 0, ...order.splice(from, 1));
      onReorderTracks(order);
    } else if (slot) {
      e.preventDefault();
      const notes = slot.group.notes;
      const names = notes.map((n) => n.name);
      const from = notes.findIndex((n) => n.path === slot.note.path);
      if (from < 0) {
        names.splice(slot.at, 0, slot.note.name);
        onMoveNote(slot.note, slot.group.folder, names);
        return;
      }
      const to = planMoveTo(from, slot.at);
      if (to === null) return;
      names.splice(to, 0, ...names.splice(from, 1));
      onReorderNotes(slot.group.folder, names);
    } else if (note && into !== null) {
      e.preventDefault();
      onMoveNote(note, into);
    }
  }

  // WebKit sends a dragleave between the grid's own elements, at times
  // with no relatedTarget, so leaving is judged by where the pointer is.
  function leaveGrid(e: DragEvent) {
    const box = gridEl.getBoundingClientRect();
    const x = e.clientX;
    const y = e.clientY;
    if (x > box.left && x < box.right && y > box.top && y < box.bottom) return;
    dropAt = null;
    noteInto = null;
    noteSlot = null;
    stopScrolling();
  }

  function trackMenu(e: MouseEvent, column: Column) {
    menu = {
      x: e.clientX,
      y: e.clientY,
      items: [
        action('New note', () => (creatingIn = column.track)),
        divider,
        action('Rename', () => (renamingTrack = column.track)),
        action('Show in Finder', () => onRevealTrack(column.track)),
        divider,
        // Legend Lore's palette, as a collection's gem takes it.
        heading('pigment'),
        ...PIGMENTS.map((p) =>
          choice(p.name, pigments[column.track] === p.hex, () => onPigmentTrack(column.track, p.hex), p.hex),
        ),
        // None keeps a swatch's room, so its name lines up with theirs.
        choice('None', !pigments[column.track], () => onPigmentTrack(column.track, null), 'transparent'),
        divider,
        action('Move to Trash', () => onTrashTrack(column), true),
      ],
    };
  }
</script>

<div
  class="grid"
  role="presentation"
  bind:this={gridEl}
  on:dragenter={overGrid}
  on:dragover={overGrid}
  on:dragleave={leaveGrid}
  on:drop={dropOnGrid}
>
  {#each cols as column, i (column.track)}
    {@const lit = inBeat.get(column.track) ?? 0}
    <section
      class="column"
      class:dragging={draggingTrack === column.track}
      class:drop-before={dropAt === i}
      class:drop-after={dropAt === cols.length && i === cols.length - 1}
      class:drop-into={noteInto === column.track}
      aria-label={column.track}
    >
      <header
        class="nameplate"
        class:pigmented={!!pigments[column.track]}
        style:--pigment={pigments[column.track]}
        draggable={renamingTrack !== column.track}
        on:dragstart={(e) => startTrackDrag(e, column.track)}
        on:contextmenu={(e) => {
          // The whole plate is the track's; while it's renamed, the field
          // keeps its own menu.
          if (renamingTrack === column.track) return;
          e.preventDefault();
          trackMenu(e, column);
        }}
        role="presentation"
      >
        <span class="plate-name">
          <span class="track-number" aria-hidden="true">{i + 1}</span>
          {#if renamingTrack === column.track}
            <RenameField
              value={column.track}
              label="Rename track"
              onCommit={async (name) => {
                const refusal = await onRenameTrack(column.track, name);
                if (!refusal) renamingTrack = null;
                return refusal;
              }}
              onCancel={() => (renamingTrack = null)}
            />
          {:else}
            <button
              type="button"
              class="track-name ledger-label"
              title={`${column.track} — drag to reorder, double-click to rename`}
              on:dblclick={() => (renamingTrack = column.track)}
            >
              {column.track}
            </button>
          {/if}
        </span>
        {#if lit}
          <span class="count in-beat" title={`${lit} of ${column.count} in ${litBeatName}`}>{lit}</span>
        {:else}
          <span class="count">{column.count}</span>
        {/if}
      </header>

      <div class="notes">
        {#each column.groups as group (group.group)}
          {#if group.group}
            <div class="group-label" title={group.group}>{group.group}</div>
          {/if}
          {#each group.notes as note (note.path)}
            {@const renaming = renamingPath === note.path}
            <button
              type="button"
              class="note-row"
              data-row
              data-path={note.path}
              class:open={note.path === openPath}
              class:selected={note.path === selectedPath}
              class:hovered={$hoverLive && hovered === note.path}
              class:grouped={group.group !== null}
              class:ambiguous={ambiguous(note.name)}
              class:member={members.has(note.path)}
              class:in-session={inSession.has(note.path)}
              class:spent={!!note.spent}
              class:out-of-scope={liveNotes !== null && !liveNotes.has(note.path)}
              class:arming={armed}
              class:dragging={noteSlot?.note.path === note.path}
              class:drop-before={lineBefore === note.path}
              class:drop-after={lineAfter === note.path}
              aria-pressed={armed ? members.has(note.path) : undefined}
              title={ambiguous(note.name)
                ? `Another note is also named “${note.name}”, so links to it are ambiguous`
                : note.spent
                  ? `${note.name} — spent ${note.spent}`
                  : note.name}
              draggable={!renaming}
              on:dragstart={(e) => startNoteDrag(e, note)}
              on:dragend={() => {
                endNoteDrag();
                // A drag delivers no pointerleave: unlatch, as Legend Lore's rows do.
                hovered = null;
              }}
              on:click={() => {
                onSelect(note);
                if (armed) onToggleMember(note);
              }}
              on:dblclick={() => onOpen(note)}
              on:pointerenter={() => (hovered = note.path)}
              on:pointerleave={() => leave(note.path)}
              on:contextmenu|preventDefault={(e) => noteMenu(e, note)}
            >
              <span class="slot" aria-hidden="true"></span>
              <!-- A rename takes the name's place, as in Legend Lore's
                   tree: the row keeps its lamp, rule and marks. A
                   draggable row would kill selecting text in the field. -->
              {#if renaming}
                <RenameField
                  value={note.name}
                  label="Rename note"
                  onCommit={async (name) => {
                    const refusal = await onRenameNote(note, name);
                    if (!refusal) renamingPath = null;
                    return refusal;
                  }}
                  onCancel={() => (renamingPath = null)}
                />
              {:else}
                <span class="label">{note.name}</span>
              {/if}
              {#if note.spent}<span class="spent-mark" aria-label="spent">✓</span>{/if}
            </button>
          {/each}
        {/each}

        {#if creatingIn === column.track}
          <div class="row-edit naming">
            <span class="slot" aria-hidden="true"></span>
            <InlineName
              placeholder="Name"
              label={`New note in ${column.track}`}
              onCommit={(name) => {
                creatingIn = null;
                onCreateNote(column.track, name);
              }}
              onCancel={() => (creatingIn = null)}
            />
          </div>
        {:else}
          <button
            type="button"
            class="ghost-row"
            title="New note"
            aria-label={`New note in ${column.track}`}
            on:click={() => (creatingIn = column.track)}
          >
            <span class="slot" aria-hidden="true"></span>
          </button>
        {/if}
      </div>
    </section>
  {/each}

  <section class="column ghost-column" aria-label="New track">
    <header class="nameplate">
      {#if creatingTrack}
        <InlineName
          placeholder="Track name"
          label="New track"
          onCommit={(name) => {
            creatingTrack = false;
            onCreateTrack(name);
          }}
          onCancel={() => (creatingTrack = false)}
        />
      {:else}
        <button type="button" class="ghost-track ledger-label" on:click={() => (creatingTrack = true)}>+ track</button>
      {/if}
    </header>
  </section>
</div>

<svelte:window on:dragend={endDrag} />

{#if menu}
  <CommandMenu x={menu.x} y={menu.y} items={menu.items} onClose={() => (menu = null)} />
{/if}

<style>
  .grid {
    display: flex;
    height: 100%;
    min-width: 0;
    overflow-x: auto;
    overflow-y: hidden;
  }

  /* Tracks are one width, as on a console, whether the shelf is open or
     not: the grid scrolls rather than squeezing or stretching them. Long
     names ellipsize rather than widening their column (min-width: 0
     overrides the flex item's min-content floor, which nowrap rows would
     otherwise set). */
  .column {
    position: relative;
    flex: 0 0 10rem;
    min-width: 0;
    display: flex;
    flex-direction: column;
    min-height: 0;
    border-right: 1px solid var(--border-subtle);
  }

  .ghost-column {
    flex: 0 0 5.5rem;
    border-right: none;
  }

  /* Legend Lore's drop line (CollectionsPanel .drop-before), turned on its
     side: 2px of parchment on the edge the track lands at. Drawn over the
     nameplate's plate, which an inset shadow would sit under. */
  .column.dragging {
    opacity: 0.4;
  }

  .column.drop-before::after,
  .column.drop-after::after {
    content: '';
    position: absolute;
    top: 0;
    bottom: 0;
    width: 2px;
    background: var(--text-accent);
    pointer-events: none;
  }

  .column.drop-before::after {
    left: 0;
  }

  /* A note over a column it would move to: the beat column's drop target
     (BeatColumn .drop-into), Legend Lore's collection under a dragged book. */
  .column.drop-into {
    outline: var(--outline-drop);
    outline-offset: -1px;
    background: var(--bg-container);
  }

  .column.drop-after::after {
    right: 0;
  }

  /* The module nameplate: flat container plate, ledger-label voice.
     Centred, not baseline-aligned, as Legend Lore's panel head: the
     min-height sets the plate and the name sits in its middle whatever
     shares it. On the baseline, a count's taller line pushed the name
     down, so a plate without one (+ track, the beats) sat higher. */
  .nameplate {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    gap: 0.4rem;
    min-height: 1.9rem;
    padding: 0.4rem 0.6rem 0.3rem;
    background: var(--bg-container);
    border-bottom: 1px solid var(--border-subtle);
  }

  /* A track's pigment fills its plate, as a mixer colours a channel's
     scribble strip, in ink: Legend Lore's selected index cell
     (SearchResults .index-cell), which the palette's lightness is set
     for. Never glows: it names the track, it isn't lit. */
  .nameplate.pigmented {
    background: var(--pigment);
  }

  .nameplate.pigmented .track-name {
    color: var(--text-inverse);
  }

  .nameplate.pigmented .track-number {
    color: color-mix(in srgb, var(--text-inverse) 70%, transparent);
  }

  /* The count keeps its badge whatever the plate: its wash mixed onto the
     plain plate's grey, so the pigment doesn't show through. */
  .nameplate.pigmented .count {
    background: color-mix(in srgb, var(--text-tertiary) 18%, var(--bg-container));
  }

  .nameplate.pigmented .count.in-beat {
    background: color-mix(in srgb, var(--text-accent) 18%, var(--bg-container));
  }

  /* The track's place in the order, as a mixer numbers its channels:
     moving a track renumbers the plates. Small grey figures, quieter than
     the count's badge. Its column is the rows' slots' (.slot): a two-digit
     number spills evenly either side, so the name stays put. */
  /* The number and the track's name on one baseline: centred apart, the
     Crimson figures and the Almendra label sat a pixel apart. The number
     adds no height (line-height: 0), so the pair is as tall as the name
     alone and the name sits where every plate's does. */
  .plate-name {
    flex: 1;
    min-width: 0;
    display: flex;
    align-items: baseline;
    gap: 0.4rem;
  }

  .track-number {
    flex-shrink: 0;
    width: 0.55rem;
    line-height: 0;
    display: flex;
    justify-content: center;
    font-size: 0.75rem;
    font-variant-numeric: tabular-nums;
    color: var(--text-tertiary);
  }

  .track-name {
    min-width: 0;
    padding: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    background: none;
    border: none;
    cursor: pointer;
    color: var(--text-secondary);
    transition: color var(--transition-fast);
  }

  .track-name:hover {
    color: var(--text-primary);
  }

  /* Renaming, the name keeps the plate's face, size and tracking, but in
     the case it's spelled in: a case-only rename has to be seen. */
  .plate-name :global(.rename-field) {
    font-family: var(--font-heading);
    font-size: 0.7rem;
    letter-spacing: 0.08em;
    line-height: 1.2;
  }

  /* The track's count of notes: a beat's count badge (BeatColumn
     .row-count), Legend Lore's LED readout. */
  .count {
    margin-left: auto;
    flex-shrink: 0;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    height: 18px;
    min-width: 18px;
    padding: 0 0.3rem;
    border-radius: var(--radius-sm);
    background: color-mix(in srgb, var(--text-tertiary) 18%, transparent);
    color: var(--text-secondary);
    font-size: 0.65rem;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    line-height: 1;
  }

  /* While a beat is lit, a track holding its notes counts those in place
     of all its own: the lit beat's count badge (BeatColumn .row-count.lit),
     parchment as its notes' squares, so a plate says where to look, below
     the fold too. */
  .count.in-beat {
    background: color-mix(in srgb, var(--text-accent) 18%, transparent);
    color: var(--text-accent);
  }

  .notes {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding: 0.25rem 0.25rem 1rem;
  }

  .group-label {
    margin: 0.5rem 0 0.1rem;
    padding: 0 0.4rem;
    font-size: 0.75rem;
    font-style: italic;
    color: var(--text-tertiary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .note-row,
  .ghost-row {
    display: block;
    width: 100%;
    padding: 0.15rem 0.4rem;
    background: none;
    /* Square, as every list row: a radius bends the open rule's ends. */
    border: none;
    font-family: var(--font-body);
    font-size: 0.9rem;
    line-height: 1.5;
    text-align: left;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    cursor: pointer;
    -webkit-user-select: none;
    user-select: none;
  }

  /* Rows line up with their plate: 0.25rem of list padding and 0.35rem
     here are the plate's 0.6rem inset, so the slot sits under the track's
     number, and the plate's 0.4rem gap puts each note's name under the
     track's. */
  .note-row {
    position: relative;
    display: flex;
    align-items: center;
    gap: 0.4rem;
    padding-left: 0.35rem;
    color: var(--text-primary);
    transition: background var(--transition-fast);
  }

  .note-row.grouped {
    padding-left: 0.85rem;
  }

  .label {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  /* The clip slot, Ableton's square, as one of the splash's lamps
     (LaunchSplash .led): a flat cell, dark until something holds the note,
     half-lit when some planned beat does, lit parchment when the selected
     beat does. Content, not a mode: no glow — the glowing lamp belongs to
     Play's live set. A box, not Font Awesome's square: an SVG path isn't
     snapped to the pixel grid, so its edges smeared at this size. */
  .slot {
    flex-shrink: 0;
    width: 0.55rem;
    height: 0.55rem;
    border-radius: var(--radius-cell);
    background: var(--bg-category);
  }

  .note-row.in-session .slot {
    background: color-mix(in srgb, var(--text-accent) 45%, var(--bg-category));
  }

  .note-row.member .slot {
    background: var(--text-accent);
  }

  .note-row.member .label {
    color: var(--text-accent);
  }

  /* Armed: the slot under the pointer blinks lit, as a splash lamp does
     while its step runs, so the click's meaning shows. */
  .note-row.arming.hovered:not(.member) .slot {
    background: var(--text-accent);
    animation: slot-blink 0.5s steps(1, end) infinite;
  }

  @keyframes slot-blink {
    50% {
      opacity: 0.3;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .note-row.arming.hovered:not(.member) .slot {
      animation: none;
      opacity: 0.55;
    }
  }

  .note-row.spent .label,
  .note-row.spent .slot {
    opacity: var(--opacity-out-of-scope);
  }

  .note-row.spent.hovered .label,
  .note-row.spent.hovered .slot {
    opacity: var(--opacity-out-of-scope-hover);
  }

  /* Outside the live set while a beat is launched: Legend Lore's tree
     while a collection plays (FileTree .out-of-scope). The row's parts dim,
     not the row, so a spent note's own dim doesn't compound and the row's
     ring and drop line stay whole; hover restores it. */
  .note-row.out-of-scope > * {
    opacity: var(--opacity-out-of-scope);
  }

  .note-row.out-of-scope.hovered > * {
    opacity: var(--opacity-out-of-scope-hover);
  }

  .spent-mark {
    flex-shrink: 0;
    font-size: 0.75rem;
    color: var(--text-tertiary);
  }

  /* Legend Lore's row states (FileTree, CollectionsPanel .row-container):
     hover fills a grey step, latched on pointerenter and painted only while
     the pointer drives ($hoverLive), so a closing menu doesn't light the
     row under a still pointer; the selected row rings. Rows take no press
     tick there. */
  .note-row.hovered {
    background: var(--bg-container);
  }

  .note-row.selected {
    box-shadow: var(--ring-focus);
  }

  /* The note in the inspector: content on show, so the parchment wash
     with a parchment rule — not purple, nothing is switched on. */
  .note-row.open {
    background: color-mix(in srgb, var(--text-accent) 10%, transparent);
    box-shadow: inset 2px 0 0 var(--text-accent);
    color: var(--text-accent);
  }

  .note-row.open.selected {
    box-shadow: var(--ring-focus), inset 2px 0 0 var(--text-accent);
  }

  /* Legend Lore's drop line (CollectionsPanel .drop-before) between a
     group's rows: 2px of parchment on the edge the note lands at, the
     dragged row faded. Drawn over the row, as the columns' line is, so an
     open row's rule stays; as there, where the line is the row's shadow,
     it takes a selected row's ring's place. */
  .note-row.dragging {
    opacity: 0.4;
  }

  .note-row.drop-before::after,
  .note-row.drop-after::after {
    content: '';
    position: absolute;
    left: 0;
    right: 0;
    height: 2px;
    background: var(--text-accent);
    pointer-events: none;
  }

  .note-row.drop-before::after {
    top: 0;
  }

  .note-row.drop-after::after {
    bottom: 0;
  }

  .note-row.selected.drop-before,
  .note-row.selected.drop-after {
    box-shadow: none;
  }

  .note-row.open.selected.drop-before,
  .note-row.open.selected.drop-after {
    box-shadow: inset 2px 0 0 var(--text-accent);
  }

  .note-row.ambiguous {
    text-decoration: underline dashed;
    text-decoration-color: var(--text-danger);
    text-underline-offset: 3px;
  }

  .row-edit {
    padding: 0.05rem 0;
    font-size: 0.9rem;
    line-height: 1.5;
  }

  /* A new note's name starts where a note's name does, the slot keeping
     its column. */
  .row-edit.naming {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    padding-left: 0.35rem;
    padding-right: 0.4rem;
  }

  /* The new note's field is a note row's height on its own (the row's
     padding, the same line), so the row takes no padding of its own. */
  .row-edit.naming {
    padding-block: 0;
  }

  /* The empty row under a track's notes, where a new one lands: a note
     row with no name. Hover is the rows' grey step, and its lamp shows
     dark, as the row it would become. */
  .ghost-row {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    padding-left: 0.35rem;
  }

  /* An unseen line of type, so the row is a note row's height to the
     pixel: a min-height rounds differently from a line box. */
  .ghost-row::after {
    content: '\200b';
  }

  .ghost-row .slot {
    background: none;
  }

  .ghost-row:hover {
    background: var(--bg-container);
  }

  .ghost-row:hover .slot {
    background: var(--bg-category);
  }

  .ghost-track:hover {
    color: var(--text-primary);
  }

  /* Keeps the nameplate's ledger-label type, like the plates beside it. */
  .ghost-track {
    padding: 0;
    background: none;
    border: none;
    color: var(--text-tertiary);
    cursor: pointer;
    white-space: nowrap;
  }
</style>
