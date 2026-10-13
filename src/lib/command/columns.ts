// The Prep grid's columns: one per track, in the campaign's order, every
// note in the track (design §5.1). Subfolders become groups under the
// notes that sit directly in the track. A group's notes come in the order
// the GM dragged them into, then by name.

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
  groups: NoteGroup[];
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
    return {
      track,
      groups: order.map((group) => {
        const folder = group === null ? track : `${track}/${group}`;
        return { group, folder, notes: inOrder(groups.get(group)!, index.note_order[folder] ?? []) };
      }),
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

/** Every note name in the campaign, alphabetical, for `[[` completion. */
export function linkableNames(index: CampaignIndex): string[] {
  return [...new Set(index.notes.map((n) => n.name))].sort(byName);
}

/** Whether more than one note answers to `name`. The sidecar case-folds
 *  with Python's casefold(); lower-casing agrees for every name short of
 *  oddities like ß. */
export function isAmbiguous(index: CampaignIndex, name: string): boolean {
  return index.ambiguous.includes(name.toLowerCase());
}
