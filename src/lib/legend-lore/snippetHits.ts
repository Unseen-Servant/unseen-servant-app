// Query-term marking for the result rows' one-line snippet: the eye
// should land on the hit, not hunt for it.

/** Shorter words are mostly articles and prepositions. */
const MIN_TERM = 3;

/** Common enough in rulebook prose that lighting them marks nothing. */
const STOPWORDS = new Set([
  'the', 'and', 'for', 'with', 'from', 'that', 'this', 'into', 'are', 'was', 'not', 'you', 'your', 'its',
]);

/** A first hit past this many characters would sit beyond the row's
 * visible width, so the snippet starts near it instead. */
const VISIBLE = 48;

/** Lead-in kept before a first hit the snippet was moved to. */
const LEAD = 24;

export interface SnippetPart {
  text: string;
  hit: boolean;
}

/** The words of `query` worth marking, lowercased and deduplicated. */
export function queryTerms(query: string): string[] {
  const words = query.toLowerCase().match(/[\p{L}\p{N}]+/gu) ?? [];
  return [...new Set(words.filter((w) => w.length >= MIN_TERM && !STOPWORDS.has(w)))];
}

/**
 * Split `text` into plain and hit parts. A hit is a whole word that
 * starts with a term, so "sword" marks "Swords" too. When the first hit
 * would fall past the visible width, the text is cut at a word boundary
 * shortly before it, behind an ellipsis.
 */
export function markSnippet(text: string, terms: string[]): SnippetPart[] {
  if (terms.length === 0) return [{ text, hit: false }];
  // Terms are letters and digits only (queryTerms), so nothing to escape.
  const re = new RegExp(`(?<![\\p{L}\\p{N}])(?:${terms.join('|')})[\\p{L}\\p{N}]*`, 'giu');

  let shown = text;
  const first = text.search(re);
  if (first > VISIBLE) {
    const space = text.lastIndexOf(' ', first - LEAD);
    shown = '…' + text.slice(space === -1 ? first - LEAD : space + 1);
  }

  const parts: SnippetPart[] = [];
  let last = 0;
  for (const m of shown.matchAll(re)) {
    if (m.index > last) parts.push({ text: shown.slice(last, m.index), hit: false });
    parts.push({ text: m[0], hit: true });
    last = m.index + m[0].length;
  }
  if (last < shown.length) parts.push({ text: shown.slice(last), hit: false });
  return parts;
}
