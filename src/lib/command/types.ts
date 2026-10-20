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
  /** Where it came from: a PDF page's file URL (Send to Command). */
  source: string | null;
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
  /** Note names by folder ("NPCs", "NPCs/Vallaki"), in the order the GM
   *  dragged them; the folder's other notes follow by name. */
  note_order: Record<string, string[]>;
  /** Each track's pigment, a hex from Legend Lore's palette (palette.ts);
   *  a track it doesn't name has none. */
  pigments: Record<string, string>;
  /** The notes sharing their name with another of their kind (a beat may
   *  share a note's), by path. */
  ambiguous: string[];
  beats: BeatEntry[];
  /** Oldest first, by date then number. */
  sessions: SessionEntry[];
  /** Every image in the campaign, by path, wherever it sits: what notes'
   *  embeds resolve against (embeds.ts). */
  images: string[];
}

export interface NewSession {
  path: string;
  name: string;
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
  /** Folders outside the campaigns the shelf copies from, as added. */
  places: string[];
}

/** Where the shelf copies from (design §3.6): another campaign, or a
 *  place, a folder the GM added. */
export type CopySource = { kind: 'campaign'; name: string } | { kind: 'place'; path: string };

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

export type Side = 'top' | 'right' | 'bottom' | 'left';
/** A line's end: plain, or an arrowhead. JSON Canvas draws a missing
 *  `toEnd` as an arrow; Command writes `none`. */
export type End = 'none' | 'arrow';

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
  /** A pigment's hex, or one of Obsidian's presets "1"–"6". */
  color?: string;
  [key: string]: unknown;
}

export interface CanvasEdge {
  id: string;
  fromNode: string;
  toNode: string;
  fromSide?: Side;
  toSide?: Side;
  label?: string;
  color?: string;
  fromEnd?: End;
  toEnd?: End;
  [key: string]: unknown;
}

/** A session's board: the canvas, and the note each card shows by id. */
export interface BoardView {
  nodes: CanvasNode[];
  edges: CanvasEdge[];
  /** The note each note card shows, by card id. */
  notes: Record<string, string>;
  /** The image each image card shows, by card id. */
  images: Record<string, string>;
}

type Frame = { x: number; y: number; width: number; height: number };

/** The cards the board's toolbar makes; note cards are placed instead. */
export type MadeKind = 'text' | 'group' | 'link';

/** What `set` changes on a card or a line; null clears a field. */
export interface BoardFields {
  text?: string;
  label?: string | null;
  url?: string;
  color?: string | null;
  fromEnd?: End;
  toEnd?: End;
}

/** A change to a board, applied by the sidecar to the file on disk. */
export type BoardOp =
  | ({ op: 'place'; id: string; path: string } & Frame)
  | ({ op: 'add'; id: string; type: MadeKind; text?: string; label?: string; url?: string; color?: string } & Frame)
  | ({ op: 'frame'; id: string } & Frame)
  | {
      op: 'connect';
      id: string;
      source: string;
      target: string;
      fromSide?: Side;
      toSide?: Side;
      label?: string;
      color?: string;
      fromEnd?: End;
      toEnd?: End;
    }
  | ({ op: 'set'; id: string } & BoardFields)
  | { op: 'remove'; id: string };
