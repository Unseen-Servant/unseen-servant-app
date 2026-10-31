import { afterEach, describe, expect, test, vi } from 'vitest';
import {
  bounds,
  bump,
  diceOf,
  drawFace,
  formatFormula,
  level,
  numberOf,
  parseFormula,
  pickFace,
  reattach,
  refigure,
  roll,
  rollOutcome,
  stepDie,
  type Term,
} from './dice';

const d = (count: number, size: number, sign: 1 | -1 = 1): Term => ({ kind: 'dice', sign, count, size });
const n = (value: number, sign: 1 | -1 = 1): Term => ({ kind: 'number', sign, value });

describe('parseFormula', () => {
  test('reads dice, a lone die and numbers, with either sign', () => {
    expect(parseFormula('3d6+1d20-2')).toEqual([d(3, 6), d(1, 20), n(2, -1)]);
    expect(parseFormula('d8 + D8')).toEqual([d(1, 8), d(1, 8)]);
    expect(parseFormula('-1d4+5')).toEqual([d(1, 4, -1), n(5)]);
  });

  test('an empty field is an empty formula', () => {
    expect(parseFormula('')).toEqual([]);
    expect(parseFormula('   ')).toEqual([]);
  });

  test('anything else does not read', () => {
    for (const text of ['3d', 'd', '+', '2d6+', '2d6 3', 'd6d6', 'x', '1.5d6', '2d6*2']) {
      expect(parseFormula(text), text).toBeNull();
    }
  });

  test('refuses past the limits', () => {
    expect(parseFormula('0d6')).toBeNull();
    expect(parseFormula('1d1')).toBeNull();
    expect(parseFormula('1d1001')).toBeNull();
    expect(parseFormula('1000')).toBeNull();
    expect(parseFormula('60d6+41d6')).toBeNull();
    expect(parseFormula('100d1000+999')).not.toBeNull();
  });
});

test('formatFormula writes every count and puts signs between terms', () => {
  expect(formatFormula([d(3, 6), d(1, 20), n(2, -1)])).toBe('3d6+1d20-2');
  expect(formatFormula([d(1, 4, -1), n(5)])).toBe('-1d4+5');
  expect(formatFormula([])).toBe('');
});

describe('a pad press and right-click', () => {
  test('a press adds to the first added term of its size, else starts one', () => {
    expect(stepDie([], 6, 1)).toEqual([d(1, 6)]);
    expect(stepDie([d(2, 6), n(3)], 6, 1)).toEqual([d(3, 6), n(3)]);
    expect(stepDie([d(1, 20)], 6, 1)).toEqual([d(1, 20), d(1, 6)]);
  });

  test('a right-click takes a die off, then past zero subtracts one', () => {
    expect(stepDie([d(3, 6)], 6, -1)).toEqual([d(2, 6)]);
    expect(stepDie([d(1, 20), d(1, 6)], 6, -1)).toEqual([d(1, 20)]);
    expect(stepDie([d(2, 12)], 6, -1)).toEqual([d(2, 12), d(1, 6, -1)]);
    expect(stepDie([d(1, 6, -1)], 6, -1)).toEqual([d(2, 6, -1)]);
  });

  test('each undoes the other', () => {
    expect(stepDie([d(1, 12), d(1, 6, -1)], 6, 1)).toEqual([d(1, 12)]);
  });

  test('stops at the dice limit, but can always take away', () => {
    expect(stepDie([d(100, 6)], 6, 1)).toBeNull();
    expect(stepDie([d(100, 6)], 6, -1)).toEqual([d(99, 6)]);
  });

  test('a pad counts the dice its size adds, less those it takes away', () => {
    expect(diceOf([d(2, 6), d(1, 6), d(1, 6, -1), d(1, 8)], 6)).toBe(2);
    expect(diceOf([d(2, 6, -1)], 6)).toBe(-2);
  });
});

describe('pigments', () => {
  const OCHRE = '#e6c667';
  const ORCHIL = '#c29ce9';
  const hope = (count = 1): Term => ({ kind: 'dice', sign: 1, count, size: 12, pigment: OCHRE });
  const fear = (count = 1): Term => ({ kind: 'dice', sign: 1, count, size: 12, pigment: ORCHIL });

  test('two pads of the same die are two terms, each counted on its own pad', () => {
    const both = stepDie(stepDie([], 12, 1, OCHRE)!, 12, 1, ORCHIL)!;
    expect(both).toEqual([hope(), fear()]);
    expect(formatFormula(both)).toBe('1d12+1d12');
    expect(diceOf(both, 12, OCHRE)).toBe(1);
    expect(diceOf(both, 12)).toBe(0);
    expect(stepDie(both, 12, 1, OCHRE)).toEqual([hope(2), fear()]);
  });

  test('typing keeps each pigment where the term still stands for the same die', () => {
    expect(reattach(parseFormula('1d12+1d12+2')!, [hope(), fear()])).toEqual([hope(), fear(), n(2)]);
    expect(reattach(parseFormula('1d12+1d8')!, [hope(), fear()])).toEqual([hope(), d(1, 8)]);
    expect(reattach(parseFormula('1d6')!, [])).toEqual([d(1, 6)]);
  });
});

