// The session board (design §5.2): the cards the GM placed, read from the
// session's canvas, and the session's other notes auto-placed beside them so
// a board nobody arranged still reads. Gestures on a card become the
// operations the sidecar applies to the file.

import { linkTarget } from './editorTheme';
import type { BoardOp, BoardView, CampaignIndex, CanvasNode, NoteEntry, Side } from './types';

export const CARD = { width: 260, height: 180 };
export const GAP = 32;

/** Auto-placed cards aren't in the file yet; their ids say so. */
const AUTO = 'auto:';

export type CardKind = 'note' | 'text' | 'group' | 'link' | 'other';

export interface Card {
  id: string;
  kind: CardKind;
  /** The note a note card shows; null when the note it names isn't there. */
  path: string | null;
  /** False for a note auto-placed beside the arrangement: moving it places it. */
  placed: boolean;
  x: number;
  y: number;
  width: number;
  height: number;
  /** A text card's Markdown, a group's label, a link's URL, or the path a
   *  note card names as written. */
  text: string;
}

export interface Line {
  id: string;
  source: string;
  target: string;
  fromSide: Side;
  toSide: Side;
  label: string | null;
}

const KINDS: Record<string, CardKind> = { file: 'note', text: 'text', group: 'group', link: 'link' };

function placedCard(node: CanvasNode, path: string | null): Card {
  const kind = KINDS[node.type] ?? 'other';
  const text = kind === 'note' ? node.file : kind === 'group' ? node.label : kind === 'link' ? node.url : node.text;
  return {
    id: node.id,
    kind,
    path: kind === 'note' ? path : null,
    placed: true,
    x: node.x,
    y: node.y,
    width: node.width,
    height: node.height,
    text: typeof text === 'string' ? text : '',
  };
}

/** Every card on the board: what the canvas holds, then each note of
 *  `wanted` (the session's notes, anything live) it doesn't, laid out in
 *  columns by track to the right of what the GM arranged. */
export function cards(view: BoardView, index: CampaignIndex, wanted: Iterable<string>): Card[] {
  const placed = view.nodes.map((n) => placedCard(n, view.notes[n.id] ?? null));
  const onBoard = new Set(placed.map((c) => c.path).filter(Boolean));
  const notes = new Map(index.notes.map((n) => [n.path, n]));
  const loose = [...new Set(wanted)]
    .filter((p) => !onBoard.has(p) && notes.has(p))
    .map((p) => notes.get(p)!);
  if (!loose.length) return placed;

  const order = [...index.tracks];
  const column = (track: string | null) => (track && order.includes(track) ? order.indexOf(track) : order.length);
  const used = [...new Set(loose.map((n) => column(n.track)))].sort((a, b) => a - b);

  const x0 = placed.length ? Math.max(...placed.map((c) => c.x + c.width)) + GAP * 2 : 0;
  const y0 = placed.length ? Math.min(...placed.map((c) => c.y)) : 0;
  const auto: Card[] = [];
  used.forEach((col, i) => {
    loose
      .filter((n) => column(n.track) === col)
      .sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base', numeric: true }))
      .forEach((n, row) =>
        auto.push({
          id: AUTO + n.path,
          kind: 'note',
          path: n.path,
          placed: false,
          x: x0 + i * (CARD.width + GAP),
          y: y0 + row * (CARD.height + GAP),
          ...CARD,
          text: n.path,
        }),
      );
  });
  return [...placed, ...auto];
}

function centre(c: Card) {
  return { x: c.x + c.width / 2, y: c.y + c.height / 2 };
}

/** The sides two cards face each other on, for a line the file gives no
 *  sides for. */
export function facing(a: Card, b: Card): [Side, Side] {
  const from = centre(a);
  const to = centre(b);
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  if (Math.abs(dx) >= Math.abs(dy)) return dx >= 0 ? ['right', 'left'] : ['left', 'right'];
  return dy >= 0 ? ['bottom', 'top'] : ['top', 'bottom'];
}

/** The lines between cards on the board; one naming a card that isn't
 *  there is left out. */
export function lines(view: BoardView, board: Card[]): Line[] {
  const byId = new Map(board.map((c) => [c.id, c]));
  return view.edges.flatMap((e) => {
    const a = byId.get(e.fromNode);
    const b = byId.get(e.toNode);
    if (!a || !b) return [];
    const [fromSide, toSide] = facing(a, b);
    return [
      {
        id: e.id,
        source: a.id,
        target: b.id,
        fromSide: e.fromSide ?? fromSide,
        toSide: e.toSide ?? toSide,
        label: typeof e.label === 'string' ? e.label : null,
      },
    ];
  });
}

/** A fresh id in Obsidian's shape: 16 hex digits. */
export function newId(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(8));
  return [...bytes].map((b) => b.toString(16).padStart(2, '0')).join('');
}

export type Frame = { x: number; y: number; width: number; height: number };

