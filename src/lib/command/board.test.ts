import { describe, expect, it } from 'vitest';
import { CARD, GAP, NOTE_HREF, applyOps, bodyOf, cards, connectOps, facing, findNotes, frameOp, lines, linkify, type Card } from './board';
import type { BoardView, CampaignIndex, NoteEntry } from './types';

const note = (path: string): NoteEntry => {
  const parts = path.split('/');
  return { name: parts[parts.length - 1].replace(/\.md$/, ''), path, track: parts.length > 1 ? parts[0] : null, group: null, spent: null, source: null };
};

const index: CampaignIndex = {
  name: 'Strahd',
  tracks: ['PCs', 'NPCs', 'Locations'],
  notes: ['NPCs/Ismark.md', 'NPCs/Ireena.md', 'Locations/Tser Pool.md', 'Overview.md', 'PCs/Bo.md'].map(note),
  note_order: {},
  ambiguous: [],
  beats: [],
  sessions: [],
};

const empty: BoardView = { nodes: [], edges: [], notes: {} };

describe('cards', () => {
  it('lays out notes nobody placed in columns by track, by name', () => {
    const out = cards(empty, index, ['Overview.md', 'NPCs/Ismark.md', 'Locations/Tser Pool.md', 'NPCs/Ireena.md', 'NPCs/Gone.md']);
    expect(out.map((c) => [c.path, c.placed, c.x, c.y])).toEqual([
      ['NPCs/Ireena.md', false, 0, 0],
      ['NPCs/Ismark.md', false, 0, CARD.height + GAP],
      ['Locations/Tser Pool.md', false, CARD.width + GAP, 0],
      ['Overview.md', false, 2 * (CARD.width + GAP), 0],
    ]);
  });

  it('keeps what the canvas holds and puts the rest to its right', () => {
    const view: BoardView = {
      nodes: [
        { id: 'a', type: 'file', file: 'Strahd/NPCs/Ismark.md', x: -100, y: 40, width: 300, height: 200 },
        { id: 't', type: 'text', text: 'wolves', x: 300, y: -60, width: 200, height: 100 },
        { id: 'g', type: 'group', label: 'Barovia', x: -120, y: -80, width: 700, height: 400 },
        { id: 'x', type: 'mystery', x: 0, y: 0, width: 50, height: 50 },
      ],
      edges: [],
      notes: { a: 'NPCs/Ismark.md' },
    };
    const out = cards(view, index, ['NPCs/Ismark.md', 'NPCs/Ireena.md']);
    expect(out.map((c) => [c.id, c.kind, c.text, c.placed])).toEqual([
      ['a', 'note', 'Strahd/NPCs/Ismark.md', true],
      ['t', 'text', 'wolves', true],
      ['g', 'group', 'Barovia', true],
      ['x', 'other', '', true],
      ['auto:NPCs/Ireena.md', 'note', 'NPCs/Ireena.md', false],
    ]);
    expect([out[4].x, out[4].y]).toEqual([580 + 2 * GAP, -80]);
  });

  it('shows a card whose note is gone without a path', () => {
    const view: BoardView = {
      nodes: [{ id: 'a', type: 'file', file: 'Strahd/NPCs/Gone.md', x: 0, y: 0, width: 100, height: 100 }],
      edges: [],
      notes: {},
    };
    expect(cards(view, index, [])[0]).toMatchObject({ kind: 'note', path: null, text: 'Strahd/NPCs/Gone.md' });
  });
});

const at = (id: string, x: number, y: number, placed = true): Card => ({
  id, kind: 'note', path: `NPCs/${id}.md`, placed, x, y, width: 100, height: 100, text: '',
});

describe('lines', () => {
  it('takes sides from the file, else the sides the cards face', () => {
    expect(facing(at('a', 0, 0), at('b', 300, 50))).toEqual(['right', 'left']);
    expect(facing(at('a', 0, 0), at('b', 20, -300))).toEqual(['top', 'bottom']);
    const view: BoardView = {
      nodes: [],
      notes: {},
      edges: [
        { id: 'e1', fromNode: 'a', toNode: 'b', fromSide: 'top', toSide: 'top', label: 'owes' },
        { id: 'e2', fromNode: 'b', toNode: 'a' },
        { id: 'e3', fromNode: 'a', toNode: 'gone' },
      ],
    };
    expect(lines(view, [at('a', 0, 0), at('b', 300, 0)])).toEqual([
      { id: 'e1', source: 'a', target: 'b', fromSide: 'top', toSide: 'top', label: 'owes' },
      { id: 'e2', source: 'b', target: 'a', fromSide: 'left', toSide: 'right', label: null },
    ]);
  });
});

