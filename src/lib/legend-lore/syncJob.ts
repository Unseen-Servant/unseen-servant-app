import { invoke } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';
import { jobNotification } from '../shell/notificationStore';
import { progressLabel, type JobSummary } from './syncMessages';

export interface SyncProgressPayload {
  files_done: number;
  total_files: number;
  chunks_total: number;
  current_file: string;
  phase: string;
  // The current book's embedding; 0/0 while it is extracted or between books.
  book_chunks_done: number;
  book_chunks_total: number;
}

export interface RunSyncJobOptions<TResult> {
  command: string;
  args?: Record<string, unknown>;
  startMessage: string;
  errorPrefix: string;
  streamsProgress: boolean;
  buildResultMessage: (result: TResult) => JobSummary;
  onComplete?: (result: TResult) => void | Promise<void>;
}

// Failures stay up until dismissed or the next job starts — they are the
// one outcome the user has to act on. Successes clear themselves.
function showFailure(message: string, detail?: string) {
  jobNotification.show({ type: 'error', message, detail, dismissible: true, duration: null });
}

export async function runSyncJob<TResult>(
  opts: RunSyncJobOptions<TResult>,
  refreshAfter: () => Promise<void>,
): Promise<TResult | null> {
  jobNotification.dismiss();

  jobNotification.show({
    type: 'progress',
    message: opts.startMessage,
    duration: null,
  });

  let unlisten: (() => void) | null = null;
  if (opts.streamsProgress) {
    let prevFilesDone = 0;
    unlisten = await listen<SyncProgressPayload>('sync-progress', (event) => {
      const label = progressLabel(event.payload, prevFilesDone);
      prevFilesDone = event.payload.files_done;
      if (!label) return;
      jobNotification.show({
        type: 'progress',
        message: label.message,
        book: label.book,
        meter: label.meter,
        duration: null,
      });
    });
  }

  try {
    const result = await invoke<TResult>(opts.command, opts.args ?? {});
    if (opts.onComplete) await opts.onComplete(result);
    await refreshAfter();
    const { message, isError, detail } = opts.buildResultMessage(result);
    if (isError) {
      showFailure(message, detail);
    } else {
      jobNotification.show({ type: 'success', message, detail, duration: 5000 });
    }
    return result;
  } catch (e) {
    const msg = String(e);
    if (msg.includes('sync-busy:')) {
      jobNotification.show({
        type: 'info',
        message: 'Another sync is already running.',
        duration: 4000,
      });
    } else {
      showFailure(`${opts.errorPrefix}: ${msg}`, msg);
    }
    return null;
  } finally {
    if (unlisten) unlisten();
  }
}
