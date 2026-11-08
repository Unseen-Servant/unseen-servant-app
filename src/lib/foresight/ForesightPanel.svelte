<script lang="ts">
  // Foresight, the turn tracker (docs/roadmap/2026-11-03-foresight-design.md).
  // A step sequencer: one step per row, the playhead is the turn, each loop
  // a round. An encounter is a note in an encounter track of the campaign
  // open in Command; its table is the tracker (encounter.ts), and every change is written to it
  // at once, a write at a time, the latest state winning. A change made to
  // the note elsewhere comes back through the vault watcher; when it lands
  // under a write of Foresight's, the note's version wins.
  //
  // The top line is Augury's strip: ◀ ▶ step through the encounter tracks, on
  // the encounter last open in that track or else its first, and + names a
  // new track. The line under it holds the encounter selector and the turn.
  // Empty, Foresight is the bare instrument: the first row named in its
  // empty row makes the track's next note, or with no encounter track yet
  // the track too. Clearing spends the note, which stays in the campaign. The
  // track shown (`foresightTrack`) and the last encounter open in each
  // (`foresightOpen`) are kept per campaign, and Foresight follows the
  // campaign open in Command, as Augury's Tracks set does.
  //
  // The columns are the GM's, edited on the plate with the idioms of
  // Command's tracks: + names one in place, a double-click renames, a drag
  // moves, right-click has Rename and Remove. Each track keeps the columns of
  // its last encounter for the next one, with the campaign, and they're
  // edited there while Foresight is empty. A click on a cell opens it; a number cell takes −7
  // or +3 (encounter.ts enterCell). Rows drag to reorder, and the clicked
  // row takes the keys: ↓/J ↑/K, M, R, ⌘D.
  //
  // Command's drags land here: a note joins as a row linked to it, between
  // rows or at the end, a track's nameplate brings its notes, and an
  // encounter note opens. Drops don't cross windows, so `[[` in the empty
  // row offers the notes too, and Command's *Open in Foresight* and a
  // double-click on a linked name go through Rust. A note gone from its
  // path was renamed or moved, wherever that was done: an encounter with
  // the hash Foresight holds is it, and it's followed there.
  import { onDestroy, tick, type Snippet } from 'svelte';
  import { load } from '@tauri-apps/plugin-store';
  import { DIGIT_VIEWBOX, SEGMENTS, isLit, readoutCells } from '../augury/sevenSegment';
  import { commandApi, onVaultChange } from '../command/api';
  import { linkedNote } from '../command/columns';
  import CommandMenu from '../command/CommandMenu.svelte';
  import InlineName from '../command/InlineName.svelte';
  import { action, choice, divider, keyed, type MenuItem, type OpenMenu } from '../command/menu';
  import { CARD_MIME, TRACK_MIME, draggedNote, isCardDrag, isNoteDrag, isTrackDrag } from '../command/noteDrag';
  import type { CampaignIndex, NoteEntry } from '../command/types';
  import { m } from '../paraglide/messages';
  import { confirmPrompt } from '../shell/confirmStore';
  import { focusPath } from '../shell/focus';
  import { hoist } from '../shell/hoist';
  import { chordHint, eventMatchKey } from '../shell/keybindings';
  import { bindKeys } from '../shell/keys';
  import { appContext } from '../shell/shellState';
  import { parseRecord } from '../shell/storeParsers';
  import { grab } from '../ui/grab';
  import { CARET_RIGHT } from '../ui/iconPaths';
  import RenameField from '../ui/RenameField.svelte';
  import NameField from './NameField.svelte';
  import {
    addColumn,
    addNotes,
    addRow,
    arrival,
    duplicateRow,
    encounterApi,
    encounterTracks,
    enterCell,
    isFigures,
    isRowNote,
    landing,
    linkName,
    moveColumn,
    moveRow,
    onOpenEncounter,
    removeColumn,
    removeRow,
    renameColumn,
    renameRow,
    setCell,
    step,
    stepTrack,
    toggleOut,
    trackEncounters,
    trackNotes,
    typedLink,
    type Encounter,
    type EncounterRow,
  } from './encounter';

  export let windowKey: Snippet | undefined = undefined;
  export let statusSlot: HTMLElement | null = null;

  type Table = Pick<Encounter, 'columns' | 'rows'>;

  // The campaign whose encounter shows; undefined until the first follows.
  let shown: string | null | undefined = undefined;
  let enc: Encounter | null = null;
  // As the settings store keeps them: the track shown by campaign, and the
  // last encounter open by campaign and track.
  let shownTrack: Record<string, string> = {};
  let opened: Record<string, Record<string, string>> = {};
  // The campaign's encounter tracks, and the columns each one's next
  // encounter takes ('' before there's a track), as its index has them.
  // `columnEdits` counts the changes, so an index read before one is dropped.
  let tracks: string[] = [];
  let kept: Record<string, string[]> = {};
  let columnEdits = 0;
  // The campaign Foresight has opened its encounter for; a launch can come
  // before the sidecar is up to answer.
  let settled: string | null = null;
  // The track ◀ ▶ are heading for while it's read, so a second press goes on
  // from there. `arrivals` counts the openings, so a slower one is dropped.
  let headed: string | null = null;
  let arrivals = 0;
  let namingTrack = false;
  let selectorMenu: OpenMenu | null = null;
  let selectorEl: HTMLElement;
  let selected: string | null = null;
  // The empty row's field, opened again after each name for the next.
  let naming = false;
  let named = 0;
  // What's open in place: a cell, a row's name, a column's name, a new
  // column's field.
  let editing: { row: string; col: number } | null = null;
  let renamingRow: string | null = null;
  let renamingColumn: number | null = null;
  let namingColumn = false;
  let menu: OpenMenu | null = null;
  // A row or a column carried by hand, and where it would land: before the
  // row or column at that index, the length for the end.
  let draggingRow: string | null = null;
  let rowDrop: number | null = null;
  let draggingColumn: number | null = null;
  let columnDrop: number | null = null;
  // An encounter from Command over the panel: a drop opens it.
  let opening = false;
  let rowEls: Record<string, HTMLElement> = {};
  // The campaign's index, read when a drag or the empty row needs it and
  // kept until a note other than the open encounter changes.
  let known: CampaignIndex | null = null;
  let knowing: Promise<CampaignIndex | null> | null = null;
  let indexReads = 0;
  let indexTimer: ReturnType<typeof setTimeout> | undefined;
  // The first row is making the encounter; rows added meanwhile wait.
  let creating = false;
  let waiting: ((e: Encounter) => Encounter)[] = [];
  // One write at a time: `dirty` while the state on screen isn't on disk
  // yet, `stale` when the note changed under a write and is read again.
  // `version` counts the states shown, so a read begun before one of them
  // is dropped.
  let writing = false;
  let dirty = false;
  let stale = false;
  let version = 0;
  let flushed: Promise<void> = Promise.resolve();
  let refreshTimer: ReturnType<typeof setTimeout> | undefined;

  /** The columns the very first encounter starts with. */
  const defaultColumns = () => [m.foresight_column_combatant(), m.foresight_column_hp(), m.foresight_column_remarks()];

  // The open encounter's track, else the one shown, while it's still there.
  $: here = enc?.track ?? (shown && tracks.includes(shownTrack[shown]) ? shownTrack[shown] : (tracks[0] ?? null));
  $: columns = enc?.columns.length ? enc.columns : (kept[here ?? ''] ?? defaultColumns());
  $: rows = enc?.rows ?? [];
  // What a column holds decides how it reads, never its name.
  $: figures = columns.map((_, c) => c > 0 && isFigures(rows, c));
  // The step number, the name (never squeezed past a short name), a cell
  // per column (figures narrow), a new column's field while it's named, the
  // M key's slot. Content never sizes a track: each row is a grid of its
  // own, and they must line up.
  $: grid = [
    '1.1rem',
    'minmax(4.5rem, 1.2fr)',
    ...columns.slice(1).map((_, i) => (figures[i + 1] ? '2.9rem' : 'minmax(0, 1fr)')),
    ...(namingColumn ? ['minmax(0, 1fr)'] : []),
    '18px',
  ].join(' ');
  $: cells = readoutCells(enc?.round ?? null, 1);
  $: turnRow = rows.find((r) => r.name === enc?.turn) ?? null;
  // The open encounter's columns are its track's next one's, while the track
  // is there: renamed, the encounter is about to follow it.
  $: if (enc?.columns.length && tracks.includes(enc.track) && enc.columns.join('\n') !== kept[enc.track]?.join('\n')) keepColumns(enc.track, enc.columns);

  const ready = (async () => {
    try {
      const store = await load('settings.json');
      const saved = parseRecord(await store.get('foresightOpen')) ?? {};
      opened = Object.fromEntries(Object.entries(saved).filter(([, v]) => parseRecord(v))) as Record<string, Record<string, string>>;
      const showing = parseRecord(await store.get('foresightTrack')) ?? {};
      shownTrack = Object.fromEntries(Object.entries(showing).filter(([, v]) => typeof v === 'string')) as Record<string, string>;
    } catch (e) {
      console.error('Failed to read the open encounters:', e);
    }
  })();

  async function save(key: 'foresightOpen' | 'foresightTrack', value: unknown) {
    try {
      const store = await load('settings.json');
      await store.set(key, value);
    } catch (e) {
      console.error(`Failed to save ${key}:`, e);
    }
  }

  /** `got` is what shows now: its track is the one shown, and it's the last
   *  open there. */
  function keepOpen(campaign: string, got: Encounter) {
    opened = { ...opened, [campaign]: { ...opened[campaign], [got.track]: got.path } };
    void save('foresightOpen', opened);
    shownTrack = { ...shownTrack, [campaign]: got.track };
    void save('foresightTrack', shownTrack);
  }

  function keepTrack(campaign: string, track: string) {
    shownTrack = { ...shownTrack, [campaign]: track };
    void save('foresightTrack', shownTrack);
  }

  function forgetOpen(campaign: string, track: string) {
    const { [track]: _gone, ...rest } = opened[campaign] ?? {};
    opened = { ...opened, [campaign]: rest };
    void save('foresightOpen', opened);
  }

  /** The columns `track`'s next encounter takes. With no track yet they wait
   *  here for the first, which takes them with its table. */
  function keepColumns(track: string | null, next: string[]) {
    kept = { ...kept, [track ?? '']: next };
    columnEdits += 1;
    if (shown && track) {
      encounterApi.saveColumns(shown, track, next).catch((e) => console.error('Failed to keep the columns:', e));
    }
  }

  // An encounter with no table yet takes its track's columns.
  function shape(got: Encounter): Encounter {
    return got.columns.length ? got : { ...got, columns: kept[got.track] ?? defaultColumns() };
  }

  function closeAll() {
    selected = null;
    naming = false;
    editing = null;
    renamingRow = null;
    renamingColumn = null;
    namingColumn = false;
    namingTrack = false;
    menu = null;
  }

  // Foresight follows Command's campaign.
  $: void follow($appContext.campaign ?? null);

  async function follow(campaign: string | null) {
    if (campaign === shown) return;
    shown = campaign;
    enc = null;
    tracks = [];
    kept = {};
    settled = null;
    headed = null;
    closeAll();
    forgetIndex();
    waiting = [];
    await ready;
    if (campaign) await settle(campaign);
  }

  /** The campaign's first look: its track shown, on arrival. */
  async function settle(campaign: string) {
    const index = await indexFor();
    if (!index || shown !== campaign || settled === campaign) return;
    settled = campaign;
    const track = tracks.includes(shownTrack[campaign]) ? shownTrack[campaign] : tracks[0];
    if (track) await arrive(campaign, track);
  }

  function forgetIndex() {
    known = null;
    knowing = null;
  }

  /** Arrive at a track: the encounter last open there, else its first still
   *  to run, else Foresight is empty on it. */
  async function arrive(campaign: string, track: string) {
    const at = ++arrivals;
    try {
      await flushed;
      const index = await indexFor();
      if (!index || at !== arrivals || shown !== campaign) return;
      const path = arrival(index, track, opened[campaign]?.[track]);
      const got = path ? await encounterApi.read(campaign, path).catch(() => null) : null;
      if (at !== arrivals || shown !== campaign) return;
      closeAll();
      version += 1;
      enc = got && !got.spent ? shape(got) : null;
      if (enc) keepOpen(campaign, enc);
      else keepTrack(campaign, track);
    } finally {
      if (at === arrivals) headed = null;
    }
  }

  /** ◀ and ▶ on the top line. */
  function stepTracks(by: 1 | -1) {
    const campaign = shown;
    const track = stepTrack(tracks, headed ?? here, by);
    if (!campaign || !track) return;
    headed = track;
    forgetIndex();
    void arrive(campaign, track);
  }

  /** The encounter selector: the track's encounters still to run, and a new
   *  one. */
  async function openSelector() {
    const campaign = shown;
    if (!campaign) return;
    forgetIndex();
    const index = await indexFor();
    if (!index || shown !== campaign) return;
    const notes = here ? trackEncounters(index, here) : [];
    const box = selectorEl.getBoundingClientRect();
    const items: MenuItem[] = [
      ...notes.map((note) => choice(note.name, note.path === enc?.path, () => void openEncounter(campaign, note.path))),
      ...(notes.length ? [divider] : []),
      action(m.foresight_new_encounter(), () => void startNew(here)),
    ];
    selectorMenu = { x: box.left, y: box.bottom + 3, items };
    menu = selectorMenu;
  }

  /** *+ New*: Foresight empty on the track, the empty row's field open. The
   *  note waits for its first row, and the one open stays as it is. */
  async function startNew(track: string | null) {
    const campaign = shown;
    if (!campaign) return;
    arrivals += 1;
    headed = null;
    await flushed;
    if (shown !== campaign) return;
    closeAll();
    enc = null;
    version += 1;
    if (track) keepTrack(campaign, track);
    naming = true;
    void indexFor();
  }

  /** `+` on the top line. A name that's taken is refused in the field. */
  async function createTrack(name: string): Promise<string | null> {
    const campaign = shown;
    if (!campaign) return null;
    try {
      const made = await commandApi.createTrack(campaign, name);
      await commandApi.kindTrack(campaign, made, 'encounter');
      forgetIndex();
      await indexFor();
      await startNew(made);
      return null;
    } catch (e) {
      return String(e);
    }
  }

  function indexFor(): Promise<CampaignIndex | null> {
    const campaign = shown;
    if (!campaign) return Promise.resolve(null);
    if (knowing) return knowing;
    const read = ++indexReads;
    const edits = columnEdits;
    knowing = commandApi.getCampaign(campaign).then(
      (got) => {
        if (shown === campaign && read === indexReads) {
          known = got;
          tracks = encounterTracks(got);
          if (edits === columnEdits) kept = { ...(kept[''] ? { '': kept[''] } : {}), ...got.encounter_columns };
        }
        return got;
      },
      (e) => {
        console.error('Failed to read the campaign:', e);
        knowing = null;
        return null;
      },
    );
    return knowing;
  }

  /** Open an encounter of the campaign; the one open is on disk already, so
   *  nothing is lost. A spent one stays Command's to un-spend. */
  async function openEncounter(campaign: string, path: string) {
    const at = ++arrivals;
    headed = null;
    await flushed;
    try {
      const got = await encounterApi.read(campaign, path);
      if (at !== arrivals || shown !== campaign || got.spent) return;
      closeAll();
      enc = shape(got);
      version += 1;
      keepOpen(campaign, got);
    } catch (e) {
      console.error('Failed to open the encounter:', e);
    }
  }

  /** The open encounter's note, gone from its path: the encounter with the
   *  version Foresight holds, wherever it went, or null. */
  async function relocated(campaign: string, gone: Encounter): Promise<Encounter | null> {
    forgetIndex();
    const index = await indexFor();
    for (const note of index?.notes ?? []) {
      if (!note.encounter || note.path === gone.path) continue;
      const got = await encounterApi.read(campaign, note.path).catch(() => null);
      if (got?.hash === gone.hash) return got;
    }
    return null;
  }

  /** Read the open encounter again after a change on disk. Foresight's own
   *  writes come back with the hash it holds, and change nothing. */
  async function refresh() {
    const campaign = shown;
    const path = enc?.path;
    const at = version;
    if (!campaign || !path) return;
    if (writing) {
      stale = true;
      return;
    }
    try {
      const got = await encounterApi.read(campaign, path);
      if (shown !== campaign || enc?.path !== path || writing || version !== at) return;
      if (got.spent) {
        enc = null;
        closeAll();
        forgetOpen(campaign, got.track);
      } else if (got.hash !== enc.hash) {
        enc = shape(got);
        if (selected && !enc.rows.some((r) => r.name === selected)) selected = null;
      }
    } catch (e) {
      // Renamed or moved: follow it, and write what the move may have
      // refused. Deleted, or moved out of the encounter tracks: Foresight is
      // empty.
      if (shown !== campaign || enc?.path !== path || writing) return;
      const moved = await relocated(campaign, enc);
      if (shown !== campaign || enc?.path !== path || writing) return;
      if (moved) {
        keepOpen(campaign, moved);
        change({ ...enc, path: moved.path, name: moved.name, track: moved.track });
      } else {
        console.error('Failed to read the encounter again:', e);
        enc = null;
        closeAll();
      }
    }
  }

  const unlistenVault = onVaultChange((event) => {
    const ours = event.campaign === null || event.campaign === shown;
    // The top line shows the tracks, so what's forgotten is read again.
    if (ours && (!event.paths.length || event.paths.some((p) => p !== enc?.path))) {
      forgetIndex();
      clearTimeout(indexTimer);
      indexTimer = setTimeout(() => void (shown && settled !== shown ? settle(shown) : indexFor()), 120);
    }
    if (!enc || !ours || (event.campaign !== null && !event.paths.includes(enc.path))) return;
    clearTimeout(refreshTimer);
    refreshTimer = setTimeout(() => void refresh(), 150);
  });

  /** Show `next` and write it. */
  function change(next: Encounter) {
    enc = next;
    version += 1;
    dirty = true;
    if (!writing) flushed = write();
  }

  async function write() {
    const campaign = shown;
    writing = true;
    try {
      while (dirty && enc && campaign && shown === campaign) {
        dirty = false;
        const sent = enc;
        const outcome = await encounterApi.save(campaign, sent);
        if (shown !== campaign || enc?.path !== sent.path) break;
        if (outcome.status === 'conflict') {
          stale = true;
          break;
        }
        enc = { ...enc, hash: outcome.hash };
        version += 1;
      }
    } catch (e) {
      console.error('Failed to save the encounter:', e);
      stale = true;
    } finally {
      writing = false;
    }
    // The note changed under the write, or the write failed: the note's
    // version replaces what wasn't written.
    if (stale) {
      stale = false;
      dirty = false;
      await refresh();
    }
  }

  const unlistenOpen = onOpenEncounter((at) => {
    if (at.campaign === shown) void openEncounter(at.campaign, at.path);
  });

  /** A change to the columns: the open encounter's, or with none open the
   *  ones the track's next encounter takes. */
  function editColumns(edit: <T extends Table>(t: T) => T) {
    if (enc) change(edit(enc));
    else keepColumns(here, edit({ columns, rows: [] as EncounterRow[] }).columns);
  }

  // ---- turns and rows --------------------------------------------------------

  function pass(by: 1 | -1) {
    if (!enc) return;
    const next = step(enc, by);
    if (next.turn !== enc.turn || next.round !== enc.round) change({ ...enc, ...next });
  }

  function toggle(name: string) {
    if (enc) change(toggleOut(enc, name));
  }

  function duplicate(name: string) {
    if (!enc) return;
    const next = duplicateRow(enc, name);
    change(next);
    void reveal(next.rows[next.rows.findIndex((r) => r.name === name) + 1]?.name ?? name);
  }

  function remove(name: string) {
    if (!enc) return;
    change(removeRow(enc, name));
    if (selected === name) selected = null;
  }

  function commitRename(name: string, wanted: string) {
    renamingRow = null;
    if (!enc) return;
    const at = enc.rows.findIndex((r) => r.name === name);
    const next = renameRow(enc, name, wanted);
    change(next);
    if (selected === name) selected = next.rows[at]?.name ?? null;
  }

  function commitCell(name: string, col: number, before: string, typed: string) {
    editing = null;
    if (enc) change(setCell(enc, name, col, enterCell(before, typed)));
  }

  function clearCell(name: string, col: number) {
    editing = null;
    if (enc) change(setCell(enc, name, col, ''));
  }

  /** Select a row and bring it into view. */
  async function reveal(name: string) {
    selected = name;
    await tick();
    rowEls[name]?.scrollIntoView({ block: 'nearest' });
  }

  /** ↓/J and ↑/K: the next or previous row, from the turn's when none is
   *  selected. */
  function moveSelection(by: 1 | -1): boolean {
    if (!rows.length) return false;
    const at = rows.findIndex((r) => r.name === selected);
    const from = at >= 0 ? at + by : Math.max(0, rows.findIndex((r) => r.name === enc?.turn));
    void reveal(rows[Math.min(rows.length - 1, Math.max(0, from))].name);
    return true;
  }

  /** Add rows to the open encounter, or make one to hold them. */
  async function addTo(edit: (e: Encounter) => Encounter) {
    const campaign = shown;
    if (!campaign) return;
    if (enc) {
      change(edit(enc));
      return;
    }
    if (creating) {
      waiting = [...waiting, edit];
      return;
    }
    creating = true;
    try {
      const blank: Encounter = { path: '', name: '', track: here ?? '', hash: '', spent: null, round: 1, turn: null, columns, rows: [] };
      const made = await encounterApi.create(campaign, here, columns, edit(blank).rows);
      if (shown !== campaign) return;
      arrivals += 1;
      keepOpen(campaign, made);
      enc = shape(made);
      forgetIndex();
      void indexFor();
      if (waiting.length) change(waiting.reduce((e, add) => add(e), enc));
    } catch (e) {
      console.error('Failed to start an encounter:', e);
    } finally {
      creating = false;
      waiting = [];
    }
  }

  /** The empty row's name: a note taken from `[[`'s offer, a link typed in
   *  its brackets, or a plain name. */
  async function commitName(text: string, note: NoteEntry | null) {
    named += 1;
    const typed = note ? null : typedLink(text);
    const index = note || typed ? await indexFor() : null;
    // An alias typed is the GM's name for the row; without one, a note it
    // names joins as a dropped note does.
    const plain = typed && typed.name === linkName(typed.link);
    const linked = note ?? (index && plain ? linkedNote(index, typed.link) : undefined);
    if (linked && index) void addTo((e) => addNotes(e, [linked], index.notes));
    else if (typed) void addTo((e) => addRow(e, typed.name, typed.link));
    else void addTo((e) => addRow(e, note?.name ?? text));
  }

  /** A double-click on a linked name, or *Open note*: the note, in Command,
   *  wherever it is. A link to nothing goes nowhere. */
  async function openLinked(row: EncounterRow) {
    const campaign = shown;
    if (!campaign || !row.link) return;
    const index = await indexFor();
    const note = index && linkedNote(index, row.link);
    if (note) await commandApi.openNote(campaign, note.path).catch((e) => console.error('Failed to open the note:', e));
  }

  /** Clearing is spending: the note is spent and stays in the campaign. */
  async function clear() {
    const campaign = shown;
    const open = enc;
    if (!campaign || !open) return;
    const { path, track } = open;
    await flushed;
    try {
      await commandApi.setSpent(campaign, path, true);
      if (shown === campaign && enc?.path === path) {
        enc = null;
        closeAll();
      }
      forgetOpen(campaign, track);
      forgetIndex();
      void indexFor();
    } catch (e) {
      console.error('Failed to clear the encounter:', e);
    }
  }

  function rowMenu(e: MouseEvent, row: EncounterRow) {
    selected = row.name;
    menu = {
      x: e.clientX,
      y: e.clientY,
      items: [
        ...(row.link ? [action(m.foresight_open_note(), () => void openLinked(row))] : []),
        keyed(m.foresight_rename(), 'foresight.rename', () => (renamingRow = row.name)),
        keyed(m.foresight_duplicate(), 'foresight.duplicate', () => duplicate(row.name)),
        action(m.foresight_remove(), () => remove(row.name), true),
      ],
    };
  }

  // ---- columns ---------------------------------------------------------------

  function columnMenu(e: MouseEvent, c: number) {
    menu = {
      x: e.clientX,
      y: e.clientY,
      items: [
        action(m.foresight_rename(), () => (renamingColumn = c)),
        ...(c > 0 ? [action(m.foresight_remove(), () => void dropColumn(c), true)] : []),
      ],
    };
  }

  /** A column holding cells goes only once the GM says so. */
  async function dropColumn(c: number) {
    if (rows.some((r) => (r.cells[c - 1] ?? '').trim() !== '')) {
      const confirmed = await confirmPrompt.request({
        title: m.foresight_remove_column_title({ column: columns[c] }),
        message: m.foresight_remove_column_message(),
        confirmLabel: m.foresight_remove(),
        danger: true,
      });
      if (!confirmed) return;
    }
    editColumns((t) => removeColumn(t, c));
  }

  // ---- carrying by hand ------------------------------------------------------

  function startRowDrag(e: DragEvent, name: string) {
    draggingRow = name;
    if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move';
  }

  /** A row or a note over row `i` (the empty row is the rows' length)
   *  points between rows, by which half of the row the pointer is in. */
  function overRow(e: DragEvent, i: number) {
    const box = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const slot = i < rows.length && e.clientY >= box.top + box.height / 2 ? i + 1 : i;
    if (draggingRow === null) {
      overPanel(e, slot);
      return;
    }
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
    rowDrop = slot;
  }

  function dropRow(e: DragEvent) {
    if (draggingRow === null) return;
    e.preventDefault();
    if (enc && rowDrop !== null) change(moveRow(enc, draggingRow, rowDrop));
    endDrag();
  }

  // ---- drags from Command ----------------------------------------------------

  /** What a drag from Command carries, read while the event lasts. */
  type Carry = { note: NoteEntry } | { paths: string[] } | { track: string };

  function carryOf(e: DragEvent): Carry | null {
    const data = e.dataTransfer;
    if (!data) return null;
    const note = isNoteDrag(e) ? draggedNote() : null;
    if (note) return { note };
    if (isCardDrag(e)) return { paths: data.getData(CARD_MIME).split('\n').filter(Boolean) };
    if (isTrackDrag(e)) return { track: data.getData(TRACK_MIME) };
    return null;
  }

  /** The carried notes as the campaign has them. A note from elsewhere, the
   *  shelf's other campaigns, isn't one of them. */
  function notesOf(carry: Carry, index: CampaignIndex): NoteEntry[] {
    if ('track' in carry) return trackNotes(index, carry.track);
    const paths = 'note' in carry ? [carry.note.path] : carry.paths;
    return paths.flatMap((p) => index.notes.find((n) => n.path === p) ?? []);
  }

  /** Over the panel, a row's slot given or the end. Until the index is read
   *  only a note's own entry says what the drop would do; rows, otherwise. */
  function overPanel(e: DragEvent, slot: number) {
    if (e.defaultPrevented || !shown) return;
    const carry = carryOf(e);
    if (!carry) return;
    const notes = known ? notesOf(carry, known) : 'note' in carry ? [carry.note] : null;
    const lands = notes ? landing(notes) : 'rows';
    opening = lands === 'open';
    rowDrop = lands === 'rows' ? slot : null;
    if (lands === 'none') return;
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy';
  }

  async function dropOnPanel(e: DragEvent) {
    const campaign = shown;
    const carry = carryOf(e);
    if (!campaign || !carry) return;
    e.preventDefault();
    const slot = rowDrop ?? undefined;
    endDrag();
    const index = await indexFor();
    if (!index || shown !== campaign) return;
    const notes = notesOf(carry, index);
    const lands = landing(notes);
    if (lands === 'open') void openEncounter(campaign, notes[0].path);
    if (lands === 'rows') void addTo((t) => addNotes(t, notes.filter(isRowNote), index.notes, slot));
  }

  function startColumnDrag(e: DragEvent, c: number) {
    draggingColumn = c;
    if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move';
  }

  /** A column over column `c`'s name points between columns; over the
   *  names' column, it lands first after it. */
  function overColumn(e: DragEvent, c: number) {
    if (draggingColumn === null) return;
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
    const box = (e.currentTarget as HTMLElement).getBoundingClientRect();
    columnDrop = c === 0 ? 1 : e.clientX >= box.left + box.width / 2 ? c + 1 : c;
  }

  function dropColumnAt(e: DragEvent) {
    if (draggingColumn === null) return;
    e.preventDefault();
    if (columnDrop !== null) {
      const [from, to] = [draggingColumn, columnDrop];
      editColumns((t) => moveColumn(t, from, to));
    }
    endDrag();
  }

  // A drag delivers no pointerleave: unlatch on its end, dropped or not.
  function endDrag() {
    draggingRow = null;
    rowDrop = null;
    draggingColumn = null;
    columnDrop = null;
    opening = false;
  }

  function leave(e: DragEvent) {
    if (!(e.currentTarget as HTMLElement).contains(e.relatedTarget as Node | null)) {
      rowDrop = null;
      columnDrop = null;
      opening = false;
    }
  }

  // ---- keys ------------------------------------------------------------------

  const unbindKeys = bindKeys(
    (event, ctx) => {
      if (event.defaultPrevented || event.isComposing || ctx.typing || ctx.menu || event.altKey) return false;
      if (eventMatchKey(event) === 'meta+d') {
        if (!selected || !enc) return false;
        duplicate(selected);
        return true;
      }
      if (event.metaKey || event.ctrlKey) return false;
      if (event.key === ' ' && event.shiftKey) {
        pass(1);
        return !!enc;
      }
      if (event.shiftKey) return false;
      const key = event.key.length === 1 ? event.key.toLowerCase() : event.key;
      if (key === 'ArrowDown' || key === 'j') return moveSelection(1);
      if (key === 'ArrowUp' || key === 'k') return moveSelection(-1);
      if (!selected || !enc) return false;
      if (key === 'm') {
        toggle(selected);
        return true;
      }
      if (key === 'r') {
        renamingRow = selected;
        return true;
      }
      if (key === 'Escape') {
        selected = null;
        return true;
      }
      return false;
    },
    { tool: 'foresight' },
  );

  onDestroy(() => {
    unbindKeys();
    clearTimeout(refreshTimer);
    clearTimeout(indexTimer);
    void unlistenVault.then((stop) => stop());
    void unlistenOpen.then((stop) => stop());
  });
