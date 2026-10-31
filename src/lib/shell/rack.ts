// The main window's rack (PANELS.md): eight views, each a tree of splits with
// one tool per leaf, and whether its layout is locked. Pure functions over
// that tree; PanelHost holds the views, renders them and saves them.

import { PANELS, type PanelId } from './panels';
import { parseRecord, parseStringArray } from './storeParsers';

export type Dir = 'row' | 'col';

export type RackNode =
  | { kind: 'tool'; id: PanelId }
  | { kind: 'split'; dir: Dir; sizes: number[]; children: RackNode[] };

type Split = Extract<RackNode, { kind: 'split' }>;

/** One view of the rack: its layout (null while empty), and whether it
 *  holds — no mount or take-out, no carry, no resize, no pop-out. */
export interface RackView {
  root: RackNode | null;
  locked: boolean;
}

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** The frame between two neighbours in a split; dragging it resizes them. */
export interface Rail {
  /** The split's place in the tree, as child indexes from the root. */
  path: number[];
  /** The rail sits between children `index` and `index + 1`. */
  index: number;
  dir: Dir;
  rect: Rect;
  /** The split's length less its rails: what its sizes are shares of. */
  span: number;
  /** A locked view holds every rail still. */
  inert: boolean;
}

export type Zone = 'left' | 'right' | 'top' | 'bottom' | 'center';

/** Where a carried tool would land, and what the view would become. */
export type Landing =
  | { ok: true; root: RackNode; rect: Rect }
  | { ok: false; reason: 'self' | 'locked' | 'room'; rect: Rect };

export const VIEW_COUNT = 8;
/** The rail's thickness in px. */
export const RAIL = 5;
/** How far into a slot an edge zone reaches, as a share of the slot. */
const EDGE = 0.28;

// The Servant joins the rack once it's built.
export const RACK_TOOLS = PANELS.filter((p) => p.id !== 'servant');

function minOf(id: PanelId): { w: number; h: number } {
  return PANELS.find((p) => p.id === id)!.rackMin;
}

function isCompact(id: PanelId): boolean {
  return PANELS.find((p) => p.id === id)!.compact;
}

/** The box a tool is drawn in within its slot: a compact tool's hugs its
 *  minimum height at the slot's top, a short unit in a tall bay, with bare
 *  rack below. The slot itself, and the rails, stay as the layout puts
 *  them. */
export function boxOf(id: PanelId, r: Rect): Rect {
  return isCompact(id) ? { ...r, h: Math.min(r.h, minOf(id).h) } : r;
}

export function emptyViews(): RackView[] {
  return Array.from({ length: VIEW_COUNT }, () => ({ root: null, locked: false }));
}

/** First launch: Legend Lore on view 1, where its tab used to be, and
 *  Command on 2 with Augury mounted beside it in a rack `w` wide. */
export function defaultViews(w = 0): RackView[] {
  const views = emptyViews();
  views[0] = { root: { kind: 'tool', id: 'legend-lore' }, locked: false };
  views[1] = { root: mount({ kind: 'tool', id: 'command' }, 'augury', w), locked: false };
  return views;
}

export function toolsIn(node: RackNode | null): PanelId[] {
  if (!node) return [];
  return node.kind === 'tool' ? [node.id] : node.children.flatMap(toolsIn);
}

// ---- layout -----------------------------------------------------------------

/** Each tool's rect and each rail, in a rack of w × h. */
export function layout(root: RackNode | null, w: number, h: number, locked: boolean) {
  const rects = new Map<PanelId, Rect>();
  const rails: Rail[] = [];
  if (root && w > 0 && h > 0) place(root, { x: 0, y: 0, w, h }, [], rects, rails, locked);
  return { rects, rails };
}

function place(node: RackNode, r: Rect, path: number[], rects: Map<PanelId, Rect>, rails: Rail[], locked: boolean) {
  if (node.kind === 'tool') {
    rects.set(node.id, r);
    return;
  }
  const row = node.dir === 'row';
  const n = node.children.length;
  const span = (row ? r.w : r.h) - RAIL * (n - 1);
  const lens = lengths(node, span);
  let at = row ? r.x : r.y;
  node.children.forEach((child, i) => {
    const len = lens[i];
    place(child, row ? { ...r, x: at, w: len } : { ...r, y: at, h: len }, [...path, i], rects, rails, locked);
    at += len;
    if (i === n - 1) return;
    rails.push({
      path,
      index: i,
      dir: node.dir,
      rect: row ? { ...r, x: at, w: RAIL } : { ...r, y: at, h: RAIL },
      span,
      inert: locked,
    });
    at += RAIL;
  });
}

