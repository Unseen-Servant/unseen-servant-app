import { describe, it, expect } from 'vitest';
import { createCommitScheduler, mergeArmedCollection, type CommitOptions } from './collectionCommit';
import type { CollectionInfo } from './types';

/** Let queued promise callbacks run. Real timers; only the scheduler's clock is faked. */
const settle = () => new Promise<void>((r) => setTimeout(r, 0));

/**
 * A hand-cranked clock. Deterministic in a way fake global timers are not
 * once promises are in the mix — every advance drains due timers in order
 * and lets their microtasks finish before moving on.
 */
function makeClock() {
  let t = 0;
  let seq = 0;
  const timers = new Map<number, { at: number; fn: () => void }>();
  return {
    injected: {
      now: () => t,
      setTimer: (fn: () => void, ms: number) => {
        const id = ++seq;
        timers.set(id, { at: t + ms, fn });
        return id;
      },
      clearTimer: (h: unknown) => {
        timers.delete(h as number);
      },
    },
    async advance(ms: number) {
      const target = t + ms;
      for (;;) {
        let dueId = -1;
        let dueAt = Infinity;
        for (const [id, e] of timers) {
          if (e.at <= target && e.at < dueAt) {
            dueAt = e.at;
            dueId = id;
          }
        }
        if (dueId === -1) break;
        const entry = timers.get(dueId)!;
        timers.delete(dueId);
        t = entry.at;
        entry.fn();
        await settle();
      }
      t = target;
      await settle();
    },
  };
}

function harness(over: Partial<CommitOptions> = {}) {
  const clock = makeClock();
  const writes: { name: string; paths: string[] }[] = [];
  const errors: { name: string; err: unknown }[] = [];
  const scheduler = createCommitScheduler({
    write: async (name, paths) => {
      writes.push({ name, paths });
    },
    onError: (name, err) => {
      errors.push({ name, err });
    },
    ...clock.injected,
    ...over,
  });
  return { clock, writes, errors, scheduler };
}

describe('createCommitScheduler — coalescing', () => {
  it('collapses a burst into one write carrying the last payload', async () => {
    const { clock, writes, scheduler } = harness();
    for (let i = 1; i <= 5; i++) {
      scheduler.schedule('A', [`/${i}.pdf`]);
      await clock.advance(100);
    }
    await clock.advance(600);
    expect(writes).toEqual([{ name: 'A', paths: ['/5.pdf'] }]);
  });

  it('does not write before the quiet period elapses', async () => {
    const { clock, writes, scheduler } = harness();
    scheduler.schedule('A', ['/a.pdf']);
    await clock.advance(500);
    expect(writes).toHaveLength(0);
    await clock.advance(200);
    expect(writes).toHaveLength(1);
  });

  it('still persists during a sweep that never goes quiet (max wait)', async () => {
    const { clock, writes, scheduler } = harness();
    for (let i = 0; i < 50; i++) {
      scheduler.schedule('A', [`/${i}.pdf`]);
      await clock.advance(100);
    }
    expect(writes.length).toBeGreaterThanOrEqual(1);
  });

  it('reports itself idle once everything has settled', async () => {
    const { clock, scheduler } = harness();
    scheduler.schedule('A', ['/a.pdf']);
    expect(scheduler.pending()).toBe(true);
    await clock.advance(700);
    expect(scheduler.pending()).toBe(false);
  });
});

describe('createCommitScheduler — serialization', () => {
  // The regression guard. update_collection replaces file_paths wholesale,
  // so two PUTs in flight at once means the slower one wins.
  it('never lets two writes overlap', async () => {
    let concurrent = 0;
    let peak = 0;
    let release: (() => void) | null = null;
    const { clock, writes, scheduler } = harness({
      write: async (name, paths) => {
        concurrent++;
        peak = Math.max(peak, concurrent);
        writes.push({ name, paths });
        await new Promise<void>((r) => {
          release = r;
        });
        concurrent--;
      },
    });
    // `writes` is captured by the override above; re-read it from harness.
    void writes;

    scheduler.schedule('A', ['/1.pdf']);
    await clock.advance(700);
    expect(concurrent).toBe(1);

    scheduler.schedule('A', ['/2.pdf']);
    await clock.advance(700);
    expect(peak).toBe(1);

    release!();
    await settle();
    await settle();
    expect(peak).toBe(1);
  });

  it('coalesces everything scheduled during a flight into one follow-up', async () => {
    let release: (() => void) | null = null;
    const seen: string[][] = [];
    const { clock, scheduler } = harness({
      write: async (_name, paths) => {
        seen.push(paths);
        await new Promise<void>((r) => {
          release = r;
        });
      },
    });

    scheduler.schedule('A', ['/1.pdf']);
    await clock.advance(700);
    expect(seen).toEqual([['/1.pdf']]);

    scheduler.schedule('A', ['/2.pdf']);
    scheduler.schedule('A', ['/3.pdf']);
    scheduler.schedule('A', ['/4.pdf']);
    await clock.advance(700);
    expect(seen).toHaveLength(1);

    release!();
    await settle();
    await settle();
    expect(seen).toEqual([['/1.pdf'], ['/4.pdf']]);
  });

  it('writes the previous collection before the one that displaced it', async () => {
    const { clock, writes, scheduler } = harness();
    scheduler.schedule('A', ['/a.pdf']);
    scheduler.schedule('B', ['/b.pdf']);
    await clock.advance(700);
    expect(writes.map((w) => w.name)).toEqual(['A', 'B']);
  });
});

