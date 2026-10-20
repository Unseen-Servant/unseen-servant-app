import { describe, expect, it } from 'vitest';
import { applyOps } from './board';
import { inverse } from './boardUndo';
import type { BoardOp, BoardView } from './types';

const view: BoardView = {
  nodes: [
    { id: 'g1', type: 'group', x: -40, y: -60, width: 700, height: 400, label: 'Barovia' },
    { id: 'n1', type: 'file', file: 'Strahd/NPCs/Ismark.md', x: 0, y: 0, width: 260, height: 180 },
    { id: 't1', type: 'text', text: 'Ask about the wolves', x: 300, y: 0, width: 200, height: 200, color: '#e6c667' },
  ],
  edges: [{ id: 'e1', fromNode: 'n1', fromSide: 'right', toNode: 't1', toSide: 'left', toEnd: 'none', label: 'asks' }],
  notes: { n1: 'NPCs/Ismark.md' },
};

/** A board as a reader sees it: each node and line by id, key order and
 *  unset keys aside. */
const shape = (v: BoardView) => {
  const tidy = (o: object) => JSON.stringify(Object.fromEntries(Object.entries(o).filter(([, x]) => x !== undefined).sort()));
  return {
    nodes: v.nodes.map(tidy).sort(),
    edges: v.edges.map(tidy).sort(),
    notes: v.notes,
  };
};

const undone = (ops: BoardOp[]) => applyOps(applyOps(view, ops, 'Strahd'), inverse(view, ops, 'Strahd'), 'Strahd');

describe('board undo', () => {
  it('takes back a gesture of every kind, as the board was before it', () => {
    const ops: BoardOp[] = [
      { op: 'frame', id: 't1', x: 10, y: 20, width: 300, height: 120 },
      { op: 'set', id: 'g1', label: 'Village of Barovia', color: '4' },
      { op: 'set', id: 'e1', label: null },
      { op: 'remove', id: 'n1' },
      { op: 'add', id: 't2', type: 'text', text: 'Fog', x: 0, y: 300, width: 200, height: 200 },
      { op: 'connect', id: 'e2', source: 't1', target: 't2' },
    ];
    expect(shape(undone(ops))).toEqual(shape(view));
  });

  it('puts a removed card back before the lines that join it', () => {
    expect(inverse(view, [{ op: 'remove', id: 'n1' }], 'Strahd')).toEqual([
      { op: 'place', id: 'n1', path: 'NPCs/Ismark.md', x: 0, y: 0, width: 260, height: 180 },
      expect.objectContaining({ op: 'connect', id: 'e1', source: 'n1', target: 't1', label: 'asks', toEnd: 'none' }),
    ]);
  });

  it('frames a note placed again where it was, and removes one placed new', () => {
    expect(inverse(view, [{ op: 'place', id: 'x', path: 'NPCs/Ismark.md', x: 5, y: 5, width: 260, height: 180 }], 'Strahd')).toEqual([
      { op: 'frame', id: 'n1', x: 0, y: 0, width: 260, height: 180 },
    ]);
    expect(inverse(view, [{ op: 'place', id: 'x', path: 'NPCs/Ireena.md', x: 5, y: 5, width: 260, height: 180 }], 'Strahd')).toEqual([
      { op: 'remove', id: 'x' },
    ]);
  });

  it('clears a field the gesture set, and gives back the ends a line had by default', () => {
    const arrowed: BoardView = { ...view, edges: [{ id: 'e1', fromNode: 'n1', toNode: 't1' }] };
    expect(inverse(arrowed, [{ op: 'set', id: 'e1', label: 'asks', fromEnd: 'arrow', toEnd: 'none' }], 'Strahd')).toEqual([
      { op: 'set', id: 'e1', label: null, fromEnd: 'none', toEnd: 'arrow' },
    ]);
  });

  it('leaves out what the board no longer holds', () => {
    expect(inverse(view, [{ op: 'frame', id: 'gone', x: 0, y: 0, width: 1, height: 1 }, { op: 'remove', id: 'gone' }], 'Strahd')).toEqual([]);
  });
});
