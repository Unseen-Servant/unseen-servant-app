// Foresight's encounter (docs/roadmap/2026-11-03-foresight-design.md): a note
// in an encounter track, whose table is the tracker, read and written by the sidecar
// (sidecar/command/encounter.py) through Rust (command.rs). The turn logic is
// here, pure: whose turn comes next, the round, the rows out of the fight.

import { invoke } from '@tauri-apps/api/core';
import { listen, type UnlistenFn } from '@tauri-apps/api/event';
import { columns } from '../command/columns';
import type { CampaignIndex, NoteEntry, SaveOutcome } from '../command/types';

export interface EncounterRow {
  name: string;
  /** The note the name links to, as the link spells it; null for a name
   *  typed in. */
  link: string | null;
  /** Out of the fight: struck through on disk, passed over by the turn. */
  out: boolean;
  /** A cell for each column after the first. */
  cells: string[];
}

export interface Encounter {
  path: string;
  name: string;
  /** The encounter track holding it. */
  track: string;
  /** The version read, which a save is checked against. */
  hash: string;
  spent: string | null;
  round: number;
  /** The name of the row whose turn it is; null with no rows. */
  turn: string | null;
  /** The table's header row, the rows' names first. */
  columns: string[];
  rows: EncounterRow[];
}

export const encounterApi = {
  read: (campaign: string, path: string) => invoke<Encounter>('command_read_encounter', { campaign, path }),
  save: (campaign: string, e: Encounter) =>
    invoke<SaveOutcome>('command_save_encounter', {
      campaign,
      path: e.path,
      baseHash: e.hash,
      round: e.round,
      turn: e.turn,
      columns: e.columns,
      rows: e.rows,
    }),
  /** In `track`, or with none the campaign's first encounter track, or a new
   *  one. */
  create: (campaign: string, track: string | null, columns: string[], rows: EncounterRow[]) =>
    invoke<Encounter>('command_create_encounter', { campaign, track, columns, rows }),
  /** The columns `track`'s next encounter takes. */
  saveColumns: (campaign: string, track: string, columns: string[]) =>
    invoke<void>('command_save_encounter_columns', { campaign, track, columns }),
};

/** Command asks Foresight to open an encounter (commandApi.openEncounter). */
export function onOpenEncounter(handler: (at: { campaign: string; path: string }) => void): Promise<UnlistenFn> {
  return listen<{ campaign: string; path: string }>('foresight://open', (e) => handler(e.payload));
}

/** The turn passed `by` one row, forward or back, over the rows out of the
 *  fight. Past the last row it wraps to the first and the round counts up;
 *  back before the first it wraps to the last and the round counts down,
 *  never below 1. With no row in the fight, nothing moves. */
export function step(e: Pick<Encounter, 'rows' | 'turn' | 'round'>, by: 1 | -1): { turn: string | null; round: number } {
  const n = e.rows.length;
  if (!e.rows.some((r) => !r.out)) return { turn: e.turn, round: e.round };
  let at = e.rows.findIndex((r) => r.name === e.turn);
  let round = e.round;
  if (at < 0) return { turn: e.rows.find((r) => !r.out)!.name, round };
  do {
    at += by;
    if (at >= n) {
      at = 0;
      round += 1;
    } else if (at < 0) {
      at = n - 1;
      round = Math.max(1, round - 1);
    }
  } while (e.rows[at].out);
  return { turn: e.rows[at].name, round };
}

/** The row named `name` taken out of the fight, or back in. Taken out on its
 *  turn, the turn passes on; back in while the turn sits on a row out of
 *  the fight (every row was out), the turn is its. */
export function toggleOut(e: Encounter, name: string): Encounter {
  const rows = e.rows.map((r) => (r.name === name ? { ...r, out: !r.out } : r));
  const row = rows.find((r) => r.name === name);
  if (!row) return e;
  const next = { ...e, rows };
  if (row.out && e.turn === name) return { ...next, ...step(next, 1) };
  const holder = rows.find((r) => r.name === e.turn);
  if (!row.out && (!holder || holder.out)) return { ...next, turn: name };
  return next;
}

/** `wanted`, or with the next number when a row has the name already
 *  ("Goblin 2"), as Command numbers a note's name. */