describe('createCommitScheduler — flush, retry, cancel', () => {
  it('flush resolves only once the write has landed', async () => {
    const { writes, scheduler } = harness();
    scheduler.schedule('A', ['/a.pdf']);
    await scheduler.flush();
    expect(writes).toEqual([{ name: 'A', paths: ['/a.pdf'] }]);
    expect(scheduler.pending()).toBe(false);
  });

  it('flush drains every queued collection', async () => {
    const { writes, scheduler } = harness();
    scheduler.schedule('A', ['/a.pdf']);
    scheduler.schedule('B', ['/b.pdf']);
    await scheduler.flush();
    expect(writes.map((w) => w.name)).toEqual(['A', 'B']);
  });

  it('retries once, then reports', async () => {
    let attempts = 0;
    const errors: unknown[] = [];
    const { clock, scheduler } = harness({
      write: async () => {
        attempts++;
        throw new Error('sidecar down');
      },
      onError: (_name, err) => errors.push(err),
    });

    scheduler.schedule('A', ['/a.pdf']);
    await clock.advance(700);
    expect(attempts).toBe(1);
    expect(errors).toHaveLength(0);

    await clock.advance(1100);
    expect(attempts).toBe(2);
    expect(errors).toHaveLength(1);
  });

  it('recovers if the retry succeeds', async () => {
    let attempts = 0;
    const errors: unknown[] = [];
    const { clock, scheduler } = harness({
      write: async () => {
        attempts++;
        if (attempts === 1) throw new Error('flaky');
      },
      onError: (_name, err) => errors.push(err),
    });
    scheduler.schedule('A', ['/a.pdf']);
    await clock.advance(2000);
    expect(attempts).toBe(2);
    expect(errors).toHaveLength(0);
  });

  it('cancel drops queued work', async () => {
    const { clock, writes, scheduler } = harness();
    scheduler.schedule('A', ['/a.pdf']);
    scheduler.cancel();
    await clock.advance(2000);
    expect(writes).toHaveLength(0);
    expect(scheduler.pending()).toBe(false);
  });

  it('cancel silences the retry and the error of a write already on the wire', async () => {
    const errors: unknown[] = [];
    let attempts = 0;
    const { clock, scheduler } = harness({
      write: async () => {
        attempts++;
        throw new Error('sidecar down');
      },
      onError: (_name, err) => errors.push(err),
    });
    scheduler.schedule('A', ['/a.pdf']);
    await clock.advance(700);
    expect(attempts).toBe(1);

    scheduler.cancel();
    await clock.advance(3000);
    expect(attempts).toBe(1);
    expect(errors).toHaveLength(0);
  });

  it('stays usable after a cancel', async () => {
    const { clock, writes, scheduler } = harness();
    scheduler.schedule('A', ['/a.pdf']);
    scheduler.cancel();
    scheduler.schedule('A', ['/b.pdf']);
    await clock.advance(700);
    expect(writes).toEqual([{ name: 'A', paths: ['/b.pdf'] }]);
  });
});

describe('mergeArmedCollection', () => {
  function col(name: string, file_paths: string[], over: Partial<CollectionInfo> = {}): CollectionInfo {
    return {
      id: name,
      name,
      file_paths,
      file_count: file_paths.length,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      last_used_at: null,
      description: '',
      color: null,
      archived: false,
      ...over,
    };
  }

  const fetched = { A: col('A', ['/server.pdf'], { color: '#abc', updated_at: '2026-02-02T00:00:00Z' }) };

  it('passes the fetch through when nothing is armed', () => {
    expect(mergeArmedCollection(fetched, null, ['/local.pdf'])).toBe(fetched);
  });

  it('passes the fetch through when no commit is pending', () => {
    expect(mergeArmedCollection(fetched, 'A', null)).toBe(fetched);
  });

  it('passes the fetch through when the armed collection is gone from it', () => {
    expect(mergeArmedCollection(fetched, 'Deleted', ['/local.pdf'])).toBe(fetched);
  });

  it('keeps un-persisted membership but takes everything else from the server', () => {
    const merged = mergeArmedCollection(fetched, 'A', ['/local.pdf', '/local2.pdf']);
    expect(merged.A.file_paths).toEqual(['/local.pdf', '/local2.pdf']);
    expect(merged.A.file_count).toBe(2);
    expect(merged.A.color).toBe('#abc');
    expect(merged.A.updated_at).toBe('2026-02-02T00:00:00Z');
  });

  it('does not mutate the fetched record', () => {
    mergeArmedCollection(fetched, 'A', ['/local.pdf']);
    expect(fetched.A.file_paths).toEqual(['/server.pdf']);
  });
});
