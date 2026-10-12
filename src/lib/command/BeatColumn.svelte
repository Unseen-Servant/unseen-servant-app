<script lang="ts">
  // The beat launcher (design §5.1): the active session's plan in order,
  // then beats no plan holds yet. It works as Legend Lore's collections
  // panel does. Clicking a beat selects it — its notes light up across the
  // tracks — and a double-click opens it, as rows do in Legend Lore. Arming
  // a beat (the record-arm key at the row's end, a collection's transport)
  // makes a click on a note put it in the beat or take it out. Spent beats
  // outside the plan are put away until asked for, as archived collections
  // are.
  import InlineName from './InlineName.svelte';
  import { hoverLive } from '../ui/inputModality';
  import CommandMenu from './CommandMenu.svelte';
  import { CIRCLE, CIRCLE_RING } from '../ui/iconPaths';
  import { action, divider, heading, type MenuItem, type OpenMenu } from './menu';
  import type { PlanRow } from './prep';
  import type { BeatEntry } from './types';

  export let rows: PlanRow[];
  /** Beats no plan of the session holds, spent ones included. */
  export let spare: BeatEntry[];
  export let sessionName: string | null;
  export let selectedPath: string | null;
  export let armedPath: string | null;
  /** The note in the editor, a beat when one is open. */
  export let openPath: string | null;
  export let onSelect: (beat: BeatEntry) => void;
  export let onOpen: (beat: BeatEntry) => void;
  export let onArm: (beat: BeatEntry) => void;
  export let onCreate: (name: string) => void;
  export let onWrite: (row: PlanRow) => void;
  export let onAddToPlan: (beat: BeatEntry) => void;
  export let onMove: (row: PlanRow, to: number) => void;
  export let onRemove: (row: PlanRow) => void;
  export let onRename: (beat: BeatEntry, name: string) => void;
  export let onSpent: (beat: BeatEntry, spent: boolean) => void;
  export let onReveal: (beat: BeatEntry) => void;
  export let onTrash: (beat: BeatEntry) => void;

  let creating = false;
  let renamingPath: string | null = null;
  let menu: OpenMenu | null = null;

  // Legend Lore's "Show archived": local to the column, and only offered
  // while there's something to show.
  let showSpent = false;
  $: spentCount = spare.filter((b) => b.spent).length;
  $: if (!spentCount) showSpent = false;
  $: shown = showSpent ? spare : spare.filter((b) => !b.spent);

  // Hover latched on pointerenter, as Legend Lore's rows (FileTree).
  let hovered: string | null = null;
  function leave(path: string) {
    if (hovered === path) hovered = null;
  }

  // The transport first, as a collection's menu has it.
  function armItem(beat: BeatEntry): MenuItem {
    return action(beat.path === armedPath ? 'Disarm' : 'Arm', () => onArm(beat));
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
      ? [armItem(row.beat), divider, ...order, divider, ...beatItems(row.beat)]
      : [...order, divider, action('Write this beat', () => onWrite(row))];
    menu = { x: e.clientX, y: e.clientY, items };
  }

  function spareMenu(e: MouseEvent, beat: BeatEntry) {
    menu = {
      x: e.clientX,
      y: e.clientY,
      items: [
        armItem(beat),
        divider,
        ...(sessionName ? [action(`Add to ${sessionName}`, () => onAddToPlan(beat)), divider] : []),
        ...beatItems(beat),
      ],
    };
  }
</script>

