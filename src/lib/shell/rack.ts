// The main window's rack (PANELS.md): eight views, each a tree of splits with
// one tool per leaf, and the tools locked in it. Pure functions over that
// tree; PanelHost holds the views, renders them and saves them.

import { PANELS, type PanelId } from './panels';
import { parseRecord, parseStringArray } from './storeParsers';

export type Dir = 'row' | 'col';

export type RackNode =
  | { kind: 'tool'; id: PanelId }
  | { kind: 'split'; dir: Dir; sizes: number[]; children: RackNode[] };

type Split = Extract<RackNode, { kind: 'split' }>;

/** One view of the rack: its layout (null while empty) and its locks. */
export interface RackView {
  root: RackNode | null;
  locked: PanelId[];
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
  /** A locked tool on either side holds the rail still. */
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

export function emptyViews(): RackView[] {
  return Array.from({ length: VIEW_COUNT }, () => ({ root: null, locked: [] }));
}

/** First launch: each tool on the view its tab used to be. */
export function defaultViews(): RackView[] {
  const views = emptyViews();
  RACK_TOOLS.forEach((t, i) => (views[i] = { root: { kind: 'tool', id: t.id }, locked: [] }));
  return views;
}

export function toolsIn(node: RackNode | null): PanelId[] {
  if (!node) return [];
  return node.kind === 'tool' ? [node.id] : node.children.flatMap(toolsIn);
}

// ---- layout -----------------------------------------------------------------

/** Each tool's rect and each rail, in a rack of w × h. */
export function layout(root: RackNode | null, w: number, h: number, locked: readonly PanelId[]) {
  const rects = new Map<PanelId, Rect>();
  const rails: Rail[] = [];
  if (root && w > 0 && h > 0) place(root, { x: 0, y: 0, w, h }, [], rects, rails, new Set(locked));
  return { rects, rails };
}

function place(node: RackNode, r: Rect, path: number[], rects: Map<PanelId, Rect>, rails: Rail[], locked: Set<PanelId>) {
  if (node.kind === 'tool') {
    rects.set(node.id, r);
    return;
  }
  const row = node.dir === 'row';
  const n = node.children.length;
  const span = (row ? r.w : r.h) - RAIL * (n - 1);
  let at = row ? r.x : r.y;
  let used = 0;
  node.children.forEach((child, i) => {
    const len = i === n - 1 ? span - used : Math.round(span * node.sizes[i]);
    used += len;
    place(child, row ? { ...r, x: at, w: len } : { ...r, y: at, h: len }, [...path, i], rects, rails, locked);
    at += len;
    if (i === n - 1) return;
    const held = (c: RackNode) => toolsIn(c).some((id) => locked.has(id));
    rails.push({
      path,
      index: i,
      dir: node.dir,
      rect: row ? { ...r, x: at, w: RAIL } : { ...r, y: at, h: RAIL },
      span,
      inert: held(child) || held(node.children[i + 1]),
    });
    at += RAIL;
  });
}

/** The least length a subtree can be given along `dir`. */
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
 *  the whole of an empty view. */
export function mount(root: RackNode | null, id: PanelId): RackNode {
  const tool: RackNode = { kind: 'tool', id };
  if (!root) return tool;
  if (root.kind === 'split' && root.dir === 'row') {
    const n = root.children.length;
    return { ...root, children: [...root.children, tool], sizes: [...root.sizes.map((s) => (s * n) / (n + 1)), 1 / (n + 1)] };
  }
  return { kind: 'split', dir: 'row', sizes: [0.6, 0.4], children: [root, tool] };
}

/** `id` beside `target`, on the side `zone` names. Next to a sibling in a
 *  split already running that way it joins the split, halving the target's
 *  share, rather than nesting a new one. */
function besides(node: RackNode, target: PanelId, zone: Exclude<Zone, 'center'>, id: PanelId): RackNode {
  const dir: Dir = zone === 'left' || zone === 'right' ? 'row' : 'col';
  const first = zone === 'left' || zone === 'top';
  const tool: RackNode = { kind: 'tool', id };
  if (node.kind === 'tool') {
    if (node.id !== target) return node;
    return { kind: 'split', dir, sizes: [0.5, 0.5], children: first ? [tool, node] : [node, tool] };
  }
  const at = node.children.findIndex((c) => c.kind === 'tool' && c.id === target);
  if (at >= 0 && node.dir === dir) {
    const children = [...node.children];
    const sizes = [...node.sizes];
    children.splice(first ? at : at + 1, 0, tool);
    sizes.splice(at, 1, node.sizes[at] / 2, node.sizes[at] / 2);
    return { ...node, children, sizes };
  }
  return { ...node, children: node.children.map((c) => besides(c, target, zone, id)) };
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

function halfOf(r: Rect, zone: Zone): Rect {
  switch (zone) {
    case 'left': return { ...r, w: r.w / 2 };
    case 'right': return { ...r, x: r.x + r.w / 2, w: r.w / 2 };
    case 'top': return { ...r, h: r.h / 2 };
    case 'bottom': return { ...r, y: r.y + r.h / 2, h: r.h / 2 };
    default: return r;
  }
}

/** What carrying `id` to (x, y) in a w × h rack would do. On an edge it
 *  splits that slot; in the middle it swaps with that tool, or takes its
 *  place when `id` isn't in the view. A locked tool takes no drops, and
 *  neither tool may end up under its minimum. Null outside every slot. */
export function landing(view: RackView, id: PanelId, x: number, y: number, w: number, h: number): Landing | null {
  if (!view.root) return { ok: true, root: { kind: 'tool', id }, rect: { x: 0, y: 0, w, h } };
  const { rects } = layout(view.root, w, h, view.locked);
  for (const [target, r] of rects) {
    if (x < r.x || x >= r.x + r.w || y < r.y || y >= r.y + r.h) continue;
    if (target === id) return { ok: false, reason: 'self', rect: r };
    if (view.locked.includes(target)) return { ok: false, reason: 'locked', rect: r };
    const zone = zoneAt(r, x, y);
    const rest = without(view.root, id)!;
    const root =
      zone !== 'center'
        ? besides(rest, target, zone, id)
        : toolsIn(view.root).includes(id)
          ? swap(view.root, id, target)
          : replaceAt(rest, pathTo(rest, target)!, { kind: 'tool', id });
    const after = layout(root, w, h, view.locked).rects;
    const fits = [id, target].every((t) => {
      const got = after.get(t);
      return !got || (got.w >= minOf(t).w && got.h >= minOf(t).h);
    });
    const rect = halfOf(r, zone);
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
  const locked = (parseStringArray(rec.locked) ?? []).filter((id): id is PanelId => (ids as string[]).includes(id));
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
