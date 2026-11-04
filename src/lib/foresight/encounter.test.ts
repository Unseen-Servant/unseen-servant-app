import { describe, expect, test } from 'vitest';
import {
  addColumn,
  addRow,
  duplicateRow,
  enterCell,
  freeName,
  isFigures,
  moveColumn,
  moveRow,
  nextNumbered,
  removeColumn,
  removeRow,
  renameColumn,
  renameRow,
  setCell,
  step,
  toggleOut,
  type Encounter,
  type EncounterRow,
} from './encounter';

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

describe('cells', () => {
  test('a number takes −7 and +3, keeping its max, with no floor or ceiling', () => {
    expect(enterCell('12/21', '-7')).toBe('5/21');
    expect(enterCell('12/21', '−7')).toBe('5/21');
    expect(enterCell('12/21', '+3')).toBe('15/21');
    expect(enterCell('3', '-10')).toBe('-7');
    expect(enterCell('20/21', '+5')).toBe('25/21');
  });

  test('a bare number replaces the value and keeps the max; n/max sets both', () => {
    expect(enterCell('12/21', '15')).toBe('15/21');
    expect(enterCell('12/21', '8/10')).toBe('8/10');
    expect(enterCell('7', '9')).toBe('9');
  });

  test('a number entered over text or nothing becomes the cell; anything else is text', () => {
    expect(enterCell('', '-7')).toBe('-7');
    expect(enterCell('prone', '+3')).toBe('3');
    expect(enterCell('', '12 / 21')).toBe('12/21');
    expect(enterCell('12/21', 'blessed')).toBe('blessed');
    expect(enterCell('', '  1d6 fire ')).toBe('1d6 fire');
  });

  test('a column whose filled cells are all numbers reads as figures, whatever its name', () => {
    const rows = [
      { ...row('A'), cells: ['12/21', 'prone'] },
      { ...row('B'), cells: ['', ''] },
      { ...row('C'), cells: ['-3', '4'] },
    ];
    expect([isFigures(rows, 1), isFigures(rows, 2)]).toEqual([true, false]);
    expect(isFigures([row('A')], 1)).toBe(false);
  });

  test('a cell is set by row and column', () => {
    const got = setCell(enc([row('A'), row('B')], 'A'), 'B', 2, 'prone');
    expect(got.rows.map((r) => r.cells)).toEqual([['', ''], ['', 'prone']]);
  });
});

describe('rows', () => {
  test('a rename keeps the link and takes the turn with it; a taken name is numbered', () => {
    const linked = { ...row('Goblin 2'), link: 'Goblin' };
    const got = renameRow(enc([row('Kira'), linked], 'Goblin 2'), 'Goblin 2', 'Sneaky');
    expect(got.rows[1]).toMatchObject({ name: 'Sneaky', link: 'Goblin' });
    expect(got.turn).toBe('Sneaky');
    expect(renameRow(enc([row('Kira'), row('Bram')], 'Kira'), 'Bram', 'kira').rows[1].name).toBe('kira 2');
  });

  test('a copy takes the next number, its link and cells, in the fight, under the original', () => {
    const goblin = (n: number, out = false) => ({ ...row(`Goblin ${n}`, out), link: 'Goblin', cells: ['3/7', 'prone'] });
    const got = duplicateRow(enc([goblin(1), goblin(2, true), row('Kira')], 'Kira'), 'Goblin 2');
    expect(got.rows.map((r) => r.name)).toEqual(['Goblin 1', 'Goblin 2', 'Goblin 3', 'Kira']);
    expect(got.rows[2]).toEqual({ name: 'Goblin 3', link: 'Goblin', out: false, cells: ['3/7', 'prone'] });
    expect(nextNumbered('Wolf', [row('Wolf')])).toBe('Wolf 2');
    expect(nextNumbered('Wolf 2', [row('Wolf'), row('Wolf 2')])).toBe('Wolf 3');
  });

  test('removing the row whose turn it is passes the turn on', () => {
    expect(removeRow(enc([row('A'), row('B'), row('C')], 'B', 2), 'B')).toMatchObject({ turn: 'C', round: 2 });
    expect(removeRow(enc([row('A'), row('B')], 'A'), 'B').rows.map((r) => r.name)).toEqual(['A']);
    expect(removeRow(enc([row('A')], 'A'), 'A')).toMatchObject({ rows: [], turn: null });
  });

  test('a row moves before another, or to the end, and the turn stays with whoever has it', () => {
    const e = enc([row('A'), row('B'), row('C')], 'B');
    expect(moveRow(e, 'A', 3).rows.map((r) => r.name)).toEqual(['B', 'C', 'A']);
    expect(moveRow(e, 'C', 0).rows.map((r) => r.name)).toEqual(['C', 'A', 'B']);
    expect(moveRow(e, 'B', 1)).toBe(e);
    expect(moveRow(e, 'C', 0).turn).toBe('B');
  });
});

describe('columns', () => {
  const table = () => ({
    columns: ['Combatant', 'HP', 'Remarks'],
    rows: [{ ...row('A'), cells: ['12', 'prone'] }],
  });

  test('added at the end, empty', () => {
    expect(addColumn(table(), 'Stress')).toEqual({
      columns: ['Combatant', 'HP', 'Remarks', 'Stress'],
      rows: [{ ...row('A'), cells: ['12', 'prone', ''] }],
    });
  });

  test('renamed, the first too', () => {
    expect(renameColumn(table(), 0, 'Name').columns).toEqual(['Name', 'HP', 'Remarks']);
  });

  test('removed with its cells, but never the first', () => {
    expect(removeColumn(table(), 1)).toEqual({ columns: ['Combatant', 'Remarks'], rows: [{ ...row('A'), cells: ['prone'] }] });
    expect(removeColumn(table(), 0)).toEqual(table());
  });

  test('moved with its cells, the first staying first', () => {
    expect(moveColumn(table(), 2, 1)).toEqual({
      columns: ['Combatant', 'Remarks', 'HP'],
      rows: [{ ...row('A'), cells: ['prone', '12'] }],
    });
    expect(moveColumn(table(), 1, 3).columns).toEqual(['Combatant', 'Remarks', 'HP']);
    expect(moveColumn(table(), 2, 0)).toEqual(table());
  });
});
