// The session board (design §5.2): the cards the GM placed, read from the
// session's canvas, and the session's other notes auto-placed beside them so
// a board nobody arranged still reads. Gestures on a card become the
// operations the sidecar applies to the file.

import { PIGMENTS } from '../legend-lore/palette';
import { linkTarget } from './editorTheme';
import type { BoardFields, BoardOp, BoardView, CampaignIndex, CanvasEdge, CanvasNode, Side } from './types';

export const CARD = { width: 260, height: 180 };
export const GAP = 32;
/** What the toolbar's Text, Sticky and Frame make at a click. */
export const TEXT_CARD = { width: 260, height: 100 };
export const STICKY = { width: 200, height: 200 };
export const NEW_FRAME = { width: 600, height: 400 };
/** A frame drawn around cards (⌘G) clears them by this much, and by more
 *  at the top for its name. */
export const FRAME_PAD = 24;
export const FRAME_TOP = 48;

const pigment = (name: string) => PIGMENTS.find((p) => p.name === name)!.hex;
/** A new sticky's colour, until the selection bar picks others. */
export const STICKY_COLOR = pigment('Ochre');
/** Obsidian's six presets, drawn as the pigments nearest them. */
const PRESETS: Record<string, string> = {
  '1': pigment('Kermes'),
  '2': pigment('Realgar'),
  '3': pigment('Ochre'),
  '4': pigment('Malachite'),
  '5': pigment('Azurite'),
  '6': pigment('Orchil'),
};

/** The colour a card or line is drawn in: its hex, a preset's pigment, or
 *  none. */