export function freeName(wanted: string, rows: EncounterRow[]): string {
  const taken = new Set(rows.map((r) => r.name.toLocaleLowerCase()));
  let candidate = wanted;
  for (let n = 2; taken.has(candidate.toLocaleLowerCase()); n++) candidate = `${wanted} ${n}`;
  return candidate;
}

/** The encounter with `rows`, the turn going to the first in the fight when
 *  no row in the fight had it. */
function withRows(e: Encounter, rows: EncounterRow[]): Encounter {
  const holder = rows.find((r) => r.name === e.turn);
  return { ...e, rows, turn: holder && !holder.out ? e.turn : (rows.find((r) => !r.out)?.name ?? null) };
}

/** A row named `name` added at the end, linked to `link` when it has one,
 *  with an empty cell for each column after the first. */
export function addRow(e: Encounter, name: string, link: string | null = null): Encounter {
  const row: EncounterRow = { name: freeName(name, e.rows), link, out: false, cells: e.columns.slice(1).map(() => '') };
  return withRows(e, [...e.rows, row]);
}

// ---- cells -------------------------------------------------------------------

const NUMBER = /^(-?\d+)(?:\s*\/\s*(-?\d+))?$/;

/** A cell's number and its max, or null when it holds text or nothing. */
export function parseNumber(cell: string): { value: number; max: number | null } | null {
  const m = NUMBER.exec(cell.trim());
  return m ? { value: Number(m[1]), max: m[2] === undefined ? null : Number(m[2]) } : null;
}

function written(value: number, max: number | null): string {
  return max === null ? String(value) : `${value}/${max}`;
}

/** What a cell holds once `typed` is entered over `before`. In a cell
 *  holding a number, −7 or +3 does the arithmetic and a bare number
 *  replaces the value, its max kept; n/max sets both. Anywhere a number
 *  becomes the cell, and anything else is text. No floor and no ceiling:
 *  the GM's numbers mean what the GM's game says. */
export function enterCell(before: string, typed: string): string {
  const text = typed.trim().replace(/−/g, '-');
  const was = parseNumber(before);
  const delta = /^([+-])\s*(\d+)$/.exec(text);
  if (was && delta) return written(was.value + (delta[1] === '-' ? -1 : 1) * Number(delta[2]), was.max);
  if (delta) return String((delta[1] === '-' ? -1 : 1) * Number(delta[2]));
  const now = parseNumber(text);
  if (now && now.max === null && was) return written(now.value, was.max);
  if (now) return written(now.value, now.max);
  return typed.trim();
}

/** Whether column `c` reads as figures: every filled cell holds a number. */
export function isFigures(rows: EncounterRow[], c: number): boolean {
  const filled = rows.map((r) => r.cells[c - 1] ?? '').filter((v) => v.trim() !== '');
  return filled.length > 0 && filled.every((v) => parseNumber(v) !== null);
}

/** Row `name`'s cell under column `c` (1 for the first after the names). */
export function setCell(e: Encounter, name: string, c: number, value: string): Encounter {
  return {
    ...e,
    rows: e.rows.map((r) => (r.name === name ? { ...r, cells: r.cells.map((v, i) => (i === c - 1 ? value : v)) } : r)),
  };
}

// ---- rows --------------------------------------------------------------------

/** Row `name` renamed, a taken name numbered (`freeName`). A linked row
 *  keeps its link, the new name its alias; the turn follows. */
export function renameRow(e: Encounter, name: string, wanted: string): Encounter {
  const others = e.rows.filter((r) => r.name !== name);
  const next = freeName(wanted, others);
  return {
    ...e,
    rows: e.rows.map((r) => (r.name === name ? { ...r, name: next } : r)),
    turn: e.turn === name ? next : e.turn,
  };
}

/** The name a copy of `name` takes: its base with the next number, Goblin 2
 *  after Goblin 1 and Goblin, Wolf 2 after Wolf. */
export function nextNumbered(name: string, rows: EncounterRow[]): string {
  const base = name.replace(/ \d+$/, '');
  const key = base.toLocaleLowerCase();
  let n = 1;
  for (const r of rows) {
    const lower = r.name.toLocaleLowerCase();
    if (lower.startsWith(`${key} `) && /^\d+$/.test(lower.slice(key.length + 1))) {
      n = Math.max(n, Number(lower.slice(key.length + 1)));
    }
  }
  return freeName(`${base} ${n + 1}`, rows);
}

