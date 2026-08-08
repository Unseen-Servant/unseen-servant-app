import type { FileItem } from './types';
import { isPathOrAncestorIn } from './selectionUtils';

export interface VisibleRow {
  path: string;
  item: FileItem;
  level: number;
  parentPath: string | null;
}

/** Scope-visibility inputs for the focus lens. Inert by default: a
 * null scopeBrightPaths means no narrowing is engaged, so nothing is
 * out of scope. */
export interface ScopeVisibility {
  scopeBrightPaths: Set<string> | null;
  indexedFolderPaths: Set<string>;
  indexedPaths: Set<string>;
  hideOutOfScope: boolean;
}

/** A row is out of scope when it is indexed material (a file in the
 * index; a folder with at least one indexed descendant) outside the
 * resolved scope. FileTree's dim and the keyboard nav's row model both
 * call this — keep them in sync through it, never by copy. */
export function isRowOutOfScope(path: string, isDir: boolean, scope: ScopeVisibility | null): boolean {
  if (!scope || scope.scopeBrightPaths === null) return false;
  const speaks = isDir ? scope.indexedFolderPaths.has(path) : scope.indexedPaths.has(path);
  return speaks && !scope.scopeBrightPaths.has(path);
}

// Flattens the file tree into the rows the user can actually navigate to,
// respecting expansion state, the optional collection filter, the
// hidden-paths rule (descendants of a hidden ancestor stay hidden unless
// `showHidden` is on), and the focus lens (out-of-scope subtrees are
// skipped entirely when `scope.hideOutOfScope` is on). Order matches the
// rendered DOM order, so consecutive rows here are visually adjacent.
export function computeVisibleRows(
  files: FileItem[],
  expandedPaths: Set<string>,
  displayPaths: Set<string> | null,
  hiddenPaths: Set<string>,
  showHidden: boolean,
  scope: ScopeVisibility | null = null,
): VisibleRow[] {
  const out: VisibleRow[] = [];

  function walk(item: FileItem, level: number, parentPath: string | null) {
    if (displayPaths !== null && !displayPaths.has(item.path)) return;
    const hiddenByUser = isPathOrAncestorIn(item.path, hiddenPaths);
    if (hiddenByUser && !showHidden) return;
    if (scope?.hideOutOfScope && isRowOutOfScope(item.path, item.is_dir, scope)) return;

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