export function paint(color: string | null): string | null {
  if (!color) return null;
  if (/^#[0-9a-f]{6}$/i.test(color)) return color;
  return PRESETS[color] ?? null;
}

/** Auto-placed cards aren't in the file yet; their ids say so. */
const AUTO = 'auto:';

export type CardKind = 'note' | 'text' | 'group' | 'link' | 'other';

/** The board toolbar's tools (board toolbar design §3.2). */
export type Tool = 'select' | 'hand' | 'text' | 'sticky' | 'line' | 'frame';

export interface Card {
  id: string;
  kind: CardKind;
  /** The note a note card shows; null when the note it names isn't there. */
  path: string | null;
  /** False for a note auto-placed beside the arrangement: the board's next
   *  change places it (placeAll). */
  placed: boolean;
  x: number;
  y: number;
  width: number;
  height: number;
  /** A text card's Markdown, a group's label, a link's URL, or the path a
   *  note card names as written. */
  text: string;
  /** As written (paint draws it); null for none. */
  color: string | null;
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
    color: typeof node.color === 'string' ? node.color : null,
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
          color: null,
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
  /** Edit a text card's text, a frame's name or a line's label in place. */
  begin: (id: string) => void;
  /** Stop editing it, writing `fields` when they changed something. */
  finish: (id: string, fields?: BoardFields) => void;
  /** Take a card or a line off the board: a text card emptied as it's edited. */
  remove: (id: string) => void;
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
  /** Its track's pigment (palette.ts), which fills its head; or null. */
  pigment: string | null;
  live: boolean;
  spent: string | null;
  /** The PDF page it came from (Send to Command), which its key opens. */
  source: string | null;
  /** The Markdown to show; null while it loads. */
  body: string | null;
  /** Its card in the card tray is pointed at: the board outlines it. */
  outlined: boolean;
  /** Its text or name is being edited in place. */
  editing: boolean;
  /** The Line tool is armed: a drag from anywhere on the card draws a line. */
  linking: boolean;
}

/** The card tray's hand: the board's cards for the live set's notes, in
 *  the live set's order, so a note played on its own joins at the end. */
export function handOf(board: Card[], notes: string[]): Card[] {
  const byPath = new Map<string, Card>();
  for (const c of board) if (c.kind === 'note' && c.path && !byPath.has(c.path)) byPath.set(c.path, c);
  return notes.flatMap((p) => byPath.get(p) ?? []);
}

/** How far apart the card tray sets `count` cards `width` px wide in a
 *  row `room` px long: side by side, `gap` apart, while they fit; past
 *  that, overlapping evenly so the last ends at the row's end and every
 *  card's left edge stays in view. */
export function handStep(count: number, room: number, width: number, gap: number): number {
  if (count * width + (count - 1) * gap <= room) return width + gap;
  return Math.max(0, (room - width) / (count - 1));
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

/** `ops` and a place for every auto-placed card they leave where it sits.
 *  The auto-placed cards are laid out around the placed ones, so a change
 *  that left them out would move them all; once every card is in the
 *  file, each moves alone. */
export function placeAll(board: Card[], ops: BoardOp[]): BoardOp[] {
  const placing = new Set(ops.flatMap((o) => (o.op === 'place' ? [o.path] : [])));
  const rest = board.filter((c) => !c.placed && !placing.has(c.path!));
  return [...ops, ...rest.map((c) => frameOp(c, c))];
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

/** The slice of a hast tree `rehypeMissingLinks` reads. */
interface HastNode {
  type: string;
  tagName?: string;
  properties?: Record<string, unknown>;
  children?: HastNode[];
}

/** A rehype plugin for `linkify`'s output: a link no note answers to gets
 *  `.missing`, so a reader can dash it as the editor does. */
export function rehypeMissingLinks(resolves: (name: string) => boolean) {
  return (tree: HastNode) => {
    const visit = (node: HastNode) => {
      const href = node.tagName === 'a' ? node.properties?.href : undefined;
      if (typeof href === 'string' && href.startsWith(NOTE_HREF)) {
        if (!resolves(decodeURIComponent(href.slice(NOTE_HREF.length)))) node.properties!.className = ['missing'];
      }
      node.children?.forEach(visit);
    };
    visit(tree);
  };
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
    } else if (op.op === 'add') {
      const { op: _, ...node } = op;
      // A frame before the cards, as the sidecar files it.
      const at = op.type === 'group' ? nodes.findIndex((n) => n.type !== 'group') : -1;
      nodes.splice(at < 0 ? nodes.length : at, 0, node);
    } else if (op.op === 'frame') {
      const { op: _, id, ...frame } = op;
      nodes = nodes.map((n) => (n.id === id ? { ...n, ...frame } : n));
    } else if (op.op === 'connect') {
      const { op: _, id, source, target, toEnd, ...rest } = op;
      edges.push({ id, fromNode: source, toNode: target, ...rest, toEnd: toEnd ?? 'none' });
    } else if (op.op === 'set') {
      const { op: _, id, ...fields } = op;
      nodes = nodes.map((n) => (n.id === id ? withFields(n, fields) : n));
      edges = edges.map((e) => (e.id === id ? withFields(e, fields) : e));
    } else {
      nodes = nodes.filter((n) => n.id !== op.id);
      edges = edges.filter((e) => e.id !== op.id && e.fromNode !== op.id && e.toNode !== op.id);
      delete notes[op.id];
    }
  }
  return { nodes, edges, notes };
}

/** `item` with `fields` set, a null or emptied label removed. */
function withFields<T extends CanvasNode | CanvasEdge>(item: T, fields: BoardFields): T {
  const out: Record<string, unknown> = { ...item };
  for (const [key, value] of Object.entries(fields)) {
    if (value === null || (key === 'label' && value === '')) delete out[key];
    else if (value !== undefined) out[key] = value;
  }
  return out as T;
}

/** The cards wholly inside `frame`, which move with it: Obsidian's rule
 *  for a group's contents. */
export function inside(board: Card[], frame: Card): Card[] {
  return board.filter(
    (c) =>
      c.id !== frame.id &&
      c.x >= frame.x &&
      c.y >= frame.y &&
      c.x + c.width <= frame.x + frame.width &&
      c.y + c.height <= frame.y + frame.height,
  );
}

/** The frame drawn around `chosen` (⌘G), clear of them on every side. */
export function around(chosen: Card[]): Frame {
  const left = Math.min(...chosen.map((c) => c.x));
  const top = Math.min(...chosen.map((c) => c.y));
  const right = Math.max(...chosen.map((c) => c.x + c.width));
  const bottom = Math.max(...chosen.map((c) => c.y + c.height));
  return {
    x: Math.round(left - FRAME_PAD),
    y: Math.round(top - FRAME_TOP),
    width: Math.round(right - left + FRAME_PAD * 2),
    height: Math.round(bottom - top + FRAME_TOP + FRAME_PAD),
  };
}

/** Each frame's place in the stack, behind every card: a smaller frame in
 *  front of a larger, so one inside another can still be picked up. Low
 *  enough that a selected frame, which Svelte Flow lifts by 1000, stays
 *  behind the cards too. */
export function frameDepths(board: Card[]): Map<string, number> {
  const frames = board.filter((c) => c.kind === 'group').sort((a, b) => b.width * b.height - a.width * a.height);
  return new Map(frames.map((c, i) => [c.id, -2000 + i]));
}

