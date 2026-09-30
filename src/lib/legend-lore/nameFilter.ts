// The `/` filter: the search bar narrowing the browse view by name. One
// rule for both views — a row stays if its own name holds every typed word,
// if it sits inside a folder (or, in the systems view, a group) that does,
// or if it is a folder on the way down to a match. Only the rows that match
// themselves are marked; the rest are there for context.

import type { SnippetPart } from './snippetHits';
import type { FileItem } from './types';

/** The filter's words, lowercased. Empty means nothing to narrow by. */
export function filterWords(text: string): string[] {
  return text.toLowerCase().split(/\s+/).filter(Boolean);
}

/** Whether `name` holds every word, anywhere and in any order. */
export function nameMatches(name: string, words: string[]): boolean {
  const n = name.toLowerCase();
  return words.every((w) => n.includes(w));
}

/** `name` split into plain and hit parts — every occurrence of every word
 *  marked. A name that doesn't match marks nothing: it is on screen as
 *  context, and a partial mark would say otherwise. */
export function markName(name: string, words: string[]): SnippetPart[] {
  if (words.length === 0 || !nameMatches(name, words)) return [{ text: name, hit: false }];
  const lower = name.toLowerCase();
  const hit = new Array<boolean>(name.length).fill(false);
  for (const w of words) {
    for (let i = lower.indexOf(w); i !== -1; i = lower.indexOf(w, i + 1)) hit.fill(true, i, i + w.length);
  }
  const parts: SnippetPart[] = [];
  let start = 0;
  for (let i = 1; i <= name.length; i++) {
    if (i === name.length || hit[i] !== hit[start]) {
      parts.push({ text: name.slice(start, i), hit: hit[start] });
      start = i;
    }
  }
  return parts;
}

/** markName over each segment of a `/`-separated path, separators kept. */
export function markPath(path: string, words: string[]): SnippetPart[] {
  return path.split('/').flatMap((seg, i) => [
    ...(i > 0 ? [{ text: '/', hit: false }] : []),
    ...(seg ? markName(seg, words) : []),
  ]);
}

/** Whether a library file passes by its own name or by any folder between
 *  the library root and it. */
export function pathMatches(path: string, root: string, words: string[]): boolean {
  const rel = root && path.startsWith(root + '/') ? path.slice(root.length + 1) : path;
  return rel.split('/').some((seg) => nameMatches(seg, words));
}

export interface TreeFilter {
  /** Every row the filter keeps. */
  show: Set<string>;
  /** The folders on the way down to a match, which open so it's on screen.
   *  A matching folder itself stays as the user would find it: closed. */
  open: Set<string>;
}

/** Walk the whole tree for the rows the filter keeps. */
export function filterTree(roots: FileItem[], words: string[]): TreeFilter {
  const show = new Set<string>();
  const open = new Set<string>();
  const ancestors: string[] = [];

  function keepAll(item: FileItem) {
    show.add(item.path);
    for (const c of item.children ?? []) keepAll(c);
  }

  function walk(item: FileItem) {
    if (nameMatches(item.name, words)) {
      keepAll(item);
      for (const a of ancestors) {
        show.add(a);
        open.add(a);
      }
    }
    // Keep walking inside a match: a match nested in it opens its way too.
    if (item.children) {
      ancestors.push(item.path);
      for (const c of item.children) walk(c);
      ancestors.pop();
    }
  }

  for (const r of roots) walk(r);
  return { show, open };
}
