import { describe, expect, it } from 'vitest';
import { CARD, FRAME_PAD, FRAME_TOP, GAP, NOTE_HREF, applyOps, around, arrowhead, bodyOf, cards, connectOps, duplicateOps, facing, frameDepths, frameOp, handOf, handStep, IMAGE_CARD, imageCard, inside, lines, linkify, paint, placeAll, rehypeMissingLinks, type Card } from './board';
import type { BoardView, CampaignIndex, NoteEntry } from './types';

const note = (path: string): NoteEntry => {
  const parts = path.split('/');
  return { name: parts[parts.length - 1].replace(/\.md$/, ''), path, track: parts.length > 1 ? parts[0] : null, group: null, spent: null, source: null, type: path.endsWith('.md') ? 'note' : 'image' };
};

const index: CampaignIndex = {
  name: 'Strahd',
  tracks: ['PCs', 'NPCs', 'Locations'],
  notes: ['NPCs/Ismark.md', 'NPCs/Ireena.md', 'Locations/Tser Pool.md', 'Overview.md', 'PCs/Bo.md'].map(note),
  note_order: {},
  pigments: {},
  kinds: {},
  ambiguous: [],
  beats: [],
  sessions: [],
  images: [],
};

const empty: BoardView = { nodes: [], edges: [], notes: {}, images: {} };