/** Each child's length along a split `span` long: its share, but never
 *  under its minimum while the split has room for every one. A child short
 *  of its minimum (a window moved to a smaller screen scales every share
 *  down) takes what it lacks from the others, each in proportion to its
 *  room above its own minimum. The shares stay as saved, so a wider window
 *  gives the old proportions back. Rounded on the running total, so the
 *  lengths fill the span and a length that is a whole number stays one. */
function lengths(node: Split, span: number): number[] {
  const mins = node.children.map((c) => minAlong(c, node.dir));
  let want = node.sizes.map((s) => span * s);
  if (mins.reduce((a, b) => a + b, 0) <= span) {
    const lack = want.reduce((sum, w, i) => sum + Math.max(0, mins[i] - w), 0);
    const room = want.map((w, i) => Math.max(0, w - mins[i]));
    const spare = room.reduce((a, b) => a + b, 0);
    if (lack > 0 && spare > 0) want = want.map((w, i) => (w < mins[i] ? mins[i] : w - (lack * room[i]) / spare));
  }
  let sum = 0;
  let edge = 0;
  return want.map((w, i) => {
    sum += w;
    const next = i === want.length - 1 ? span : Math.round(sum);
    const len = next - edge;
    edge = next;
    return len;
  });
}

/** The least length a subtree can be given along `dir`. */
export type Side = 'left' | 'right' | 'up' | 'down';

/** The tool beside `from` on a side, among the tools that can take the
 *  keyboard: the nearest whose box lies past that edge of from's and shares
 *  its span across the other axis, so a diagonal neighbour doesn't count.
 *  Null at the rack's edge. The ⌘⌥ arrows cross the rail by it once a tool
 *  has nowhere further to go inside. */
export function neighbour(rects: Map<PanelId, Rect>, among: readonly PanelId[], from: PanelId, side: Side): PanelId | null {
  const f = rects.get(from);
  if (!f) return null;
  const horizontal = side === 'left' || side === 'right';
  let best: PanelId | null = null;
  let bestGap = Infinity;
  let bestOverlap = 0;
  for (const id of among) {
    if (id === from) continue;
    const r = rects.get(id);
    if (!r) continue;
    const gap =
      side === 'right' ? r.x - (f.x + f.w)
      : side === 'left' ? f.x - (r.x + r.w)
      : side === 'down' ? r.y - (f.y + f.h)
      : f.y - (r.y + r.h);
    if (gap < 0) continue;
    const overlap = horizontal
      ? Math.min(f.y + f.h, r.y + r.h) - Math.max(f.y, r.y)
      : Math.min(f.x + f.w, r.x + r.w) - Math.max(f.x, r.x);
    if (overlap <= 0) continue;
    if (gap < bestGap || (gap === bestGap && overlap > bestOverlap)) {
      best = id;
      bestGap = gap;
      bestOverlap = overlap;
    }
  }
  return best;
}

export function minAlong(node: RackNode, dir: Dir): number {
  if (node.kind === 'tool') return dir === 'row' ? minOf(node.id).w : minOf(node.id).h;
  const mins = node.children.map((c) => minAlong(c, dir));
  return node.dir === dir ? mins.reduce((a, b) => a + b, 0) + RAIL * (mins.length - 1) : Math.max(...mins);
}

// ---- edits ------------------------------------------------------------------

function nodeAt(root: RackNode, path: number[]): RackNode {
  return path.reduce((n, i) => (n as Split).children[i], root);
}

function replaceAt(node: RackNode, path: number[], next: RackNode): RackNode {
  if (path.length === 0) return next;
  const [i, ...rest] = path;
  const split = node as Split;
  return { ...split, children: split.children.map((c, j) => (j === i ? replaceAt(c, rest, next) : c)) };
}

/** The tree without `id`. A split left with one child gives way to it, and
 *  the survivors share out the space it held. */
export function without(node: RackNode | null, id: PanelId): RackNode | null {
  if (!node) return null;
  if (node.kind === 'tool') return node.id === id ? null : node;
  const children: RackNode[] = [];
  const sizes: number[] = [];
  node.children.forEach((c, i) => {
    const kept = without(c, id);
    if (kept) {
      children.push(kept);
      sizes.push(node.sizes[i]);
    }
  });
  if (children.length === 0) return null;
  if (children.length === 1) return children[0];
  const sum = sizes.reduce((a, b) => a + b, 0);
  return { ...node, children, sizes: sizes.map((s) => s / sum) };
}

/** Mounting from the rack bar: the tool takes a column on the right, or
 *  the whole of an empty view. A compact tool's column is its minimum width
 *  in a rack `w` wide (known once measured); the columns already there keep
 *  their proportions in what's left. Half a pixel per column covers their
 *  rounding in layout, so the new column never lands a pixel short. */
