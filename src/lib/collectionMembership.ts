import type { CollectionInfo } from './types';

/**
 * Membership of one row in a collection. Files are binary; folders
 * summarise their indexed descendants.
 */
export type MemberState = 'none' | 'some' | 'all';

/**
 * Folder paths that contain at least one member ('partial') and those
 * whose every indexed descendant is a member ('full'). Precomputed once
 * per membership change so tree rows answer with an O(1) lookup instead
 * of rescanning the index.
 */
export interface FolderMembership {
  partial: Set<string>;
  full: Set<string>;
}

export const EMPTY_FOLDER_MEMBERSHIP: FolderMembership = Object.freeze({
  partial: new Set<string>(),
  full: new Set<string>(),
});

/**
 * Everything a browsing surface needs to draw and answer the arm slot,
 * bundled so the recursive tree threads one prop instead of five.
 */
export interface ArmState {
  name: string;
  color: string | null;
  paths: Set<string>;
  folders: FolderMembership;
}

/**
 * Indexed PDFs at or under `target`. A path that is itself indexed
 * resolves to just itself; anything else is treated as a folder prefix.
 * The trailing slash matters — without it "/lib/Adv" would swallow
 * "/lib/Adventures/x.pdf".
 */
export function indexedPathsUnder(target: string, indexedPaths: Set<string>): string[] {
  if (indexedPaths.has(target)) return [target];
  const prefix = target + '/';
  return [...indexedPaths].filter((p) => p.startsWith(prefix));
}

/** Names of collections holding ANY of the target's indexed PDFs. */
export function collectionsContaining(
  target: string,
  isDir: boolean,
  collections: Record<string, CollectionInfo>,
  indexedPaths: Set<string>
): string[] {
  const targets = new Set(isDir ? indexedPathsUnder(target, indexedPaths) : [target]);
  if (targets.size === 0) return [];
  return Object.values(collections)
    .filter((c) => c.file_paths.some((p) => targets.has(p)))
    .map((c) => c.name);
}

/**
 * Names of collections holding ALL of the target's indexed PDFs. Used to
 * suppress no-op entries from the "Add to collection" submenu. For folders
 * this differs from collectionsContaining (which is "any") because partial
 * overlap still permits adding the rest.
 */
export function collectionsFullyContaining(
  target: string,
  isDir: boolean,
  collections: Record<string, CollectionInfo>,
  indexedPaths: Set<string>
): string[] {
  const targets = new Set(isDir ? indexedPathsUnder(target, indexedPaths) : [target]);
  if (targets.size === 0) return [];
  return Object.values(collections)
    .filter((c) => {
      const cFiles = new Set(c.file_paths);
      for (const t of targets) if (!cFiles.has(t)) return false;
      return true;
    })
    .map((c) => c.name);
}

/** Pick a name based on `base`, suffixing " 2", " 3" etc. on collision. */
export function uniqueCollectionName(base: string, collections: Record<string, unknown>): string {
  if (!collections[base]) return base;
  let suffix = 2;
  while (collections[`${base} ${suffix}`]) suffix++;
  return `${base} ${suffix}`;
}

/**
 * Roll file-level membership up to folders in a single pass over the
 * index. Only indexed paths vote, so a collection holding paths that a
 * sync has since dropped can never mark a folder full.
 */
export function computeFolderMembership(
  indexedPaths: Set<string>,
  memberPaths: Set<string>
): FolderMembership {
  const partial = new Set<string>();
  const withNonMember = new Set<string>();
  for (const p of indexedPaths) {
    const target = memberPaths.has(p) ? partial : withNonMember;
    let dir = p;
    while ((dir = dir.substring(0, dir.lastIndexOf('/'))) !== '') {
      if (target.has(dir)) break;
      target.add(dir);
    }
  }
  const full = new Set<string>();
  for (const dir of partial) if (!withNonMember.has(dir)) full.add(dir);
  return { partial, full };
}

/** How a tree row should draw its membership control. */
export function memberStateFor(
  path: string,
  isDir: boolean,
  memberPaths: Set<string>,
  folders: FolderMembership
): MemberState {
  if (!isDir) return memberPaths.has(path) ? 'all' : 'none';
  if (folders.full.has(path)) return 'all';
  return folders.partial.has(path) ? 'some' : 'none';
}

/**
 * Membership of a whole group of files — the systems view's per-system
 * "select all" header. An empty group reads as 'none': there is nothing
 * in it to be a member.
 */
export function groupMemberState(
  items: readonly { path: string }[],
  memberPaths: Set<string>
): MemberState {
  let members = 0;
  for (const item of items) if (memberPaths.has(item.path)) members++;
  if (members === 0) return 'none';
  return members === items.length ? 'all' : 'some';
}

/** Additive merge preserving order. Never mutates `current`. */
export function addMembers(
  current: readonly string[],
  incoming: readonly string[]
): { next: string[]; added: number } {
  const seen = new Set(current);
  const next = [...current];
  let added = 0;
  for (const p of incoming) {
    if (seen.has(p)) continue;
    seen.add(p);
    next.push(p);
    added++;
  }
  return { next, added };
}

/** Subtractive filter preserving order. Never mutates `current`. */
export function removeMembers(
  current: readonly string[],
  targets: Set<string>
): { next: string[]; removed: number } {
  const next = current.filter((p) => !targets.has(p));
  return { next, removed: current.length - next.length };
}
