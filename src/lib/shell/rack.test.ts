import { describe, expect, test } from 'vitest';
import {
  RAIL,
  defaultViews,
  landing,
  layout,
  mount,
  neighbour,
  parseViews,
  resize,
  toolsIn,
  without,
  zoneAt,
  type RackNode,
  type RackView,
} from './rack';

const LL: RackNode = { kind: 'tool', id: 'legend-lore' };
const CMD: RackNode = { kind: 'tool', id: 'command' };
const row = (a: number, ...children: RackNode[]): RackNode => ({ kind: 'split', dir: 'row', sizes: [a, 1 - a], children });
const col = (a: number, ...children: RackNode[]): RackNode => ({ kind: 'split', dir: 'col', sizes: [a, 1 - a], children });
const view = (root: RackNode | null, locked = false): RackView => ({ root, locked });

describe('layout', () => {
  test('splits the rack between neighbours with a rail between them, to the pixel', () => {
    const { rects, rails } = layout(row(0.6, LL, CMD), 1280, 760, false);
    const ll = rects.get('legend-lore')!;
    const cmd = rects.get('command')!;
    expect(ll).toEqual({ x: 0, y: 0, w: Math.round((1280 - RAIL) * 0.6), h: 760 });
    expect(cmd.x).toBe(ll.w + RAIL);
    expect(cmd.x + cmd.w).toBe(1280);
    expect(rails).toEqual([{ path: [], index: 0, dir: 'row', rect: { x: ll.w, y: 0, w: RAIL, h: 760 }, span: 1280 - RAIL, inert: false }]);
  });

  test('a locked view holds every rail still', () => {
    expect(layout(col(0.5, CMD, LL), 1280, 760, true).rails[0].inert).toBe(true);
  });

  test('an empty view, or a rack not measured yet, places nothing', () => {
    expect(layout(null, 1280, 760, false).rects.size).toBe(0);
    expect(layout(LL, 0, 0, false).rects.size).toBe(0);
  });
});

describe('tree edits', () => {
  test('taking a tool out collapses its split into the survivor', () => {
    expect(without(row(0.6, LL, CMD), 'command')).toEqual(LL);
    expect(without(LL, 'legend-lore')).toBeNull();
  });

  test('mounting fills an empty view, then takes a column on the right', () => {
    expect(mount(null, 'command')).toEqual(CMD);
    expect(mount(LL, 'command')).toEqual(row(0.6, LL, CMD));
  });
});

describe('resize', () => {
  test('moves the rail by the drag, as a share of the split', () => {
    const root = row(0.6, LL, CMD);
    const rail = layout(root, 1280, 760, false).rails[0];
    const next = resize(root, rail, -100) as Extract<RackNode, { kind: 'split' }>;
    expect(next.sizes[0]).toBeCloseTo(0.6 - 100 / rail.span);
    expect(next.sizes[0] + next.sizes[1]).toBeCloseTo(1);
  });

  test('stops at either neighbour\'s minimum', () => {
    const root = row(0.6, LL, CMD);
    const rail = layout(root, 1280, 760, false).rails[0];
    const narrow = resize(root, rail, -1000) as Extract<RackNode, { kind: 'split' }>;
    expect(narrow.sizes[0] * rail.span).toBeCloseTo(560);
    const wide = resize(root, rail, 1000) as Extract<RackNode, { kind: 'split' }>;
    expect(wide.sizes[1] * rail.span).toBeCloseTo(420);
  });
});

describe('zoneAt', () => {
  const r = { x: 0, y: 0, w: 1000, h: 800 };
  test('an edge band splits, the middle swaps', () => {
    expect(zoneAt(r, 50, 400)).toBe('left');
    expect(zoneAt(r, 950, 400)).toBe('right');
    expect(zoneAt(r, 500, 30)).toBe('top');
    expect(zoneAt(r, 500, 780)).toBe('bottom');
    expect(zoneAt(r, 500, 400)).toBe('center');
  });
});