/** A copy of row `name` under it: the next number, its link and its cells,
 *  in the fight. */
export function duplicateRow(e: Encounter, name: string): Encounter {
  const at = e.rows.findIndex((r) => r.name === name);
  if (at < 0) return e;
  const copy = { ...e.rows[at], name: nextNumbered(name, e.rows), out: false, cells: [...e.rows[at].cells] };
  return { ...e, rows: [...e.rows.slice(0, at + 1), copy, ...e.rows.slice(at + 1)] };
}

/** Row `name` gone. On its turn, the turn passes on first. */
export function removeRow(e: Encounter, name: string): Encounter {
  const passed = e.turn === name ? { ...e, ...step(e, 1) } : e;
  const rows = passed.rows.filter((r) => r.name !== name);
  const turn = passed.turn === name ? null : passed.turn;
  return { ...passed, rows, turn: turn ?? rows.find((r) => !r.out)?.name ?? null };
}

/** Row `name` moved to stand before the row now at `to` (the rows' length
 *  for the end). The turn stays with whoever has it. */
export function moveRow(e: Encounter, name: string, to: number): Encounter {
  const from = e.rows.findIndex((r) => r.name === name);
  if (from < 0 || to === from || to === from + 1) return e;
  const rows = [...e.rows];
  const [row] = rows.splice(from, 1);
  rows.splice(to > from ? to - 1 : to, 0, row);
  return { ...e, rows };
}

// ---- columns -----------------------------------------------------------------

type Table = Pick<Encounter, 'columns' | 'rows'>;

/** A column named `name` at the end, empty. */
export function addColumn<T extends Table>(t: T, name: string): T {
  return { ...t, columns: [...t.columns, name], rows: t.rows.map((r) => ({ ...r, cells: [...r.cells, ''] })) };
}

/** Column `c` renamed; the first, the rows' names, too. */
export function renameColumn<T extends Table>(t: T, c: number, name: string): T {
  return { ...t, columns: t.columns.map((col, i) => (i === c ? name : col)) };
}

/** Column `c` and its cells gone. The first stays. */
export function removeColumn<T extends Table>(t: T, c: number): T {
  if (c < 1) return t;
  return {
    ...t,
    columns: t.columns.filter((_, i) => i !== c),
    rows: t.rows.map((r) => ({ ...r, cells: r.cells.filter((_, i) => i !== c - 1) })),
  };
}

/** Column `c` moved, with its cells, to stand before the column now at
 *  `to` (the columns' length for the end). The first stays first. */
export function moveColumn<T extends Table>(t: T, c: number, to: number): T {
  if (c < 1 || to < 1 || to === c || to === c + 1) return t;
  const order = t.columns.map((_, i) => i);
  order.splice(c, 1);
  order.splice(to > c ? to - 1 : to, 0, c);
  return {
    ...t,
    columns: order.map((i) => t.columns[i]),
    rows: t.rows.map((r) => ({ ...r, cells: order.slice(1).map((i) => r.cells[i - 1] ?? '') })),
  };
}

// ---- the link with Command ---------------------------------------------------

/** What a link with no alias shows: its note's name, without folders,
 *  heading or `.md` (encounter.py `_shown`). */
