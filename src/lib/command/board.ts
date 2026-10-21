// The session board (design §5.2): the cards the GM placed, read from the
// session's canvas, and the session's other notes auto-placed beside them so
// a board nobody arranged still reads. Gestures on a card become the
// operations the sidecar applies to the file.

import { PIGMENTS } from '../legend-lore/palette';
import { linkTarget } from './editorTheme';
import { IMAGE } from './embeds';
import type { BoardFields, BoardOp, BoardView, CampaignIndex, CanvasEdge, CanvasNode, End, MadeKind, Side } from './types';

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
/** An image dropped on the board is at most this wide or tall (#407). */
export const IMAGE_CARD = 480;

/** The card for an image `width` × `height` px: in its proportions, at
 *  most IMAGE_CARD a side, and no smaller than the sidecar lets a card be
 *  (board.MIN_SIZE). */
export function imageCard(width: number, height: number): { width: number; height: number } {
  const scale = Math.min(1, IMAGE_CARD / Math.max(width, height, 1));
  return { width: Math.max(40, Math.round(width * scale)), height: Math.max(40, Math.round(height * scale)) };
}

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

export type CardKind = 'note' | 'image' | 'text' | 'group' | 'link' | 'other';

/** The board toolbar's tools (board toolbar design §3.2). */
export type Tool = 'select' | 'hand' | 'note' | 'text' | 'sticky' | 'line' | 'frame';

export interface Card {
  id: string;
  kind: CardKind;
  /** The note a note card shows, or an image card's image; null when the
   *  note it names isn't there. */
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
  /** As written (paint draws it); null for none. */
  color: string | null;
  /** Where it has arrowheads: JSON Canvas puts one on the target's end
   *  unless told not to. */
  fromEnd: End;
  toEnd: End;
}

const KINDS: Record<string, CardKind> = { file: 'note', text: 'text', group: 'group', link: 'link' };

/** A card the canvas holds. A file node naming an image is an image card
 *  (#407); one naming nothing that's there is a missing note card. */
function placedCard(node: CanvasNode, note: string | null, image: string | null): Card {
  const kind = image ? 'image' : (KINDS[node.type] ?? 'other');
  const text = kind === 'note' || kind === 'image' ? node.file : kind === 'group' ? node.label : kind === 'link' ? node.url : node.text;
  return {
    id: node.id,
    kind,
    path: kind === 'note' ? note : image,
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
 *  `wanted` (the session's notes, anything live) it doesn't, laid out to
 *  the right of what the GM arranged in a column per group of `groups`
 *  (beatGroups: the session's notes by beat, in plan order), then one for
 *  the rest by name. */
export function cards(view: BoardView, index: CampaignIndex, wanted: Iterable<string>, groups: string[][] = []): Card[] {
  const placed = view.nodes.map((n) => placedCard(n, view.notes[n.id] ?? null, view.images[n.id] ?? null));
  const onBoard = new Set(placed.map((c) => c.path).filter(Boolean));
  const notes = new Map(index.notes.map((n) => [n.path, n]));
  const loose = new Set([...wanted].filter((p) => !onBoard.has(p) && notes.has(p)));
  if (!loose.size) return placed;

  const grouped = new Set(groups.flat());
  const rest = [...loose]
    .filter((p) => !grouped.has(p))
    .sort((a, b) => notes.get(a)!.name.localeCompare(notes.get(b)!.name, undefined, { sensitivity: 'base', numeric: true }));
  const columns = [...groups.map((g) => g.filter((p) => loose.has(p))), rest].filter((c) => c.length);

  const x0 = placed.length ? Math.max(...placed.map((c) => c.x + c.width)) + GAP * 2 : 0;
  const y0 = placed.length ? Math.min(...placed.map((c) => c.y)) : 0;
  return [
    ...placed,
    ...columns.flatMap((column, i) =>
      column.map((path, row) => ({
        id: AUTO + path,
        kind: notes.get(path)!.type === 'image' ? ('image' as const) : ('note' as const),
        path,
        placed: false,
        x: x0 + i * (CARD.width + GAP),
        y: y0 + row * (CARD.height + GAP),
        ...CARD,
        text: path,
        color: null,
      })),
    ),
  ];
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
        color: typeof e.color === 'string' ? e.color : null,
        fromEnd: e.fromEnd === 'arrow' ? 'arrow' : 'none',
        toEnd: e.toEnd === 'none' ? 'none' : 'arrow',
      },
    ];
  });
}

const OUTWARD: Record<Side, [number, number]> = { top: [0, -1], right: [1, 0], bottom: [0, 1], left: [-1, 0] };

/** An arrowhead's outline, its point at (x, y) on a card's `side` and
 *  facing into the card. The line draws it itself rather than through an
 *  SVG marker, whose colour WebKit won't take from a token (board toolbar
 *  design §4). */
export function arrowhead(x: number, y: number, side: Side): string {
  const [nx, ny] = OUTWARD[side];
  const [length, half] = [10, 4];
  const bx = x + nx * length;
  const by = y + ny * length;
  return `M${x},${y}L${bx - ny * half},${by + nx * half}L${bx + ny * half},${by - nx * half}Z`;
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
  /** Change cards' or lines' fields in one step: the selection bar's colour
   *  and ends. */
  set: (ids: string[], fields: BoardFields) => void;
}