describe('cards', () => {
  it('lays out notes nobody placed in a column per beat group, in order, then the rest by name', () => {
    const wanted = ['Overview.md', 'NPCs/Ismark.md', 'Locations/Tser Pool.md', 'NPCs/Ireena.md', 'PCs/Bo.md', 'NPCs/Gone.md'];
    const out = cards(empty, index, wanted, [['NPCs/Ismark.md', 'Overview.md'], ['Locations/Tser Pool.md']]);
    expect(out.map((c) => [c.path, c.placed, c.x, c.y])).toEqual([
      ['NPCs/Ismark.md', false, 0, 0],
      ['Overview.md', false, 0, CARD.height + GAP],
      ['Locations/Tser Pool.md', false, CARD.width + GAP, 0],
      ['PCs/Bo.md', false, 2 * (CARD.width + GAP), 0],
      ['NPCs/Ireena.md', false, 2 * (CARD.width + GAP), CARD.height + GAP],
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
      images: {},
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
      images: {},
    };
    expect(cards(view, index, [])[0]).toMatchObject({ kind: 'note', path: null, text: 'Strahd/NPCs/Gone.md' });
  });
});

const at = (id: string, x: number, y: number, placed = true): Card => ({
  id, kind: 'note', path: `NPCs/${id}.md`, placed, x, y, width: 100, height: 100, text: '', color: null,
});

describe('lines', () => {
  it('takes sides from the file, else the sides the cards face', () => {
    expect(facing(at('a', 0, 0), at('b', 300, 50))).toEqual(['right', 'left']);
    expect(facing(at('a', 0, 0), at('b', 20, -300))).toEqual(['top', 'bottom']);
    const view: BoardView = {
      nodes: [],
      notes: {},
      images: {},
      edges: [
        { id: 'e1', fromNode: 'a', toNode: 'b', fromSide: 'top', toSide: 'top', label: 'owes', toEnd: 'none' },
        { id: 'e2', fromNode: 'b', toNode: 'a' },
        { id: 'e3', fromNode: 'a', toNode: 'gone' },
      ],
    };
    const plain = { color: null, fromEnd: 'none', toEnd: 'none' };
    expect(lines(view, [at('a', 0, 0), at('b', 300, 0)])).toEqual([
      { id: 'e1', source: 'a', target: 'b', fromSide: 'top', toSide: 'top', label: 'owes', ...plain },
      { id: 'e2', source: 'b', target: 'a', fromSide: 'left', toSide: 'right', label: null, ...plain, toEnd: 'arrow' },
    ]);
  });

  it("reads a line's colour and ends, an unwritten target end as JSON Canvas's arrowhead", () => {
    const view: BoardView = {
      nodes: [],
      notes: {},
      images: {},
      edges: [{ id: 'e', fromNode: 'a', toNode: 'b', color: '4', fromEnd: 'arrow' }],
    };
    expect(lines(view, [at('a', 0, 0), at('b', 300, 0)])[0]).toMatchObject({ color: '4', fromEnd: 'arrow', toEnd: 'arrow' });
  });

  it('points an arrowhead into the card it ends on', () => {
    // On a card's left side the head opens out to the left, its point on the edge.
    expect(arrowhead(100, 50, 'left')).toBe('M100,50L90,46L90,54Z');
    expect(arrowhead(0, 0, 'top')).toBe('M0,0L4,-10L-4,-10Z');
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

  it('puts every auto-placed card down where it sits, so a card moved later moves alone', () => {
    const view: BoardView = {
      nodes: [{ id: 'a', type: 'file', file: 'Strahd/NPCs/Ismark.md', x: 0, y: 0, width: 100, height: 100 }],
      edges: [],
      notes: { a: 'NPCs/Ismark.md' },
      images: {},
    };
    const wanted = ['NPCs/Ismark.md', 'NPCs/Ireena.md', 'Locations/Tser Pool.md', 'Overview.md'];
    const where = (board: Card[]) => board.map((c) => [c.path, c.x, c.y]);
    let board = cards(view, index, wanted);

    // Moving the placed card right would push the auto-placed ones after it.
    let ops = placeAll(board, [frameOp(board[0], { x: 900, y: -50, width: 100, height: 100 })]);
    expect(ops.map((o) => o.op)).toEqual(['frame', 'place', 'place', 'place']);
    let after = cards(applyOps(view, ops, 'Strahd'), index, wanted);
    expect(after.every((c) => c.placed)).toBe(true);
    expect(where(after)).toEqual([['NPCs/Ismark.md', 900, -50], ...where(board.slice(1))]);

    // An auto-placed card moved first is placed once, where it's dropped.
    board = cards(view, index, wanted);
    ops = placeAll(board, [frameOp(board[1], { x: 5, y: 500, width: 260, height: 180 })]);
    expect(ops.filter((o) => o.op === 'place' && o.path === 'NPCs/Ireena.md')).toHaveLength(1);
    after = cards(applyOps(view, ops, 'Strahd'), index, wanted);
    expect(where(after)).toEqual([where(board)[0], ['NPCs/Ireena.md', 5, 500], ...where(board.slice(2))]);
  });
});

describe('the card tray', () => {
  it('holds the live notes in the live set\'s order, each once', () => {
    const board = cards(empty, index, ['NPCs/Ismark.md', 'Locations/Tser Pool.md', 'NPCs/Ireena.md']);
    const hand = handOf(board, ['Locations/Tser Pool.md', 'NPCs/Ismark.md', 'NPCs/Gone.md']);
    expect(hand.map((c) => c.path)).toEqual(['Locations/Tser Pool.md', 'NPCs/Ismark.md']);
  });

  it('sets cards side by side while they fit, then overlaps them evenly', () => {
    expect(handStep(5, 1248, 234, 8)).toBe(242);
    // Nine: the last card ends at the row's end.
    const step = handStep(9, 1248, 234, 8);
    expect(8 * step + 234).toBeCloseTo(1248);
    expect(handStep(1, 100, 234, 8)).toBe(0);
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
      `Ask [Ismark](${NOTE_HREF}Ismark) or [her](${NOTE_HREF}NPCs%2FIreena) about [Tser Pool#Camp](${NOTE_HREF}Tser%20Pool). ![[map.png]]`,
    );
  });
});

describe('rehypeMissingLinks', () => {
  const a = (href: string) => ({ type: 'element', tagName: 'a', properties: { href } as Record<string, unknown>, children: [] });

  it('marks only the note links nothing answers to', () => {
    const known = a(`${NOTE_HREF}Ismark`);
    const gone = a(`${NOTE_HREF}Tser%20Pool`);
    const web = a('https://example.com');
    rehypeMissingLinks((name) => name === 'Ismark')({
      type: 'root',
      children: [{ type: 'element', tagName: 'p', properties: {}, children: [known, gone, web] }],
    });
    expect(known.properties.className).toBeUndefined();
    expect(gone.properties.className).toEqual(['missing']);
    expect(web.properties.className).toBeUndefined();
  });
});

describe('applyOps', () => {
  it('draws what the sidecar is about to write', () => {
    const view: BoardView = {
      nodes: [{ id: 'a', type: 'file', file: 'Strahd/NPCs/Ismark.md', x: 0, y: 0, width: 100, height: 100 }],
      edges: [{ id: 'old', fromNode: 'a', toNode: 'gone' }],
      notes: { a: 'NPCs/Ismark.md' },
      images: {},
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
      images: {},
    });
    expect(view.nodes[0].x).toBe(0);
  });

  it('files a placed image among the images, and forgets it once removed', () => {
    const view: BoardView = { nodes: [], edges: [], notes: {}, images: {} };
    const after = applyOps(view, [{ op: 'place', id: 'm', path: 'Shelf/Barovia.png', x: 0, y: 0, width: 480, height: 300 }], 'Strahd');
    expect([after.notes, after.images]).toEqual([{}, { m: 'Shelf/Barovia.png' }]);
    expect(applyOps(after, [{ op: 'remove', id: 'm' }], 'Strahd').images).toEqual({});
  });
});

describe('image cards', () => {
  it('shows a file node naming an image as the image (#407)', () => {
    const view: BoardView = {
      nodes: [{ id: 'm', type: 'file', file: 'Strahd/Maps/Barovia.png', x: 0, y: 0, width: 400, height: 300 }],
      edges: [],
      notes: {},
      images: { m: 'Maps/Barovia.png' },
    };
    expect(cards(view, index, []).map((c) => [c.kind, c.path, c.text])).toEqual([['image', 'Maps/Barovia.png', 'Strahd/Maps/Barovia.png']]);
  });

  it('lays out a planned image the board doesn’t hold as an image card, and deals it to the tray', () => {
    const withImage: CampaignIndex = { ...index, notes: [...index.notes, note('Maps/Barovia.png')] };
    const out = cards(empty, withImage, ['NPCs/Ismark.md', 'Maps/Barovia.png']);
    expect(out.map((c) => [c.kind, c.path, c.placed])).toEqual([
      ['image', 'Maps/Barovia.png', false],
      ['note', 'NPCs/Ismark.md', false],
    ]);
    expect(handOf(out, ['Maps/Barovia.png']).map((c) => c.kind)).toEqual(['image']);
  });

  it('sizes a dropped image in its proportions, at most IMAGE_CARD a side', () => {
    expect(imageCard(1920, 1080)).toEqual({ width: IMAGE_CARD, height: 270 });
    expect(imageCard(600, 1200)).toEqual({ width: 240, height: IMAGE_CARD });
    expect(imageCard(200, 100)).toEqual({ width: 200, height: 100 });
    expect(imageCard(2000, 20)).toEqual({ width: IMAGE_CARD, height: 40 });
  });
});

describe("the toolbar's cards", () => {
  const view: BoardView = {
    nodes: [
      { id: 'g', type: 'group', x: 0, y: 0, width: 100, height: 100 },
      { id: 'a', type: 'file', file: 'Strahd/NPCs/Ismark.md', x: 0, y: 0, width: 100, height: 100 },
    ],
    edges: [{ id: 'e', fromNode: 'a', toNode: 'g', toEnd: 'none', label: 'in' }],
    notes: { a: 'NPCs/Ismark.md' },
    images: {},
  };

  it('draws a new frame behind the cards, a new text card on top, and a line with no arrowhead', () => {
    const after = applyOps(view, [
      { op: 'add', id: 't', type: 'text', text: '', x: 0, y: 0, width: 50, height: 50 },
      { op: 'add', id: 'g2', type: 'group', x: 0, y: 0, width: 50, height: 50 },
      { op: 'connect', id: 'e2', source: 't', target: 'a' },
    ], 'Strahd');
    expect(after.nodes.map((n) => n.id)).toEqual(['g', 'g2', 'a', 't']);
    expect(after.edges[1]).toEqual({ id: 'e2', fromNode: 't', toNode: 'a', toEnd: 'none' });
  });

  it('sets a field, and clears one set to null or an emptied label', () => {
    const after = applyOps(view, [
      { op: 'set', id: 'g', label: 'Barovia', color: '#e6c667' },
      { op: 'set', id: 'e', label: '' },
    ], 'Strahd');
    expect(after.nodes[0]).toMatchObject({ label: 'Barovia', color: '#e6c667' });
    expect(after.edges[0]).not.toHaveProperty('label');
    expect(applyOps(after, [{ op: 'set', id: 'g', color: null }], 'Strahd').nodes[0]).not.toHaveProperty('color');
  });

  const frame: Card = { ...at('f', 0, 0), kind: 'group', path: null, width: 400, height: 300 };

  it('carries the cards wholly inside a frame, not those it only touches', () => {
    const board = [frame, at('in', 20, 50), at('edge', 350, 250), at('out', 500, 0)];
    expect(inside(board, frame).map((c) => c.id)).toEqual(['in']);
  });

  it('draws a frame around cards clear of them, more at the top for its name', () => {
    expect(around([at('a', 0, 0), at('b', 300, 200)])).toEqual({
      x: -FRAME_PAD,
      y: -FRAME_TOP,
      width: 400 + FRAME_PAD * 2,
      height: 300 + FRAME_TOP + FRAME_PAD,
    });
  });

  it('stacks frames behind the cards, the smaller in front even when selected', () => {
    const small = { ...frame, id: 'small', width: 100, height: 100 };
    const depths = frameDepths([at('a', 0, 0), frame, small]);
    expect(depths.has('a')).toBe(false);
    expect(depths.get('small')!).toBeGreaterThan(depths.get('f')!);
    expect(depths.get('small')! + 1000).toBeLessThan(0);
  });

  it('duplicates text, stickies and frames beside them, a frame with what it holds but its notes', () => {
    const sticky: Card = { ...at('s', 20, 50), kind: 'text', path: null, text: 'Fog', color: '#e6c667' };
    const named: Card = { ...frame, text: 'Barovia' };
    const board = [named, sticky, at('ismark', 200, 50), { ...at('t', 900, 0), kind: 'text' as const, path: null, text: 'Later' }];
    const drawn = [
      { id: 'e', source: 's', target: 'f', fromSide: 'top' as const, toSide: 'top' as const, label: 'in', color: null, fromEnd: 'none' as const, toEnd: 'arrow' as const },
      { id: 'e2', source: 's', target: 'ismark', fromSide: 'right' as const, toSide: 'left' as const, label: null, color: null, fromEnd: 'none' as const, toEnd: 'none' as const },
    ];
    const ops = duplicateOps(board, drawn, ['f']);
    const added = ops.filter((o) => o.op === 'add');
    expect(added).toEqual([
      expect.objectContaining({ type: 'group', label: 'Barovia', x: 400 + GAP, y: 0, width: 400, height: 300 }),
      expect.objectContaining({ type: 'text', text: 'Fog', color: '#e6c667', x: 20 + 400 + GAP, y: 50 }),
    ]);
    // Only the line between two copies comes along, between the copies.
    const copied = ops.filter((o) => o.op === 'connect');
    expect(copied).toEqual([expect.objectContaining({ source: added[1].id, target: added[0].id, label: 'in', toEnd: 'arrow' })]);
    expect(duplicateOps(board, drawn, ['ismark'])).toEqual([]);
  });

  it('sets a copy down clear of other cards: right, else below, else past them', () => {
    const sticky: Card = { ...at('s', 20, 50), kind: 'text', path: null, text: 'Fog' };
    // The frame the sticky sits in isn't in the way.
    const hall: Card = { ...frame, id: 'big', x: -100, y: -100, width: 2000, height: 1000 };
    const copyAt = (board: Card[]) => duplicateOps(board, [], ['s']).find((o) => o.op === 'add');
    expect(copyAt([hall, sticky])).toMatchObject({ x: 20 + 100 + GAP, y: 50 });
    expect(copyAt([hall, sticky, at('right', 150, 0)])).toMatchObject({ x: 20, y: 50 + 100 + GAP });
    expect(copyAt([hall, sticky, at('right', 150, 0), at('below', 0, 200)])).toMatchObject({ x: 250 + GAP, y: 50 });
  });

  it("paints a pigment's hex as it is and Obsidian's presets as the nearest pigment", () => {
    expect(paint('#e6c667')).toBe('#e6c667');
    expect(paint('3')).toBe('#e6c667');
    expect(paint('9')).toBeNull();
    expect(paint(null)).toBeNull();
  });
});