</script>

<section
  class="foresight"
  class:dormant={$focusPath.tool !== 'foresight'}
  class:opening
  role="presentation"
  style:--grid={grid}
  on:dragenter={(e) => carryOf(e) && void indexFor()}
  on:dragover={(e) => overPanel(e, rows.length)}
  on:dragleave={leave}
  on:drop={dropOnPanel}
>
  <!-- The top line, Augury's strip: which encounter track. -->
  <header class="bar">
    <div class="well browser" role="group" aria-label={m.foresight_tracks_label()}>
      <button
        type="button"
        class="key"
        disabled={tracks.length < 2}
        title={m.foresight_track_previous()}
        aria-label={m.foresight_track_previous()}
        on:click={() => stepTracks(-1)}
      >
        <svg class="back" viewBox="96 64 512 512" fill="currentColor" aria-hidden="true"><path d={CARET_RIGHT} /></svg>
      </button>
      <span class="display" class:none={!tracks.length} title={headed ?? here ?? m.foresight_default_track()}>
        {#if namingTrack}
          <!-- RenameField rather than InlineName: a name that's taken needs
               its refusal. -->
          <span class="track-field">
            <RenameField
              value=""
              placeholder={m.command_tracks_track_name()}
              label={m.foresight_new_track()}
              onCommit={createTrack}
              onCancel={() => (namingTrack = false)}
            />
          </span>
        {:else}
          <span class="track-name readout-label">{headed ?? here ?? m.foresight_default_track()}</span>
        {/if}
      </span>
      <button
        type="button"
        class="key"
        disabled={tracks.length < 2}
        title={m.foresight_track_next()}
        aria-label={m.foresight_track_next()}
        on:click={() => stepTracks(1)}
      >
        <svg viewBox="96 64 512 512" fill="currentColor" aria-hidden="true"><path d={CARET_RIGHT} /></svg>
      </button>
      <span class="rule" aria-hidden="true"></span>
      <button
        type="button"
        class="key plus"
        disabled={!shown}
        title={m.foresight_new_track()}
        aria-label={m.foresight_new_track()}
        on:click={() => (namingTrack = true)}>+</button
      >
    </div>
    {@render windowKey?.()}
  </header>

  <!-- Which encounter, and its turn. -->
  <div class="line">
    <div class="pick-well">
      <button
        bind:this={selectorEl}
        type="button"
        class="pick"
        class:none={!enc}
        class:open={menu !== null && menu === selectorMenu}
        disabled={!shown}
        title={enc?.name ?? m.foresight_selector_title()}
        aria-label={m.foresight_selector_title()}
        on:click={() => void openSelector()}
      >
        <span class="pick-name">{enc?.name ?? m.foresight_no_encounter()}</span>
        <!-- Font Awesome caret-right, turned down by .drop-caret -->
        <svg class="drop-caret" viewBox="96 64 512 512" fill="currentColor" aria-hidden="true"><path d={CARET_RIGHT} /></svg>
      </button>
    </div>
    <div class="well" role="group" aria-label={m.foresight_turn_label()}>
      <button
        type="button"
        class="key"
        disabled={!enc}
        title={m.foresight_turn_previous()}
        aria-label={m.foresight_turn_previous()}
        on:click={() => pass(-1)}
      >
        <svg class="back" viewBox="96 64 512 512" fill="currentColor" aria-hidden="true"><path d={CARET_RIGHT} /></svg>
      </button>
      <!-- Augury's readout lamps, small: the round, as a sequencer counts
           its bars. -->
      <span class="round" title={enc ? m.foresight_round_title({ round: enc.round }) : undefined}>
        {#each cells as char, i (i)}
          <svg class="digit" viewBox={DIGIT_VIEWBOX} aria-hidden="true">
            {#each SEGMENTS as [segment, points] (segment)}
              <polygon {points} class:lit={isLit(char, segment)} />
            {/each}
          </svg>
        {/each}
      </span>
      <button
        type="button"
        class="key"
        disabled={!enc}
        title={m.foresight_turn_next() + chordHint('foresight.next')}
        aria-label={m.foresight_turn_next()}
        on:click={() => pass(1)}
      >
        <svg viewBox="96 64 512 512" fill="currentColor" aria-hidden="true"><path d={CARET_RIGHT} /></svg>
      </button>
      <span class="rule" aria-hidden="true"></span>
      <!-- Command's spend key: clearing spends the encounter's note. -->
      <button
        type="button"
        class="key"
        disabled={!enc}
        title={enc ? m.foresight_clear_title({ name: enc.name }) : m.foresight_clear_label()}
        aria-label={m.foresight_clear_label()}
        on:click={() => void clear()}
      >
        <!-- Font Awesome "box-archive" icon (src/lib/ui/icons/box-archive-solid-full.svg),
             its viewBox cropped to the glyph. -->
        <svg class="spend" viewBox="64 96 512 448" fill="currentColor" aria-hidden="true">
          <path
            d="M64 128C64 110.3 78.3 96 96 96L544 96C561.7 96 576 110.3 576 128L576 160C576 177.7 561.7 192 544 192L96 192C78.3 192 64 177.7 64 160L64 128zM96 240L544 240L544 480C544 515.3 515.3 544 480 544L160 544C124.7 544 96 515.3 96 480L96 240zM248 304C234.7 304 224 314.7 224 328C224 341.3 234.7 352 248 352L392 352C405.3 352 416 341.3 416 328C416 314.7 405.3 304 392 304L248 304z"
          />
        </svg>
      </button>
    </div>
  </div>

  <!-- The plate names the columns, the rows' names first; Command's track
       plates are edited the same way. -->
  <div class="plate nameplate">
    <span aria-hidden="true"></span>
    {#each columns as column, c (c)}
      {#if renamingColumn === c}
        <span class="col-field" class:figures={figures[c]}>
          <RenameField
            value={column}
            label={m.foresight_column_rename_label({ column })}
            onCommit={(name) => {
              renamingColumn = null;
              editColumns((t) => renameColumn(t, c, name));
            }}
            onCancel={() => (renamingColumn = null)}
          />
        </span>
      {:else}
        <span
          class="ledger-label col"
          class:cell-head={c > 0}
          class:figures={figures[c]}
          class:dragging={draggingColumn === c}
          class:drop-before={c > 0 && columnDrop === c}
          class:drop-after={c === columns.length - 1 && columnDrop === columns.length}
          role="columnheader"
          tabindex="-1"
          title={column}
          use:grab={c > 0}
          on:dragstart={(e) => startColumnDrag(e, c)}
          on:dragend={endDrag}
          on:dragover={(e) => overColumn(e, c)}
          on:drop={dropColumnAt}
          on:dblclick={() => (renamingColumn = c)}
          on:contextmenu|preventDefault={(e) => columnMenu(e, c)}>{column}</span
        >
      {/if}
    {/each}
    {#if namingColumn}
      <span class="col-field">
        <InlineName
          bare
          placeholder={m.foresight_column_placeholder()}
          label={m.foresight_column_new_label()}
          onCommit={(name) => {
            namingColumn = false;
            editColumns((t) => addColumn(t, name));
          }}
          onCancel={() => (namingColumn = false)}
        />
      </span>
    {/if}
    <button
      type="button"
      class="add"
      class:hidden={namingColumn}
      title={m.foresight_column_add_title()}
      aria-label={m.foresight_column_add_title()}
      on:click={() => (namingColumn = true)}>+</button
    >
  </div>

  <ol class="rows" aria-label={m.foresight_rows_label()}>
    {#each rows as row, i (row.name)}
      {@const playing = row.name === enc?.turn}
      {@const open = renamingRow === row.name || editing?.row === row.name}
      <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_noninteractive_element_interactions -->
      <li
        class="row"
        class:playing
        class:out={row.out}
        class:selected={row.name === selected}
        class:dragging={draggingRow === row.name}
        class:drop-before={rowDrop === i}
        aria-current={playing ? 'step' : undefined}
        bind:this={rowEls[row.name]}
        use:grab={!open}
        on:dragstart={(e) => startRowDrag(e, row.name)}
        on:dragend={endDrag}
        on:dragover={(e) => overRow(e, i)}
        on:drop={dropRow}
        on:click={() => (selected = row.name)}
        on:contextmenu|preventDefault={(e) => rowMenu(e, row)}
      >
        <span class="num">{String(i + 1).padStart(2, '0')}</span>
        {#if renamingRow === row.name}
          <span class="name editing">
            <RenameField
              value={row.name}
              label={m.foresight_row_rename_label({ name: row.name })}
              onCommit={(name) => commitRename(row.name, name)}
              onCancel={() => (renamingRow = null)}
            />
          </span>
        {:else}
          <!-- svelte-ignore a11y_no_static_element_interactions -->
          <span class="name" title={row.name} on:dblclick={() => void openLinked(row)}>{row.name}</span>
        {/if}
        {#each row.cells as cell, c (c)}
          {#if editing?.row === row.name && editing.col === c + 1}
            <span class="cell editing" class:figures={figures[c + 1]}>
              <RenameField
                value={cell}
                label={m.foresight_cell_label({ name: row.name, column: columns[c + 1] ?? '' })}
                onCommit={(typed) => commitCell(row.name, c + 1, cell, typed)}
                onCancel={() => (editing = null)}
                onEmpty={() => clearCell(row.name, c + 1)}
              />
            </span>
          {:else}
            <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
            <span
              class="cell"
              class:figures={figures[c + 1]}
              title={cell || undefined}
              on:click={() => {
                selected = row.name;
                editing = { row: row.name, col: c + 1 };
              }}>{cell}</span
            >
          {/if}
        {/each}
        <!-- Legend Lore's mute: out of the fight, the GM's call. -->
        <button
          type="button"
          class="sm-btn"
          class:mute-on={row.out}
          aria-pressed={row.out}
          aria-label={m.foresight_out_label()}
          title={(row.out ? m.foresight_in_title({ name: row.name }) : m.foresight_out_title({ name: row.name })) + chordHint('foresight.out')}
          on:click|stopPropagation={() => toggle(row.name)}>M</button
        >
      </li>
    {/each}
    <!-- The empty row: a new row is named in place, the next one after it. -->
    <li
      class="row empty"
      class:naming
      class:drop-before={rowDrop === rows.length}
      on:dragover={(e) => overRow(e, rows.length)}
      on:drop={dropRow}
    >
      <span class="num" aria-hidden="true"></span>
      {#if naming}
        {#key named}
          <span class="field">
            <NameField
              placeholder={m.foresight_name_placeholder({ column: columns[0] ?? '' })}
              label={m.foresight_name_label()}
              notes={known?.notes ?? []}
              onCommit={(text, note) => void commitName(text, note)}
              onCancel={() => (naming = false)}
            />
          </span>
        {/key}
      {:else}
        <button
          type="button"
          class="ghost"
          disabled={!shown}
          title={shown ? m.foresight_new_row_title() : m.foresight_no_campaign()}
          on:click={() => {
            naming = true;
            void indexFor();
          }}
        >
          {m.foresight_name_placeholder({ column: columns[0] ?? '' })}
        </button>
      {/if}
    </li>
  </ol>
</section>

{#if menu}
  <CommandMenu x={menu.x} y={menu.y} items={menu.items} onClose={() => (menu = null)} />
{/if}

{#if statusSlot && enc && turnRow}
  <div class="status-section" use:hoist={statusSlot}>
    <span class="rule" aria-hidden="true"></span>
    <span class="where" title={m.foresight_status_title({ round: enc.round, name: turnRow.name })}>
      <span>{m.foresight_status_round({ round: enc.round })}</span>
      <span class="sep" aria-hidden="true">·</span>
      <span class="who">{turnRow.name}</span>
    </span>
  </div>
{/if}

<style>
  .foresight.dormant {
    --ring-focus: var(--ring-dormant);
  }

  .foresight {
    height: 100%;
    display: flex;
    flex-direction: column;
    background: var(--bg-app);
    color: var(--text-primary);
  }

  /* The dashed parchment of what a drop would become (BeatColumn .drop-into). */
  .foresight.opening {
    outline: var(--outline-drop);
    outline-offset: -1px;
  }

  /* Augury's bar: the same height, inset and rule. */
  .bar {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
    height: var(--header-height);
    padding: 1px 0.5rem 0;
    background: var(--bg-header);
    border-bottom: 1px solid var(--border-subtle);
  }

  /* Augury's strip (AuguryPanel .browser, .display, .set-name). */
  .browser {
    flex: 1;
    min-width: 0;
  }

  .display {
    flex: 1;
    min-width: 0;
    display: flex;
    align-items: center;
    height: 22px;
    padding: 0 0.3rem;
  }

  .track-name {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  /* The track the first row will make, a step down the ramp. */
  .display.none .track-name {
    color: var(--text-tertiary);
  }

  .track-field {
    flex: 1;
    min-width: 0;
    display: flex;
    font-size: 0.8rem;
  }

  .key.plus {
    font-size: 0.95rem;
    line-height: 1;
  }

  .line {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    gap: 0.4rem;
    height: 34px;
    padding: 0 0.5rem;
    background: var(--bg-header);
    border-bottom: 1px solid var(--border-subtle);
  }

  /* Command's campaign key in its well (CommandPanel .key-body, .key-face). */
  .pick-well {
    flex: 1;
    min-width: 0;
    display: flex;
    padding: 2px;
    background: var(--bg-app);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-well);
  }

  .pick {
    flex: 1;
    min-width: 0;
    display: flex;
    align-items: center;
    gap: 0.35rem;
    height: 22px;
    padding: 0 0.4rem 0 0.45rem;
    background: var(--bg-header);
    border: none;
    border-radius: var(--radius-md);
    font-family: var(--font-body);
    font-size: 0.95rem;
    color: var(--text-primary);
    cursor: pointer;
    transition: all var(--transition-fast);
    -webkit-user-select: none;
    user-select: none;
  }

  .pick:active:not(:disabled) {
    transform: scale(0.97);
  }

  .pick:disabled {
    cursor: default;
  }

  /* No encounter open: off, on the floor in tertiary ink. */
  .pick.none {
    background: transparent;
    font-style: italic;
    color: var(--text-tertiary);
  }

  .pick:hover:not(:disabled),
  .pick.open {
    color: var(--text-primary);
  }

  .pick.open {
    background: transparent;
  }

  .pick-name {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    text-align: left;
  }

  .drop-caret {
    flex-shrink: 0;
    width: 8px;
    height: 8px;
    transform: rotate(90deg);
    color: var(--text-tertiary);
    transition: color var(--transition-fast);
  }

  .pick:hover .drop-caret,
  .pick.open .drop-caret {
    color: var(--text-primary);
  }

  /* Augury's set strip (AuguryPanel .well, .key). */
  .well {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    gap: 2px;
    padding: 2px;
    background: var(--bg-app);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-well);
  }

  .key {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 26px;
    height: 22px;
    padding: 0;
    background: transparent;
    border: none;
    border-radius: var(--radius-md);
    color: var(--text-tertiary);
    cursor: pointer;
  }

  .key:hover:not(:disabled) {
    color: var(--text-primary);
  }

  .key:active:not(:disabled) {
    transform: scale(0.97);
  }

  .key:disabled {
    opacity: 0.35;
    cursor: default;
  }

  .key svg {
    width: 12px;
    height: 12px;
  }

  .key svg.spend {
    width: 11px;
    height: 11px;
  }

  .back {
    transform: scaleX(-1);
  }

  .well .rule {
    width: 1px;
    height: 14px;
    margin: 0 1px;
    background: var(--border-subtle);
  }

  /* Augury's readout lamps, small. No ghost digit ahead of the round:
     beside the name, an unlit 8 reads as part of it. */
  .round {
    --ghost: color-mix(in srgb, var(--text-accent) 12%, transparent);
    flex-shrink: 0;
    display: flex;
    justify-content: center;
    gap: 2px;
    min-width: 1.1rem;
    padding: 0 0.15rem;
  }

  .digit {
    width: 0.62rem;
    height: 1.12rem;
  }

  polygon {
    fill: var(--ghost);
  }

  polygon.lit {
    fill: var(--text-accent);
  }

  /* The plate and every row share one set of columns. */
  .plate,
  .row {
    display: grid;
    grid-template-columns: var(--grid);
    align-items: center;
    column-gap: 0.35rem;
    min-height: 1.65rem;
    padding: 0 0.5rem 0 calc(0.5rem - 2px);
    border-left: 2px solid transparent;
  }

  .plate {
    flex-shrink: 0;
    border-bottom: 1px solid var(--border-subtle);
  }

  .plate .col {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    cursor: default;
  }

  .cell-head,
  .cell {
    padding-left: 0.35rem;
  }

  /* Figures: right-aligned, the header with them. */
  .col.figures,
  .cell.figures {
    padding-left: 0;
    text-align: right;
  }

  .col-field {
    min-width: 0;
    font-size: 0.8rem;
  }

  .col-field.figures :global(.rename-field) {
    text-align: right;
  }

  .col-field :global(.inline-name::placeholder) {
    font-style: italic;
  }

  .add {
    grid-column: -2;
    width: 18px;
    height: 18px;
    padding: 0;
    background: none;
    border: none;
    color: var(--text-tertiary);
    font-family: var(--font-readout);
    font-size: 0.8rem;
    cursor: pointer;
  }

  .add:hover {
    color: var(--text-primary);
  }

  .add.hidden {
    visibility: hidden;
  }

  /* A column carried by hand: an accent rule marks where it would land. */
  .col.dragging {
    opacity: 0.4;
  }

  .col.drop-before {
    box-shadow: inset 2px 0 0 var(--text-accent);
  }

  .col.drop-after {
    box-shadow: inset -2px 0 0 var(--text-accent);
  }

  .rows {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  /* Command's ledger lines: a hairline at each row's foot. */
  .row {
    box-shadow: inset 0 -1px 0 var(--border-subtle);
    cursor: default;
  }

  .row:hover:not(.empty) {
    background: var(--bg-focused);
  }

  .row.selected {
    box-shadow: var(--ring-focus);
  }

  /* Legend Lore's playing highlight (CollectionsPanel .row-container.playing),
     as Command's live beat wears it: whose turn it is. */
  .row.playing,
  .row.playing:hover {
    background: color-mix(in srgb, var(--text-accent) 8%, transparent);
    border-left-color: var(--text-active);
  }

  /* A row carried by hand, as Command's beats: it fades, and an accent rule
     marks where it would land. */
  .row.dragging {
    opacity: 0.4;
  }

  .row.drop-before {
    box-shadow: inset 0 2px 0 var(--text-accent);
  }

  .num {
    font-family: var(--font-readout);
    font-size: 0.65rem;
    font-variant-numeric: tabular-nums;
    color: var(--text-tertiary);
  }

  .name,
  .cell {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .name {
    font-size: 0.9rem;
  }

  /* The whole height of the row takes the click that opens a cell. */
  .cell {
    align-self: stretch;
    line-height: 1.65rem;
    font-size: 0.8rem;
    color: var(--text-secondary);
    cursor: text;
  }

  /* Figures: tabular readout digits in parchment, as data. */
  .cell.figures {
    font-family: var(--font-readout);
    font-size: 0.7rem;
    font-variant-numeric: tabular-nums;
    color: var(--text-accent);
  }

  .cell.figures :global(.rename-field) {
    text-align: right;
  }

  /* A field open in a cell or a name: room for its ring. */
  .cell.editing,
  .name.editing {
    display: flex;
    align-items: center;
    overflow: visible;
  }

  /* Out of the fight: down the ramp, not faded; the mute key stays lit. */
  .row.out .name,
  .row.out .cell,
  .row.out .num {
    color: var(--text-tertiary);
  }

  /* The M key shows while lit, on the turn's row, the selected one and
     under the pointer, as Command's spend key shows on a row; its slot is
     always kept, the last. */
  .row .sm-btn {
    grid-column: -2;
  }

  .row .sm-btn:not(.mute-on) {
    visibility: hidden;
  }

  .row:hover .sm-btn,
  .row.playing .sm-btn,
  .row.selected .sm-btn {
    visibility: visible;
  }

  /* The empty row: the next line of the ledger, naming in place. */
  .ghost,
  .field {
    grid-column: 2 / -1;
    min-width: 0;
  }

  .ghost {
    padding: 0;
    background: none;
    border: none;
    text-align: left;
    font-family: var(--font-body);
    font-size: 0.9rem;
    font-style: italic;
    color: var(--text-tertiary);
    cursor: text;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .ghost:disabled {
    cursor: default;
  }

  .row.empty:hover .ghost:not(:disabled) {
    color: var(--text-secondary);
  }

  .field {
    font-size: 0.9rem;
  }

  /* Status bar section (Command's SessionStatus). */
  .where {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
  }

  .sep {
    color: var(--text-tertiary);
  }

  .who {
    max-width: 24ch;
    overflow: hidden;
    text-overflow: ellipsis;
    color: var(--text-accent);
  }
</style>
