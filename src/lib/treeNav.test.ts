import { describe, it, expect } from 'vitest';
import type { FileItem } from './types';
import { computeVisibleRows, indexOfPath, isRowOutOfScope, rowHasIndexedMaterial, type ScopeVisibility } from './treeNav';

// --- Helpers (mirroring selectionUtils.test.ts style) ---

function file(name: string, parentPath: string): FileItem {
  return { name, path: `${parentPath}/${name}`, is_dir: false, children: null };
}

function folder(name: string, parentPath: string, children: FileItem[] | null): FileItem {
  return { name, path: `${parentPath}/${name}`, is_dir: true, children };
}

// --- Test trees ---

// /root/A/ with 3 files
function flatTree(): FileItem[] {
  return [
    folder('A', '/root', [
      file('a.pdf', '/root/A'),
      file('b.pdf', '/root/A'),
      file('c.pdf', '/root/A'),
    ]),
  ];
}

// /root/parent/ with /sub/ (2 files) + sibling.pdf
function nestedTree(): FileItem[] {
  return [
    folder('parent', '/root', [
      folder('sub', '/root/parent', [
        file('x.pdf', '/root/parent/sub'),
        file('y.pdf', '/root/parent/sub'),
      ]),
      file('sibling.pdf', '/root/parent'),
    ]),
  ];
}

// --- computeVisibleRows ---

describe('computeVisibleRows', () => {
  it('returns empty for empty input', () => {
    const rows = computeVisibleRows([], new Set(), null, new Set(), false);
    expect(rows).toEqual([]);
  });

  it('returns top-level rows only when nothing is expanded', () => {
    const rows = computeVisibleRows(flatTree(), new Set(), null, new Set(), false);
    expect(rows).toHaveLength(1);
    expect(rows[0].path).toBe('/root/A');
    expect(rows[0].level).toBe(0);
    expect(rows[0].parentPath).toBeNull();
  });

  it('descends into expanded folders in DOM order', () => {
    const rows = computeVisibleRows(flatTree(), new Set(['/root/A']), null, new Set(), false);
    expect(rows.map(r => r.path)).toEqual([
      '/root/A',
      '/root/A/a.pdf',
      '/root/A/b.pdf',
      '/root/A/c.pdf',
    ]);
    expect(rows[1].level).toBe(1);
    expect(rows[1].parentPath).toBe('/root/A');
  });

  it('respects nested expansion state', () => {
    const expanded = new Set(['/root/parent', '/root/parent/sub']);
    const rows = computeVisibleRows(nestedTree(), expanded, null, new Set(), false);
    expect(rows.map(r => r.path)).toEqual([
      '/root/parent',
      '/root/parent/sub',
      '/root/parent/sub/x.pdf',
      '/root/parent/sub/y.pdf',
      '/root/parent/sibling.pdf',
    ]);
    expect(rows[2].level).toBe(2);
    expect(rows[2].parentPath).toBe('/root/parent/sub');
  });

  it('skips children of expanded folders that are still loading', () => {
    // /root/lazy is expanded but children: null (lazy load not yet completed).
    // The row should still appear; nothing nested is added.
    const tree: FileItem[] = [folder('lazy', '/root', null)];
    const rows = computeVisibleRows(tree, new Set(['/root/lazy']), null, new Set(), false);
    expect(rows).toHaveLength(1);
    expect(rows[0].path).toBe('/root/lazy');
  });

  it('does not descend into a collapsed folder even if children are loaded', () => {
    const rows = computeVisibleRows(flatTree(), new Set(), null, new Set(), false);
    expect(rows).toHaveLength(1);
  });

  describe('displayPaths filter', () => {
    it('shows everything when null', () => {
      const rows = computeVisibleRows(flatTree(), new Set(['/root/A']), null, new Set(), false);
      expect(rows).toHaveLength(4);
    });

    it('omits paths not in the set', () => {
      const display = new Set(['/root/A', '/root/A/a.pdf']);
      const rows = computeVisibleRows(flatTree(), new Set(['/root/A']), display, new Set(), false);
      expect(rows.map(r => r.path)).toEqual(['/root/A', '/root/A/a.pdf']);
    });

    it('returns empty when no displayed paths match', () => {
      const display = new Set(['/some/other/path']);
      const rows = computeVisibleRows(flatTree(), new Set(['/root/A']), display, new Set(), false);
      expect(rows).toEqual([]);
    });
  });

  describe('hidden paths', () => {
    it('hides directly-hidden rows when showHidden is off', () => {
      const hidden = new Set(['/root/A']);
      const rows = computeVisibleRows(flatTree(), new Set(['/root/A']), null, hidden, false);
      expect(rows).toEqual([]);
    });

    it('shows directly-hidden rows when showHidden is on', () => {
      const hidden = new Set(['/root/A']);
      const rows = computeVisibleRows(flatTree(), new Set(['/root/A']), null, hidden, true);
      expect(rows).toHaveLength(4);
    });

    it('hides descendants of a hidden folder when showHidden is off', () => {
      const hidden = new Set(['/root/parent']);
      const rows = computeVisibleRows(nestedTree(), new Set(['/root/parent']), null, hidden, false);
      expect(rows).toEqual([]);
    });

    it('shows descendants of a hidden folder when showHidden is on', () => {
      const hidden = new Set(['/root/parent']);
      const expanded = new Set(['/root/parent', '/root/parent/sub']);
      const rows = computeVisibleRows(nestedTree(), expanded, null, hidden, true);
      expect(rows).toHaveLength(5);
    });

    it('treats inherited hidden the same as direct hidden under the gate', () => {
      // /root/parent/sub is hidden via /root/parent (inherited).
      const hidden = new Set(['/root/parent']);
      const expanded = new Set(['/root/parent', '/root/parent/sub']);
      // showHidden off → both /sub and its files vanish along with /parent.
      const rowsOff = computeVisibleRows(nestedTree(), expanded, null, hidden, false);
      expect(rowsOff).toEqual([]);
      // showHidden on → /sub and its files reappear (still inherited-hidden,
      // but visible because the user opted in).
      const rowsOn = computeVisibleRows(nestedTree(), expanded, null, hidden, true);
      expect(rowsOn.map(r => r.path)).toContain('/root/parent/sub/x.pdf');
    });
  });

  describe('focus lens (scope)', () => {
    // /root/parent/sub holds the only indexed files and is out of scope;
    // /root/parent and /root/parent/sibling.pdf are not indexed material
    // and so never dim/hide regardless of scope.
    function scope(hideOutOfScope: boolean): ScopeVisibility {
      return {
        scopeBrightPaths: new Set(['/root/parent', '/root/parent/sibling.pdf']),
        indexedFolderPaths: new Set(['/root/parent/sub']),
        indexedPaths: new Set(['/root/parent/sub/x.pdf', '/root/parent/sub/y.pdf']),
        hideOutOfScope,
      };
    }

    it('skips an out-of-scope folder subtree entirely when hideOutOfScope is true', () => {
      const expanded = new Set(['/root/parent', '/root/parent/sub']);
      const rows = computeVisibleRows(nestedTree(), expanded, null, new Set(), false, scope(true));
      expect(rows.map(r => r.path)).toEqual([
        '/root/parent',
        '/root/parent/sibling.pdf',
      ]);
    });

    it('keeps an out-of-scope folder subtree visible when hideOutOfScope is false', () => {
      const expanded = new Set(['/root/parent', '/root/parent/sub']);
      const rows = computeVisibleRows(nestedTree(), expanded, null, new Set(), false, scope(false));
      expect(rows.map(r => r.path)).toEqual([
        '/root/parent',
        '/root/parent/sub',
        '/root/parent/sub/x.pdf',
        '/root/parent/sub/y.pdf',
        '/root/parent/sibling.pdf',
      ]);
    });
  });
});