{#snippet beatRow(beat: BeatEntry, onMenu: (e: MouseEvent) => void)}
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
    <div
      class="beat-row"
      class:selected={beat.path === selectedPath}
      class:open={beat.path === openPath}
      class:armed
      class:spent={!!beat.spent}
      class:hovered={$hoverLive && hovered === beat.path}
      on:contextmenu|preventDefault={onMenu}
      on:pointerenter={() => (hovered = beat.path)}
      on:pointerleave={() => leave(beat.path)}
      role="presentation"
    >
      <button
        type="button"
        class="beat-name"
        title={beat.spent ? `${beat.name} — spent ${beat.spent}` : beat.name}
        on:click={() => onSelect(beat)}
        on:dblclick={() => onOpen(beat)}
      >
        {beat.name}
      </button>
      {#if beat.spent}
        <span class="spent-mark" aria-label="spent">✓</span>
      {/if}
      <span class="tr" class:engaged={armed}>
        <button
          type="button"
          class="arm-btn"
          class:armed
          aria-pressed={armed}
          title={armed ? `Disarm ${beat.name} (Esc)` : `Arm ${beat.name}: click notes to put them in it`}
          on:click={() => onArm(beat)}
        >
          <svg class="arm-glyph" viewBox="64 64 512 512" fill="currentColor" aria-hidden="true">
            <path d={armed ? CIRCLE : CIRCLE_RING} />
          </svg>
        </button>
      </span>
      <span class="row-count">{beat.notes.length}</span>
    </div>
  {/if}
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
    <span class="count">{rows.length}</span>
  </header>

  <div class="list">
    {#each rows as row (row.at + ':' + row.link)}
      {#if row.beat}
        {@const beat = row.beat}
        {@render beatRow(beat, (e) => rowMenu(e, row))}
      {:else}
        <button
          type="button"
          class="beat-row missing"
          class:hovered={$hoverLive && hovered === row.link}
          title={`No beat is named “${row.link}” yet — click to write it`}
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
         dresses it as the row it becomes; nothing exists until Enter. -->
    {#if creating}
      <div class="beat-row ghost naming">
        <InlineName
          bare
          placeholder="Beat name…"
          label="New beat"
          onCommit={(name) => {
            creating = false;
            onCreate(name);
          }}
          onCancel={() => (creating = false)}
        />
        <!-- A new beat lands armed: say so before it exists, in the column
             its arm key will take. Not a control. -->
        <span class="arm-btn armed promise" aria-hidden="true">
          <svg class="arm-glyph" viewBox="64 64 512 512" fill="currentColor"><path d={CIRCLE} /></svg>
        </span>
        <span class="count-slot" aria-hidden="true"></span>
      </div>
      <div class="ghost-keys micro-label" aria-hidden="true">
        <span><kbd>↵</kbd> create</span><span><kbd>esc</kbd> back</span>
      </div>
    {:else}
      <button type="button" class="beat-row ghost" title="New beat" on:click={() => (creating = true)}>
        <span class="ghost-label">New beat</span>
      </button>
    {/if}

    {#if shown.length}
      <div class="ledger-label spare-head">{sessionName ? 'not in this session' : 'beats'}</div>
      {#each shown as beat (beat.path)}
        {@render beatRow(beat, (e) => spareMenu(e, beat))}
      {/each}
    {/if}
  </div>
</section>

{#if menu}
  <CommandMenu x={menu.x} y={menu.y} items={menu.items} onClose={() => (menu = null)} />
{/if}

<style>
  .beats {
    flex: 0 0 11.5rem;
    min-width: 0;
    display: flex;
    flex-direction: column;
    min-height: 0;
    /* The shelf's seam on the grid's other side: Legend Lore's dock edge. */
    border-left: 4px solid var(--border-subtle);
  }

  .nameplate {
    flex-shrink: 0;
    display: flex;
    align-items: baseline;
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
    border-left: 2px solid transparent;
    border-radius: var(--radius-sm);
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

  /* Open in the inspector: content on show, so parchment, the same wash
     and rule as a note open there. */
  .beat-row.open {
    background: color-mix(in srgb, var(--text-accent) 10%, transparent);
    border-left-color: var(--text-accent);
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

  /* The arm key as a collection's transport (CollectionsPanel .tr): hidden
     at rest, shown on the hovered or selected row, kept while armed. */
  .tr {
    display: inline-flex;
    flex-shrink: 0;
    opacity: 0;
    transition: opacity var(--transition-fast);
  }

  .beat-row.hovered .tr,
  .beat-row.selected .tr,
  .tr.engaged {
    opacity: 1;
  }

  /* Legend Lore's arm key: a ring in a well, purple and lit once armed. */
  .arm-btn {
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

  .arm-btn:hover {
    color: var(--text-secondary);
    border-color: var(--text-secondary);
  }

  .arm-btn:active {
    transform: scale(0.97);
  }

  .arm-btn.armed {
    color: var(--text-active);
    border-color: var(--text-active);
    background: color-mix(in srgb, var(--text-active) 15%, transparent);
    filter: var(--glow-active);
  }

  .arm-glyph {
    width: 8px;
    height: 8px;
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
  .count-slot {
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

  /* A rename takes the name's place, as in Legend Lore: the field starts
     where the name did. The left inset counts the row's 2px rule. */
  .row-edit {
    display: flex;
    align-items: center;
    padding: 0.05rem 0.35rem 0.05rem calc(0.35rem + 2px);
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
  .arm-btn.promise {
    cursor: default;
    filter: none;
  }

  /* Key hints under the naming row, starting in the name's column. */
  .ghost-keys {
    display: flex;
    gap: 0.75rem;
    padding: 0.2rem 0.35rem 0.35rem calc(0.35rem + 2px);
  }

  .ghost-keys kbd {
    font-family: var(--font-mono);
    letter-spacing: 0;
    text-transform: none;
    color: var(--text-secondary);
  }

  .spare-head {
    margin: 1rem 0 0.25rem;
    padding: 0 0.4rem;
  }
</style>
