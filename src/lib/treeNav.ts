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

/** A row has indexed material when it is a file in the index or a
 * folder with at least one indexed descendant. This is the one
 * predicate for offering S/M on a row — inline buttons, keyboard, and
 * context menu all gate on it (each ORs in its own already-engaged
 * check so stale chips stay toggleable where they were set). */
export function rowHasIndexedMaterial(
  path: string,
  isDir: boolean,
  indexedPaths: Set<string>,
  indexedFolderPaths: Set<string>,
): boolean {
  return isDir ? indexedFolderPaths.has(path) : indexedPaths.has(path);
}

/** What the library knows about a row: the index, plus the selection
 * that feeds it. Selection is part of the picture because
 * `indexedPaths` is built from up_to_date + to_update + to_remove and
 * deliberately excludes `to_add` — keying on the index alone would make
 * a row vanish the moment its box was checked, and keep every queued
 * file invisible until the run finished. */
export interface LibraryKnowledge {
  indexedPaths: Set<string>;
  indexedFolderPaths: Set<string>;
  selectedPaths: Set<string>;
  foldersWithSelections: Set<string>;
  hideUnindexed: boolean;
}

/** A row is library material when the index or the selection knows
 * about it — an indexed or queued file, or a folder with such a
 * descendant. "Hide unindexed items" drops everything else. FileTree's
 * render and the keyboard nav's row model both call this — keep them in
 * sync through it, never by copy.
 *
 * Composed from rowHasIndexedMaterial rather than unioning the two path
 * sets: a union would rebuild a multi-thousand-path Set on every
 * selection click, which the `reuseIfSame` pattern in +page.svelte
 * exists to avoid. Two O(1) lookups instead. */
export function rowHasLibraryMaterial(
  path: string,
  isDir: boolean,
  known: LibraryKnowledge,
): boolean {
  return (
    rowHasIndexedMaterial(path, isDir, known.indexedPaths, known.indexedFolderPaths) ||
    rowHasIndexedMaterial(path, isDir, known.selectedPaths, known.foldersWithSelections)
  );
}

/** A row is out of scope when it is indexed material (a file in the
 * index; a folder with at least one indexed descendant) outside the
 * resolved scope. FileTree's dim and the keyboard nav's row model both
 * call this — keep them in sync through it, never by copy. */
export function isRowOutOfScope(path: string, isDir: boolean, scope: ScopeVisibility | null): boolean {
  if (!scope || scope.scopeBrightPaths === null) return false;
  const speaks = rowHasIndexedMaterial(path, isDir, scope.indexedPaths, scope.indexedFolderPaths);
  return speaks && !scope.scopeBrightPaths.has(path);
}

/** A systems-view row is indexed by construction, so out-of-scope
 * reduces to bright-set membership (null = no narrowing engaged,
 * nothing dims). Lives beside isRowOutOfScope so every surface's dim
 * predicate stays in this one module; SystemsView's template and its
 * keyboard nav both call it, so render and nav can never drift. */
export function isIndexedRowOutOfScope(
  path: string,
  scopeBrightPaths: Set<string> | null,
): boolean {
  return scopeBrightPaths !== null && !scopeBrightPaths.has(path);
}

// Flattens the file tree into the rows the user can actually navigate to,
// respecting expansion state, the optional collection filter, the
// hidden-paths rule (descendants of a hidden ancestor stay hidden unless
// `showHidden` is on), the "Hide unindexed items" switch (rows the
// library knows nothing about are skipped when `library.hideUnindexed`
// is on), and the focus lens (out-of-scope subtrees are skipped entirely
// when `scope.hideOutOfScope` is on). Order matches the rendered DOM
// order, so consecutive rows here are visually adjacent.
export function computeVisibleRows(
  files: FileItem[],
  expandedPaths: Set<string>,
  displayPaths: Set<string> | null,
  hiddenPaths: Set<string>,
  showHidden: boolean,
  scope: ScopeVisibility | null = null,
  library: LibraryKnowledge | null = null,
): VisibleRow[] {
  const out: VisibleRow[] = [];

  function walk(item: FileItem, level: number, parentPath: string | null) {
    if (displayPaths !== null && !displayPaths.has(item.path)) return;
    const hiddenByUser = isPathOrAncestorIn(item.path, hiddenPaths);
    if (hiddenByUser && !showHidden) return;
    if (library?.hideUnindexed && !rowHasLibraryMaterial(item.path, item.is_dir, library)) return;
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
