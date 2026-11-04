import { describe, expect, test } from 'vitest';
import { addRow, freeName, step, toggleOut, type Encounter, type EncounterRow } from './encounter';

function row(name: string, out = false): EncounterRow {
  return { name, link: null, out, cells: ['', ''] };
}

function enc(rows: EncounterRow[], turn: string | null, round = 1): Encounter {
  return { path: 'Encounters/Encounter 1.md', name: 'Encounter 1', hash: 'h', spent: null, round, turn, columns: ['Combatant', 'HP', 'Remarks'], rows };
}

describe('step', () => {
  const rows = [row('Goblin boss'), row('Kira'), row('Goblin 1', true), row('Bram')];

  test('passes the turn to the next row in the fight', () => {
    expect(step(enc(rows, 'Goblin boss', 2), 1)).toEqual({ turn: 'Kira', round: 2 });
    expect(step(enc(rows, 'Kira', 2), 1)).toEqual({ turn: 'Bram', round: 2 });
  });

  test('wraps past the last row and counts the round up', () => {
    expect(step(enc(rows, 'Bram', 2), 1)).toEqual({ turn: 'Goblin boss', round: 3 });
  });

  test('passes it back, wrapping before the first row and counting down, never below 1', () => {
    expect(step(enc(rows, 'Bram', 2), -1)).toEqual({ turn: 'Kira', round: 2 });
    expect(step(enc(rows, 'Goblin boss', 2), -1)).toEqual({ turn: 'Bram', round: 1 });
    expect(step(enc(rows, 'Goblin boss', 1), -1)).toEqual({ turn: 'Bram', round: 1 });
  });

  test('nothing moves with no row in the fight', () => {
    expect(step(enc([row('A', true)], 'A', 4), 1)).toEqual({ turn: 'A', round: 4 });
    expect(step(enc([], null, 4), 1)).toEqual({ turn: null, round: 4 });
  });

  test('a turn naming no row lands on the first in the fight', () => {
    expect(step(enc(rows, 'Nobody', 2), 1)).toEqual({ turn: 'Goblin boss', round: 2 });
  });
});

describe('toggleOut', () => {
  test('out on its turn, the turn passes on', () => {
    const got = toggleOut(enc([row('A'), row('B'), row('C')], 'B', 2), 'B');
    expect(got.rows.map((r) => r.out)).toEqual([false, true, false]);
    expect([got.turn, got.round]).toEqual(['C', 2]);
  });

  test('out on its turn as the last row, the round counts up', () => {
    const got = toggleOut(enc([row('A'), row('B')], 'B', 2), 'B');
    expect([got.turn, got.round]).toEqual(['A', 3]);
  });

  test('another row out leaves the turn where it is', () => {
    expect(toggleOut(enc([row('A'), row('B')], 'A'), 'B').turn).toBe('A');
  });

  test('back in when every row was out, the turn is its', () => {
    const got = toggleOut(enc([row('A', true), row('B', true)], 'A'), 'B');
    expect(got.turn).toBe('B');
    expect(toggleOut(enc([row('A'), row('B', true)], 'A'), 'B').turn).toBe('A');
  });
});

describe('adding a row', () => {
  test('a repeated name takes the next number', () => {
    const rows = [row('Goblin'), row('Goblin 2')];
    expect(freeName('Goblin', rows)).toBe('Goblin 3');
    expect(freeName('goblin', [row('Goblin')])).toBe('goblin 2');
    expect(freeName('Kira', rows)).toBe('Kira');
  });

  test('lands at the end with a cell per column, and the turn when none had it', () => {
    const got = addRow(enc([], null), 'Kira');
    expect(got.rows).toEqual([{ name: 'Kira', link: null, out: false, cells: ['', ''] }]);
    expect(got.turn).toBe('Kira');
    expect(addRow(enc([row('A')], 'A'), 'B').turn).toBe('A');
    expect(addRow(enc([row('A', true)], 'A'), 'B').turn).toBe('B');
  });
});
