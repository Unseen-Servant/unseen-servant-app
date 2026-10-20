// The Prep grid's columns: one per track, in the campaign's order, every
// note in the track (design §5.1). Subfolders become groups under the
// notes that sit directly in the track. A group's notes come in the order
// the GM dragged them into, then by name. Spent notes leave their groups
// for the track's spent list, folded at the column's foot.

import type { CampaignIndex, NoteEntry } from './types';

export interface NoteGroup {
  /** Subfolder path below the track; null for notes directly in it. */
  group: string | null;
  /** The folder holding the notes, from the campaign: "NPCs/Vallaki". */
  folder: string;
  notes: NoteEntry[];
}

export interface Column {
  track: string;
  /** Its notes still to play, by folder; a folder with none has no group. */
  groups: NoteGroup[];
  /** Its spent notes, in the order the groups would show them. */
  spent: NoteEntry[];
  /** Every note in the track, spent ones included. */
  count: number;
}

const byName = (a: string, b: string) => a.localeCompare(b, undefined, { sensitivity: 'base', numeric: true });

export function columns(index: CampaignIndex): Column[] {
  return index.tracks.map((track) => {
    const notes = index.notes.filter((n) => n.track === track);
    const groups = new Map<string | null, NoteEntry[]>();
    for (const note of notes) {
      const list = groups.get(note.group) ?? [];
      list.push(note);
      groups.set(note.group, list);
    }
    const order = [...groups.keys()].sort((a, b) => (a === null ? -1 : b === null ? 1 : byName(a, b)));
    const all = order.map((group) => {
      const folder = group === null ? track : `${track}/${group}`;
      return { group, folder, notes: inOrder(groups.get(group)!, index.note_order[folder] ?? []) };
    });
    return {
      track,
      groups: all
        .map((g) => ({ ...g, notes: g.notes.filter((n) => !n.spent) }))
        .filter((g) => g.notes.length),
      spent: all.flatMap((g) => g.notes.filter((n) => n.spent)),
      count: notes.length,
    };
  });
}

/** Notes the saved order names first, in it, then the rest by name. Names
 *  fold case as the sidecar's do. */
function inOrder(notes: NoteEntry[], saved: string[]): NoteEntry[] {
  const rank = new Map(saved.map((name, i) => [name.toLowerCase(), i]));
  const at = (n: NoteEntry) => rank.get(n.name.toLowerCase()) ?? saved.length;
  return notes.sort((a, b) => at(a) - at(b) || byName(a.name, b.name));
}

/** A folder's order after its notes on show were dragged into `shown`:
 *  those, then its spent notes in their places, as Legend Lore keeps the
 *  collections a view hides (prep.ts beatOrder). */
export function folderOrder(column: Column, folder: string, shown: string[]): string[] {
  const folderOf = (n: NoteEntry) => (n.group === null ? n.track : `${n.track}/${n.group}`);
  return [...shown, ...column.spent.filter((n) => folderOf(n) === folder).map((n) => n.name)];
}

/** The selection key of a folder's empty row, where a new note is named:
 *  selected as a note is, by a click, though it's no note. */
export const newRowKey = (folder: string) => `new:${folder}`;
export const isNewRowKey = (key: string) => key.startsWith('new:');

/** Every note name in the campaign, alphabetical, for `[[` completion. */
export function linkableNames(index: CampaignIndex): string[] {
  return [...new Set(index.notes.map((n) => n.name))].sort(byName);
}

/** Whether the note at `path` shares its name with another of its kind, so
 *  a link to the name is ambiguous. */
export function isAmbiguous(index: CampaignIndex, path: string): boolean {
  return index.ambiguous.includes(path);
}

/** A link names a note before a beat, and a beat before a session, since a
 *  beat may share a note's name (design §3.3). */
const kindRank = (n: NoteEntry) => ['beats', 'sessions'].indexOf(n.track?.toLowerCase() ?? '') + 1;

/** What the board's Note tool offers for `typed`: notes, not beats or
 *  sessions, whose names start with it and then those holding it, each
 *  alphabetical, case aside; at most `max`, as the editor's completion
 *  draws. */
export function placeableNotes(index: CampaignIndex, typed: string, max = 100): NoteEntry[] {
  const q = typed.trim().toLowerCase();
  const later = (n: NoteEntry) => (n.name.toLowerCase().startsWith(q) ? 0 : 1);
  return index.notes
    .filter((n) => kindRank(n) === 0 && n.name.toLowerCase().includes(q))
    .sort((a, b) => later(a) - later(b) || byName(a.name, b.name))
    .slice(0, max);
}

/** The note a link's target names: by its name, or a path ending in it
 *  (`Locations/Svalich Road`), as the sidecar resolves it. Lower-casing
 *  agrees with its casefold() for every name short of oddities like ß. */
export function linkedNote(index: CampaignIndex, target: string): NoteEntry | undefined {
  const parts = target.toLowerCase().split('/').filter(Boolean);
  if (!parts.length) return undefined;
  const answers = (n: NoteEntry) => {
    const own = [index.name, ...n.path.replace(/\.md$/i, '').split('/')].map((p) => p.toLowerCase());
    const k = Math.min(parts.length, own.length);
    return parts.slice(-k).join('/') === own.slice(-k).join('/');
  };
  return index.notes.filter(answers).sort((a, b) => kindRank(a) - kindRank(b))[0];
}
