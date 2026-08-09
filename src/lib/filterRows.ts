// Which filter-console rows the keyboard can land on, in rendered order.
//
// Replaces an integer index into a live querySelectorAll('[data-fm]'): the
// systems list grows as files are indexed and whole sections appear and
// disappear with view mode, so an index means a different row from one
// render to the next. Keys are stable; indices are not.
//
// Order here IS the j/k navigation order, so it must track the template.
// The panel renders Curation, then Game systems, then the Hidden-items
// view switches (moved to the bottom in c4f4f81).

import { UNTAGGED_KEY } from './searchScope';

export type FilterRowKind = 'view' | 'curation' | 'system';

export interface FilterRow {
  key: string;
  kind: FilterRowKind;
}

export interface FilterRowsInput {
  /** Something is hidden, so the "Show hidden items" row is enabled. A
   *  disabled row never takes the cursor. */
  hasHidden: boolean;
  showCollectionFilter: boolean;
  showSystemFilter: boolean;
  systems: { name: string; count: number }[];
  /** The untagged channel renders only when this is positive. */
  untaggedCount: number;
}

export function computeFilterRows(input: FilterRowsInput): FilterRow[] {
  const rows: FilterRow[] = [];

  if (input.showCollectionFilter) {
    rows.push({ key: 'curation:collected', kind: 'curation' });
    rows.push({ key: 'curation:loose', kind: 'curation' });
  }

  if (input.showSystemFilter) {
    for (const s of input.systems) rows.push({ key: `system:${s.name}`, kind: 'system' });
    if (input.untaggedCount > 0) rows.push({ key: `system:${UNTAGGED_KEY}`, kind: 'system' });
  }

  if (input.hasHidden) rows.push({ key: 'view:showHidden', kind: 'view' });
  rows.push({ key: 'view:hideUnindexed', kind: 'view' });
  rows.push({ key: 'view:hideOutOfScope', kind: 'view' });

  return rows;
}

/** Move the cursor one row. Clamps rather than wrapping, matching the tree
 *  and collections panels. A stale key (its row vanished under the cursor)
 *  re-enters from the end the user was heading toward. */
export function stepFilterRow(
  rows: FilterRow[],
  current: string | null,
  delta: 1 | -1,
): string | null {
  if (rows.length === 0) return null;
  const idx = rows.findIndex((r) => r.key === current);
  if (idx < 0) return delta === 1 ? rows[0].key : rows[rows.length - 1].key;
  return rows[Math.min(rows.length - 1, Math.max(0, idx + delta))].key;
}