export function mount(root: RackNode | null, id: PanelId, w = 0): RackNode {
  const tool: RackNode = { kind: 'tool', id };
  if (!root) return tool;
  const row = root.kind === 'split' && root.dir === 'row';
  const n = row ? root.children.length : 1;
  const span = w - RAIL * n;
  const share = isCompact(id) && span > 0 ? Math.min((minOf(id).w + n / 2) / span, 0.5) : row ? 1 / (n + 1) : 0.4;
  if (row) {
    return { ...root, children: [...root.children, tool], sizes: [...root.sizes.map((s) => s * (1 - share)), share] };
  }
  return { kind: 'split', dir: 'row', sizes: [1 - share, share], children: [root, tool] };
}

/** `id` beside `target`, on the side `zone` names, the target keeping
 *  `keep` of its slot (half, but for a compact one). Next to a sibling in a
 *  split already running that way it joins the split, sharing out the
 *  target's share, rather than nesting a new one. */
function besides(node: RackNode, target: PanelId, zone: Exclude<Zone, 'center'>, id: PanelId, keep = 0.5): RackNode {
  const dir: Dir = zone === 'left' || zone === 'right' ? 'row' : 'col';
  const first = zone === 'left' || zone === 'top';
  const tool: RackNode = { kind: 'tool', id };
  if (node.kind === 'tool') {
    if (node.id !== target) return node;
    return {
      kind: 'split',
      dir,
      sizes: first ? [1 - keep, keep] : [keep, 1 - keep],
      children: first ? [tool, node] : [node, tool],
    };
  }
  const at = node.children.findIndex((c) => c.kind === 'tool' && c.id === target);
  if (at >= 0 && node.dir === dir) {
    const children = [...node.children];
    const sizes = [...node.sizes];
    const share = node.sizes[at];
    children.splice(first ? at : at + 1, 0, tool);
    sizes.splice(at, 1, ...(first ? [share * (1 - keep), share * keep] : [share * keep, share * (1 - keep)]));
    return { ...node, children, sizes };
  }
  return { ...node, children: node.children.map((c) => besides(c, target, zone, id, keep)) };
}

/** `a` where `b` was and `b` where `a` was. */
function swap(node: RackNode, a: PanelId, b: PanelId): RackNode {
  if (node.kind === 'tool') {
    if (node.id === a) return { kind: 'tool', id: b };
    if (node.id === b) return { kind: 'tool', id: a };
    return node;
  }
  return { ...node, children: node.children.map((c) => swap(c, a, b)) };
}

/** The rail between two neighbours moved by `delta` px, as far as either
 *  side's minimum allows. */
export function resize(root: RackNode, rail: Rail, delta: number): RackNode {
  const split = nodeAt(root, rail.path) as Split;
  const a0 = split.sizes[rail.index];
  const b0 = split.sizes[rail.index + 1];
  const lo = minAlong(split.children[rail.index], rail.dir) / rail.span;
  const hi = a0 + b0 - minAlong(split.children[rail.index + 1], rail.dir) / rail.span;
  if (lo > hi) return root;
  const a = Math.min(Math.max(a0 + delta / rail.span, lo), hi);
  const sizes = [...split.sizes];
  sizes[rail.index] = a;
  sizes[rail.index + 1] = a0 + b0 - a;
  return replaceAt(root, rail.path, { ...split, sizes });
}

// ---- carrying a tool in ----------------------------------------------------

/** The part of a slot a point is over: an edge band, or the middle. */
export function zoneAt(r: Rect, x: number, y: number): Zone {
  const left = (x - r.x) / r.w;
  const top = (y - r.y) / r.h;
  const edges: [Zone, number][] = [
    ['left', left],
    ['right', 1 - left],
    ['top', top],
    ['bottom', 1 - top],
  ];
  const [zone, depth] = edges.reduce((a, b) => (b[1] < a[1] ? b : a));
  return depth < EDGE ? zone : 'center';
}

/** The part of a slot a tool carried to its edge would take: what the
 *  target doesn't keep. */
function partOf(r: Rect, zone: Zone, keep: number): Rect {
  const give = 1 - keep;
  switch (zone) {
    case 'left': return { ...r, w: r.w * give };
    case 'right': return { ...r, x: r.x + r.w * keep, w: r.w * give };
    case 'top': return { ...r, h: r.h * give };
    case 'bottom': return { ...r, y: r.y + r.h * keep, h: r.h * give };
    default: return r;
  }
}

