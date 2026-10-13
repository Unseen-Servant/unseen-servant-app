<script lang="ts">
  // The beat launcher (design §5.1): the active session's plan in order,
  // then beats no plan holds yet. It works as Legend Lore's collections
  // panel does. Clicking a beat selects it — its notes light up across the
  // tracks — and a double-click opens it, as rows do in Legend Lore. Arming
  // a beat (the record-arm key at the row's end, a collection's transport)
  // makes a click on a note put it in the beat or take it out, and a note
  // dragged onto a beat joins it. The play key beside it launches the beat,
  // as a collection's plays, and the lit ■ stops what's live; the live beat
  // wears the rule at its left edge, as a playing collection does. Two
  // groups, each headed: the session's plan, then the beats not in it.
  // Spent beats outside the plan are put away until asked for, as archived
  // collections are.
  import InlineName from './InlineName.svelte';
  import { hoverLive } from '../ui/inputModality';
  import CommandMenu from './CommandMenu.svelte';
  import { CARET_RIGHT, CIRCLE, CIRCLE_RING, PLAY } from '../ui/iconPaths';
  import { action, divider, heading, type MenuItem, type OpenMenu } from './menu';
  import { draggedNote, isNoteDrag } from './noteDrag';
  import { planMoveTo, type PlanRow } from './prep';
  import type { BeatEntry, NoteEntry } from './types';

  export let rows: PlanRow[];
  /** Beats no plan of the session holds, spent ones included. */
  export let spare: BeatEntry[];
  export let sessionName: string | null;
  export let selectedPath: string | null;
  export let armedPath: string | null;
  /** The beat whose notes are lit in the tracks: its count turns parchment. */
  export let litPath: string | null;
  /** A click: the beat lights, or puts its notes out if it was lit. */
  export let onSelect: (beat: BeatEntry) => void;
  export let onOpen: (beat: BeatEntry) => void;
  export let onArm: (beat: BeatEntry) => void;
  /** The beat the live set was launched from. */
  export let liveBeat: string | null;
  export let onLaunch: (beat: BeatEntry) => void;
  /** Clears the live set. */
  export let onStop: () => void;
  /** A new beat, holding the note dropped to start it, if any. */
  export let onCreate: (name: string, notes: string[]) => void;
  export let onWrite: (row: PlanRow) => void;
  /** Into the plan, at `to` or the end. */
  export let onAddToPlan: (beat: BeatEntry, to?: number) => void;
  export let onMove: (row: PlanRow, to: number) => void;
  export let onRemove: (row: PlanRow) => void;
  export let onRename: (beat: BeatEntry, name: string) => void;
  export let onSpent: (beat: BeatEntry, spent: boolean) => void;
  export let onReveal: (beat: BeatEntry) => void;
  export let onTrash: (beat: BeatEntry) => void;
  /** A note dropped on a beat joins it. */
  export let onDropNote: (beat: BeatEntry, path: string) => void;
  /** The beats on show outside the plan, in the order they were dragged. */
  export let onReorder: (names: string[]) => void;

  let creating = false;
  let renamingPath: string | null = null;
  let menu: OpenMenu | null = null;

  // Legend Lore's "Show archived": local to the column, and only offered
  // while there's something to show.
  let showSpent = false;

  // Groups folded shut, as Legend Lore's filter sections: for this sitting
  // only. A folded group's title still owns up to an armed or live beat in
  // it, with Legend Lore's section lamp. Without a session there are no
  // titles, so nothing stays folded out of reach.
  let folded = new Set<'plan' | 'spare'>();
  function fold(group: 'plan' | 'spare') {
    if (folded.has(group)) folded.delete(group);
    else folded.add(group);
    folded = folded;
  }
  $: planOpen = !sessionName || !folded.has('plan');
  $: spareOpen = !sessionName || !folded.has('spare');
  $: planLit = rows.some((r) => !!r.beat && (r.beat.path === armedPath || r.beat.path === liveBeat));
  $: spentCount = spare.filter((b) => b.spent).length;
  $: if (!spentCount) showSpent = false;
  $: shown = showSpent ? spare : spare.filter((b) => !b.spent);
  $: spareLit = shown.some((b) => b.path === armedPath || b.path === liveBeat);

  // Hover latched on pointerenter, as Legend Lore's rows (FileTree).
  let hovered: string | null = null;
  function leave(path: string) {
    if (hovered === path) hovered = null;
  }

  // -- dragging, as Legend Lore's collections panel takes it ---------------
  //
  // Two drags reach the column, told apart by their private types (a
  // dragover can read nothing else). Its own beats: dropped between plan
  // rows they move within the plan or join it there; dropped between the
  // spare beats they move there, leaving the plan if they came from it, an
  // order the campaign keeps; dropped on a group's title they join that
  // group, the plan at its end or the beats not in this session. Notes from the grid or the shelf: dropped on a
  // beat they join it, and on the ghost row they start a new one.
  const BEAT_MIME = 'application/x-command-beat';
  const isBeatDrag = (e: DragEvent) => Array.from(e.dataTransfer?.types ?? []).some((t) => t.toLowerCase() === BEAT_MIME);

  /** The beat being dragged: a plan entry, or a beat no plan holds. */
  let dragging: PlanRow | BeatEntry | null = null;
  /** Where a beat drop lands: before plan row `dropSlot`, or after the last. */
  let dropSlot: number | null = null;
  /** The group title a beat is over: the drop moves it into that group. */
  let dropOn: 'plan' | 'spare' | null = null;
  /** Where a beat dragged among the spare beats lands: before spare row
   *  `dropSpare`, or after the last. */
  let dropSpare: number | null = null;
  /** The beat a note drop would join. */
  let dropInto: string | null = null;
  /** A note over the ghost row: the drop starts a beat with it. */
  let incoming: NoteEntry | null = null;
  /** The note a drop on the ghost row started the new beat with. */
  let seed: NoteEntry | null = null;

  $: draggingEntry = !!dragging && 'at' in dragging;

  function clearDrop() {
    dropSlot = null;
    dropOn = null;
    dropSpare = null;
    dropInto = null;
    incoming = null;
  }

  function startBeatDrag(e: DragEvent, item: PlanRow | BeatEntry, name: string) {
    dragging = item;
    if (!e.dataTransfer) return;
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData(BEAT_MIME, name);
    e.dataTransfer.setData('text/plain', `[[${name}]]`);
  }

  // A drag delivers no pointerleave, and the drop reorders rows under a
  // pointer that hasn't moved: unlatch, as Legend Lore's panel does.
  function endBeatDrag() {
    dragging = null;
    clearDrop();
    hovered = null;
  }

  /** A beat over plan row `i` (the ghost row is `rows.length`) points
   *  between rows, by which half of the row the pointer is in. With no
   *  session there's no plan to drop into. */
  function overSlot(e: DragEvent, i: number) {
    if (!dragging || !isBeatDrag(e) || !sessionName) return;
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
    const box = (e.currentTarget as HTMLElement).getBoundingClientRect();
    clearDrop();
    dropSlot = i < rows.length && e.clientY >= box.top + box.height / 2 ? i + 1 : i;
  }

  function overBeat(e: DragEvent, beat: BeatEntry) {
    if (!isNoteDrag(e)) return;
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy';
    clearDrop();
    dropInto = beat.path;
  }

  function overGhost(e: DragEvent) {
    overSlot(e, rows.length);
    if (!isNoteDrag(e)) return;
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy';
    clearDrop();
    incoming = draggedNote();
  }

  /** A beat over a group's title, lit as a beat is under a note: a spare
   *  beat over the session's joins the end of the plan, as the menu's Add
   *  does, and a plan entry over "not in this session" leaves the plan. A
   *  title takes nothing from its own group. */
  function overHead(e: DragEvent, group: 'plan' | 'spare') {
    if (!dragging || !isBeatDrag(e) || ('at' in dragging) !== (group === 'spare')) return;
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
    clearDrop();
    dropOn = group;
  }

  /** A beat over spare row `i` points between rows, as in the plan: a
   *  spare beat moves there, and a plan entry leaves the plan and lands
   *  there. The beats outside a plan keep the order the GM drags them into. */
  function overSpareSlot(e: DragEvent, i: number) {
    if (!dragging || !isBeatDrag(e)) return;
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
    const box = (e.currentTarget as HTMLElement).getBoundingClientRect();
    clearDrop();
    dropSpare = e.clientY >= box.top + box.height / 2 ? i + 1 : i;
  }

  function dropBeat(e: DragEvent) {
    if (!dragging || !isBeatDrag(e)) return false;
    e.preventDefault();
    const drag = dragging;
    const slot = dropSlot;
    const on = dropOn;
    const spareAt = dropSpare;
    endBeatDrag();
    if ('at' in drag) {
      if (on === 'spare') onRemove(drag);
      else if (spareAt !== null) {
        onRemove(drag);
        // A plan entry naming no beat yet has nothing to place.
        if (drag.beat) {
          const names = shown.map((b) => b.name);
          names.splice(spareAt, 0, drag.beat.name);
          onReorder(names);
        }
      } else if (slot !== null) {
        const to = planMoveTo(drag.at, slot);
        if (to !== null) onMove(drag, to);
      }
    } else if (on === 'plan') onAddToPlan(drag);
    else if (slot !== null) onAddToPlan(drag, slot);
    else if (spareAt !== null) {
      const from = shown.indexOf(drag);
      const to = from < 0 ? null : planMoveTo(from, spareAt);
      if (to !== null) {
        const names = shown.map((b) => b.name);
        names.splice(to, 0, ...names.splice(from, 1));
        onReorder(names);
      }
    }
    return true;
  }

  function dropNote(e: DragEvent, beat: BeatEntry) {
    if (!isNoteDrag(e)) return;
    e.preventDefault();
    const note = draggedNote();
    clearDrop();
    hovered = null;
    if (note) onDropNote(beat, note.path);
  }

  function dropOnGhost(e: DragEvent) {
    if (dropBeat(e) || !isNoteDrag(e)) return;
    e.preventDefault();
    seed = draggedNote();
    clearDrop();
    hovered = null;
    creating = true;
  }

  // Off every target, nothing stays lit: a row that takes the drag claims it
  // (preventDefault) before it bubbles here.
  function overList(e: DragEvent) {
    if (!e.defaultPrevented) clearDrop();
  }

  function leaveList(e: DragEvent) {
    if (!(e.currentTarget as HTMLElement).contains(e.relatedTarget as Node | null)) clearDrop();
  }

  // The transport first, as a collection's menu has it.
  function transportItems(beat: BeatEntry): MenuItem[] {
    return [
      action(beat.path === armedPath ? 'Disarm' : 'Arm', () => onArm(beat)),
      beat.path === liveBeat ? action('Stop', onStop) : action('Launch', () => onLaunch(beat)),
    ];
  }

  function beatItems(beat: BeatEntry): MenuItem[] {
    return [
      action('Rename', () => (renamingPath = beat.path)),
      action(beat.spent ? 'Mark unspent' : 'Mark spent', () => onSpent(beat, !beat.spent)),
      divider,
      action('Show in Finder', () => onReveal(beat)),
      action('Move to Trash', () => onTrash(beat), true),
    ];
  }

  function rowMenu(e: MouseEvent, row: PlanRow) {
    const order: MenuItem[] = [
      ...(row.at > 0 ? [action('Move up', () => onMove(row, row.at - 1))] : []),
      ...(row.at < rows.length - 1 ? [action('Move down', () => onMove(row, row.at + 1))] : []),
      action(`Remove from ${sessionName}`, () => onRemove(row)),
    ];
    const items = row.beat
      ? [...transportItems(row.beat), divider, ...order, divider, ...beatItems(row.beat)]
      : [...order, divider, action('Write this beat', () => onWrite(row))];
    menu = { x: e.clientX, y: e.clientY, items };
  }

  function spareMenu(e: MouseEvent, beat: BeatEntry) {
    menu = {
      x: e.clientX,
      y: e.clientY,
      items: [
        ...transportItems(beat),
        divider,
        ...(sessionName ? [action(`Add to ${sessionName}`, () => onAddToPlan(beat)), divider] : []),
        ...beatItems(beat),
      ],
    };
  }
