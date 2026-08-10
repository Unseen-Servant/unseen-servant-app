// Where the caret lands when a pane owns the arrow keys but has no caret yet.
//
// That state is reachable because pane ownership and caret placement are two
// separate things: clicking a pane's chrome (masthead, sort button, empty
// space below the last row) hands it the arrows without pointing at any row,
// so nothing should be ringed until the user actually navigates.
//
// Restoring the last-focused row rather than row 0 keeps a coarse "point at
// the panel" gesture from throwing away where the user was — the same promise
// Cmd+Alt+←/→/↑/↓ already make. When that row is gone (filtered out, deleted,
// renamed) we fall back to entering from the end the user is heading away
// from, matching stepFilterRow and the tree's own clamp-don't-wrap rule.

/** Resolve the caret's entry row for a pane that has none.
 *  `keys` is the pane's rows in rendered order; `last` the remembered row;
 *  `delta` the direction of the keypress that triggered materialization. */
export function materializeKey(
  keys: string[],
  last: string | null,
  delta: 1 | -1,
): string | null {
  if (keys.length === 0) return null;
  if (last !== null && keys.includes(last)) return last;
  return delta > 0 ? keys[0] : keys[keys.length - 1];
}
