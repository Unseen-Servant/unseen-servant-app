<script lang="ts">
  // The shelf (design §3.6): what this campaign has gathered but not filed
  // on a track yet, then its loose notes. Its rows behave as the grid's: a
  // click opens a note, or with a beat armed puts it in the beat; the menu
  // files it on a track. The picker browses another campaign instead,
  // whose notes copy onto this shelf: reuse between campaigns is a copy.
  import CommandMenu from './CommandMenu.svelte';
  import InlineName from './InlineName.svelte';
  import RenameField from '../ui/RenameField.svelte';
  import { hoverLive } from '../ui/inputModality';
  import { commandApi } from './api';
  import { endNoteDrag, startNoteDrag } from './noteDrag';
  import { action, divider, heading, keyed, type OpenMenu } from './menu';
  import type { CampaignIndex, NoteEntry } from './types';

  export let campaign: string;
  export let campaigns: string[];
  export let index: CampaignIndex;
  export let openPath: string | null;
  /** Notes in the selected beat. */
  export let members: Set<string>;
  /** Notes some beat of the session's plan holds. */
  export let inSession: Set<string>;
  /** The live set, while there is one: notes outside it dim, as Legend
   *  Lore's tree does while a collection plays. */
  export let liveNotes: Set<string> | null;
  /** A beat is armed: a click toggles membership instead of opening. */
  export let armed: boolean;
  export let ambiguous: (name: string) => boolean;
  export let onOpen: (note: NoteEntry) => void;
  /** The note last clicked: Legend Lore's focused row. */
  export let selectedPath: string | null;
  export let onSelect: (note: NoteEntry) => void;
  export let onToggleMember: (note: NoteEntry) => void;
  export let onCreate: (name: string) => void;
  /** Resolves the reason a rename was refused, or null when it took. */
  export let onRename: (note: NoteEntry, name: string) => Promise<string | null>;
  export let onSpent: (note: NoteEntry, spent: boolean) => void;
  export let onMove: (note: NoteEntry, track: string) => void;
  export let onReveal: (note: NoteEntry) => void;
  export let onTrash: (note: NoteEntry) => void;
  export let onCopy: (fromCampaign: string, note: NoteEntry) => void;

  const SHELF = 'shelf';
  const byName = (a: NoteEntry, b: NoteEntry) =>
    a.name.localeCompare(b.name, undefined, { sensitivity: 'base', numeric: true });
  const onShelf = (n: NoteEntry) => n.track?.toLowerCase() === SHELF;

  let creating = false;
  let renamingPath: string | null = null;
  let menu: OpenMenu | null = null;

  // Hover latched on pointerenter, as Legend Lore's rows (FileTree).
  let hovered: string | null = null;
  function leave(path: string) {
    if (hovered === path) hovered = null;
  }

  $: shelf = index.notes.filter(onShelf).sort(byName);
  $: loose = index.notes.filter((n) => n.track === null).sort(byName);

  // -- browsing another campaign ------------------------------------------

  /** The campaign being browsed to copy from; null for this one's shelf. */
  let source: string | null = null;
  let other: CampaignIndex | null = null;
  let otherError: string | null = null;

  $: if (source && (source === campaign || !campaigns.includes(source))) source = null;
  $: void browse(source);

  async function browse(name: string | null) {
    other = null;
    otherError = null;
    if (!name) return;
    try {
      const loaded = await commandApi.getCampaign(name);
      if (source === name) other = loaded;
    } catch (e) {
      if (source === name) otherError = String(e);
    }
  }

  /** Another campaign's notes to copy from: its shelf, then each track. */
  function sections(idx: CampaignIndex): { title: string; notes: NoteEntry[] }[] {
    const of = (track: string) => idx.notes.filter((n) => n.track === track).sort(byName);
    return [
      { title: SHELF, notes: idx.notes.filter(onShelf).sort(byName) },
      ...idx.tracks.map((t) => ({ title: t, notes: of(t) })),
    ].filter((s) => s.notes.length);
  }

  function pickSource(e: MouseEvent) {
    const box = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const others = campaigns.filter((c) => c !== campaign);
    menu = {
      x: box.left,
      y: box.bottom + 4,
      items: [
        action(`${campaign}'s shelf`, () => (source = null)),
        ...(others.length ? [divider, heading('copy from'), ...others.map((c) => action(c, () => (source = c)))] : []),
      ],
    };
  }

  /** R on the selected note: renamed in its row, if the shelf is showing it. */
  export function rename(path: string) {
    if (!source && [...shelf, ...loose].some((n) => n.path === path)) renamingPath = path;
  }

  // A right-click selects the row, as the grid's does.
  function noteMenu(e: MouseEvent, note: NoteEntry) {
    onSelect(note);
    menu = {
      x: e.clientX,
      y: e.clientY,
      items: [
        action(note.spent ? 'Mark unspent' : 'Mark spent', () => onSpent(note, !note.spent)),
        ...(index.tracks.length ? [divider, heading('file on'), ...index.tracks.map((t) => action(t, () => onMove(note, t)))] : []),
        ...(note.track === null ? [action('Shelf', () => onMove(note, 'Shelf'))] : []),
        divider,
        keyed('Rename', 'command.rename', () => (renamingPath = note.path)),
        action('Show in Finder', () => onReveal(note)),
        action('Move to Trash', () => onTrash(note), true),
      ],
    };
  }
</script>

