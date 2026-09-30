// Collection order, shared by the panel's rows and the track-select slots.
//
// ⌘1–9 address "the Nth track as the panel shows it", so the slot list must
// be derived from the same sort the panel renders — a second copy of the
// sort would let the numbers drift from the rows they name.

export type CollectionSortKey = 'custom' | 'name' | 'size' | 'created';

interface Sortable {
  name: string;
  file_count: number;
  created_at: string;
  archived?: boolean;
}

/** Sort a copy of `list` by the panel's sort key. Custom order is the
 *  persisted name array; names it doesn't know yet (created since the last
 *  drag) sort after it, alphabetically. */
export function orderCollections<T extends Sortable>(
  list: T[],
  sortKey: CollectionSortKey,
  customOrder: string[],
): T[] {
  const out = [...list];
  if (sortKey === 'name') {
    out.sort((a, b) => a.name.localeCompare(b.name));
  } else if (sortKey === 'size') {
    out.sort((a, b) => b.file_count - a.file_count);
  } else if (sortKey === 'created') {
    out.sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
  } else {
    const idx = new Map(customOrder.map((n, i) => [n, i]));
    out.sort((a, b) => {
      const ia = idx.get(a.name) ?? Infinity;
      const ib = idx.get(b.name) ?? Infinity;
      if (ia !== ib) return ia - ib;
      return a.name.localeCompare(b.name);
    });
  }
  return out;
}

/** Names that carry a transport, in panel order. Archived tracks have no
 *  play button, so they take no slot — the slots stay stable whether or
 *  not the panel is showing its archive. Slot N is index N−1. */
export function transportNames<T extends Sortable>(
  list: T[],
  sortKey: CollectionSortKey,
  customOrder: string[],
): string[] {
  return orderCollections(list.filter((c) => !c.archived), sortKey, customOrder).map((c) => c.name);
}

/** "Play only this": the new playing set when a track is selected on its
 *  own. Selecting the track that already plays alone stops it — the same
 *  press-again-to-undo a transport button gives. */
export function playOnly(playing: Set<string>, name: string): Set<string> {
  if (playing.size === 1 && playing.has(name)) return new Set();
  return new Set([name]);
}

/** The @-menu's filter: case-insensitive substring, with names that start
 *  with the query ahead of ones that merely contain it. Order within each
 *  group is the input order (panel order). An empty query keeps everything. */
export function filterByQuery(names: string[], query: string): string[] {
  const q = query.trim().toLowerCase();
  if (!q) return names;
  const prefix: string[] = [];
  const inner: string[] = [];
  for (const n of names) {
    const i = n.toLowerCase().indexOf(q);
    if (i === 0) prefix.push(n);
    else if (i > 0) inner.push(n);
  }
  return [...prefix, ...inner];
}