test('a word die picks one of its faces', () => {
  expect(pickFace(['Rain', 'Fog', 'Storm'], () => 2)).toBe('Fog');
  expect(pickFace(['Only'])).toBe('Only');
});

test('the ±1 pad counts the numbers, and moves the last one, dropping it at zero', () => {
  expect(numberOf([n(2), d(1, 20), n(5, -1)])).toBe(-3);
  expect(numberOf([d(1, 20)])).toBe(0);
  expect(bump([d(1, 20)], 1)).toEqual([d(1, 20), n(1)]);
  expect(bump([d(1, 20)], -1)).toEqual([d(1, 20), n(1, -1)]);
  expect(bump([d(1, 20), n(4)], 1)).toEqual([d(1, 20), n(5)]);
  expect(bump([d(1, 20), n(1)], -1)).toEqual([d(1, 20)]);
  expect(bump([n(2), d(1, 20), n(1, -1)], -1)).toEqual([n(2), d(1, 20), n(2, -1)]);
  expect(bump([n(999)], 1)).toBeNull();
});

test('bounds run from every die on its low face to every die on its high one', () => {
  expect(bounds([d(3, 6), n(3)])).toEqual({ min: 6, max: 21 });
  expect(bounds([d(1, 20), d(1, 4, -1), n(2, -1)])).toEqual({ min: -5, max: 17 });
});

describe('roll', () => {
  test('totals each term with its sign and keeps the faces in order', () => {
    const faces = [3, 5, 4, 17, 2];
    const r = roll([d(3, 6), d(1, 20), d(1, 4, -1), n(2)], () => faces.shift()!);
    expect(r.faces).toEqual([[3, 5, 4], [17], [2], []]);
    expect(r.total).toBe(3 + 5 + 4 + 17 - 2 + 2);
    expect([r.min, r.max]).toEqual([2, 39]);
  });
});

describe('an edge', () => {
  test('rolls twice and keeps the higher total, or the lower', () => {
    const faces = (...f: number[]) => () => f.shift()!;
    const adv = rollOutcome([d(1, 20), n(5)], 'advantage', faces(9, 17));
    expect([adv.kept.total, adv.dropped!.total]).toEqual([22, 14]);
    const dis = rollOutcome([d(1, 20), n(5)], 'disadvantage', faces(9, 17));
    expect([dis.kept.total, dis.dropped!.total]).toEqual([14, 22]);
    expect(rollOutcome([d(1, 20)], null, faces(9)).dropped).toBeNull();
  });
});

test('refigure keeps the faces when only the numbers changed', () => {
  const faces = [4, 6, 15];
  const r = roll([d(2, 6), d(1, 20)], () => faces.shift()!);
  const after = refigure(r, [d(2, 6), d(1, 20), n(2)]);
  expect(after.faces).toEqual([[4, 6], [15], []]);
  expect(after.total).toBe(27);
  expect([after.min, after.max]).toEqual([5, 34]);
});

describe('drawFace', () => {
  afterEach(() => vi.restoreAllMocks());

  test('throws back a draw past the last whole multiple of the sides', () => {
    const words = [2 ** 32 - 1, 7];
    vi.spyOn(crypto, 'getRandomValues').mockImplementation((array) => {
      (array as Uint32Array)[0] = words.shift()!;
      return array;
    });
    expect(drawFace(6)).toBe(7 % 6 + 1);
    expect(words).toHaveLength(0);
  });

  test('stays between 1 and the sides', () => {
    for (let i = 0; i < 500; i++) {
      const face = drawFace(7);
      expect(face).toBeGreaterThanOrEqual(1);
      expect(face).toBeLessThanOrEqual(7);
    }
  });
});

test('level places the total between the bounds on ten cells', () => {
  expect(level({ total: 15, min: 6, max: 21 })).toBe(6);
  expect(level({ total: 6, min: 6, max: 21 })).toBe(0);
  expect(level({ total: 21, min: 6, max: 21 })).toBe(10);
  expect(level({ total: 4, min: 4, max: 4 })).toBe(10);
});