describe('landing', () => {
  test('an empty view takes the tool whole', () => {
    expect(landing(view(null), 'command', 10, 10, 1280, 760)).toMatchObject({ ok: true, root: CMD });
  });

  test('an edge of a slot splits it, the carried tool on that side', () => {
    const got = landing(view(LL), 'command', 640, 740, 1280, 760);
    expect(got).toMatchObject({ ok: true, root: col(0.5, LL, CMD) });
  });

  test('carrying a tool already in the view moves it', () => {
    const got = landing(view(row(0.6, LL, CMD)), 'command', 300, 740, 1280, 760);
    expect(got).toMatchObject({ ok: true, root: col(0.5, LL, CMD) });
  });

  test('the middle of another tool swaps the two; the slots keep their sizes', () => {
    const got = landing(view(row(0.5, LL, CMD)), 'command', 320, 380, 1280, 760);
    expect(got).toMatchObject({ ok: true, root: row(0.5, CMD, LL) });
    // At 60/40 the swap would leave Legend Lore 508px of its 560.
    expect(landing(view(row(0.6, LL, CMD)), 'command', 380, 380, 1280, 760)).toMatchObject({ ok: false, reason: 'room' });
  });

  test('a locked view refuses drops, empty or not, and so does the tool\'s own slot', () => {
    expect(landing(view(LL, true), 'command', 640, 740, 1280, 760)).toMatchObject({ ok: false, reason: 'locked' });
    expect(landing(view(null, true), 'command', 10, 10, 1280, 760)).toMatchObject({ ok: false, reason: 'locked' });
    expect(landing(view(row(0.6, LL, CMD)), 'command', 1100, 380, 1280, 760)).toMatchObject({ ok: false, reason: 'self' });
  });

  test('a split that would leave either tool under its minimum is refused', () => {
    // Side by side in 900px, Legend Lore would get 447 of its 560.
    expect(landing(view(LL), 'command', 880, 380, 900, 760)).toMatchObject({ ok: false, reason: 'room' });
  });

  test('outside every slot is no landing at all', () => {
    expect(landing(view(row(0.6, LL, CMD)), 'command', 765, 380, 1280, 760)).toBeNull();
  });
});

describe('parseViews', () => {
  test('reads back what was saved', () => {
    const views = defaultViews();
    views[2] = view(col(0.58, CMD, LL), true);
    expect(parseViews(JSON.parse(JSON.stringify(views)))).toEqual(views);
  });

  test('anything but a list is no saved rack', () => {
    expect(parseViews(undefined)).toBeUndefined();
    expect(parseViews({ root: LL })).toBeUndefined();
  });

  test('a view that does not read back cleanly comes back empty', () => {
    const views = parseViews([
      view(row(0.5, LL, LL)), // a tool twice
      { root: { kind: 'tool', id: 'servant' }, locked: false }, // not in the rack
      { root: { kind: 'split', dir: 'row', sizes: [1], children: [LL] }, locked: false },
      { root: { kind: 'split', dir: 'row', sizes: [-1, 2], children: [LL, CMD] }, locked: false },
    ])!;
    expect(views.slice(0, 4).every((v) => v.root === null)).toBe(true);
    expect(views).toHaveLength(8);
  });

  test('the lock reads back, old per-tool locks locking the view, and sizes renormalize', () => {
    const [v, w, x] = parseViews([
      { root: { kind: 'split', dir: 'row', sizes: [3, 1], children: [LL, CMD] }, locked: ['servant', 'command'] },
      { root: LL, locked: true },
      { root: LL, locked: [] },
    ])!;
    expect(v.locked).toBe(true);
    expect(w.locked).toBe(true);
    expect(x.locked).toBe(false);
    expect((v.root as Extract<RackNode, { kind: 'split' }>).sizes).toEqual([0.75, 0.25]);
  });
});

test('first launch puts each tool on its own view, where its tab was', () => {
  expect(defaultViews().map((v) => toolsIn(v.root))).toEqual([['legend-lore'], ['command'], [], [], [], [], [], []]);
});

describe('neighbour', () => {
  const both = ['legend-lore', 'command'] as const;

  test('side by side: right and left cross, up and down find nothing', () => {
    const { rects } = layout(row(0.6, LL, CMD), 1280, 760, false);
    expect(neighbour(rects, both, 'legend-lore', 'right')).toBe('command');
    expect(neighbour(rects, both, 'command', 'left')).toBe('legend-lore');
    expect(neighbour(rects, both, 'legend-lore', 'left')).toBeNull();
    expect(neighbour(rects, both, 'command', 'right')).toBeNull();
    expect(neighbour(rects, both, 'legend-lore', 'up')).toBeNull();
    expect(neighbour(rects, both, 'legend-lore', 'down')).toBeNull();
  });

  test('stacked: down and up cross', () => {
    const { rects } = layout(col(0.5, LL, CMD), 1280, 760, false);
    expect(neighbour(rects, both, 'legend-lore', 'down')).toBe('command');
    expect(neighbour(rects, both, 'command', 'up')).toBe('legend-lore');
    expect(neighbour(rects, both, 'legend-lore', 'right')).toBeNull();
  });

  test('a tool that cannot take the keyboard is not a neighbour, nor is one with no slot', () => {
    const { rects } = layout(row(0.6, LL, CMD), 1280, 760, false);
    expect(neighbour(rects, ['legend-lore'], 'legend-lore', 'right')).toBeNull();
    expect(neighbour(rects, both, 'servant', 'right')).toBeNull();
  });
});
