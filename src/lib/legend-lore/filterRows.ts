// Which filter-console rows the keyboard can land on, in rendered order.
//
// Replaces an integer index into a live querySelectorAll('[data-fm]'): the
// systems list grows as files are indexed and whole sections appear and
// disappear with view mode, so an index means a different row from one
// render to the next. Keys are stable; indices are not.
//
// Order here IS the j/k navigation order, so it must track the template.
// The panel renders Curation, then Game systems, then the Hidden-items
// view switches (moved to the bottom in c4f4f81). Each section's header is
// a row too, like a folder in the tree: ←/→ fold it, and it stays
// reachable while its rows are folded away.

import { UNTAGGED_KEY } from './searchScope';

export type FilterSection = 'curation' | 'system' | 'view';
export type FilterRowKind = FilterSection | 'header';

export interface FilterRow {
  key: string;
  kind: FilterRowKind;
  /** The section the row sits in; a header's own section. */
  section: FilterSection;
}

export function sectionHeaderKey(section: FilterSection): string {
  return `sect:${section}`;
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
  /** Sections folded shut in the panel. Their rows aren't rendered, so the
   *  cursor can't land on them either; the header stays. */
  collapsed?: ReadonlySet<FilterSection>;
}

export function computeFilterRows(input: FilterRowsInput): FilterRow[] {
  const rows: FilterRow[] = [];
  const open = (section: FilterSection) => !input.collapsed?.has(section);
  const header = (section: FilterSection) =>
    rows.push({ key: sectionHeaderKey(section), kind: 'header', section });
  const row = (key: string, section: FilterSection) =>
    rows.push({ key, kind: section, section });

  if (input.showCollectionFilter) {
    header('curation');
    if (open('curation')) {
      row('curation:collected', 'curation');
      row('curation:loose', 'curation');
    }
  }

  if (input.showSystemFilter) {
    header('system');
    if (open('system')) {
      for (const s of input.systems) row(`system:${s.name}`, 'system');
      if (input.untaggedCount > 0) row(`system:${UNTAGGED_KEY}`, 'system');
    }
  }

  header('view');
  if (open('view')) {
    if (input.hasHidden) row('view:showHidden', 'view');
    row('view:hideUnindexed', 'view');
    row('view:hideOutOfScope', 'view');
    row('view:hideImages', 'view');
  }

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
