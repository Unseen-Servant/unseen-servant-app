import type { FileItem } from './types';
import { isPathOrAncestorIn } from './selectionUtils';

export interface VisibleRow {
  path: string;
  item: FileItem;
  level: number;
  parentPath: string | null;
}

// Flattens the file tree into the rows the user can actually navigate to,
// respecting expansion state, the optional active-context filter, and the
// hidden-paths rule (descendants of a hidden ancestor stay hidden unless
// `showHidden` is on). Order matches the rendered DOM order, so consecutive
// rows here are visually adjacent.
export function computeVisibleRows(
  files: FileItem[],
  expandedPaths: Set<string>,
  displayPaths: Set<string> | null,
  hiddenPaths: Set<string>,
  showHidden: boolean,
): VisibleRow[] {
  const out: VisibleRow[] = [];

  function walk(item: FileItem, level: number, parentPath: string | null) {
    if (displayPaths !== null && !displayPaths.has(item.path)) return;
    const hiddenByUser = isPathOrAncestorIn(item.path, hiddenPaths);
    if (hiddenByUser && !showHidden) return;

    out.push({ path: item.path, item, level, parentPath });

    if (item.is_dir && expandedPaths.has(item.path) && item.children) {
      for (const child of item.children) walk(child, level + 1, item.path);
    }
  }

  for (const f of files) walk(f, 0, null);
  return out;
}

export function indexOfPath(rows: VisibleRow[], path: string | null): number {
  if (path === null) return -1;
  for (let i = 0; i < rows.length; i++) if (rows[i].path === path) return i;
  return -1;
}
