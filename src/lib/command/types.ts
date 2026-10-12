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

/** A line of a session's `## Log`. Command's own lines say what happened;
 *  anything else the GM wrote there is a jot. */
export interface LogEntry {
  /** "19:42"; null for a line without one. */
  time: string | null;
  kind: 'launch' | 'spent' | 'unspent' | 'captured' | 'jot';
  /** The note the line names, for every kind but a jot. */
  link: string | null;
  path: string | null;
  /** The line after its time. */
  text: string;
}

export interface SessionEntry {
  name: string;
  path: string;
  date: string | null;
  /** The plan, in order. */
  beats: LinkRef[];
  log: LogEntry[];
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
  /** Launching a beat marks it spent. */
  spend_on_launch: boolean;
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

/** What's live in one campaign (`command://live` carries the same). */
export interface LiveSet {
  campaign: string;
  /** Grows with every change to this campaign's set. */
  seq: number;
  /** The beat the set was launched from. */
  beat: string | null;
  notes: string[];
}

export interface Captured {
  path: string;
  live: LiveSet;
}

export type Side = 'top' | 'right' | 'bottom' | 'left';

/** A JSON Canvas node as on disk. Fields Command doesn't use pass through. */
export interface CanvasNode {
  id: string;
  type: string;
  x: number;
  y: number;
  width: number;
  height: number;
  file?: string;
  text?: string;
  label?: string;
  url?: string;
  [key: string]: unknown;
}

export interface CanvasEdge {
  id: string;
  fromNode: string;
  toNode: string;
  fromSide?: Side;
  toSide?: Side;
  label?: string;
  [key: string]: unknown;
}

/** A session's board: the canvas, and the note each card shows by id. */
export interface BoardView {
  nodes: CanvasNode[];
  edges: CanvasEdge[];
  notes: Record<string, string>;
}

type Frame = { x: number; y: number; width: number; height: number };

/** A change to a board, applied by the sidecar to the file on disk. */
export type BoardOp =
  | ({ op: 'place'; id: string; path: string } & Frame)
  | ({ op: 'frame'; id: string } & Frame)
  | { op: 'connect'; id: string; source: string; target: string; fromSide?: Side; toSide?: Side }
  | { op: 'remove'; id: string };
