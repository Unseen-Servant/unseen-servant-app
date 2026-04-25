import { invoke } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';
import { notification } from './notificationStore';

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
  notification.dismiss();

  notification.show({
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
      notification.show({
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
    notification.show({
      type: isError ? 'error' : 'success',
      message,
      duration: 5000,
    });
    return result;
  } catch (e) {
    notification.show({
      type: 'error',
      message: `${opts.errorPrefix}: ${String(e)}`,
      duration: 6000,
    });
    return null;
  } finally {
    if (unlisten) unlisten();
  }
}
