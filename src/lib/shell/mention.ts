// `@` mentions in the search bar: a word that starts with @ names a
// collection to play rather than text to search. The bar strips every such
// word before a query leaves it, so a half-typed `@mon` never reaches the
// sidecar and a picked one leaves the query exactly as it was.

export interface Mention {
  /** Index of the `@`. */
  start: number;
  /** One past the token's last character. */
  end: number;
  /** What follows the `@` — the filter text. */
  query: string;
}

const isSpace = (ch: string | undefined) => ch !== undefined && /\s/.test(ch);

/** The @-word the caret sits in (or at the end of), or null. */
export function mentionAt(value: string, caret: number): Mention | null {
  let start = caret;
  while (start > 0 && !isSpace(value[start - 1])) start--;
  if (value[start] !== '@') return null;
  let end = caret;
  while (end < value.length && !isSpace(value[end])) end++;
  return { start, end, query: value.slice(start + 1, end) };
}

/** Remove a mention along with one of the spaces around it, so the words
 *  either side don't run together or double up. */
export function removeMention(value: string, m: Mention): { value: string; caret: number } {
  const before = value.slice(0, m.start);
  let after = value.slice(m.end);
  if (after.startsWith(' ') && (before === '' || before.endsWith(' '))) after = after.slice(1);
  return { value: before + after, caret: before.length };
}

/** The query with every @-word taken out — what the bar searches for. */
export function stripMentions(value: string): string {
  let out = value;
  for (let i = 0; i < out.length; i++) {
    if (out[i] === '@' && (i === 0 || isSpace(out[i - 1]))) {
      const m = mentionAt(out, i);
      if (m) {
        out = removeMention(out, m).value;
        i = m.start - 1;
      }
    }
  }
  return out;
}
