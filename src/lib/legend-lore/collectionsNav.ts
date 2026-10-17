// Which collections-panel rows the keyboard can land on, in rendered
// order: each collection's head row, then — while it is expanded — its
// file rows. Mirrors filterRows.ts: the output order IS the j/k order,
// so it must track the template (heads in the panel's sort order,
// children in childFiles' alphabetical order).
//
// A child key is `name SEP path`. The separator is a newline: an <input>
// strips newlines, so no collection name can contain one, and no macOS
// path practically does. CSS.escape handles U+000A correctly (unlike
// U+0000, which it maps to U+FFFD and would break the panel's
// data-cp-row lookup).

export const CHILD_SEP = '\n';

export interface CollectionNavEntry {
  key: string;
  /** The collection this row belongs to — its own name for a head row. */
  name: string;
  /** The file's path, or null for the collection head row. */
  path: string | null;
}

export function childNavKey(name: string, path: string): string {
  return name + CHILD_SEP + path;
}

/** Split a focus key back into collection and (optional) file path. */
export function parseNavKey(key: string): { name: string; path: string | null } {
  const i = key.indexOf(CHILD_SEP);
  return i < 0 ? { name: key, path: null } : { name: key.slice(0, i), path: key.slice(i + 1) };
}

/** A focus key after collection `from` is renamed `to`: its head row and
 *  its file rows follow the new name; any other key stays. */
export function renameNavKey(key: string | null, from: string, to: string): string | null {
  if (key === null) return null;
  const { name, path } = parseNavKey(key);
  if (name !== from) return key;
  return path === null ? to : childNavKey(to, path);
}

export function computeCollectionNav(
  names: string[],
  expanded: Set<string>,
  childrenOf: (name: string) => string[],
): CollectionNavEntry[] {
  const out: CollectionNavEntry[] = [];
  for (const name of names) {
    out.push({ key: name, name, path: null });
    if (expanded.has(name)) {
      for (const path of childrenOf(name)) {
        out.push({ key: childNavKey(name, path), name, path });
      }
    }
  }
  return out;
}

/** Move the caret one row. Clamps rather than wrapping, and a stale key
 *  (its row vanished under the cursor) re-enters from the end the user
 *  was heading toward — the same rules as stepFilterRow. */
export function stepNavKey(
  entries: CollectionNavEntry[],
  current: string | null,
  delta: 1 | -1,
): string | null {
  if (entries.length === 0) return null;
  const idx = entries.findIndex((e) => e.key === current);
  if (idx < 0) return delta === 1 ? entries[0].key : entries[entries.length - 1].key;
  return entries[Math.min(entries.length - 1, Math.max(0, idx + delta))].key;
}
