import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';

const tauri = vi.hoisted(() => ({
  invoke: vi.fn(),
  listen: vi.fn(),
}));
vi.mock('@tauri-apps/api/core', () => ({ invoke: tauri.invoke }));
vi.mock('@tauri-apps/api/event', () => ({ listen: tauri.listen }));

import { runSyncJob, type RunSyncJobOptions, type SyncProgressPayload } from './syncJob';
import { jobNotification } from '../shell/notificationStore';

interface Result { added: number; errors: string[] }

let emit: ((payload: SyncProgressPayload) => void) | null;
let unlisten: ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.useFakeTimers();
  emit = null;
  unlisten = vi.fn();
  tauri.invoke.mockReset();
  tauri.listen.mockReset().mockImplementation(async (_event: string, handler: (e: { payload: SyncProgressPayload }) => void) => {
    emit = (payload) => handler({ payload });
    return unlisten;
  });
  jobNotification.dismiss();
});

afterEach(() => {
  vi.useRealTimers();
});

function options(overrides: Partial<RunSyncJobOptions<Result>> = {}): RunSyncJobOptions<Result> {
  return {
    command: 'sync_index',
    args: { paths: ['/lib/a.pdf'] },
    startMessage: 'Syncing…',
    errorPrefix: 'Sync failed',
    streamsProgress: true,
    buildResultMessage: (r) => ({ message: `Added ${r.added}`, isError: r.errors.length > 0, detail: r.errors.join('\n') || undefined }),
    ...overrides,
  };
}

const ok: Result = { added: 2, errors: [] };

describe('runSyncJob', () => {
  it('runs the command with its args, then onComplete, then refreshAfter, and reports success', async () => {
    const order: string[] = [];
    tauri.invoke.mockImplementation(async () => { order.push('invoke'); return ok; });
    const onComplete = vi.fn(async () => { order.push('onComplete'); });
    const refreshAfter = vi.fn(async () => { order.push('refresh'); });

    const result = await runSyncJob(options({ onComplete }), refreshAfter);

    expect(result).toBe(ok);
    expect(tauri.invoke).toHaveBeenCalledWith('sync_index', { paths: ['/lib/a.pdf'] });
    expect(onComplete).toHaveBeenCalledWith(ok);
    expect(order).toEqual(['invoke', 'onComplete', 'refresh']);
    expect(get(jobNotification)).toMatchObject({ type: 'success', message: 'Added 2', duration: 5000 });
  });

  it('shows the start message while the command runs', async () => {
    let resolve!: (r: Result) => void;
    tauri.invoke.mockReturnValue(new Promise<Result>((r) => { resolve = r; }));

    const job = runSyncJob(options(), async () => {});
    await vi.waitFor(() => expect(tauri.invoke).toHaveBeenCalled());
    expect(get(jobNotification)).toMatchObject({ type: 'progress', message: 'Syncing…', duration: null });

    resolve(ok);
    await job;
  });

  it('turns sync-progress events into a progress notification', async () => {
    let resolve!: (r: Result) => void;
    tauri.invoke.mockReturnValue(new Promise<Result>((r) => { resolve = r; }));

    const job = runSyncJob(options(), async () => {});
    await vi.waitFor(() => expect(emit).not.toBeNull());
    emit!({
      files_done: 0, total_files: 12, chunks_total: 0, current_file: 'Monster Manual.pdf',
      phase: 'add', book_chunks_done: 0, book_chunks_total: 0,
    });
    expect(get(jobNotification)).toMatchObject({ type: 'progress', message: 'Indexing 1 of 12', book: 'Monster Manual' });

    resolve(ok);
    await job;
  });

  it('does not listen for progress when the command does not stream it', async () => {
    tauri.invoke.mockResolvedValue(ok);
    await runSyncJob(options({ streamsProgress: false }), async () => {});
    expect(tauri.listen).not.toHaveBeenCalled();
  });

  it('keeps a result that reports errors up as a sticky failure, and still returns it', async () => {
    const withErrors = { added: 1, errors: ['bad.pdf: no text'] };
    tauri.invoke.mockResolvedValue(withErrors);

    const result = await runSyncJob(options(), async () => {});

    expect(result).toBe(withErrors);
    expect(get(jobNotification)).toMatchObject({
      type: 'error', message: 'Added 1', detail: 'bad.pdf: no text', dismissible: true, duration: null,
    });
  });

  it('reports sync-busy as information, not as a failure', async () => {
    tauri.invoke.mockRejectedValue('sync-busy: a sync is already in progress');
    const refreshAfter = vi.fn(async () => {});

    const result = await runSyncJob(options(), refreshAfter);

    expect(result).toBeNull();
    expect(refreshAfter).not.toHaveBeenCalled();
    expect(get(jobNotification)).toMatchObject({ type: 'info', message: 'Another sync is already running.' });
  });

  it('reports any other rejection as a sticky failure under the error prefix', async () => {
    tauri.invoke.mockRejectedValue('Sidecar error (500): No data directory configured');

    const result = await runSyncJob(options(), async () => {});

    expect(result).toBeNull();
    expect(get(jobNotification)).toMatchObject({
      type: 'error',
      message: 'Sync failed: Sidecar error (500): No data directory configured',
      dismissible: true,
      duration: null,
    });
  });

  it('stops listening for progress whether the command succeeds or fails', async () => {
    tauri.invoke.mockResolvedValueOnce(ok).mockRejectedValueOnce('boom');

    await runSyncJob(options(), async () => {});
    expect(unlisten).toHaveBeenCalledTimes(1);

    await runSyncJob(options(), async () => {});
    expect(unlisten).toHaveBeenCalledTimes(2);
  });
});
