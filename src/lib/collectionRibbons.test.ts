import { describe, it, expect } from 'vitest';
import { buildRibbonIndex, firstColorByPath } from './collectionRibbons';
import type { CollectionInfo } from './types';

function col(name: string, file_paths: string[], over: Partial<CollectionInfo> = {}): CollectionInfo {
  return {
    id: name,
    name,
    file_paths,
    file_count: file_paths.length,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    last_used_at: null,
    description: '',
    color: null,
    archived: false,
    ...over,
  };
}

function byName(list: CollectionInfo[]): Record<string, CollectionInfo> {
  return Object.fromEntries(list.map((c) => [c.name, c]));
}

describe('buildRibbonIndex', () => {
  it('maps a path to the collection holding it', () => {
    const index = buildRibbonIndex(byName([col('Strahd', ['/a.pdf'], { color: '#800' })]));
    expect(index.get('/a.pdf')).toEqual([{ name: 'Strahd', color: '#800' }]);
  });

  it('keeps uncolored collections with a null color', () => {
    const index = buildRibbonIndex(byName([col('Loose', ['/a.pdf'])]));
    expect(index.get('/a.pdf')).toEqual([{ name: 'Loose', color: null }]);
  });

  it('orders colored collections first, alphabetical within each group', () => {
    const index = buildRibbonIndex(
      byName([
        col('Zeta', ['/a.pdf'], { color: '#111' }),
        col('Alpha', ['/a.pdf']),
        col('Beta', ['/a.pdf'], { color: '#222' }),
        col('Yankee', ['/a.pdf']),
      ])
    );
    expect(index.get('/a.pdf')?.map((r) => r.name)).toEqual(['Beta', 'Zeta', 'Alpha', 'Yankee']);
  });

  it('excludes archived collections by default', () => {
    const index = buildRibbonIndex(byName([col('Shelved', ['/a.pdf'], { archived: true })]));
    expect(index.get('/a.pdf')).toBeUndefined();
  });

  it('includes archived collections when asked', () => {
    const index = buildRibbonIndex(byName([col('Shelved', ['/a.pdf'], { archived: true })]), {
      includeArchived: true,
    });
    expect(index.get('/a.pdf')?.map((r) => r.name)).toEqual(['Shelved']);
  });

  it('returns an empty map for no collections', () => {
    expect(buildRibbonIndex({}).size).toBe(0);
  });
});

describe('firstColorByPath', () => {
  it('takes the alphabetically-first colored collection', () => {
    const m = firstColorByPath(
      byName([
        col('Zeta', ['/a.pdf'], { color: '#zzz' }),
        col('Alpha', ['/a.pdf'], { color: '#aaa' }),
      ])
    );
    expect(m.get('/a.pdf')).toBe('#aaa');
  });

  it('skips uncolored collections rather than claiming the slot', () => {
    const m = firstColorByPath(
      byName([col('Alpha', ['/a.pdf']), col('Beta', ['/a.pdf'], { color: '#bbb' })])
    );
    expect(m.get('/a.pdf')).toBe('#bbb');
  });

  it('leaves a path uncolored when no colored collection holds it', () => {
    expect(firstColorByPath(byName([col('Alpha', ['/a.pdf'])])).has('/a.pdf')).toBe(false);
  });

  // Search-result index cells have always shown archived pigment; the
  // ribbon strip's archived exclusion must not leak into this one.
  it('counts archived collections, unlike the ribbon strip', () => {
    const m = firstColorByPath(byName([col('Shelved', ['/a.pdf'], { color: '#s', archived: true })]));
    expect(m.get('/a.pdf')).toBe('#s');
  });
});
