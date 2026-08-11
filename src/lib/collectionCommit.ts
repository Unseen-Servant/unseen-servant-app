import type { CollectionInfo } from './types';

/**
 * Persisting membership while a collection is armed.
 *
 * `update_collection` replaces `file_paths` wholesale, so two PUTs in
 * flight at once means the slower one wins and clicks vanish. This
 * scheduler is the guard: it coalesces a burst of toggles into one write
 * and never lets a second write start before the first settles.
 */
export interface CommitScheduler {
  /** Queue `filePaths` as the collection's new membership. Latest wins. */
  schedule(name: string, filePaths: string[]): void;
  /** Resolve once everything queued or in flight has been written. */
  flush(): Promise<void>;
  /** True while a write is queued, armed, or on the wire. */
  pending(): boolean;
  /** Abandon queued work and silence the in-flight write's retry/error. */
  cancel(): void;
}

export interface CommitOptions {
  write: (name: string, filePaths: string[]) => Promise<void>;
  onError: (name: string, err: unknown) => void;
  /** Quiet period after the last toggle before writing. */
  debounceMs?: number;
  /** Ceiling on that quiet period, so a continuous sweep still persists. */
  maxWaitMs?: number;
  retries?: number;
  retryDelayMs?: number;
  now?: () => number;
  setTimer?: (fn: () => void, ms: number) => unknown;
  clearTimer?: (handle: unknown) => void;
}

export function createCommitScheduler(opts: CommitOptions): CommitScheduler {
  const debounceMs = opts.debounceMs ?? 600;
  const maxWaitMs = opts.maxWaitMs ?? 4000;
  const retries = opts.retries ?? 1;
  const retryDelayMs = opts.retryDelayMs ?? 1000;
  const now = opts.now ?? (() => Date.now());
  const setTimer = opts.setTimer ?? ((fn: () => void, ms: number) => setTimeout(fn, ms));
  const clearTimer =
    opts.clearTimer ?? ((h: unknown) => clearTimeout(h as ReturnType<typeof setTimeout>));

  // name → latest payload. A Map keeps insertion order, so a rename or
  // re-arm mid-burst can't write one track's paths under another's name:
  // each queued entry carries its own name.
  const queue = new Map<string, string[]>();
  let queuedSince: number | null = null;
  let lastScheduled: string | null = null;
  let timer: unknown = null;
  let inFlight: Promise<void> | null = null;
  // Bumped by cancel() so an in-flight write's retry and error reporting
  // know they've been abandoned.
  let generation = 0;

  function disarmTimer() {
    if (timer !== null) {
      clearTimer(timer);
      timer = null;
    }
  }

  function armTimer() {
    disarmTimer();
    const waited = queuedSince === null ? 0 : now() - queuedSince;
    const wait = Math.max(0, Math.min(debounceMs, maxWaitMs - waited));
    timer = setTimer(() => {
      timer = null;
      pump();
    }, wait);
  }

  function sleep(ms: number): Promise<void> {
    return new Promise((resolve) => {
      setTimer(() => resolve(), ms);
    });
  }

  async function attempt(name: string, paths: string[], left: number): Promise<void> {
    const gen = generation;
    try {
      await opts.write(name, paths);
    } catch (err) {
      if (gen !== generation) return;
      if (left > 0) {
        await sleep(retryDelayMs);
        if (gen !== generation) return;
        return attempt(name, paths, left - 1);
      }
      opts.onError(name, err);
    }
  }

  function pump(): void {
    if (inFlight !== null) return;
    const next = queue.entries().next();
    if (next.done) {
      queuedSince = null;
      return;
    }
    const [name, paths] = next.value;
    queue.delete(name);
    if (queue.size === 0) queuedSince = null;
    disarmTimer();
    // attempt() never rejects — it funnels failure into onError — so
    // inFlight is always safe to await.
    inFlight = attempt(name, paths, retries).then(() => {
      inFlight = null;
      pump();
    });
  }

  return {
    schedule(name: string, filePaths: string[]) {
      // A different track means the previous one's burst is over; don't
      // make its writes wait out a fresh debounce.
      const switched = lastScheduled !== null && lastScheduled !== name && queue.size > 0;
      queue.set(name, filePaths);
      lastScheduled = name;
      if (queuedSince === null) queuedSince = now();
      if (switched) {
        disarmTimer();
        pump();
        if (queue.size > 0) armTimer();
      } else {
        armTimer();
      }
    },

    async flush() {
      disarmTimer();
      pump();
      while (inFlight !== null) {
        await inFlight;
        pump();
      }
    },

    pending() {
      return queue.size > 0 || inFlight !== null || timer !== null;
    },

    cancel() {
      disarmTimer();
      queue.clear();
      queuedSince = null;
      lastScheduled = null;
      generation++;
    },
  };
}

/**
 * Fold a server fetch over the armed collection's un-persisted membership.
 *
 * `loadCollections()` runs on every sync completion. Without this, a sync
 * landing mid-session would overwrite the armed collection with disk state,
 * dropping clicks the user has made but the scheduler hasn't written yet —
 * and the next flush would then persist that reverted set.
 *
 * Pass `localPaths` only while a commit is actually pending; everything
 * other than membership always comes from the server.
 */
export function mergeArmedCollection(
  fetched: Record<string, CollectionInfo>,
  armedName: string | null,
  localPaths: string[] | null
): Record<string, CollectionInfo> {
  if (!armedName || !localPaths) return fetched;
  const server = fetched[armedName];
  if (!server) return fetched;
  return {
    ...fetched,
    [armedName]: { ...server, file_paths: localPaths, file_count: localPaths.length },
  };
}
