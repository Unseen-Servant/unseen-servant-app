// Status-bar wording for sync jobs: the running label and the summaries.
//
// Counts are in books, never chunks — a sync's chunk tally mixes deleted
// and embedded rows, so it has no meaning to report.

import type { SyncResult } from './types';
import type { SyncProgressPayload } from './syncJob';

export interface JobSummary {
  message: string;
  isError: boolean;
  // Tooltip text: which books failed and why, plus anything the one-line
  // message folds away.
  detail?: string;
}

const VERBS: Record<string, string> = {
  remove: 'Removing',
  auto_remove: 'Removing',
  rename: 'Renaming',
  add: 'Indexing',
  update: 'Re-indexing',
};

function books(n: number): string {
  return `${n} book${n === 1 ? '' : 's'}`;
}

export function bookName(filename: string): string {
  return filename.replace(/\.pdf$/i, '');
}

// The sidecar sends one event as a book starts and one as it finishes; only
// the second advances files_done. Numbering the book in hand ("4 of 12")
// rather than the finished count keeps the bar from reading "0 of 12"
// through the whole first book.
export function progressLabel(
  p: SyncProgressPayload,
  prevFilesDone: number,
): { message: string; book: string; meter?: { done: number; total: number } } | null {
  if (!p.phase || p.total_files === 0) return null;
  const ordinal = p.files_done > prevFilesDone
    ? p.files_done
    : Math.min(p.files_done + 1, p.total_files);
  return {
    message: `${VERBS[p.phase] ?? 'Syncing'} ${ordinal} of ${p.total_files}`,
    book: bookName(p.current_file),
    meter: p.book_chunks_total > 0
      ? { done: p.book_chunks_done, total: p.book_chunks_total }
      : undefined,
  };
}

function withFailures(done: string, errors: string[], nothing: string): JobSummary {
  const failed = errors.length;
  const message = done && failed
    ? `${done} · ${failed} failed`
    : done || (failed ? `${books(failed)} failed` : nothing);
  return {
    message,
    isError: failed > 0,
    detail: failed > 0 ? errors.join('\n') : undefined,
  };
}

// "Added 3 books, removed 1, updated 2 · 1 failed"
export function syncSummary(r: SyncResult): JobSummary {
  const counts: [string, number][] = [
    ['Added', r.added],
    ['Removed', r.removed + r.auto_removed],
    ['Renamed', r.renamed],
    ['Updated', r.updated],
  ];
  const done = counts
    .filter(([, n]) => n > 0)
    .map(([verb, n], i) => (i === 0 ? `${verb} ${books(n)}` : `${verb.toLowerCase()} ${n}`))
    .join(', ');
  const summary = withFailures(done, r.errors, 'Nothing to sync');
  if (r.auto_removed > 0) {
    const note = `${books(r.auto_removed)} deleted from disk`;
    summary.detail = summary.detail ? `${note}\n${summary.detail}` : note;
  }
  return summary;
}

export function reindexSummary(r: SyncResult): JobSummary {
  const done = r.updated > 0 ? `Re-indexed ${books(r.updated)}` : '';
  return withFailures(done, r.errors, 'Nothing to re-index');
}

export function clearSummary(r: { removed_files: number }): JobSummary {
  return { message: `Cleared ${books(r.removed_files)} from the index`, isError: false };
}
