// The Prep grid's columns: one per track, in the campaign's order, every
// note in the track (design §5.1). Subfolders become groups under the
// notes that sit directly in the track.

import type { CampaignIndex, NoteEntry } from './types';

export interface NoteGroup {
  /** Subfolder path below the track; null for notes directly in it. */
  group: string | null;
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
      groups: order.map((group) => ({
        group,
        notes: groups.get(group)!.sort((a, b) => byName(a.name, b.name)),
      })),
      count: notes.length,
    };
  });
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