/** What a card can ask of the board around it. */
export interface CardActions {
  launch: (card: Card, live: boolean) => void;
  spend: (card: Card, spent: boolean) => void;
  edit: (card: Card) => void;
  follow: (name: string) => void;
  frame: (card: Card, frame: Frame) => void;
}

/** Where the card components find the board's CardActions (Svelte
 *  context): functions in a node's data would make Svelte Flow take the
 *  nodes for deeply reactive state. */
export const CARD_ACTIONS = Symbol('card actions');

/** A card as Svelte Flow hands it to its component. */
export interface CardData extends Record<string, unknown> {
  card: Card;
  /** A note card's note name; empty for the other kinds. */
  name: string;
  track: string | null;
  live: boolean;
  spent: string | null;
  /** The PDF page it came from (Send to Command), which its key opens. */
  source: string | null;
  /** The Markdown to show; null while it loads. */
  body: string | null;
}

/** What putting a card at `frame` writes: a placed card is framed; an
 *  auto-placed note is placed, under a new id the returned op carries. */
export function frameOp(card: Card, frame: Frame): BoardOp {
  const rounded = {
    x: Math.round(frame.x),
    y: Math.round(frame.y),
    width: Math.round(frame.width),
    height: Math.round(frame.height),
  };
  if (card.placed) return { op: 'frame', id: card.id, ...rounded };
  return { op: 'place', id: newId(), path: card.path!, ...rounded };
}

/** The operations a line drawn from `a` to `b` writes: an auto-placed end
 *  is placed where it sits first. */
export function connectOps(a: Card, b: Card, fromSide?: Side, toSide?: Side): BoardOp[] {
  const ops: BoardOp[] = [];
  const idOf = (c: Card) => {
    if (c.placed) return c.id;
    const op = frameOp(c, c);
    ops.push(op);
    return op.id;
  };
  const source = idOf(a);
  const target = idOf(b);
  ops.push({ op: 'connect', id: newId(), source, target, fromSide, toSide });
  return ops;
}

/** A note's text without its frontmatter: what a card shows. */
export function bodyOf(content: string): string {
  const m = /^﻿?---\r?\n[\s\S]*?\r?\n(?:---|\.\.\.)[ \t]*(?:\r?\n|$)/.exec(content);
  return (m ? content.slice(m[0].length) : content).replace(/^\s+/, '');
}

/** Where a followed `[[link]]` points on a card. */
export const NOTE_HREF = '#note:';

/** `[[Name|shown]]` as a Markdown link a card can follow, to the note
 *  `NOTE_HREF` names. An embed (`![[map.png]]`) stays as written. */
export function linkify(md: string): string {
  return md.replace(/(?<!!)\[\[([^[\]\n]+?)\]\]/g, (_, inner: string) => {
    const bar = inner.search(/\\?\|/);
    const shown = bar >= 0 ? inner.slice(inner.indexOf('|', bar) + 1) : inner;
    return `[${shown.trim()}](${NOTE_HREF}${encodeURIComponent(linkTarget(inner))})`;
  });
}

/** `view` as it will read once the sidecar has applied `ops` — drawn at
 *  once, so a card doesn't spring back while the write is under way. The
 *  sidecar's answer replaces it. */
export function applyOps(view: BoardView, ops: BoardOp[], campaign: string): BoardView {
  let nodes = [...view.nodes];
  let edges = [...view.edges];
  const notes = { ...view.notes };
  for (const op of ops) {
    if (op.op === 'place') {
      const { op: _, path, ...frame } = op;
      nodes.push({ ...frame, type: 'file', file: `${campaign}/${path}` });
      notes[op.id] = path;
    } else if (op.op === 'frame') {
      const { op: _, id, ...frame } = op;
      nodes = nodes.map((n) => (n.id === id ? { ...n, ...frame } : n));
    } else if (op.op === 'connect') {
      edges.push({ id: op.id, fromNode: op.source, toNode: op.target, fromSide: op.fromSide, toSide: op.toSide });
    } else {
      nodes = nodes.filter((n) => n.id !== op.id);
      edges = edges.filter((e) => e.id !== op.id && e.fromNode !== op.id && e.toNode !== op.id);
      delete notes[op.id];
    }
  }
  return { nodes, edges, notes };
}

/** The notes the find line offers for `query`: names starting with it,
 *  then names containing it, each by name. Beats and sessions aren't
 *  cards, so they're left out. */
export function findNotes(index: CampaignIndex, query: string, limit = 8): NoteEntry[] {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  const reserved = new Set(['beats', 'sessions']);
  const byName = (a: NoteEntry, b: NoteEntry) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base', numeric: true });
  const notes = index.notes.filter((n) => !(n.track && reserved.has(n.track.toLowerCase())));
  const starts = notes.filter((n) => n.name.toLowerCase().startsWith(q)).sort(byName);
  const within = notes.filter((n) => !n.name.toLowerCase().startsWith(q) && n.name.toLowerCase().includes(q)).sort(byName);
  return [...starts, ...within].slice(0, limit);
}
