/**
 * Locating the embed unit that actually matched inside the section the
 * sidecar returns.
 *
 * `/api/search` now returns the whole assembled section as `text` and the
 * unit that hit as `matched_text`. The inspector shows the section (that
 * is the point — context around the hit), so it has to say *which* part
 * of it matched. The unit is usually a verbatim slice of the section, but
 * not always: table rows are linearised on the way into the index, so the
 * stored text and the embed unit can diverge after a common prefix.
 */

/** How much of the unit has to line up for a non-exact hit to count. */
const PREFIX_LENGTH = 60;

const BLOCK_SEP = '\n\n';

export interface MatchedParts {
  before: string;
  match: string;
  after: string;
}

/**
 * Character range of `matchedText` within `sectionText`: the exact
 * substring when it is there, otherwise the unit's first 60 characters,
 * otherwise null (the caller then renders the section undivided).
 */
export function findMatchedRange(
  sectionText: string,
  matchedText: string
): [number, number] | null {
  if (!sectionText || !matchedText) return null;

  const exact = sectionText.indexOf(matchedText);
  if (exact !== -1) return [exact, exact + matchedText.length];

  const prefix = matchedText.slice(0, PREFIX_LENGTH);
  // A unit shorter than the prefix window has already been searched for
  // in full above, so only a real prefix can still hit.
  if (prefix.length === matchedText.length) return null;

  const at = sectionText.indexOf(prefix);
  return at === -1 ? null : [at, at + prefix.length];
}

/**
 * Split `text` into the part before the match, the match, and the part
 * after, for rendering as three separate Markdown documents.
 *
 * The range is snapped *outward* to the nearest blank-line boundaries so
 * every part is a whole set of Markdown blocks — rendering half a table
 * or half a list as its own document would produce garbage. A unit inside
 * a table (tables carry no blank lines) therefore highlights the whole
 * table, which is the honest thing to show anyway.
 *
 * `before + match + after === text` always holds.
 */
export function splitAround(text: string, range: [number, number]): MatchedParts {
  const len = text.length;
  const start = Math.min(Math.max(range[0], 0), len);
  let end = Math.min(Math.max(range[1], start), len);

  // A range ending inside the blank line after its last block would
  // otherwise search for the *next* separator and swallow the rest of
  // the section, so step back over trailing whitespace first.
  while (end > start && /\s/.test(text[end - 1])) end--;

  const sepBefore = text.lastIndexOf(BLOCK_SEP, start);
  const blockStart = sepBefore === -1 ? 0 : sepBefore + BLOCK_SEP.length;

  const sepAfter = text.indexOf(BLOCK_SEP, end);
  const blockEnd = sepAfter === -1 ? len : sepAfter;

  const from = Math.min(blockStart, blockEnd);
  return {
    before: text.slice(0, from),
    match: text.slice(from, blockEnd),
    after: text.slice(blockEnd),
  };
}