/** What carrying `id` to (x, y) in a w × h rack would do. On an edge it
 *  splits that slot; in the middle it swaps with that tool, or takes its
 *  place when `id` isn't in the view. A locked view takes no drops, and
 *  neither tool may end up under its minimum. Null outside every slot. */
export function landing(view: RackView, id: PanelId, x: number, y: number, w: number, h: number): Landing | null {
  if (!view.root) {
    const rect = { x: 0, y: 0, w, h };
    return view.locked ? { ok: false, reason: 'locked', rect } : { ok: true, root: { kind: 'tool', id }, rect };
  }
  const { rects } = layout(view.root, w, h, view.locked);
  for (const [target, r] of rects) {
    if (x < r.x || x >= r.x + r.w || y < r.y || y >= r.y + r.h) continue;
    if (target === id) return { ok: false, reason: 'self', rect: r };
    if (view.locked) return { ok: false, reason: 'locked', rect: r };
    // A compact tool's edges and middle are its box's; under the box is
    // bare rack, and a tool carried there goes beneath it.
    const box = boxOf(target, r);
    const zone = y >= box.y + box.h ? 'bottom' : zoneAt(box, x, y);
    // A compact tool keeps its minimum (and the rail and a pixel of
    // rounding); the carried tool takes the rest.
    const along = zone === 'left' || zone === 'right' ? 'w' : 'h';
    const keep = isCompact(target) ? Math.min(1, (minOf(target)[along] + RAIL + 1) / r[along]) : 0.5;
    const rest = without(view.root, id)!;
    const root =
      zone !== 'center'
        ? besides(rest, target, zone, id, keep)
        : toolsIn(view.root).includes(id)
          ? swap(view.root, id, target)
          : replaceAt(rest, pathTo(rest, target)!, { kind: 'tool', id });
    const after = layout(root, w, h, view.locked).rects;
    const fits = [id, target].every((t) => {
      const got = after.get(t);
      return !got || (got.w >= minOf(t).w && got.h >= minOf(t).h);
    });
    const rect = partOf(r, zone, keep);
    return fits ? { ok: true, root, rect } : { ok: false, reason: 'room', rect };
  }
  return null;
}

function pathTo(node: RackNode, id: PanelId, path: number[] = []): number[] | null {
  if (node.kind === 'tool') return node.id === id ? path : null;
  for (let i = 0; i < node.children.length; i++) {
    const found = pathTo(node.children[i], id, [...path, i]);
    if (found) return found;
  }
  return null;
}

// ---- the settings store -----------------------------------------------------

/** The views as saved, or undefined when the value isn't a list. A view
 *  that doesn't read back cleanly comes back empty rather than half-built. */
export function parseViews(v: unknown): RackView[] | undefined {
  if (!Array.isArray(v)) return undefined;
  const views = emptyViews();
  v.slice(0, VIEW_COUNT).forEach((raw, i) => (views[i] = parseView(raw) ?? views[i]));
  return views;
}

function parseView(raw: unknown): RackView | null {
  const rec = parseRecord(raw);
  if (!rec) return null;
  const root = rec.root === null ? null : parseNode(rec.root, 0);
  if (root === undefined) return null;
  const ids = toolsIn(root);
  // A tool lives once per view.
  if (new Set(ids).size !== ids.length) return null;
  // Settings from before the view lock held a list of locked tools: any
  // lock then locks the view now.
  const locked = rec.locked === true || (parseStringArray(rec.locked) ?? []).length > 0;
  return { root, locked };
}

function parseNode(raw: unknown, depth: number): RackNode | undefined {
  const rec = parseRecord(raw);
  if (!rec || depth > 8) return undefined;
  if (rec.kind === 'tool') {
    const tool = RACK_TOOLS.find((t) => t.id === rec.id);
    return tool ? { kind: 'tool', id: tool.id } : undefined;
  }
  if (rec.kind !== 'split' || (rec.dir !== 'row' && rec.dir !== 'col')) return undefined;
  if (!Array.isArray(rec.children) || !Array.isArray(rec.sizes)) return undefined;
  if (rec.children.length < 2 || rec.sizes.length !== rec.children.length) return undefined;
  const sizes = rec.sizes as unknown[];
  if (sizes.some((s) => typeof s !== 'number' || !Number.isFinite(s) || s <= 0)) return undefined;
  const children = rec.children.map((c) => parseNode(c, depth + 1));
  if (children.some((c) => !c)) return undefined;
  const sum = (sizes as number[]).reduce((a, b) => a + b, 0);
  return { kind: 'split', dir: rec.dir, sizes: (sizes as number[]).map((s) => s / sum), children: children as RackNode[] };
}
