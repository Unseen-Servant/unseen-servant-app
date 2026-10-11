// Shapes crossing the Tauri boundary for Command (src-tauri/src/command.rs,
// sidecar/command/). Paths are campaign-relative, '/'-separated.

export interface NoteEntry {
  name: string;
  path: string;
  /** First folder; null for a loose note at the campaign root. */
  track: string | null;
  /** Folders below the track ("Vallaki"), null directly in it. */
  group: string | null;
}

export interface CampaignIndex {
  name: string;
  /** Track folders in display order (Beats and Sessions excluded). */
  tracks: string[];
  notes: NoteEntry[];
  /** Case-folded names more than one note answers to. */
  ambiguous: string[];
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
