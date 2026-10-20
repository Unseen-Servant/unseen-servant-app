// Undo on the session board (board toolbar design §4): every gesture is one
// batch of operations, kept with the batch that takes it back, worked out
// from the board as it stood before it. Undo applies that batch, and keeps
// what it in turn takes back for redo.

import { applyOps } from './board';
import type { BoardFields, BoardOp, BoardView, CanvasEdge, CanvasNode, MadeKind } from './types';

const MADE: MadeKind[] = ['text', 'group', 'link'];
const FIELDS: (keyof BoardFields)[] = ['text', 'label', 'url', 'color', 'fromEnd', 'toEnd'];

/** The operations that take `ops` back, applied to `view` as it was before
 *  them. Each is undone against the board it met, last first. A card or
 *  line `view` doesn't hold has nothing to restore, and is left out. */
export function inverse(view: BoardView, ops: BoardOp[], campaign: string): BoardOp[] {
  const steps: BoardOp[][] = [];
  let at = view;
  for (const op of ops) {
    steps.push(undoOne(at, op));
    at = applyOps(at, [op], campaign);
  }
  return steps.reverse().flat();
}

function undoOne(view: BoardView, op: BoardOp): BoardOp[] {
  const node = view.nodes.find((n) => n.id === op.id);
  const edge = view.edges.find((e) => e.id === op.id);
  switch (op.op) {
    case 'place': {
      // A note already on the board is framed rather than placed again.
      const id = Object.keys(view.notes).find((k) => view.notes[k] === op.path);
      const was = id ? view.nodes.find((n) => n.id === id) : undefined;
      return was ? [frameOf(was)] : [{ op: 'remove', id: op.id }];
    }
    case 'add':
    case 'connect':
      return [{ op: 'remove', id: op.id }];
    case 'frame':
      return node ? [frameOf(node)] : [];
    case 'set': {
      const target: CanvasNode | CanvasEdge | undefined = node ?? edge;
      if (!target) return [];
      const was: Record<string, unknown> = {};
      for (const key of FIELDS) {
        // A line written without a toEnd has JSON Canvas's arrowhead there.
        if (key in op) was[key] = target[key] ?? (key === 'toEnd' ? 'arrow' : null);
      }
      return [{ op: 'set', id: op.id, ...(was as BoardFields) }];
    }
    case 'remove': {
      if (edge) return [reconnect(edge)];
      if (!node) return [];
      const card = restore(view, node);
      if (!card) return [];
      const touching = view.edges.filter((e) => e.fromNode === node.id || e.toNode === node.id);
      return [card, ...touching.map(reconnect)];
    }
  }
}

function frameOf(node: CanvasNode): BoardOp {
  return { op: 'frame', id: node.id, x: node.x, y: node.y, width: node.width, height: node.height };
}

/** A removed card put back as it was, or null for one the board can't
 *  make (a kind only Obsidian knows). A note card comes back with its
 *  place and size; fields Obsidian gave it don't. */
function restore(view: BoardView, node: CanvasNode): BoardOp | null {
  const frame = { x: node.x, y: node.y, width: node.width, height: node.height };
  if (node.type === 'file') {
    const path = view.notes[node.id];
    return path ? { op: 'place', id: node.id, path, ...frame } : null;
  }
  const type = MADE.find((t) => t === node.type);
  if (!type) return null;
  const op: BoardOp = { op: 'add', id: node.id, type, ...frame };
  if (typeof node.text === 'string') op.text = node.text;
  if (typeof node.label === 'string') op.label = node.label;
  if (typeof node.url === 'string') op.url = node.url;
  if (typeof node.color === 'string') op.color = node.color;
  return op;
}

function reconnect(edge: CanvasEdge): BoardOp {
  return {
    op: 'connect',
    id: edge.id,
    source: edge.fromNode,
    target: edge.toNode,
    fromSide: edge.fromSide,
    toSide: edge.toSide,
    label: edge.label,
    color: edge.color,
    fromEnd: edge.fromEnd,
    // A line without one has JSON Canvas's arrowhead.
    toEnd: edge.toEnd ?? 'arrow',
  };
}
