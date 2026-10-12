<script lang="ts">
  // The Prep grid (design §5.1): one column per track, every note in it,
  // subfolders as groups. A click selects a note, as a row in Legend Lore,
  // and a double-click opens it; while a beat is armed, the click also puts
  // it in the beat or takes it out. Right-click for rename, spent, move and
  // trash. The ghost rows at the foot of each column and the
  // end of the grid name a new note or track in place.
  //
  // Each row's slot reads the session at a glance: a parchment dot for a
  // note in the selected beat, a ring for one some other planned beat holds.
  // A spent note dims and carries a check.
  import InlineName from './InlineName.svelte';
  import { hoverLive } from '../ui/inputModality';
  import CommandMenu from './CommandMenu.svelte';
  import { action, divider, heading, type OpenMenu } from './menu';
  import { endNoteDrag, startNoteDrag } from './noteDrag';
  import type { Column } from './columns';
  import type { NoteEntry } from './types';

  export let cols: Column[];
  export let openPath: string | null;
  /** Notes in the selected beat. */
  export let members: Set<string>;
  /** Notes some beat of the session's plan holds. */
  export let inSession: Set<string>;
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
  export let onRenameNote: (note: NoteEntry, name: string) => void;
  export let onMoveNote: (note: NoteEntry, track: string) => void;
  export let onTrashNote: (note: NoteEntry) => void;
  export let onRevealNote: (note: NoteEntry) => void;
  export let onCreateTrack: (name: string) => void;
  export let onRenameTrack: (track: string, name: string) => void;
  export let onTrashTrack: (column: Column) => void;
  export let onRevealTrack: (track: string) => void;

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

  function noteMenu(e: MouseEvent, note: NoteEntry) {
    const others = cols.map((c) => c.track).filter((t) => t !== note.track);
    menu = {
      x: e.clientX,
      y: e.clientY,
      items: [
        action('Rename', () => (renamingPath = note.path)),
        action(note.spent ? 'Mark unspent' : 'Mark spent', () => onSpent(note, !note.spent)),
        divider,
        heading('move to'),
        ...others.map((t) => action(t, () => onMoveNote(note, t))),
        action('Shelf', () => onMoveNote(note, 'Shelf')),
        divider,
        action('Show in Finder', () => onRevealNote(note)),
        action('Move to Trash', () => onTrashNote(note), true),
      ],
    };
  }

  function trackMenu(e: MouseEvent, column: Column) {
    menu = {
      x: e.clientX,
      y: e.clientY,
      items: [
        action('New note', () => (creatingIn = column.track)),
        action('Rename', () => (renamingTrack = column.track)),
        divider,
        action('Show in Finder', () => onRevealTrack(column.track)),
        action('Move to Trash', () => onTrashTrack(column), true),
      ],
    };
  }
</script>

