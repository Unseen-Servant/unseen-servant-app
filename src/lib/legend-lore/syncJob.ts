import { invoke } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';
import { jobNotification } from '../shell/notificationStore';

export interface SyncProgressPayload {
  files_done: number;
  total_files: number;
  chunks_total: number;
  current_file: string;
  phase: string;
}

export interface RunSyncJobOptions<TResult> {
  command: string;
  args?: Record<string, unknown>;
  startMessage: string;
  errorPrefix: string;
  streamsProgress: boolean;
  buildResultMessage: (result: TResult) => { message: string; isError: boolean };
  onComplete?: (result: TResult) => void | Promise<void>;
}

export async function runSyncJob<TResult>(
  opts: RunSyncJobOptions<TResult>,
  refreshAfter: () => Promise<void>,
): Promise<TResult | null> {
  jobNotification.dismiss();

  jobNotification.show({
    type: 'progress',
    message: opts.startMessage,
    filesCompleted: 0,
    filesTotal: 0,
    chunksProcessed: 0,
    duration: null,
  });

  let unlisten: (() => void) | null = null;
  if (opts.streamsProgress) {
    unlisten = await listen<SyncProgressPayload>('sync-progress', (event) => {
      const p = event.payload;
      jobNotification.show({
        type: 'progress',
        message: `${p.files_done}/${p.total_files} files`,
        filesCompleted: p.files_done,
        filesTotal: p.total_files,
        chunksProcessed: p.chunks_total,
        duration: null,
      });
    });
  }

  try {
    const result = await invoke<TResult>(opts.command, opts.args ?? {});
    if (opts.onComplete) await opts.onComplete(result);
    await refreshAfter();
    const { message, isError } = opts.buildResultMessage(result);
    jobNotification.show({
      type: isError ? 'error' : 'success',
      message,
      duration: 5000,
    });
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
      jobNotification.show({
        type: 'error',
        message: `${opts.errorPrefix}: ${msg}`,
        duration: 6000,
      });
    }
    return null;
  } finally {
    if (unlisten) unlisten();
  }
}
