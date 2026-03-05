import { describe, it, expect } from 'vitest';
import type { FileItem } from './types';
import {
  areAllDescendantsSelected,
  hasAnyDescendantSelected,
  hasSelectableDescendants,
  computeAncestorPaths,
} from './selectionUtils';

// --- Helpers ---

function file(name: string, parentPath: string): FileItem {
  return { name, path: `${parentPath}/${name}`, is_dir: false, children: null };
}

function folder(name: string, parentPath: string, children: FileItem[] | null): FileItem {
  return { name, path: `${parentPath}/${name}`, is_dir: true, children };
}

// --- Test trees ---

// Simple flat folder: /root/A/ with 3 files
function flatFolder() {
  return folder('A', '/root', [
    file('a.pdf', '/root/A'),
    file('b.pdf', '/root/A'),
    file('c.pdf', '/root/A'),
  ]);
}

// Nested: /root/parent/ with subfolder + sibling file
//   /root/parent/sub/ with 2 files
//   /root/parent/sibling.pdf
function nestedFolder() {
  return folder('parent', '/root', [
    folder('sub', '/root/parent', [
      file('x.pdf', '/root/parent/sub'),
      file('y.pdf', '/root/parent/sub'),
    ]),
    file('sibling.pdf', '/root/parent'),
  ]);
}

// Deep: /root/L1/L2/L3/ with files at the bottom
function deepFolder() {
  return folder('L1', '/root', [
    folder('L2', '/root/L1', [
      folder('L3', '/root/L1/L2', [
        file('deep1.pdf', '/root/L1/L2/L3'),
        file('deep2.pdf', '/root/L1/L2/L3'),
      ]),
    ]),
  ]);
}

// Folder with only subdirectories (no direct files)
function dirOnlyFolder() {
  return folder('top', '/root', [
    folder('subA', '/root/top', [
      file('a1.pdf', '/root/top/subA'),
    ]),
    folder('subB', '/root/top', [
      file('b1.pdf', '/root/top/subB'),
      file('b2.pdf', '/root/top/subB'),
    ]),
  ]);
}

// =====================================================================
// areAllDescendantsSelected
// =====================================================================

describe('areAllDescendantsSelected', () => {
  it('returns false for folder with null children (unloaded)', () => {
    const f = folder('A', '/root', null);
    expect(areAllDescendantsSelected(f, new Set())).toBe(false);
  });

  it('returns false for folder with empty children array', () => {
    const f = folder('A', '/root', []);
    expect(areAllDescendantsSelected(f, new Set())).toBe(false);
  });

  it('returns false when no children are selected', () => {
    const f = flatFolder();
    expect(areAllDescendantsSelected(f, new Set())).toBe(false);
  });

  it('returns false when some children are selected', () => {
    const f = flatFolder();
    const selected = new Set(['/root/A/a.pdf']);
    expect(areAllDescendantsSelected(f, selected)).toBe(false);
  });

  it('returns true when all children are selected', () => {
    const f = flatFolder();
    const selected = new Set(['/root/A/a.pdf', '/root/A/b.pdf', '/root/A/c.pdf']);
    expect(areAllDescendantsSelected(f, selected)).toBe(true);
  });

  it('returns false when subfolder is fully selected but sibling file is not', () => {
    const f = nestedFolder();
    const selected = new Set(['/root/parent/sub/x.pdf', '/root/parent/sub/y.pdf']);
    expect(areAllDescendantsSelected(f, selected)).toBe(false);
  });

  it('returns true when all files in nested structure are selected', () => {
    const f = nestedFolder();
    const selected = new Set([
      '/root/parent/sub/x.pdf',
      '/root/parent/sub/y.pdf',
      '/root/parent/sibling.pdf',
    ]);
    expect(areAllDescendantsSelected(f, selected)).toBe(true);
  });

  it('returns true for folder with only subdirectories when all sub-files selected', () => {
    const f = dirOnlyFolder();
    const selected = new Set([
      '/root/top/subA/a1.pdf',
      '/root/top/subB/b1.pdf',
      '/root/top/subB/b2.pdf',
    ]);
    expect(areAllDescendantsSelected(f, selected)).toBe(true);
  });

  it('returns false for folder with only subdirectories when partial sub-files selected', () => {
    const f = dirOnlyFolder();
    const selected = new Set(['/root/top/subA/a1.pdf']);
    expect(areAllDescendantsSelected(f, selected)).toBe(false);
  });

  it('returns true for deeply nested tree when all leaf files selected', () => {
    const f = deepFolder();
    const selected = new Set(['/root/L1/L2/L3/deep1.pdf', '/root/L1/L2/L3/deep2.pdf']);
    expect(areAllDescendantsSelected(f, selected)).toBe(true);
  });

  it('returns false for deeply nested tree when one leaf file missing', () => {
    const f = deepFolder();
    const selected = new Set(['/root/L1/L2/L3/deep1.pdf']);
    expect(areAllDescendantsSelected(f, selected)).toBe(false);
  });

  it('returns false when subfolder has unloaded children', () => {
    const f = folder('parent', '/root', [
      folder('unloaded', '/root/parent', null),
      file('sibling.pdf', '/root/parent'),
    ]);
    const selected = new Set(['/root/parent/sibling.pdf']);
    expect(areAllDescendantsSelected(f, selected)).toBe(false);
  });
});