<div class="grid">
  {#each cols as column (column.track)}
    <section class="column" aria-label={column.track}>
      <header class="nameplate">
        {#if renamingTrack === column.track}
          <InlineName
            value={column.track}
            rename
            label="Rename track"
            onCommit={(name) => {
              renamingTrack = null;
              onRenameTrack(column.track, name);
            }}
            onCancel={() => (renamingTrack = null)}
          />
        {:else}
          <button
            type="button"
            class="track-name ledger-label"
            title={`${column.track} — rename, reveal or trash`}
            on:click={(e) => trackMenu(e, column)}
            on:contextmenu|preventDefault={(e) => trackMenu(e, column)}
          >
            {column.track}
          </button>
          <span class="count">{column.count}</span>
        {/if}
      </header>

      <div class="notes">
        {#each column.groups as group (group.group)}
          {#if group.group}
            <div class="group-label" title={group.group}>{group.group}</div>
          {/if}
          {#each group.notes as note (note.path)}
            {#if renamingPath === note.path}
              <div class="row-edit renaming" class:grouped={group.group !== null}>
                <span class="slot" aria-hidden="true"></span>
                <InlineName
                  value={note.name}
                  rename
                  label="Rename note"
                  onCommit={(name) => {
                    renamingPath = null;
                    onRenameNote(note, name);
                  }}
                  onCancel={() => (renamingPath = null)}
                />
              </div>
            {:else}
              <button
                type="button"
                class="note-row"
                data-row
                class:open={note.path === openPath}
                class:selected={note.path === selectedPath}
                class:hovered={$hoverLive && hovered === note.path}
                class:grouped={group.group !== null}
                class:ambiguous={ambiguous(note.name)}
                class:member={members.has(note.path)}
                class:in-session={inSession.has(note.path)}
                class:spent={!!note.spent}
                class:arming={armed}
                aria-pressed={armed ? members.has(note.path) : undefined}
                title={ambiguous(note.name)
                  ? `Another note is also named “${note.name}”, so links to it are ambiguous`
                  : note.spent
                    ? `${note.name} — spent ${note.spent}`
                    : note.name}
                draggable="true"
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
                <span class="label">{note.name}</span>
                {#if note.spent}<span class="spent-mark" aria-label="spent">✓</span>{/if}
              </button>
            {/if}
          {/each}
        {/each}

        {#if creatingIn === column.track}
          <div class="row-edit">
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
          <button type="button" class="ghost-row" on:click={() => (creatingIn = column.track)}>+ note</button>
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

  /* Tracks are one width, as on a console: long names ellipsize rather
     than widening their column (min-width: 0 overrides the flex item's
     min-content floor, which nowrap rows would otherwise set). */
  .column {
    flex: 1 0 8.5rem;
    min-width: 0;
    max-width: 16rem;
    display: flex;
    flex-direction: column;
    min-height: 0;
    border-right: 1px solid var(--border-subtle);
  }

  .ghost-column {
    flex: 0 0 5.5rem;
    border-right: none;
  }

  /* The module nameplate: flat container plate, ledger-label voice. */
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

  .count {
    margin-left: auto;
    font-size: 0.75rem;
    font-variant-numeric: tabular-nums;
    color: var(--text-tertiary);
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

  .note-row {
    display: flex;
    align-items: center;
    gap: 0.35rem;
    padding-left: 0.25rem;
    color: var(--text-primary);
    transition: background var(--transition-fast);
  }

  .note-row.grouped {
    padding-left: 0.75rem;
  }

  .label {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  /* The clip slot: empty, a ring (the session holds this note), or a
     parchment dot (the selected beat does). Content, not a mode: no glow —
     the lit lamp belongs to Play's live set. */
  .slot {
    flex-shrink: 0;
    width: 6px;
    height: 6px;
    border-radius: 50%;
    border: 1px solid transparent;
  }

  .note-row.in-session .slot {
    border-color: var(--text-tertiary);
  }

  .note-row.member .slot {
    background: var(--text-accent);
    border-color: var(--text-accent);
  }

  .note-row.member .label {
    color: var(--text-accent);
  }

  /* Armed: every slot offers itself, so the click's meaning shows. */
  .note-row.arming.hovered:not(.member) .slot {
    border-color: var(--text-accent);
  }

  .note-row.spent .label,
  .note-row.spent .slot {
    opacity: var(--opacity-out-of-scope);
  }

  .note-row.spent.hovered .label,
  .note-row.spent.hovered .slot {
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

  /* A rename takes the name's place, as in Legend Lore: the row's slot
     keeps its column, so the field starts where the name did. */
  .row-edit.renaming {
    display: flex;
    align-items: center;
    gap: 0.35rem;
    padding-left: 0.25rem;
    padding-right: 0.4rem;
  }

  .row-edit.renaming.grouped {
    padding-left: 0.75rem;
  }

  .ghost-row {
    color: var(--text-tertiary);
  }

  .ghost-row:hover,
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
