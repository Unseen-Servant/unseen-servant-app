// Query-term marking for the result rows' one-line snippet and the
// inspector's section: the eye should land on the hit, not hunt for it.

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

/** A whole word starting with one of `terms`, so "sword" matches "Swords". */
function termPattern(terms: string[]): RegExp {
  // Terms are letters and digits only (queryTerms), so nothing to escape.
  return new RegExp(`(?<![\\p{L}\\p{N}])(?:${terms.join('|')})[\\p{L}\\p{N}]*`, 'giu');
}

function splitHits(text: string, re: RegExp): SnippetPart[] {
  const parts: SnippetPart[] = [];
  let last = 0;
  for (const m of text.matchAll(re)) {
    if (m.index > last) parts.push({ text: text.slice(last, m.index), hit: false });
    parts.push({ text: m[0], hit: true });
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push({ text: text.slice(last), hit: false });
  return parts;
}

/**
 * Split `text` into plain and hit parts. A hit is a whole word that
 * starts with a term, so "sword" marks "Swords" too. When the first hit
 * would fall past the visible width, the text is cut at a word boundary
 * shortly before it, behind an ellipsis.
 */
export function markSnippet(text: string, terms: string[]): SnippetPart[] {
  if (terms.length === 0) return [{ text, hit: false }];
  const re = termPattern(terms);

  let shown = text;
  const first = text.search(re);
  if (first > VISIBLE) {
    const space = text.lastIndexOf(' ', first - LEAD);
    shown = '…' + text.slice(space === -1 ? first - LEAD : space + 1);
  }

  return splitHits(shown, re);
}

/** The slice of a hast tree the marker touches. */
interface HastNode {
  type: string;
  value?: string;
  tagName?: string;
  properties?: Record<string, unknown>;
  children?: HastNode[];
}

/**
 * A rehype plugin wrapping each hit in rendered Markdown in a
 * `span.hit`. It works on the hast tree, after Markdown is parsed, so a
 * hit never splits a table row or an emphasis marker.
 */
export function rehypeMarkTerms(terms: string[]) {
  return (tree: HastNode) => {
    if (terms.length === 0) return;
    const re = termPattern(terms);
    const visit = (node: HastNode) => {
      if (!node.children) return;
      node.children = node.children.flatMap((child) => {
        if (child.type !== 'text' || !child.value) {
          visit(child);
          return [child];
        }
        return splitHits(child.value, re).map((part) =>
          part.hit
            ? {
                type: 'element',
                tagName: 'span',
                properties: { className: ['hit'] },
                children: [{ type: 'text', value: part.text }],
              }
            : { type: 'text', value: part.text }
        );
      });
    };
    visit(tree);
  };
}