/** Where the card components find the board's CardActions (Svelte
 *  context): functions in a node's data would make Svelte Flow take the
 *  nodes for deeply reactive state. */
export const CARD_ACTIONS = Symbol('card actions');
/** Where a line finds whether it's the selection, and so wears the
 *  selection bar (a store in Svelte context). */
export const BAR_LINE = Symbol('bar line');

/** A card as Svelte Flow hands it to its component. */
export interface CardData extends Record<string, unknown> {
  card: Card;
  /** A note card's note name; empty for the other kinds. */
  name: string;
  track: string | null;
  /** Its track's pigment (palette.ts), which fills its head; or null. */
  pigment: string | null;
  live: boolean;
  /** It can go in the live set: a note, or an image a track or the shelf
   *  holds (images design §3), which the campaign's index lists. */
  playable: boolean;
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

/** The card tray's hand: the board's cards for the live set's notes and
 *  images, in the live set's order, so a note played on its own joins at
 *  the end. */
export function handOf(board: Card[], notes: string[]): Card[] {
  const byPath = new Map<string, Card>();
  for (const c of board) if ((c.kind === 'note' || c.kind === 'image') && c.path && !byPath.has(c.path)) byPath.set(c.path, c);
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

/** A note's place among the bodies Play's cards show (CommandPanel keeps
 *  them): by campaign too, since two campaigns can share a path. */
export const bodyKey = (campaign: string, path: string) => `${campaign}\n${path}`;

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
  const images = { ...view.images };
  for (const op of ops) {
    if (op.op === 'place') {
      const { op: _, path, ...frame } = op;
      nodes.push({ ...frame, type: 'file', file: `${campaign}/${path}` });
      (IMAGE.test(path) ? images : notes)[op.id] = path;
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
      delete images[op.id];
    }
  }
  return { nodes, edges, notes, images };
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

const MADE: CardKind[] = ['text', 'group', 'link'];

const overlaps = (a: Frame, b: Frame) =>
  a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height;

/** Copies of the text cards, stickies, frames and links among `ids` (⌘D),
 *  set to the right of them, or below when that's taken, and else past the
 *  cards in the way to the right: a copied frame mustn't take in cards
 *  that aren't its. A frame brings copies of what's wholly inside it, but
 *  not its note cards, since a note has one card per board. The lines
 *  between copied cards are copied too. */
export function duplicateOps(board: Card[], drawn: Line[], ids: string[]): BoardOp[] {
  const chosen = new Map<string, Card>();
  for (const id of ids) {
    const card = board.find((c) => c.id === id);
    if (!card || !MADE.includes(card.kind)) continue;
    chosen.set(card.id, card);
    if (card.kind === 'group') for (const c of inside(board, card)) if (MADE.includes(c.kind)) chosen.set(c.id, c);
  }
  const all = [...chosen.values()];
  if (!all.length) return [];
  const box = around(all, 0, 0);
  // A frame the originals sit in isn't in the way: the copies sit in it too.
  const inWay = board.filter((c) => !chosen.has(c.id) && !(c.kind === 'group' && inside(all, c).length === all.length));
  const blocking = (dx: number, dy: number) => inWay.filter((c) => overlaps(c, { ...box, x: box.x + dx, y: box.y + dy }));
  const right = box.width + GAP;
  const below = box.height + GAP;
  let [dx, dy] = blocking(right, 0).length && !blocking(0, below).length ? [0, below] : [right, 0];
  for (let hit = blocking(dx, dy); hit.length; hit = blocking(dx, dy)) {
    dx = Math.max(...hit.map((c) => c.x + c.width)) - box.x + GAP;
  }
  const copies = new Map(all.map((c) => [c.id, newId()]));
  const ops: BoardOp[] = all.map((c) => {
    const content = c.kind === 'group' ? (c.text ? { label: c.text } : {}) : c.kind === 'link' ? { url: c.text } : { text: c.text };
    return {
      op: 'add',
      id: copies.get(c.id)!,
      type: c.kind as MadeKind,
      x: c.x + dx,
      y: c.y + dy,
      width: c.width,
      height: c.height,
      ...content,
      ...(c.color ? { color: c.color } : {}),
    };
  });
  for (const l of drawn) {
    const source = copies.get(l.source);
    const target = copies.get(l.target);
    if (!source || !target) continue;
    ops.push({
      op: 'connect',
      id: newId(),
      source,
      target,
      fromSide: l.fromSide,
      toSide: l.toSide,
      ...(l.label ? { label: l.label } : {}),
      ...(l.color ? { color: l.color } : {}),
      fromEnd: l.fromEnd,
      toEnd: l.toEnd,
    });
  }
  return ops;
}

/** The frame drawn around `chosen` (⌘G), clear of them on every side, by
 *  more at the top for its name. */
export function around(chosen: Card[], pad = FRAME_PAD, top = FRAME_TOP): Frame {
  const left = Math.min(...chosen.map((c) => c.x));
  const y = Math.min(...chosen.map((c) => c.y));
  const right = Math.max(...chosen.map((c) => c.x + c.width));
  const bottom = Math.max(...chosen.map((c) => c.y + c.height));
  return {
    x: Math.round(left - pad),
    y: Math.round(y - top),
    width: Math.round(right - left + pad * 2),
    height: Math.round(bottom - y + top + pad),
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