// --- rowHasIndexedMaterial ---

describe('rowHasIndexedMaterial', () => {
  const indexedPaths = new Set(['/root/A/a.pdf']);
  const indexedFolderPaths = new Set(['/root', '/root/A']);

  it('is true for an indexed file', () => {
    expect(rowHasIndexedMaterial('/root/A/a.pdf', false, indexedPaths, indexedFolderPaths)).toBe(true);
  });

  it('is false for an unindexed file', () => {
    expect(rowHasIndexedMaterial('/root/A/notes.txt', false, indexedPaths, indexedFolderPaths)).toBe(false);
  });

  it('is true for a folder with an indexed descendant', () => {
    expect(rowHasIndexedMaterial('/root/A', true, indexedPaths, indexedFolderPaths)).toBe(true);
  });

  it('is false for a folder with no indexed descendants', () => {
    expect(rowHasIndexedMaterial('/root/junk', true, indexedPaths, indexedFolderPaths)).toBe(false);
  });
});

// --- isRowOutOfScope ---

describe('isRowOutOfScope', () => {
  const baseScope: ScopeVisibility = {
    scopeBrightPaths: new Set(['/root/A']),
    indexedFolderPaths: new Set(['/root/B']),
    indexedPaths: new Set(['/root/A/a.pdf']),
    hideOutOfScope: false,
  };

  it('is true for an indexed file outside the resolved scope', () => {
    expect(isRowOutOfScope('/root/A/a.pdf', false, { ...baseScope, scopeBrightPaths: new Set() })).toBe(true);
  });

  it('is false for an unindexed file', () => {
    expect(isRowOutOfScope('/root/A/unindexed.pdf', false, { ...baseScope, scopeBrightPaths: new Set() })).toBe(false);
  });

  it('is true for a folder with indexed descendants when none are in scope', () => {
    expect(isRowOutOfScope('/root/B', true, baseScope)).toBe(true);
  });

  it('is false for a folder with no indexed descendants', () => {
    expect(isRowOutOfScope('/root/C', true, baseScope)).toBe(false);
  });

  it('is false when scopeBrightPaths is null (no narrowing engaged)', () => {
    expect(isRowOutOfScope('/root/B', true, { ...baseScope, scopeBrightPaths: null })).toBe(false);
  });

  it('is false when scope itself is null', () => {
    expect(isRowOutOfScope('/root/B', true, null)).toBe(false);
  });
});

// --- indexOfPath ---

describe('indexOfPath', () => {
  const rows = [
    { path: '/a', item: file('a', '/'), level: 0, parentPath: null },
    { path: '/b', item: file('b', '/'), level: 0, parentPath: null },
    { path: '/c', item: file('c', '/'), level: 0, parentPath: null },
  ];

  it('returns -1 for null path', () => {
    expect(indexOfPath(rows, null)).toBe(-1);
  });

  it('returns -1 for unknown path', () => {
    expect(indexOfPath(rows, '/nope')).toBe(-1);
  });

  it('returns -1 for empty rows', () => {
    expect(indexOfPath([], '/a')).toBe(-1);
  });

  it('finds first, middle, and last entries', () => {
    expect(indexOfPath(rows, '/a')).toBe(0);
    expect(indexOfPath(rows, '/b')).toBe(1);
    expect(indexOfPath(rows, '/c')).toBe(2);
  });
});