describe('operations', () => {
  it('frames a placed card and places an auto-placed one', () => {
    expect(frameOp(at('a', 0, 0), { x: 10.4, y: 20, width: 300, height: 150.6 })).toEqual({
      op: 'frame', id: 'a', x: 10, y: 20, width: 300, height: 151,
    });
    const placed = frameOp(at('b', 0, 0, false), { x: 1, y: 2, width: 3, height: 4 });
    expect(placed).toMatchObject({ op: 'place', path: 'NPCs/b.md', x: 1, y: 2, width: 3, height: 4 });
    expect(placed.id).toMatch(/^[0-9a-f]{16}$/);
  });

  it('places an auto-placed end before connecting it', () => {
    const ops = connectOps(at('a', 0, 0), at('b', 300, 0, false), 'right', 'left');
    expect(ops.map((o) => o.op)).toEqual(['place', 'connect']);
    expect(ops[1]).toMatchObject({ source: 'a', target: ops[0].id, fromSide: 'right', toSide: 'left' });
  });
});

describe('bodyOf', () => {
  it('drops the frontmatter and leading blank lines', () => {
    expect(bodyOf('---\nnotes: []\n---\n\nDusk.\n')).toBe('Dusk.\n');
    expect(bodyOf('﻿---\r\nspent: 2026-10-04\r\n---\r\nText')).toBe('Text');
    expect(bodyOf('No frontmatter.')).toBe('No frontmatter.');
    expect(bodyOf('---\nunclosed\nText')).toBe('---\nunclosed\nText');
  });
});

describe('linkify', () => {
  it('makes wikilinks followable and leaves embeds alone', () => {
    expect(linkify('Ask [[Ismark]] or [[NPCs/Ireena.md|her]] about [[Tser Pool#Camp]]. ![[map.png]]')).toBe(
      `Ask [Ismark](${NOTE_HREF}Ismark) or [her](${NOTE_HREF}Ireena) about [Tser Pool#Camp](${NOTE_HREF}Tser%20Pool). ![[map.png]]`,
    );
  });
});

describe('applyOps', () => {
  it('draws what the sidecar is about to write', () => {
    const view: BoardView = {
      nodes: [{ id: 'a', type: 'file', file: 'Strahd/NPCs/Ismark.md', x: 0, y: 0, width: 100, height: 100 }],
      edges: [{ id: 'old', fromNode: 'a', toNode: 'gone' }],
      notes: { a: 'NPCs/Ismark.md' },
    };
    const after = applyOps(view, [
      { op: 'place', id: 'b', path: 'NPCs/Ireena.md', x: 200, y: 0, width: 100, height: 100 },
      { op: 'frame', id: 'a', x: 5, y: 6, width: 120, height: 90 },
      { op: 'connect', id: 'e1', source: 'a', target: 'b', fromSide: 'right', toSide: 'left' },
      { op: 'remove', id: 'old' },
    ], 'Strahd');
    expect(after.nodes).toEqual([
      { id: 'a', type: 'file', file: 'Strahd/NPCs/Ismark.md', x: 5, y: 6, width: 120, height: 90 },
      { id: 'b', type: 'file', file: 'Strahd/NPCs/Ireena.md', x: 200, y: 0, width: 100, height: 100 },
    ]);
    expect(after.edges.map((e) => e.id)).toEqual(['e1']);
    expect(after.notes).toEqual({ a: 'NPCs/Ismark.md', b: 'NPCs/Ireena.md' });
    expect(applyOps(after, [{ op: 'remove', id: 'a' }], 'Strahd')).toEqual({
      nodes: [after.nodes[1]],
      edges: [],
      notes: { b: 'NPCs/Ireena.md' },
    });
    expect(view.nodes[0].x).toBe(0);
  });
});

describe('findNotes', () => {
  it('offers names starting with the query, then containing it, never beats or sessions', () => {
    const withBeats: CampaignIndex = {
      ...index,
      notes: [...index.notes, ...['Beats/Ireena flees.md', 'Sessions/Session 1.md', 'NPCs/Mad Mary.md'].map(note)],
    };
    expect(findNotes(withBeats, 'ir').map((n) => n.name)).toEqual(['Ireena']);
    expect(findNotes(withBeats, 'MA').map((n) => n.name)).toEqual(['Mad Mary', 'Ismark']);
    expect(findNotes(withBeats, '  ')).toEqual([]);
  });
});