{#snippet row(note: NoteEntry)}
  {@const renaming = renamingPath === note.path}
  <button
    type="button"
    class="note-row"
    data-row
    class:open={note.path === openPath}
    class:selected={note.path === selectedPath}
    class:hovered={$hoverLive && hovered === note.path}
    class:ambiguous={ambiguous(note.name)}
    class:member={members.has(note.path)}
    class:in-session={inSession.has(note.path)}
    class:spent={!!note.spent}
    class:out-of-scope={liveNotes !== null && !liveNotes.has(note.path)}
    class:arming={armed}
    aria-pressed={armed ? members.has(note.path) : undefined}
    title={note.spent ? `${note.name} — spent ${note.spent}` : note.name}
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
    <!-- As the grid's: a rename takes the name's place in the row. -->
    {#if renaming}
      <RenameField
        value={note.name}
        label="Rename note"
        onCommit={async (name) => {
          const refusal = await onRename(note, name);
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
{/snippet}

<aside class="shelf" aria-label="Shelf">
  <header class="nameplate">
    <button type="button" class="source-key" title="This shelf, or another campaign to copy from" on:click={pickSource}>
      <span class="ledger-label">{source ? `from ${source}` : 'shelf'}</span>
      <span class="drop" aria-hidden="true">▾</span>
    </button>
    {#if !source}<span class="count">{shelf.length}</span>{/if}
  </header>

  <div class="list">
    {#if !source}
      {#each shelf as note (note.path)}
        {@render row(note)}
      {:else}
        {#if !creating}
          <p class="quiet">Nothing gathered yet. Send hits here from Legend Lore, or start a note.</p>
        {/if}
      {/each}
      {#if creating}
        <div class="row-edit naming">
          <span class="slot" aria-hidden="true"></span>
          <InlineName
            placeholder="Name"
            label="New note on the shelf"
            onCommit={(name) => {
              creating = false;
              onCreate(name);
            }}
            onCancel={() => (creating = false)}
          />
        </div>
      {:else}
        <button type="button" class="ghost-row" title="New note" aria-label="New note on the shelf" on:click={() => (creating = true)}>
          <span class="slot" aria-hidden="true"></span>
        </button>
      {/if}

      {#if loose.length}
        <div class="ledger-label section-head" title="Notes directly in the campaign folder, on no track">loose</div>
        {#each loose as note (note.path)}
          {@render row(note)}
        {/each}
      {/if}
    {:else if otherError}
      <p class="quiet error">{otherError}</p>
    {:else if other}
      {#each sections(other) as section (section.title)}
        <div class="ledger-label section-head">{section.title}</div>
        {#each section.notes as note (note.path)}
          <button
            type="button"
            class="note-row copy-row"
            title={`Copy ${note.name} onto ${campaign}'s shelf`}
            on:click={() => onCopy(source!, note)}
          >
            <span class="label">{note.name}</span>
            <span class="copy-hint" aria-hidden="true">copy</span>
          </button>
        {/each}
      {:else}
        <p class="quiet">{source} has no notes to copy.</p>
      {/each}
    {/if}
  </div>
</aside>

{#if menu}
  <CommandMenu x={menu.x} y={menu.y} items={menu.items} onClose={() => (menu = null)} />
{/if}

<style>
  /* Narrow, so it covers few tracks: they keep their width when it opens,
     and the grid scrolls. */
  .shelf {
    flex: 0 0 11rem;
    min-width: 0;
    display: flex;
    flex-direction: column;
    min-height: 0;
    /* Legend Lore's dock seam (.left-dock): the sidebar's plates and the
       grid's sit side by side in one grey, so a hairline isn't enough. */
    border-right: 4px solid var(--border-subtle);
  }

  /* The grid's nameplate (TrackGrid), so the sidebar reads as one more
     module on the same console. */
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

  .source-key {
    display: flex;
    align-items: baseline;
    gap: 0.3rem;
    min-width: 0;
    padding: 0;
    background: none;
    border: none;
    cursor: pointer;
  }

  .source-key .ledger-label {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--text-secondary);
    transition: color var(--transition-fast);
  }

  .source-key:hover .ledger-label {
    color: var(--text-primary);
  }

  .drop {
    font-size: 0.7rem;
    color: var(--text-tertiary);
  }

  /* The shelf's count of notes: the tracks' count badge (TrackGrid .count). */
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

  .list {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding: 0.25rem 0.25rem 1rem;
  }

  .section-head {
    margin: 0.75rem 0 0.15rem;
    padding: 0 0.4rem;
  }

  .quiet {
    margin: 0.35rem 0.4rem;
    font-size: 0.8rem;
    line-height: 1.4;
    color: var(--text-tertiary);
  }

  .quiet.error {
    color: var(--text-danger);
  }

  /* The grid's note row (TrackGrid), kept local as each list keeps it. */
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

  .label {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  /* The grid's clip slot (TrackGrid .slot), Ableton's square lit as a
     splash lamp. */
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

  /* Another campaign's note: the row copies it, and says so on hover. */
  .copy-row {
    padding-left: 0.4rem;
  }

  .copy-hint {
    flex-shrink: 0;
    font-family: var(--font-mono);
    font-size: 0.7rem;
    color: var(--text-accent);
    opacity: 0;
    transition: opacity var(--transition-fast);
  }

  .copy-row:hover .copy-hint,
  .copy-row:focus-visible .copy-hint {
    opacity: 1;
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
    gap: 0.35rem;
    padding-left: 0.25rem;
    padding-right: 0.4rem;
  }

  /* As the grid's (TrackGrid .row-edit.naming): the field is a note row's
     height on its own. */
  .row-edit.naming {
    padding-block: 0;
  }

  /* The grid's empty row (TrackGrid .ghost-row): a nameless note row whose
     lamp shows dark under the pointer, a line of unseen type tall. */
  .ghost-row {
    display: flex;
    align-items: center;
    gap: 0.35rem;
    padding-left: 0.25rem;
  }

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
</style>
