// Status-bar wording for sync jobs: the running label and the summaries.
//
// Counts are in books, never chunks — a sync's chunk tally mixes deleted
// and embedded rows, so it has no meaning to report.

import type { PromptCounts, SyncResult } from './types';
import type { SyncProgressPayload } from './syncJob';
import { m } from '../paraglide/messages';

export interface JobSummary {
  message: string;
  isError: boolean;
  // Tooltip text: which books failed and why, plus anything the one-line
  // message folds away.
  detail?: string;
}

type Progress = (inputs: { ordinal: number; total: number }) => string;

const VERBS: Record<string, Progress> = {
  remove: m.lore_sync_progress_removing,
  auto_remove: m.lore_sync_progress_removing,
  rename: m.lore_sync_progress_moving,
  add: m.lore_sync_progress_indexing,
  update: m.lore_sync_progress_reindexing,
};

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
    message: (VERBS[p.phase] ?? m.lore_sync_progress_syncing)({ ordinal, total: p.total_files }),
    book: bookName(p.current_file),
    meter: p.book_chunks_total > 0
      ? { done: p.book_chunks_done, total: p.book_chunks_total }
      : undefined,
  };
}

function withFailures(done: string, errors: string[], nothing: string): JobSummary {
  const failed = errors.length;
  const message = done && failed
    ? m.lore_sync_done_failed({ done, failed })
    : done || (failed ? m.lore_sync_books_failed({ count: failed }) : nothing);
  return {
    message,
    isError: failed > 0,
    detail: failed > 0 ? errors.join('\n') : undefined,
  };
}

// "Added 3 books, removed 1, updated 2 · 1 failed"
export function syncSummary(r: SyncResult): JobSummary {
  type Count = (inputs: { count: number }) => string;
  const counts: [Count, Count, number][] = [
    [m.lore_sync_added_first, m.lore_sync_added_rest, r.added],
    [m.lore_sync_removed_first, m.lore_sync_removed_rest, r.removed + r.auto_removed],
    [m.lore_sync_moved_first, m.lore_sync_moved_rest, r.renamed],
    [m.lore_sync_updated_first, m.lore_sync_updated_rest, r.updated],
  ];
  const done = counts
    .filter(([, , n]) => n > 0)
    .map(([first, rest, n], i) => (i === 0 ? first({ count: n }) : rest({ count: n })))
    .join(', ');
  const summary = withFailures(done, r.errors, m.lore_sync_nothing_to_sync());
  if (r.auto_removed > 0) {
    const note = m.lore_sync_books_missing({ count: r.auto_removed });
    summary.detail = summary.detail ? `${note}\n${summary.detail}` : note;
  }
  return summary;
}

export function reindexSummary(r: SyncResult): JobSummary {
  const done = r.updated > 0 ? m.lore_sync_reindexed({ count: r.updated }) : '';
  return withFailures(done, r.errors, m.lore_sync_nothing_to_reindex());
}

// The standing prompt before a sync: "2 moved, 1 missing on disk, 3 to add".
// Empty when there is nothing to ask about.
export function syncPromptMessage(c: PromptCounts): string {
  const parts: string[] = [];
  if (c.moved > 0) parts.push(m.lore_sync_prompt_moved({ count: c.moved }));
  if (c.missing > 0) parts.push(m.lore_sync_prompt_missing({ count: c.missing }));
  if (c.add > 0) parts.push(m.lore_sync_prompt_add({ count: c.add }));
  if (c.remove > 0) parts.push(m.lore_sync_prompt_remove({ count: c.remove }));
  if (c.update > 0) parts.push(m.lore_sync_prompt_update({ count: c.update }));
  if (c.errors > 0) parts.push(m.lore_sync_prompt_errors({ count: c.errors }));
  return parts.join(', ');
}

export function clearSummary(r: { removed_files: number }): JobSummary {
  return { message: m.lore_sync_cleared({ count: r.removed_files }), isError: false };
}
