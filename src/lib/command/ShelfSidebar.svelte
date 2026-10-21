<script lang="ts">
  // The shelf (design §3.6): what this campaign has gathered but not filed
  // on a track yet, then its loose notes. Its rows behave as the grid's: a
  // click opens a note, or with a beat armed puts it in the beat; the menu
  // files it on a track. A note dragged off a track drops back on the shelf
  // anywhere over it. The picker browses another campaign instead, or a
  // place (a folder the GM added), whose notes copy onto this shelf:
  // reuse between campaigns is a copy.
  import CommandMenu from './CommandMenu.svelte';
  import InlineName from './InlineName.svelte';
  import RenameField from '../ui/RenameField.svelte';
  import SpendKey from './SpendKey.svelte';
  import { hoverLive } from '../ui/inputModality';
  import { grab } from '../ui/grab';
  import { commandApi } from './api';
  import { carriesFiles, droppedImages } from './embeds';
  import { draggedNote, endNoteDrag, isNoteDrag, startNoteDrag } from './noteDrag';
  import { action, divider, keyed, submenu, type OpenMenu } from './menu';
  import { nameParts, newRowKey } from './columns';
  import type { CampaignIndex, CopySource, NoteEntry } from './types';

  /** Where a menu opened from the keyboard sits: in from the row's edge,
   *  under it, where a right-click would land. */
  const MENU_INSET = 16;

  export let campaign: string;
  export let campaigns: string[];
  /** Folders the shelf copies from (CommandSettings.places). */
  export let places: string[];
  export let index: CampaignIndex;
  export let openPath: string | null;
  /** Notes in the focused beat. */
  export let members: Set<string>;
  /** Notes some beat of the session's plan holds. */
  export let inSession: Set<string>;
  /** A beat is armed: a click toggles membership instead of opening. */
  export let armed: boolean;
  export let ambiguous: (path: string) => boolean;
  export let onOpen: (note: NoteEntry) => void;
  /** The note last clicked: Legend Lore's focused row. */
  export let selectedPath: string | null;
  export let onSelect: (note: NoteEntry) => void;
  /** Select the shelf's empty row, by its key (columns.ts newRowKey). */
  export let onSelectNew: (key: string) => void;
  export let onToggleMember: (note: NoteEntry) => void;
  export let onCreate: (name: string) => void;
  /** Resolves the reason a rename was refused, or null when it took. */
  export let onRename: (note: NoteEntry, name: string) => Promise<string | null>;
  export let onSpent: (note: NoteEntry, spent: boolean) => void;
  export let onMove: (note: NoteEntry, track: string) => void;
  /** Images dropped from Finder on the shelf, copied onto it. */
  export let onDropImages: (files: File[]) => void;
  export let onReveal: (note: NoteEntry) => void;
  export let onTrash: (note: NoteEntry) => void;
  export let onCopy: (from: CopySource, note: NoteEntry) => void;
  /** Resolves the folder added, or null when the GM cancelled. */
  export let onAddPlace: () => Promise<string | null>;
  export let onForgetPlace: (path: string) => void;

  const SHELF = 'shelf';
  /** The shelf's folder, as notes are filed into it. */
  const SHELF_FOLDER = 'Shelf';
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

  // -- browsing another campaign or a place --------------------------------

  type Section = { title: string; notes: NoteEntry[] };

  /** What's being browsed to copy from; null for this campaign's shelf. */
  let source: CopySource | null = null;
  let other: Section[] | null = null;
  let otherError: string | null = null;

  /** A place by its folder's name, as Finder's sidebar names it. */
  const placeName = (path: string) => path.split(/[\\/]/).filter(Boolean).pop() ?? path;
  const sourceName = (s: CopySource) => (s.kind === 'campaign' ? s.name : placeName(s.path));

  $: if (
    source &&
    (source.kind === 'campaign'
      ? source.name === campaign || !campaigns.includes(source.name)
      : !places.includes(source.path))
  )
    source = null;
  $: void browse(source);

  async function browse(from: CopySource | null) {
    other = null;
    otherError = null;
    if (!from) return;
    try {
      const loaded =
        from.kind === 'campaign'
          ? sections(await commandApi.getCampaign(from.name))
          : placeSections((await commandApi.getPlace(from.path)).notes);
      if (source === from) other = loaded;
    } catch (e) {
      if (source === from) otherError = String(e);
    }
  }

  /** Another campaign's notes to copy from: its shelf, then each track. */
  function sections(idx: CampaignIndex): Section[] {
    const of = (track: string) => idx.notes.filter((n) => n.track === track).sort(byName);
    return [
      { title: SHELF, notes: idx.notes.filter(onShelf).sort(byName) },
      ...idx.tracks.map((t) => ({ title: t, notes: of(t) })),
    ].filter((s) => s.notes.length);
  }

  /** A place's notes by the folder they're in, its own first, untitled. */
  function placeSections(notes: NoteEntry[]): Section[] {
    const folder = (n: NoteEntry) => [n.track, n.group].filter(Boolean).join('/');
    const folders = [...new Set(notes.map(folder))].sort((a, b) =>
      a.localeCompare(b, undefined, { sensitivity: 'base', numeric: true }),
    );
    return folders.map((f) => ({ title: f, notes: notes.filter((n) => folder(n) === f).sort(byName) }));
  }

  async function addPlace() {
    const added = await onAddPlace();
    if (added) source = { kind: 'place', path: added };
  }

  // Copy from is always offered: with no other campaign, it's where a
  // folder is added.
  function pickSource(e: MouseEvent) {
    const box = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const others = campaigns.filter((c) => c !== campaign);
    const browsing = source;
    menu = {
      x: box.left,
      y: box.bottom + 4,
      items: [
        action(`${campaign}'s shelf`, () => (source = null)),
        divider,
        submenu('Copy from', [
          ...others.map((c) => action(c, () => (source = { kind: 'campaign', name: c }))),
          ...(others.length && places.length ? [divider] : []),
          ...places.map((p) => action(placeName(p), () => (source = { kind: 'place', path: p }))),
          ...(others.length || places.length ? [divider] : []),
          action('Add folder…', () => void addPlace()),
        ]),
        ...(browsing?.kind === 'place' ? [action('Forget this folder', () => onForgetPlace(browsing.path))] : []),
      ],
    };
  }

  // -- dragging onto the shelf --------------------------------------------
  //
  // A note from a track, or a loose one, moves onto the shelf wherever it's
  // dropped over it: the shelf sorts by name, so there's no place among its
  // rows to pick. Not while browsing another campaign, whose notes copy.

  let shelfEl: HTMLElement;
  /** A note over the shelf would move onto it. */
  let dropInto = false;

  const target = (e: DragEvent): NoteEntry | null => {
    const note = isNoteDrag(e) ? draggedNote() : null;
    return note && !source && !onShelf(note) ? note : null;
  };

  function overShelf(e: DragEvent) {
    // Images from Finder land on the shelf, which holds notes and images
    // alike (images design §4).
    if (carriesFiles(e)) {
      dropInto = !source;
      if (!dropInto) return;
      e.preventDefault();
      if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy';
      return;
    }
    dropInto = target(e) !== null;
    if (!dropInto) return;
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
  }

  function dropOnShelf(e: DragEvent) {
    if (carriesFiles(e)) {
      dropInto = false;
      if (source) return;
      e.preventDefault();
      const files = droppedImages(e);
      if (files.length) onDropImages(files);
      return;
    }
    const note = target(e);
    dropInto = false;
    if (!note) return;
    e.preventDefault();
    onMove(note, 'Shelf');
  }

  // As the grid's (TrackGrid leaveGrid): WebKit sends a dragleave between
  // the shelf's own elements, so leaving is judged by where the pointer is.
  function leaveShelf(e: DragEvent) {
    const box = shelfEl.getBoundingClientRect();
    const x = e.clientX;
    const y = e.clientY;
    if (x > box.left && x < box.right && y > box.top && y < box.bottom) return;
    dropInto = false;
  }

  /** R on the selected note: renamed in its row, if the shelf is showing
   *  it; on its selected empty row, the new note is named there. */
  export function rename(path: string) {
    if (!source && path === newRowKey(SHELF_FOLDER)) {
      creating = true;
      return;
    }
    if (!source && [...shelf, ...loose].some((n) => n.path === path)) renamingPath = path;
  }

  /** ⌘N with the shelf, or nothing, selected: a new note named in the
   *  shelf's empty row, when the shelf is its own campaign's. */
  export function create() {
    if (!source) creating = true;
  }

  /** ⇧F10 on the selected note: its menu, at its row, if the shelf shows
   *  it. */
  export function menuFor(path: string): boolean {
    const note = !source ? [...shelf, ...loose].find((n) => n.path === path) : undefined;
    const row = shelfEl?.querySelector<HTMLElement>(`[data-path="${CSS.escape(path)}"]`);
    if (!note || !row) return false;
    const box = row.getBoundingClientRect();
    noteMenuAt(box.left + MENU_INSET, box.bottom, note);
    return true;
  }

  // A right-click selects the row, as the grid's does.
  function noteMenu(e: MouseEvent, note: NoteEntry) {
    noteMenuAt(e.clientX, e.clientY, note);
  }

  function noteMenuAt(x: number, y: number, note: NoteEntry) {
    onSelect(note);
    const fitting = index.tracks.filter((t) => (index.kinds[t] ?? 'note') === note.type);
    const groups = [
      // An image isn't spent (images design §2).
      note.type === 'image' ? [] : [keyed(note.spent ? 'Mark unspent' : 'Mark spent', 'command.spend', () => onSpent(note, !note.spent))],
      // The grid's Move to flyout, in the columns' order: the shelf at the
      // left, for a loose note, then the tracks of its kind, as Live keeps
      // audio clips off MIDI tracks (images design §3.2).
      fitting.length || note.track === null
        ? [
            submenu('Move to', [
              ...(note.track === null ? [action('Shelf', () => onMove(note, 'Shelf'))] : []),
              ...fitting.map((t) => action(t, () => onMove(note, t))),
            ]),
          ]
        : [],
      [
        keyed('Rename', 'command.rename', () => (renamingPath = note.path)),
        keyed('Show in Finder', 'command.reveal', () => onReveal(note)),
        keyed('Move to Trash', 'command.delete', () => onTrash(note), true),
      ],
    ].filter((g) => g.length);
    menu = {
      x,
      y,
      items: groups.flatMap((g, i) => (i ? [divider, ...g] : g)),
    };
  }
