<script lang="ts">
  // The beat launcher (design §5.1): the active session's plan in order,
  // then beats no plan holds yet. Clicking a beat selects it — its notes
  // light up across the tracks — and a double-click opens it, as rows do in
  // Legend Lore. Arming a beat (the record-arm
  // ring, as on Legend Lore's collections) makes a click on a note put it in
  // the beat or take it out.
  import InlineName from './InlineName.svelte';
  import { hoverLive } from '../ui/inputModality';
  import CommandMenu from './CommandMenu.svelte';
  import { CIRCLE, CIRCLE_RING } from '../ui/iconPaths';
  import { action, divider, heading, type MenuItem, type OpenMenu } from './menu';
  import type { PlanRow } from './prep';
  import type { BeatEntry } from './types';

  export let rows: PlanRow[];
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

  // Hover latched on pointerenter, as Legend Lore's rows (FileTree).
  let hovered: string | null = null;
  function leave(path: string) {
    if (hovered === path) hovered = null;
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
    const own = row.beat ? [divider, ...beatItems(row.beat)] : [divider, action('Write this beat', () => onWrite(row))];
    menu = { x: e.clientX, y: e.clientY, items: [...order, ...own] };
  }

  function spareMenu(e: MouseEvent, beat: BeatEntry) {
    menu = {
      x: e.clientX,
      y: e.clientY,
      items: [...(sessionName ? [action(`Add to ${sessionName}`, () => onAddToPlan(beat)), divider] : []), ...beatItems(beat)],
    };
  }
</script>

{#snippet beatRow(beat: BeatEntry, onMenu: (e: MouseEvent) => void)}
  {#if renamingPath === beat.path}
    <div class="row-edit renaming">
      <span class="arm-spacer"></span>
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
    <div
      class="beat-row"
      class:selected={beat.path === selectedPath}
      class:open={beat.path === openPath}
      class:armed={beat.path === armedPath}
      class:spent={!!beat.spent}
      class:hovered={$hoverLive && hovered === beat.path}
      on:contextmenu|preventDefault={onMenu}
      on:pointerenter={() => (hovered = beat.path)}
      on:pointerleave={() => leave(beat.path)}
      role="presentation"
    >
      <button
        type="button"
        class="arm-btn"
        class:armed={beat.path === armedPath}
        aria-pressed={beat.path === armedPath}
        title={beat.path === armedPath ? `Disarm ${beat.name} (Esc)` : `Arm ${beat.name}: click notes to put them in it`}
        on:click={() => onArm(beat)}
      >
        <svg class="arm-glyph" viewBox="64 64 512 512" fill="currentColor" aria-hidden="true">
          <path d={beat.path === armedPath ? CIRCLE : CIRCLE_RING} />
        </svg>
      </button>
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
      {:else}
        <span class="count">{beat.notes.length}</span>
      {/if}
    </div>
  {/if}
{/snippet}

<section class="beats" aria-label="Beats">
  <header class="nameplate">
    <span class="ledger-label title">beats</span>
    <span class="count plan-count">{rows.length}</span>
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
          <span class="arm-spacer"></span>
          <span class="beat-name">{row.link}</span>
        </button>
      {/if}
    {/each}

    {#if creating}
      <div class="row-edit">
        <InlineName
          placeholder="Beat name"
          label="New beat"
          onCommit={(name) => {
            creating = false;
            onCreate(name);
          }}
          onCancel={() => (creating = false)}
        />
      </div>
    {:else}
      <button type="button" class="ghost-row" on:click={() => (creating = true)}>+ beat</button>
    {/if}

    {#if spare.length}
      <div class="ledger-label spare-head">{sessionName ? 'not in this session' : 'beats'}</div>
      {#each spare as beat (beat.path)}
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
    color: var(--text-secondary);
  }

  .plan-count {
    margin-left: auto;
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
    gap: 0.4rem;
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

  .arm-btn,
  .arm-spacer {
    flex-shrink: 0;
    width: 18px;
    height: 18px;
  }

  /* Legend Lore's arm key: a ring in a well, purple and lit once armed. */
  .arm-btn {
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

  .row-edit {
    padding: 0.05rem 0;
    font-size: 0.9rem;
    line-height: 1.5;
  }

  /* A rename takes the name's place, as in Legend Lore: the arm key's
     column stays, so the field starts where the name did. The left inset
     counts the row's 2px rule. */
  .row-edit.renaming {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    padding-left: calc(0.35rem + 2px);
    padding-right: 0.35rem;
  }

  .ghost-row {
    display: block;
    width: 100%;
    padding: 0.15rem 0.4rem 0.15rem calc(0.35rem + 18px + 0.4rem + 2px);
    background: none;
    border: none;
    border-radius: var(--radius-sm);
    font-family: var(--font-body);
    font-size: 0.9rem;
    line-height: 1.5;
    text-align: left;
    color: var(--text-tertiary);
    cursor: pointer;
  }

  .ghost-row:hover {
    color: var(--text-primary);
  }

  .spare-head {
    margin: 1rem 0 0.25rem;
    padding: 0 0.4rem;
  }
</style>