// =====================================================================
// areAllDescendantsSelected with filter (collection mode)
// =====================================================================

describe('areAllDescendantsSelected with filter', () => {
  it('returns true when all indexed files are selected', () => {
    const f = flatFolder();
    const filter = new Set(['/root/A/a.pdf', '/root/A/b.pdf']); // c.pdf not indexed
    const selected = new Set(['/root/A/a.pdf', '/root/A/b.pdf']);
    expect(areAllDescendantsSelected(f, selected, filter)).toBe(true);
  });

  it('returns false when some indexed files are not selected', () => {
    const f = flatFolder();
    const filter = new Set(['/root/A/a.pdf', '/root/A/b.pdf']);
    const selected = new Set(['/root/A/a.pdf']);
    expect(areAllDescendantsSelected(f, selected, filter)).toBe(false);
  });

  it('returns true (vacuously) when no files match the filter', () => {
    const f = flatFolder();
    const filter = new Set<string>(); // nothing indexed
    expect(areAllDescendantsSelected(f, new Set(), filter)).toBe(true);
  });

  it('handles nested folders with filter correctly', () => {
    const f = nestedFolder();
    const filter = new Set(['/root/parent/sub/x.pdf', '/root/parent/sibling.pdf']);
    const selected = new Set(['/root/parent/sub/x.pdf', '/root/parent/sibling.pdf']);
    expect(areAllDescendantsSelected(f, selected, filter)).toBe(true);
  });
});

// =====================================================================
// hasAnyDescendantSelected
// =====================================================================

describe('hasAnyDescendantSelected', () => {
  it('returns false when no descendants are selected', () => {
    const f = flatFolder();
    expect(hasAnyDescendantSelected(f, new Set())).toBe(false);
  });

  it('returns true when one file in nested subfolder is selected', () => {
    const f = nestedFolder();
    const selected = new Set(['/root/parent/sub/x.pdf']);
    expect(hasAnyDescendantSelected(f, selected)).toBe(true);
  });

  it('returns true when all descendants are selected', () => {
    const f = flatFolder();
    const selected = new Set(['/root/A/a.pdf', '/root/A/b.pdf', '/root/A/c.pdf']);
    expect(hasAnyDescendantSelected(f, selected)).toBe(true);
  });

  it('returns false for folder with null children', () => {
    const f = folder('A', '/root', null);
    expect(hasAnyDescendantSelected(f, new Set(['/root/A/a.pdf']))).toBe(false);
  });

  it('respects filter in collection mode', () => {
    const f = flatFolder();
    const filter = new Set(['/root/A/b.pdf']);
    const selected = new Set(['/root/A/a.pdf']); // a.pdf selected but not in filter
    expect(hasAnyDescendantSelected(f, selected, filter)).toBe(false);
  });
});

// =====================================================================
// hasSelectableDescendants
// =====================================================================