</script>

{#snippet row(note: NoteEntry)}
  {@const renaming = renamingPath === note.path}
  <!-- A div, as the grid's, so the spend key can be a button inside it. -->
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <div
    class="note-row"
    role="button"
    tabindex="-1"
    data-row
    data-path={note.path}
    class:open={note.path === openPath}
    class:selected={note.path === selectedPath}
    class:hovered={$hoverLive && hovered === note.path}
    class:ambiguous={ambiguous(note.path)}
    class:member={members.has(note.path)}
    class:in-session={inSession.has(note.path)}
    class:spent={!!note.spent}
    class:arming={armed}
    aria-pressed={armed ? members.has(note.path) : undefined}
    title={note.spent ? `${note.name} — spent ${note.spent}` : note.name}
    use:grab={!renaming}
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
        value={nameParts(note).stem}
        label="Rename note"
        onCommit={async (name) => {
          const refusal = await onRename(note, name);
          if (!refusal) renamingPath = null;
          return refusal;
        }}
        onCancel={() => (renamingPath = null)}
      />
    {:else}
      {@const name = nameParts(note)}
      <span class="label">{name.stem}{#if name.ext}<span class="ext">{name.ext}</span>{/if}</span>
    {/if}
    <!-- Spent, its key lit and kept through a rename; otherwise shown on
         the hovered or selected row, as a collection's transport is. An
         image isn't spent, so it has none (images design §4). -->
    {#if note.type !== 'image' && (note.spent || (!renaming && (($hoverLive && hovered === note.path) || note.path === selectedPath)))}
      <SpendKey spent={note.spent ?? null} name={note.name} onToggle={() => onSpent(note, !note.spent)} />
    {/if}
  </div>
{/snippet}

<aside
  class="shelf"
  class:drop-into={dropInto}
  aria-label="Shelf"
  bind:this={shelfEl}
  on:dragenter={overShelf}
  on:dragover={overShelf}
  on:dragleave={leaveShelf}
  on:drop={dropOnShelf}
>
  <header class="nameplate">
    <button type="button" class="source-key" title="This shelf, or another campaign to copy from" on:click={pickSource}>
      <span class="ledger-label">{source ? `from ${sourceName(source)}` : 'shelf'}</span>
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
            bare
            placeholder="Note name…"
            label="New note on the shelf"
            onCommit={(name) => {
              creating = false;
              onCreate(name);
            }}
            onCancel={() => (creating = false)}
          />
        </div>
      {:else}
        <button
          type="button"
          class="ghost-row"
          data-row
          class:selected={selectedPath === newRowKey(SHELF_FOLDER)}
          title="New note — double-click to name it"
          aria-label="New note on the shelf"
          on:click={() => onSelectNew(newRowKey(SHELF_FOLDER))}
          on:dblclick={() => (creating = true)}
        >
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
      {#each other as section (section.title)}
        {#if section.title}<div class="ledger-label section-head">{section.title}</div>{/if}
        {#each section.notes as note (note.path)}
          {@const name = nameParts(note)}
          <button
            type="button"
            class="note-row copy-row"
            title={`Copy ${note.name} onto ${campaign}'s shelf`}
            on:click={() => onCopy(source!, note)}
          >
            <span class="label">{name.stem}{#if name.ext}<span class="ext">{name.ext}</span>{/if}</span>
            <span class="copy-hint" aria-hidden="true">copy</span>
          </button>
        {/each}
      {:else}
        <p class="quiet">{source && sourceName(source)} has no notes to copy.</p>
      {/each}
    {/if}
  </div>
</aside>

<svelte:window on:dragend={() => (dropInto = false)} />

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

  /* A note over the shelf it would move onto: the grid's column under a
     dragged note (TrackGrid .column.drop-into). */
  .shelf.drop-into {
    outline: var(--outline-drop);
    outline-offset: -1px;
    background: var(--bg-container);
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
    min-height: 1.65rem;
    padding: 0.2rem 0.6rem 0.15rem;
    background: var(--bg-container);
    /* Ruled below in the panel's own ground, not the grid's grey; flush
       with the bar above, as the track plates are. */
    border-bottom: 1px solid var(--bg-app);
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
    /* Flush under the plate, as the tracks' first notes are, so the
       shelf's rows line up with theirs. */
    padding: 0 0.25rem 1rem;
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
    position: relative;
    display: flex;
    align-items: center;
    gap: 0.35rem;
    padding-left: 0.25rem;
    color: var(--text-primary);
    transition: background var(--transition-fast);
  }

  /* Ruled rows, a ledger's lines: a hairline under each note, the
     grid's (TrackGrid), in the column's own divider grey. Drawn over the row's foot rather than as a
     border, so a row keeps the 1.65rem every row in the app has. The
     empty row under the notes is ruled too, the ledger's next line, and
     so is the field a new note is named in. */
  .note-row::before,
  .ghost-row::before,
  .row-edit.naming::before {
    content: '';
    position: absolute;
    left: 0;
    right: 0;
    bottom: 0;
    height: 1px;
    background: var(--border-subtle);
    pointer-events: none;
  }

  /* The selected row's ring is drawn inside it, on the same last pixel:
     there the ring is the row's rule, or the rule would hide its foot. */
  .note-row.selected::before,
  .ghost-row.selected::before {
    display: none;
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

  /* An image's extension, a step down the text ramp from its name. */
  .ext {
    color: var(--text-secondary);
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

  /* Legend Lore's row states (FileTree, CollectionsPanel .row-container):
     hover fills a grey step, latched on pointerenter and painted only while
     the pointer drives ($hoverLive), so a closing menu doesn't light the
     row under a still pointer; the selected row rings. Rows take no press
     tick there. */
  .note-row.hovered {
    background: var(--bg-container);
  }

  .note-row.selected,
  .ghost-row.selected {
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
    position: relative;
    display: flex;
    align-items: center;
    gap: 0.35rem;
    padding-left: 0.25rem;
    padding-right: 0.4rem;
  }

  /* As the grid's (TrackGrid .row-edit.naming): a note row's padding
     around the bare field's line, and dressed as the open note it
     becomes. */
  .row-edit.naming {
    padding-block: 0.15rem;
  }

  .row-edit.naming {
    background: color-mix(in srgb, var(--text-accent) 10%, transparent);
    box-shadow: var(--ring-focus), inset 2px 0 0 var(--text-accent);
  }

  .row-edit.naming::before {
    display: none;
  }

  .row-edit.naming :global(.inline-name) {
    color: var(--text-accent);
  }

  .row-edit.naming :global(.inline-name::placeholder) {
    font-style: italic;
  }

  /* The grid's empty row (TrackGrid .ghost-row): a nameless note row whose
     lamp shows dark at all times, a line of unseen type tall. */
  .ghost-row {
    position: relative;
    display: flex;
    align-items: center;
    gap: 0.35rem;
    padding-left: 0.25rem;
  }

  .ghost-row::after {
    content: '\200b';
  }

  .ghost-row:hover {
    background: var(--bg-container);
  }
</style>