</script>

<!-- `row` is the plan entry the beat stands in, null for a spare beat. -->
{#snippet beatRow(beat: BeatEntry, row: PlanRow | null, onMenu: (e: MouseEvent) => void)}
  {#if renamingPath === beat.path}
    <div class="row-edit">
      <InlineName
        value={beat.name}
        rename
        label="Rename beat"
        onCommit={(name) => {
          renamingPath = null;
          onRename(beat, name);
        }}
        onCancel={() => (renamingPath = null)}
      />
    </div>
  {:else}
    {@const armed = beat.path === armedPath}
    {@const playing = beat.path === liveBeat}
    <div
      class="beat-row"
      data-row
      class:selected={beat.path === selectedPath}
      class:live={playing}
      class:armed
      class:spent={!!beat.spent}
      class:hovered={$hoverLive && hovered === beat.path}
      class:dragging={dragging !== null && dragging === (row ?? beat)}
      class:drop-before={row ? dropSlot === row.at : dropSpare !== null && shown[dropSpare] === beat}
      class:drop-after={!row && dropSpare === shown.length && shown[shown.length - 1] === beat}
      class:drop-into={dropInto === beat.path}
      draggable="true"
      on:dragstart={(e) => startBeatDrag(e, row ?? beat, beat.name)}
      on:dragend={endBeatDrag}
      on:dragover={(e) => {
        if (row) overSlot(e, row.at);
        else overSpareSlot(e, shown.indexOf(beat));
        overBeat(e, beat);
      }}
      on:drop={(e) => {
        if (!dropBeat(e)) dropNote(e, beat);
      }}
      on:contextmenu|preventDefault={onMenu}
      on:pointerenter={() => (hovered = beat.path)}
      on:pointerleave={() => leave(beat.path)}
      role="presentation"
    >
      <button
        type="button"
        class="beat-name"
        title={beat.spent ? `${beat.name} — spent ${beat.spent}` : beat.name}
        on:click={(e) => {
          // Only a double-click's first click: the second mustn't put out
          // what the first lit on the way into the editor.
          if (e.detail <= 1) onSelect(beat);
        }}
        on:dblclick={() => onOpen(beat)}
      >
        {beat.name}
      </button>
      {#if beat.spent}
        <span class="spent-mark" aria-label="spent">✓</span>
      {/if}
      <!-- The keys take a double-click's first click only: its second would
           undo the first, so a launch stopped at once and played nothing. -->
      <span class="tr" class:engaged={armed || playing}>
        <button
          type="button"
          class="tr-btn"
          class:armed
          aria-pressed={armed}
          title={armed ? `Disarm ${beat.name} (Esc)` : `Arm ${beat.name}: click notes to put them in it`}
          on:click={(e) => e.detail <= 1 && onArm(beat)}
        >
          <svg class="arm-glyph" viewBox="64 64 512 512" fill="currentColor" aria-hidden="true">
            <path d={armed ? CIRCLE : CIRCLE_RING} />
          </svg>
        </button>
        <button
          type="button"
          class="tr-btn"
          class:playing
          aria-pressed={playing}
          title={playing ? `Stop ${beat.name}` : `Launch ${beat.name}: its notes go live`}
          on:click={(e) => e.detail <= 1 && (playing ? onStop() : onLaunch(beat))}
        >
          {#if playing}
            <span class="stop-mark" aria-hidden="true"></span>
          {:else}
            <svg viewBox="0 0 640 640" fill="currentColor" aria-hidden="true"><path d={PLAY} /></svg>
          {/if}
        </button>
      </span>
      <span class="row-count" class:lit={beat.path === litPath}>{beat.notes.length}</span>
    </div>
  {/if}
{/snippet}

<!-- A group's title: the fold toggle, and a drop target for beats from the
     other group. -->
{#snippet groupHead(group: 'plan' | 'spare', label: string, count: number, lit: boolean)}
  {@const open = !folded.has(group)}
  <button
    type="button"
    class="group-head"
    class:spare-head={group === 'spare'}
    class:drop-into={dropOn === group}
    aria-expanded={open}
    on:click={() => fold(group)}
    on:dragover={(e) => overHead(e, group)}
    on:drop={dropBeat}
  >
    <svg class="caret" class:open viewBox="96 64 512 512" fill="currentColor" aria-hidden="true"><path d={CARET_RIGHT} /></svg>
    <span class="ledger-label">{label}</span>
    {#if !open && lit}
      <span class="sect-lamp" role="img" aria-label="A beat in here is armed or live" title="A beat in here is armed or live"></span>
    {/if}
    <span class="count">{count}</span>
  </button>
{/snippet}

<section class="beats" aria-label="Beats">
  <header class="nameplate">
    <span class="ledger-label title">beats</span>
    {#if spentCount}
      <button
        type="button"
        class="plate-btn"
        aria-pressed={showSpent}
        title={showSpent ? 'Put away spent beats no plan holds' : `Show ${spentCount} spent beat${spentCount === 1 ? '' : 's'} no plan holds`}
        on:click={() => (showSpent = !showSpent)}
      >{showSpent ? 'hide spent' : 'show spent'}</button>
    {/if}
  </header>

  <div class="list" role="presentation" on:dragover={overList} on:dragleave={leaveList}>
    <!-- Without a session there's one group, all the beats, and the plate
         already names it. -->
    {#if sessionName}
      {@render groupHead('plan', sessionName, rows.length, planLit)}
    {/if}
    {#if planOpen}
      {#each rows as row (row.at + ':' + row.link)}
        {#if row.beat}
          {@const beat = row.beat}
          {@render beatRow(beat, row, (e) => rowMenu(e, row))}
        {:else}
          <button
            type="button"
            class="beat-row missing"
            data-row
            class:hovered={$hoverLive && hovered === row.link}
            class:dragging={dragging === row}
            class:drop-before={dropSlot === row.at}
            title={`No beat is named “${row.link}” yet — click to write it`}
            draggable="true"
            on:dragstart={(e) => startBeatDrag(e, row, row.link)}
            on:dragend={endBeatDrag}
            on:dragover={(e) => overSlot(e, row.at)}
            on:drop={dropBeat}
            on:click={() => onWrite(row)}
            on:pointerenter={() => (hovered = row.link)}
            on:pointerleave={() => leave(row.link)}
            on:contextmenu|preventDefault={(e) => rowMenu(e, row)}
          >
            <span class="beat-name">{row.link}</span>
          </button>
        {/if}
      {/each}

      <!-- Legend Lore's ghost track: the next beat, waiting, drawn as a row in
           outline. It sits after the plan, where a new beat lands. Naming
           dresses it as the row it becomes; nothing exists until Enter. A
           note dropped on it starts the beat with that note. -->
      {#if creating}
        <div class="beat-row ghost naming">
          <InlineName
            bare
            placeholder={seed ? `Beat with ${seed.name}…` : 'Beat name…'}
            label="New beat"
            onCommit={(name) => {
              creating = false;
              onCreate(name, seed ? [seed.path] : []);
              seed = null;
            }}
            onCancel={() => {
              creating = false;
              seed = null;
            }}
          />
          <!-- A new beat lands armed: say so before it exists, in the column
               its arm key will take. Not a control. -->
          <span class="tr engaged" aria-hidden="true">
            <span class="tr-btn armed promise">
              <svg class="arm-glyph" viewBox="64 64 512 512" fill="currentColor"><path d={CIRCLE} /></svg>
            </span>
            <span class="key-slot"></span>
          </span>
          {#if seed}
            <span class="row-count">1</span>
          {:else}
            <span class="count-slot" aria-hidden="true"></span>
          {/if}
        </div>
        <div class="ghost-keys micro-label" aria-hidden="true">
          <span><kbd>↵</kbd> create</span><span><kbd>esc</kbd> back</span>
        </div>
      {:else}
        <button
          type="button"
          class="beat-row ghost"
          class:drop-before={dropSlot === rows.length}
          class:drop-into={incoming !== null}
          title="New beat — or drop a note here"
          on:click={() => (creating = true)}
          on:dragover={overGhost}
          on:drop={dropOnGhost}
        >
          <!-- Under a drag, say what the drop will make. One label throughout:
               swapping the element under the pointer mid-drag detaches the
               drag's target, and WebKit then refuses the drop. -->
          <span class="ghost-label">New beat{#if incoming}&nbsp;with <em>{incoming.name}</em>{/if}</span>
          {#if incoming}<span class="row-count">1</span>{/if}
        </button>
        {#if !rows.length && !spare.length}
          <div class="ledger-label empty-hint">or drag a note here</div>
        {/if}
      {/if}
    {/if}

    <!-- While a plan entry is dragged, this title shows even with no spare
         beats under it: dropped on it, the entry leaves the plan. -->
    {#if shown.length || draggingEntry}
      {#if sessionName}
        {@render groupHead('spare', 'not in this session', shown.length, spareLit)}
      {/if}
      {#if spareOpen}
        {#each shown as beat (beat.path)}
          {@render beatRow(beat, null, (e) => spareMenu(e, beat))}
        {/each}
      {/if}
    {/if}
  </div>
</section>

{#if menu}
  <CommandMenu x={menu.x} y={menu.y} items={menu.items} onClose={() => (menu = null)} />
{/if}

<style>
  /* Room for a name beside the transport and the count. With the
     shelf open at 1280px, the grid scrolls to reach its + track column. */
  .beats {
    flex: 0 0 15rem;
    min-width: 0;
    display: flex;
    flex-direction: column;
    min-height: 0;
    /* The shelf's seam on the grid's other side: Legend Lore's dock edge. */
    border-left: 4px solid var(--border-subtle);
  }

  /* Centred, not baseline-aligned, as Legend Lore's panel head: the
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

  .title {
    flex: 1;
    color: var(--text-secondary);
  }

  /* A group's title, the fold toggle of Legend Lore's filter sections
     (FilterPanel .sect-toggle): the caret, what the group holds, and how
     many over the rows' counts. Hover is a step up the text ramp, as there. */
  .group-head {
    display: flex;
    align-items: baseline;
    gap: 0.3rem;
    width: 100%;
    margin: 0.2rem 0 0.05rem;
    /* Room inside for the drop outline when a beat is dragged over it. On
       the left, the caret sits under the plate's title as the filter
       panel's sits under FILTERS: its box 0.45rem - 3px before the title
       (there 0.75rem against 0.3rem + 3px), here the plate's 0.6rem inset
       less the list's 0.25rem padding. */
    padding: 0.15rem calc(0.35rem + 0.3rem) 0.15rem calc(0.6rem - 0.25rem - 0.45rem + 3px);
    background: none;
    border: none;
    font: inherit;
    text-align: left;
    cursor: pointer;
  }

  .group-head .ledger-label {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    transition: color var(--transition-fast);
  }

  /* The label's size; centred, since an <svg> sits on the baseline by its
     bottom edge (FilterPanel .sect-arrow). */
  .group-head .caret {
    align-self: center;
    width: 0.7rem;
    height: 0.7rem;
    color: var(--text-tertiary);
  }

  .group-head:hover .ledger-label,
  .group-head:hover .caret {
    color: var(--text-secondary);
  }

  /* Legend Lore's section lamp (FilterPanel .sect-lamp): lit face only, on
     a folded group holding the armed or the live beat. */
  .sect-lamp {
    align-self: center;
    flex-shrink: 0;
    width: 10px;
    height: 2px;
    border-radius: var(--radius-sm);
    background: var(--text-active);
    filter: var(--glow-active);
  }

  .list {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding: 0.25rem 0.25rem 1rem;
  }

  .beat-row {
    display: flex;
    align-items: center;
    gap: 0.3rem;
    width: 100%;
    padding: 0.1rem 0.35rem;
    border: none;
    /* Legend Lore's rule slot (CollectionsPanel .row-container), reserved so
       arming or launching doesn't shift the row. Square, as its rows are:
       a radius bends the rule's ends. */
    border-left: 3px solid transparent;
    background: none;
    font-family: var(--font-body);
    font-size: 0.9rem;
    line-height: 1.5;
    text-align: left;
    color: var(--text-primary);
    transition: background var(--transition-fast);
  }

  /* Legend Lore's row states, as on the note rows: a latched grey-step
     hover, and a ring on the selected beat, whose notes are lit across the
     tracks. */
  .beat-row.hovered {
    background: var(--bg-container);
  }

  .beat-row.selected {
    box-shadow: var(--ring-focus);
  }

  /* The live beat, the one launched: a playing collection's parchment
     wash and purple rule, as Play's arrangement marks the same beat. */
  .beat-row.live {
    background: color-mix(in srgb, var(--text-accent) 8%, transparent);
    border-left-color: var(--text-active);
  }

  /* Armed: the row Legend Lore wears for the collection you're editing —
     parchment wash, purple rule. */
  .beat-row.armed {
    background: color-mix(in srgb, var(--text-accent) 25%, transparent);
    border-left-color: var(--text-active);
  }

  .beat-row.spent .beat-name {
    opacity: var(--opacity-out-of-scope);
  }

  .beat-row.spent.hovered .beat-name {
    opacity: var(--opacity-out-of-scope-hover);
  }

  .beat-name {
    flex: 1;
    min-width: 0;
    padding: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    background: none;
    border: none;
    font: inherit;
    text-align: left;
    color: inherit;
    cursor: pointer;
    -webkit-user-select: none;
    user-select: none;
  }

  .beat-row.missing {
    cursor: pointer;
  }

  .beat-row.missing .beat-name {
    color: var(--text-secondary);
    text-decoration: underline dashed;
    text-decoration-color: var(--text-accent);
    text-underline-offset: 3px;
  }

  /* The arm and play keys as a collection's transport (CollectionsPanel
     .tr): hidden at rest, shown on the hovered or selected row, kept while
     armed or live. */
  .tr {
    display: inline-flex;
    gap: 0.25rem;
    flex-shrink: 0;
    opacity: 0;
    transition: opacity var(--transition-fast);
  }

  .beat-row.hovered .tr,
  .beat-row.selected .tr,
  .tr.engaged {
    opacity: 1;
  }

  /* Legend Lore's transport keys: a glyph in a well, purple and lit once
     armed or playing. */
  .tr-btn {
    flex-shrink: 0;
    width: 18px;
    height: 18px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0;
    background: transparent;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    color: var(--text-tertiary);
    cursor: pointer;
    transition: all var(--transition-fast);
  }

  .tr-btn:hover {
    color: var(--text-secondary);
    border-color: var(--text-secondary);
  }

  .tr-btn:active {
    transform: scale(0.97);
  }

  .tr-btn.armed,
  .tr-btn.playing {
    color: var(--text-active);
    border-color: var(--text-active);
    background: color-mix(in srgb, var(--text-active) 15%, transparent);
    filter: var(--glow-active);
  }

  .tr-btn svg {
    display: block;
    width: 9px;
    height: 9px;
  }

  /* Even sizes centre on whole pixels in the 16px well, as in Legend Lore;
     the ▶ stays 9px, off-centre on purpose. */
  .tr-btn .arm-glyph {
    width: 8px;
    height: 8px;
  }

  .stop-mark {
    width: 6px;
    height: 6px;
    background: currentColor;
  }

  .count,
  .spent-mark {
    flex-shrink: 0;
    font-size: 0.75rem;
    font-variant-numeric: tabular-nums;
    color: var(--text-tertiary);
  }

  /* Legend Lore's LED count readout (CollectionsPanel .row-count), so a
     beat's size reads as a collection's. */
  .row-count,
  .count-slot,
  .key-slot {
    flex-shrink: 0;
    height: 18px;
    min-width: 18px;
  }

  .row-count {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0 0.3rem;
    border-radius: var(--radius-sm);
    background: color-mix(in srgb, var(--text-tertiary) 18%, transparent);
    color: var(--text-secondary);
    font-size: 0.65rem;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    line-height: 1;
  }

  /* The lit beat's count, in the parchment of its notes' squares across
     the tracks: which beat lights them, at a glance. */
  .row-count.lit {
    background: color-mix(in srgb, var(--text-accent) 18%, transparent);
    color: var(--text-accent);
  }

  /* A rename takes the name's place, as in Legend Lore: the field starts
     where the name did, past the row's 3px rule. */
  .row-edit {
    display: flex;
    align-items: center;
    padding: 0.05rem 0.35rem 0.05rem calc(0.35rem + 3px);
    font-size: 0.9rem;
    line-height: 1.5;
  }

  /* Legend Lore's ghost track (CollectionsPanel .ghost): a row's geometry
     in outline, an italic tertiary name. Hover is the rows' grey step. */
  .ghost {
    color: var(--text-tertiary);
    cursor: pointer;
  }

  .ghost:hover {
    background: var(--bg-container);
    color: var(--text-secondary);
  }

  .ghost-label {
    flex: 1;
    min-width: 0;
    font-style: italic;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  /* Naming in place: the slot already dresses as the row it will become —
     the wash and purple rule, and the caret's ring. */
  .ghost.naming {
    cursor: default;
    background: color-mix(in srgb, var(--text-accent) 8%, transparent);
    border-left-color: var(--text-active);
    box-shadow: var(--ring-focus);
  }

  /* The arm the row will land with — purple ink, but no glow: a glow
     reports a state you switched on, and this is only a promise. */
  .tr-btn.promise {
    cursor: default;
    filter: none;
  }

  /* Key hints under the naming row, starting in the name's column. */
  .ghost-keys {
    display: flex;
    gap: 0.75rem;
    padding: 0.2rem 0.35rem 0.35rem calc(0.35rem + 3px);
  }

  .ghost-keys kbd {
    font-family: var(--font-mono);
    letter-spacing: 0;
    text-transform: none;
    color: var(--text-secondary);
  }

  .spare-head {
    margin-top: 0.85rem;
  }

  .empty-hint {
    padding: 0.3rem 0.35rem 0.5rem calc(0.35rem + 3px);
  }

  /* Under a drag, as Legend Lore's collections panel: the dragged row fades,
     an accent rule marks where a beat would land in the plan, and the
     dashed parchment "could become a member" outline marks what a drop
     would join: a beat under a note, a group's title under a beat. */
  .beat-row.dragging {
    opacity: 0.4;
  }

  .beat-row.drop-before {
    box-shadow: inset 0 2px 0 var(--text-accent);
  }

  .beat-row.drop-after {
    box-shadow: inset 0 -2px 0 var(--text-accent);
  }

  .beat-row.drop-into,
  .group-head.drop-into {
    outline: var(--outline-drop);
    outline-offset: -1px;
    background: var(--bg-container);
  }

  /* The ghost under a note drag says what it will make. */
  .ghost.drop-into {
    background: color-mix(in srgb, var(--text-accent) 8%, transparent);
    color: var(--text-accent);
  }

  .ghost.drop-into .ghost-label {
    font-style: normal;
  }
</style>