export function linkName(link: string): string {
  const target = link.split(/[#^]/, 1)[0].trim();
  return (target.split('/').at(-1) ?? '').replace(/\.md$/, '');
}

/** The link a row writes for `note`: its name, or its path when another note
 *  shares the name, so Obsidian opens this one (prep.py `_link`). */
export function linkTo(note: NoteEntry, notes: NoteEntry[]): string {
  const name = note.name.toLocaleLowerCase();
  const shared = notes.some((n) => n.path !== note.path && n.name.toLocaleLowerCase() === name);
  return shared ? note.path.replace(/\.md$/, '') : note.name;
}

/** Whether a row can stand for `note`: not an image, an encounter, a beat
 *  or a session. */
export function isRowNote(note: NoteEntry): boolean {
  const track = note.track?.toLocaleLowerCase();
  return note.type === 'note' && !note.encounter && track !== 'beats' && track !== 'sessions';
}

/** `notes` as rows from `at` (the end when it's past the rows). A note a row
 *  links to already comes in as the next number, its alias: Goblin 2. */
export function addNotes(e: Encounter, notes: NoteEntry[], all: NoteEntry[], at = e.rows.length): Encounter {
  const added: EncounterRow[] = [];
  for (const note of notes) {
    const rows = [...e.rows, ...added];
    const name = note.name.toLocaleLowerCase();
    const again = rows.some((r) => r.link !== null && linkName(r.link).toLocaleLowerCase() === name);
    added.push({
      name: again ? nextNumbered(note.name, rows) : freeName(note.name, rows),
      link: linkTo(note, all),
      out: false,
      cells: e.columns.slice(1).map(() => ''),
    });
  }
  const to = Math.min(at, e.rows.length);
  return withRows(e, [...e.rows.slice(0, to), ...added, ...e.rows.slice(to)]);
}

/** A track's notes for a nameplate dropped on Foresight: those still to
 *  play, as its column shows them, that a row can stand for. */
export function trackNotes(index: CampaignIndex, track: string): NoteEntry[] {
  const column = columns(index).find((c) => c.track === track);
  return (column?.groups ?? []).flatMap((g) => g.notes).filter(isRowNote);
}

/** The campaign's encounter tracks, in its order. */
export function encounterTracks(index: CampaignIndex): string[] {
  return index.tracks.filter((t) => index.kinds[t] === 'encounter');
}

/** The track `by` along from `from`, wrapping as Augury's sets do. From a
 *  track that's gone, the first or the last. */
export function stepTrack(tracks: string[], from: string | null, by: 1 | -1): string | null {
  if (!tracks.length) return null;
  const at = from === null ? -1 : tracks.indexOf(from);
  if (at < 0) return by > 0 ? tracks[0] : tracks[tracks.length - 1];
  return tracks[(at + by + tracks.length) % tracks.length];
}

/** A track's encounters still to run, as its column shows them. */
export function trackEncounters(index: CampaignIndex, track: string): NoteEntry[] {
  const column = columns(index).find((c) => c.track === track);
  return (column?.groups ?? []).flatMap((g) => g.notes).filter((n) => n.encounter);
}

/** The encounter to open on arriving at a track: the one last open there
 *  while it's still to run, else the track's first. */
export function arrival(index: CampaignIndex, track: string, last: string | undefined): string | null {
  const notes = trackEncounters(index, track);
  return notes.find((n) => n.path === last)?.path ?? notes[0]?.path ?? null;
}

/** What notes carried onto Foresight do: open the one encounter, join as
 *  rows, or nothing (an image alone; a spent encounter, Command's to
 *  un-spend). */
export function landing(notes: NoteEntry[]): 'open' | 'rows' | 'none' {
  if (notes.length === 1 && notes[0].encounter) return notes[0].spent ? 'none' : 'open';
  return notes.some(isRowNote) ? 'rows' : 'none';
}

/** The notes `[[` offers for `typed`: names starting with it first, then
 *  names holding it, at most eight. */
export function completions(notes: NoteEntry[], typed: string): NoteEntry[] {
  const q = typed.trim().toLocaleLowerCase();
  const names = notes.filter(isRowNote).map((note) => ({ note, name: note.name.toLocaleLowerCase() }));
  const hits = names.filter((n) => n.name.includes(q));
  hits.sort((a, b) => Number(b.name.startsWith(q)) - Number(a.name.startsWith(q)) || a.name.localeCompare(b.name));
  return hits.slice(0, 8).map((n) => n.note);
}

/** The link in a name typed with its brackets, closed or not, an alias
 *  naming the row; null for a plain name. */
export function typedLink(text: string): { link: string; name: string } | null {
  const m = /^\[\[([^[\]]+?)(?:\]\]?)?$/.exec(text.trim());
  if (!m) return null;
  const [target, alias] = m[1].split(/\\?\|/, 2);
  const link = target.trim();
  return link ? { link, name: alias?.trim() || linkName(link) } : null;
}

