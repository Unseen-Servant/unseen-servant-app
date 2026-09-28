import { describe, it, expect } from 'vitest';
import { computeFilterRows, stepFilterRow, type FilterRowsInput } from './filterRows';

function input(over: Partial<FilterRowsInput> = {}): FilterRowsInput {
  return {
    hasHidden: false,
    showCollectionFilter: false,
    showSystemFilter: false,
    systems: [],
    untaggedCount: 0,
    ...over,
  };
}

describe('computeFilterRows', () => {
  it('always offers the Hidden-items header and its two unconditional rows', () => {
    expect(computeFilterRows(input()).map(r => r.key)).toEqual([
      'sect:view',
      'view:hideUnindexed',
      'view:hideOutOfScope',
    ]);
  });

  it('omits view:showHidden when nothing is hidden', () => {
    expect(computeFilterRows(input()).map(r => r.key)).not.toContain('view:showHidden');
  });

  it('includes view:showHidden when something is hidden', () => {
    expect(computeFilterRows(input({ hasHidden: true })).map(r => r.key)).toContain('view:showHidden');
  });

  it('omits curation rows when the section is hidden', () => {
    expect(computeFilterRows(input()).map(r => r.key)).not.toContain('curation:collected');
  });

  it('includes both curation rows when the section shows', () => {
    const keys = computeFilterRows(input({ showCollectionFilter: true })).map(r => r.key);
    expect(keys).toContain('curation:collected');
    expect(keys).toContain('curation:loose');
  });

  it('omits system rows when the section is hidden', () => {
    const keys = computeFilterRows(input({ systems: [{ name: 'D&D', count: 3 }] })).map(r => r.key);
    expect(keys).not.toContain('system:D&D');
  });

  it('includes one row per system when the section shows', () => {
    const keys = computeFilterRows(input({
      showSystemFilter: true,
      systems: [{ name: 'D&D', count: 3 }, { name: 'CoC', count: 1 }],
    })).map(r => r.key);
    expect(keys).toContain('system:D&D');
    expect(keys).toContain('system:CoC');
  });

  it('omits the untagged bucket when its count is zero', () => {
    const keys = computeFilterRows(input({ showSystemFilter: true })).map(r => r.key);
    expect(keys).not.toContain('system:unknown');
  });

  it('includes the untagged bucket when its count is positive', () => {
    const keys = computeFilterRows(input({ showSystemFilter: true, untaggedCount: 4 })).map(r => r.key);
    expect(keys).toContain('system:unknown');
  });

  it('orders rows Curation then Systems then View, matching the rendered panel', () => {
    const keys = computeFilterRows(input({
      hasHidden: true,
      showCollectionFilter: true,
      showSystemFilter: true,
      systems: [{ name: 'D&D', count: 3 }],
      untaggedCount: 2,
    })).map(r => r.key);
    expect(keys).toEqual([
      'sect:curation',
      'curation:collected',
      'curation:loose',
      'sect:system',
      'system:D&D',
      'system:unknown',
      'sect:view',
      'view:showHidden',
      'view:hideUnindexed',
      'view:hideOutOfScope',
    ]);
  });

  it('keeps a row key stable when another system is added — the case an index got wrong', () => {
    const before = computeFilterRows(input({ showSystemFilter: true, systems: [{ name: 'D&D', count: 3 }] }));
    const after = computeFilterRows(input({
      showSystemFilter: true,
      systems: [{ name: 'CoC', count: 1 }, { name: 'D&D', count: 3 }],
    }));
    expect(before.find(r => r.key === 'system:D&D')).toBeDefined();
    expect(after.find(r => r.key === 'system:D&D')).toBeDefined();
    // The index moved; the key did not.
    expect(before.findIndex(r => r.key === 'system:D&D'))
      .not.toBe(after.findIndex(r => r.key === 'system:D&D'));
  });

  it('skips the rows of a collapsed section but keeps its header', () => {
    const keys = computeFilterRows(input({
      hasHidden: true,
      showCollectionFilter: true,
      showSystemFilter: true,
      systems: [{ name: 'D&D', count: 3 }],
      untaggedCount: 2,
      collapsed: new Set(['system', 'view']),
    })).map(r => r.key);
    expect(keys).toEqual([
      'sect:curation',
      'curation:collected',
      'curation:loose',
      'sect:system',
      'sect:view',
    ]);
  });

  it('keeps only the headers when every section is collapsed', () => {
    expect(computeFilterRows(input({
      showCollectionFilter: true,
      showSystemFilter: true,
      systems: [{ name: 'D&D', count: 3 }],
      collapsed: new Set(['curation', 'system', 'view']),
    })).map(r => r.key)).toEqual(['sect:curation', 'sect:system', 'sect:view']);
  });

  it('tags every row with its section, headers included', () => {
    const rows = computeFilterRows(input({
      showSystemFilter: true,
      systems: [{ name: 'D&D', count: 3 }],
    }));
    expect(rows.find(r => r.key === 'sect:system')).toEqual({ key: 'sect:system', kind: 'header', section: 'system' });
    expect(rows.find(r => r.key === 'system:D&D')).toEqual({ key: 'system:D&D', kind: 'system', section: 'system' });
  });
});

describe('stepFilterRow', () => {
  const rows = computeFilterRows(input({ hasHidden: true }));
  // rows: sect:view, view:showHidden, view:hideUnindexed, view:hideOutOfScope

  it('returns null for an empty row list', () => {
    expect(stepFilterRow([], null, 1)).toBeNull();
  });

  it('enters at the first row when moving down from nothing', () => {
    expect(stepFilterRow(rows, null, 1)).toBe('sect:view');
  });

  it('enters at the last row when moving up from nothing', () => {
    expect(stepFilterRow(rows, null, -1)).toBe('view:hideOutOfScope');
  });

  it('moves down one row', () => {
    expect(stepFilterRow(rows, 'view:showHidden', 1)).toBe('view:hideUnindexed');
  });

  it('moves up one row', () => {
    expect(stepFilterRow(rows, 'view:hideUnindexed', -1)).toBe('view:showHidden');
  });

  it('clamps at the bottom rather than wrapping', () => {
    expect(stepFilterRow(rows, 'view:hideOutOfScope', 1)).toBe('view:hideOutOfScope');
  });

  it('clamps at the top rather than wrapping', () => {
    expect(stepFilterRow(rows, 'sect:view', -1)).toBe('sect:view');
  });

  it('recovers to an end row when the current key is stale', () => {
    expect(stepFilterRow(rows, 'system:vanished', 1)).toBe('sect:view');
  });
});
