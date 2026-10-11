// Shapes crossing the Tauri boundary for Command (src-tauri/src/command.rs,
// sidecar/command/). Paths are campaign-relative, '/'-separated.

export interface NoteEntry {
  name: string;
  path: string;
  /** First folder; null for a loose note at the campaign root. */
  track: string | null;
  /** Folders below the track ("Vallaki"), null directly in it. */
  group: string | null;
  /** The date it was spent, as written; null while unspent. */
  spent: string | null;
}

/** A link in a beat or a plan: the name it gives and the note it resolves
 *  to, null when no single note answers to the name. */
export interface LinkRef {
  link: string;
  path: string | null;
}

export interface BeatEntry {
  name: string;
  path: string;
  spent: string | null;
  notes: LinkRef[];
}

export interface SessionEntry {
  name: string;
  path: string;
  date: string | null;
  /** The plan, in order. */
  beats: LinkRef[];
}

export interface CampaignIndex {
  name: string;
  /** Track folders in display order (Beats and Sessions excluded). */
  tracks: string[];
  notes: NoteEntry[];
  /** Case-folded names more than one note answers to. */
  ambiguous: string[];
  beats: BeatEntry[];
  /** Oldest first, by date then number. */
  sessions: SessionEntry[];
}

export interface NewSession {
  path: string;
  name: string;
  carried: string[];
}

export interface Note {
  path: string;
  name: string;
  content: string;
  hash: string;
}

export type SaveOutcome = { status: 'saved'; hash: string } | { status: 'conflict'; hash: string };

export interface CommandSettings {
  root: string | null;
}

export interface Moved {
  path: string;
  rewritten: string[];
}

export interface Renamed {
  name: string;
  rewritten: string[];
}

/** `command://vault`. A null campaign means anything may have changed. */
export interface VaultEvent {
  type: 'vault';
  campaign: string | null;
  paths: string[];
}
