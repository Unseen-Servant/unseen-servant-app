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

/** A parent chunk bigger than this share of the section isn't a
 * highlight — marking almost everything marks nothing. */
const MAX_CHUNK_SHARE = 0.8;

const BLOCK_SEP = '\n\n';

export interface MatchedParts {
  before: string;
  match: string;
  after: string;
}

/**
 * Character range of the hit within `sectionText`, in three tiers: the
 * exact `matchedText`, else its first 60 characters, else the exact
 * parent `chunkText` when one is given and it isn't most of the section,
 * else null (the caller then renders the section undivided).
 *
 * The chunk tier is what covers tables. A table row is linearised into a
 * sentence on the way into the index ("Level: 2; Damage: 2d6; Range:
 * 90 ft"), so the embed unit shares no run of characters with the
 * section's pipe markup — but the chunk it came from is still verbatim
 * section text.
 */
export function findMatchedRange(
  sectionText: string,
  matchedText: string,
  chunkText?: string
): [number, number] | null {
  if (!sectionText) return null;

  if (matchedText) {
    const exact = sectionText.indexOf(matchedText);
    if (exact !== -1) return [exact, exact + matchedText.length];

    const prefix = matchedText.slice(0, PREFIX_LENGTH);
    // A unit shorter than the prefix window has already been searched
    // for in full above, so only a real prefix can still hit.
    if (prefix.length < matchedText.length) {
      const at = sectionText.indexOf(prefix);
      if (at !== -1) return [at, at + prefix.length];
    }
  }

  if (chunkText && chunkText.length < MAX_CHUNK_SHARE * sectionText.length) {
    const at = sectionText.indexOf(chunkText);
    if (at !== -1) return [at, at + chunkText.length];
  }

  return null;
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
 *
 * Known limitation: blank lines are the only boundary, so a construct
 * that legitimately contains one — a loose list, a fenced code block —
 * can still be cut at the match.
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