describe('hasSelectableDescendants', () => {
  it('returns true for folder with files and no filter', () => {
    const f = flatFolder();
    expect(hasSelectableDescendants(f)).toBe(true);
  });

  it('returns false for folder with files when none match filter', () => {
    const f = flatFolder();
    expect(hasSelectableDescendants(f, new Set())).toBe(false);
  });

  it('returns false for folder with only empty subfolders', () => {
    const f = folder('top', '/root', [
      folder('emptyA', '/root/top', []),
      folder('emptyB', '/root/top', []),
    ]);
    expect(hasSelectableDescendants(f)).toBe(false);
  });

  it('returns false for folder with null children', () => {
    const f = folder('A', '/root', null);
    expect(hasSelectableDescendants(f)).toBe(false);
  });

  it('returns true for deeply nested folder with files', () => {
    const f = deepFolder();
    expect(hasSelectableDescendants(f)).toBe(true);
  });
});

// =====================================================================
// computeAncestorPaths
// =====================================================================

describe('computeAncestorPaths', () => {
  it('returns correct ancestors for a single file', () => {
    const result = computeAncestorPaths(new Set(['/a/b/c.pdf']));
    expect(result).toEqual(new Set(['/a/b', '/a']));
  });

  it('returns no duplicates for two files in the same folder', () => {
    const result = computeAncestorPaths(new Set(['/a/b/c.pdf', '/a/b/d.pdf']));
    expect(result).toEqual(new Set(['/a/b', '/a']));
  });

  it('returns union of ancestors for files in different branches', () => {
    const result = computeAncestorPaths(new Set(['/a/b/c.pdf', '/a/x/y.pdf']));
    expect(result).toEqual(new Set(['/a/b', '/a/x', '/a']));
  });

  it('returns empty set for empty input', () => {
    const result = computeAncestorPaths(new Set());
    expect(result).toEqual(new Set());
  });
});

// =====================================================================
// Composite state derivation (simulating FileTree reactive logic)
// =====================================================================

describe('composite checkbox state', () => {
  function deriveState(item: FileItem, selectedPaths: Set<string>) {
    const hasAny = item.is_dir && (
      item.children !== null
        ? hasAnyDescendantSelected(item, selectedPaths)
        : computeAncestorPaths(selectedPaths).has(item.path)
    );
    const isFullySelected = item.is_dir && item.children !== null &&
      areAllDescendantsSelected(item, selectedPaths);
    const isChecked = item.is_dir ? isFullySelected : selectedPaths.has(item.path);
    const isIndeterminate = item.is_dir && hasAny && !isFullySelected;
    return { isChecked, isIndeterminate };
  }

  it('folder with no selections → unchecked, not indeterminate', () => {
    const f = flatFolder();
    const { isChecked, isIndeterminate } = deriveState(f, new Set());
    expect(isChecked).toBe(false);
    expect(isIndeterminate).toBe(false);
  });

  it('folder with partial selections → unchecked, indeterminate', () => {
    const f = flatFolder();
    const { isChecked, isIndeterminate } = deriveState(f, new Set(['/root/A/a.pdf']));
    expect(isChecked).toBe(false);
    expect(isIndeterminate).toBe(true);
  });

  it('folder with all selected → checked, not indeterminate', () => {
    const f = flatFolder();
    const selected = new Set(['/root/A/a.pdf', '/root/A/b.pdf', '/root/A/c.pdf']);
    const { isChecked, isIndeterminate } = deriveState(f, selected);
    expect(isChecked).toBe(true);
    expect(isIndeterminate).toBe(false);
  });

  it('file selected → checked', () => {
    const f = file('a.pdf', '/root');
    const { isChecked, isIndeterminate } = deriveState(f, new Set(['/root/a.pdf']));
    expect(isChecked).toBe(true);
    expect(isIndeterminate).toBe(false);
  });

  it('file not selected → unchecked', () => {
    const f = file('a.pdf', '/root');
    const { isChecked, isIndeterminate } = deriveState(f, new Set());
    expect(isChecked).toBe(false);
    expect(isIndeterminate).toBe(false);
  });
});
