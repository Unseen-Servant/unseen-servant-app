import type { CollectionInfo } from './types';

/** One collection a file belongs to, as drawn in a tree row's ribbon strip. */
export interface Ribbon {
  name: string;
  color: string | null;
}

/** Shared empty result so the many uncollected rows never allocate. */
export const EMPTY_RIBBONS: readonly Ribbon[] = Object.freeze([]);

/**
 * File path → the collections holding it, colored ones first so the two
 * ribbon slots a row can spend go to the collections that can actually be
 * told apart. Alphabetical within each group, which keeps the strip stable
 * as unrelated collections come and go.
 *
 * Archived collections are shelved, so they stay out unless asked for.
 */
export function buildRibbonIndex(
  collections: Record<string, CollectionInfo>,
  opts: { includeArchived?: boolean } = {}
): Map<string, Ribbon[]> {
  const includeArchived = opts.includeArchived ?? false;
  const list = Object.values(collections)
    .filter((c) => includeArchived || !c.archived)
    .sort((a, b) => {
      const ca = a.color ? 0 : 1;
      const cb = b.color ? 0 : 1;
      if (ca !== cb) return ca - cb;
      return a.name.localeCompare(b.name);
    });

  const index = new Map<string, Ribbon[]>();
  for (const col of list) {
    // One object per collection, shared across its paths — read-only.
    const ribbon: Ribbon = { name: col.name, color: col.color };
    for (const p of col.file_paths) {
      const existing = index.get(p);
      if (existing) existing.push(ribbon);
      else index.set(p, [ribbon]);
    }
  }
  return index;
}

/**
 * Split a row's ribbons into the ones that get drawn and a count for the
 * rest. Only colored collections earn a slot — an outline ribbon says
 * nothing a second outline ribbon doesn't — but every membership is
 * accounted for in the overflow, so nothing is silently invisible.
 *
 * Relies on buildRibbonIndex's colored-first ordering, so the scan can
 * stop at the first uncolored entry.
 */
export function splitRibbons(
  ribbons: readonly Ribbon[],
  max = 2
): { shown: readonly Ribbon[]; overflow: number } {
  if (ribbons.length === 0) return { shown: EMPTY_RIBBONS, overflow: 0 };
  const shown: Ribbon[] = [];
  for (const r of ribbons) {
    if (!r.color || shown.length === max) break;
    shown.push(r);
  }
  return { shown, overflow: ribbons.length - shown.length };
}

/**
 * File path → collection pigment for the search-result index cells.
 * Color is reserved for collections; a file in several colored
 * collections takes the alphabetically-first one for determinism.
 */
export function firstColorByPath(collections: Record<string, CollectionInfo>): Map<string, string> {
  const m = new Map<string, string>();
  const sorted = Object.values(collections).sort((a, b) => a.name.localeCompare(b.name));
  for (const col of sorted) {
    if (!col.color) continue;
    for (const p of col.file_paths) {
      if (!m.has(p)) m.set(p, col.color);
    }
  }
  return m;
}
