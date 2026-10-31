import { expect, test } from 'vitest';
import { isLit, readoutCells, SEGMENTS } from './sevenSegment';

test('no total is three dark cells', () => {
  expect(readoutCells(null)).toEqual(['', '', '']);
});

test('a total sits right, a longer one adds cells, and minus takes a cell', () => {
  expect(readoutCells(7)).toEqual(['', '', '7']);
  expect(readoutCells(-3)).toEqual(['', '-', '3']);
  expect(readoutCells(12345)).toEqual(['1', '2', '3', '4', '5']);
});

test('each digit lights its segments', () => {
  const lit = (char: string) => SEGMENTS.filter(([s]) => isLit(char, s)).map(([s]) => s).join('');
  expect(lit('8')).toBe('abcdefg');
  expect(lit('1')).toBe('bc');
  expect(lit('7')).toBe('abc');
  expect(lit('-')).toBe('g');
  expect(lit('')).toBe('');
});
