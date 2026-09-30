import { describe, expect, test } from 'vitest';
import { filterByQuery, orderCollections, playOnly, transportNames } from './collectionOrder';

const col = (name: string, over: Partial<{ file_count: number; created_at: string; archived: boolean }> = {}) => ({
  name,
  file_count: 0,
  created_at: '2026-01-01T00:00:00Z',
  archived: false,
  ...over,
});

describe('orderCollections', () => {
  test('custom order follows the persisted array, unknown names after it alphabetically', () => {
    const list = [col('b'), col('z'), col('a'), col('c')];
    expect(orderCollections(list, 'custom', ['c', 'a']).map((c) => c.name)).toEqual(['c', 'a', 'b', 'z']);
  });

  test('size sorts largest first, created newest first', () => {
    const list = [col('a', { file_count: 1, created_at: '2026-03-01' }), col('b', { file_count: 5, created_at: '2026-01-01' })];
    expect(orderCollections(list, 'size', []).map((c) => c.name)).toEqual(['b', 'a']);
    expect(orderCollections(list, 'created', []).map((c) => c.name)).toEqual(['a', 'b']);
  });

  test('does not mutate its input', () => {
    const list = [col('b'), col('a')];
    orderCollections(list, 'name', []);
    expect(list.map((c) => c.name)).toEqual(['b', 'a']);
  });
});

describe('transportNames', () => {
  test('archived tracks take no slot', () => {
    const list = [col('a'), col('b', { archived: true }), col('c')];
    expect(transportNames(list, 'name', [])).toEqual(['a', 'c']);
  });
});

describe('playOnly', () => {
  test('replaces whatever plays with the one track', () => {
    expect([...playOnly(new Set(['a', 'b']), 'c')]).toEqual(['c']);
    expect([...playOnly(new Set(['a', 'b']), 'a')]).toEqual(['a']);
    expect([...playOnly(new Set(), 'a')]).toEqual(['a']);
  });

  test('selecting the track that already plays alone stops it', () => {
    expect(playOnly(new Set(['a']), 'a').size).toBe(0);
  });
});

describe('filterByQuery', () => {
  const names = ['Monsters', 'Dungeon Monsters', 'Spells', 'monsoon tables'];

  test('empty query keeps every name in order', () => {
    expect(filterByQuery(names, '  ')).toEqual(names);
  });

  test('prefix matches lead, then inner matches, each in input order', () => {
    expect(filterByQuery(names, 'mon')).toEqual(['Monsters', 'monsoon tables', 'Dungeon Monsters']);
  });

  test('no match is empty', () => {
    expect(filterByQuery(names, 'xyz')).toEqual([]);
  });
});
