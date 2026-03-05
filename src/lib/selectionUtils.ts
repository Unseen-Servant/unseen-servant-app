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
 * Check if ANY file descendant of a folder is in the selected set.
 * Returns false for folders with null children.
 */
export function hasAnyDescendantSelected(
  folder: FileItem,
  selected: Set<string>,
  filter?: Set<string>
): boolean {
  if (!folder.children) return false;

  for (const child of folder.children) {
    if (child.is_dir) {
      if (hasAnyDescendantSelected(child, selected, filter)) return true;
    } else if (!filter || filter.has(child.path)) {
      if (selected.has(child.path)) return true;
    }
  }
  return false;
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
