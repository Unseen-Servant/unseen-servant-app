/**
 * Dragging tree rows onto a collection.
 *
 * Two halves, and both are needed. The private MIME is the only thing a
 * `dragover` handler can actually see — the browser's protected mode makes
 * `getData()` return "" until drop — so it's what discriminates a path drag
 * from the collections panel's own row-reorder drag. The module store then
 * carries the real payload, because resolving a folder to its indexed PDFs
 * needs `indexedPaths`, which the panel doesn't have; the page resolves at
 * dragstart and stashes the result here.
 *
 * The browser clears its own type list when a drag ends, so a botched
 * `dragend` can never strand the wire-level flag.
 */

/** Lowercase on purpose: browsers lowercase custom types in `.types`. */
export const TREE_PATHS_MIME = 'application/x-legendlore-tree-paths';

export interface TreePathsPayload {
  /** Absolute paths of indexed PDFs. Never empty — an empty drag is refused at dragstart. */
  paths: string[];
  /** What the user thinks they're dragging, e.g. `Curse of Strahd (47 files)`. */
  label: string;
}

/** The bits of DataTransfer we touch, so tests can pass a stub. */
export interface DataTransferLike {
  setData(format: string, data: string): void;
  effectAllowed: string;
}

export function isTreePathsDrag(types: readonly string[] | undefined | null): boolean {
  if (!types) return false;
  for (const t of types) {
    if (t.toLowerCase() === TREE_PATHS_MIME) return true;
  }
  return false;
}

/** Stamp the wire-level marker plus a human-readable fallback. */
export function writeTreePathsTransfer(dt: DataTransferLike, payload: TreePathsPayload): void {
  dt.effectAllowed = 'copy';
  dt.setData(TREE_PATHS_MIME, String(payload.paths.length));
  dt.setData('text/plain', payload.label);
}

let current: TreePathsPayload | null = null;

export function setTreePathsPayload(payload: TreePathsPayload): void {
  current = payload;
}

export function getTreePathsPayload(): TreePathsPayload | null {
  return current;
}

export function clearTreePathsPayload(): void {
  current = null;
}
