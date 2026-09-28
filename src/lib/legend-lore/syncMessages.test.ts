import { describe, expect, it } from 'vitest';
import { bookName, clearSummary, progressLabel, reindexSummary, syncSummary } from './syncMessages';
import type { SyncResult } from './types';

function payload(files_done: number, phase = 'add', current_file = 'Monster Manual.pdf') {
  return { files_done, total_files: 12, chunks_total: 0, current_file, phase };
}

function result(overrides: Partial<SyncResult> = {}): SyncResult {
  return {
    added: 0, removed: 0, auto_removed: 0, renamed: 0, updated: 0,
    errors: [], total_indexed: 0, chunks_total: 999,
    renames: [], auto_removed_paths: [], stale_paths: [],
    ...overrides,
  };
}

describe('progressLabel', () => {
  it('keeps the start message until the first phase arrives', () => {
    expect(progressLabel({ ...payload(0), phase: '' }, 0)).toBeNull();
  });

  it('numbers the book in hand, not the finished count', () => {
    expect(progressLabel(payload(0), 0)).toEqual({ message: 'Indexing 1 of 12', book: 'Monster Manual' });
    expect(progressLabel(payload(3), 3)?.message).toBe('Indexing 4 of 12');
  });

  it('keeps the finished book numbered on its completion tick', () => {
    expect(progressLabel(payload(4), 3)?.message).toBe('Indexing 4 of 12');
    expect(progressLabel(payload(12), 11)?.message).toBe('Indexing 12 of 12');
  });

  it('names the phase', () => {
    expect(progressLabel(payload(1, 'remove'), 0)?.message).toBe('Removing 1 of 12');
    expect(progressLabel(payload(1, 'auto_remove'), 0)?.message).toBe('Removing 1 of 12');
    expect(progressLabel(payload(1, 'rename'), 0)?.message).toBe('Renaming 1 of 12');
    expect(progressLabel(payload(0, 'update'), 0)?.message).toBe('Re-indexing 1 of 12');
  });
});

describe('bookName', () => {
  it('drops the .pdf extension only', () => {
    expect(bookName('Player.Handbook.PDF')).toBe('Player.Handbook');
    expect(bookName('notes.pdf.bak')).toBe('notes.pdf.bak');
  });
});

describe('syncSummary', () => {
  it('leads with the outcome and never mentions chunks', () => {
    expect(syncSummary(result({ added: 3, removed: 1, updated: 2 })).message)
      .toBe('Added 3 books, removed 1, updated 2');
    expect(syncSummary(result({ renamed: 1 })).message).toBe('Renamed 1 book');
  });

  it('folds disk deletions into removed and explains them in the tooltip', () => {
    const s = syncSummary(result({ removed: 1, auto_removed: 2 }));
    expect(s.message).toBe('Removed 3 books');
    expect(s.detail).toBe('2 books deleted from disk');
  });

  it('counts failures and lists them in the tooltip', () => {
    const errors = ['a.pdf: Empty or scanned PDF', 'b.pdf: timeout'];
    const s = syncSummary(result({ added: 3, errors }));
    expect(s).toEqual({
      message: 'Added 3 books · 2 failed',
      isError: true,
      detail: 'a.pdf: Empty or scanned PDF\nb.pdf: timeout',
    });
    expect(syncSummary(result({ errors: errors.slice(1) })).message).toBe('1 book failed');
  });

  it('says so when there was nothing to do', () => {
    expect(syncSummary(result())).toEqual({ message: 'Nothing to sync', isError: false, detail: undefined });
  });
});

describe('reindexSummary', () => {
  it('reports books re-indexed and failures', () => {
    expect(reindexSummary(result({ updated: 40 })).message).toBe('Re-indexed 40 books');
    expect(reindexSummary(result({ updated: 39, errors: ['x.pdf: boom'] })).message)
      .toBe('Re-indexed 39 books · 1 failed');
    expect(reindexSummary(result()).message).toBe('Nothing to re-index');
  });
});

describe('clearSummary', () => {
  it('counts books, not chunks', () => {
    expect(clearSummary({ removed_files: 1 }).message).toBe('Cleared 1 book from the index');
  });
});
