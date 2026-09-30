import type { FileItem } from './types';

/**
 * Check if ALL file descendants of a folder are in the selected set.
 * Returns false for folders with null or empty children.
 * When filter is provided, only considers files present in the filter set
 * (used for collection mode where only indexed files are selectable).
 */
export function areAllDescendantsSelected(
  folder: FileItem,
  selected: Set<string>,
  filter?: Set<string>
): boolean {
  if (!folder.children || folder.children.length === 0) return false;

  for (const child of folder.children) {
    if (child.is_dir) {
      if (!areAllDescendantsSelected(child, selected, filter)) return false;
    } else if (!filter || filter.has(child.path)) {
      if (!selected.has(child.path)) return false;
    }
  }
  return true;
}

/**
 * Check if a folder has any selectable file descendants.
 * When filter is provided, only files in the filter count.
 */
export function hasSelectableDescendants(
  folder: FileItem,
  filter?: Set<string>
): boolean {
  if (!folder.children) return false;

  for (const child of folder.children) {
    if (child.is_dir) {
      if (hasSelectableDescendants(child, filter)) return true;
    } else if (!filter || filter.has(child.path)) {
      return true;
    }
  }
  return false;
}

/**
 * Compute the set of ancestor folder paths for a given set of file paths.
 * Used to determine which folders "contain" selected items.
 */
export function computeAncestorPaths(paths: Set<string>): Set<string> {
  const ancestors = new Set<string>();
  for (const p of paths) {
    let dir = p;
    while ((dir = dir.substring(0, dir.lastIndexOf('/'))) !== '') {
      if (ancestors.has(dir)) break;
      ancestors.add(dir);
    }
  }
  return ancestors;
}

/**
 * Returns true if `path` itself is in `roots`, or any ancestor folder is.
 * Used for inheritance-style flags (e.g. hidden) where flagging a folder
 * implicitly flags its descendants.
 */
export function isPathOrAncestorIn(path: string, roots: Set<string>): boolean {
  if (roots.size === 0) return false;
  if (roots.has(path)) return true;
  let dir = path;
  while ((dir = dir.substring(0, dir.lastIndexOf('/'))) !== '') {
    if (roots.has(dir)) return true;
  }
  return false;
}

/**
 * A FileTree row's indexing checkbox. A file is checked when selected. A
 * folder is checked only when its loaded children are all selected, and
 * indeterminate when something below it is selected but not all of it —
 * `foldersWithSelections` (computeAncestorPaths of the selection) answers
 * that in O(1), even for a folder whose children aren't loaded.
 */
export function checkboxState(
  item: FileItem,
  selectedPaths: Set<string>,
  foldersWithSelections: Set<string>,
): { isChecked: boolean; isIndeterminate: boolean } {
  if (!item.is_dir) return { isChecked: selectedPaths.has(item.path), isIndeterminate: false };
  const isFullySelected = item.children !== null && areAllDescendantsSelected(item, selectedPaths);
  return {
    isChecked: isFullySelected,
    isIndeterminate: foldersWithSelections.has(item.path) && !isFullySelected,
  };
}
