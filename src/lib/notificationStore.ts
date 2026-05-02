import { writable } from 'svelte/store';

// Two notification channels feed the status bar's two regions:
//
//   jobNotification     — owned by runSyncJob and discrete-action handlers.
//                         Renders progress, terminal success/error, transient
//                         info. Lives in the left region.
//   pendingNotification — owned by polling and selection-change handlers
//                         (showSyncPrompt). Renders the standing "N to add,
//                         M to remove [Sync Now]" prompt. Lives in the right
//                         region.
//
// Each call site imports exactly one channel; the regions never compete.

export type NotificationType = 'success' | 'info' | 'error' | 'action' | 'progress';

export interface Notification {
  id: string;
  type: NotificationType;
  message: string;
  actionLabel?: string;
  actionDisabled?: boolean;
  onAction?: () => void;
  onDismiss?: () => void;
  duration: number | null;
  filesCompleted?: number;
  filesTotal?: number;
  chunksProcessed?: number;
}

function createNotificationStore() {
  const { subscribe, set } = writable<Notification | null>(null);

  let timer: ReturnType<typeof setTimeout> | null = null;

  function clearTimer() {
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
  }

  function dismiss() {
    clearTimer();
    set(null);
  }

  function show(notif: Omit<Notification, 'id'>) {
    clearTimer();
    const id = Date.now().toString(36);
    set({ ...notif, id });

    if (notif.duration !== null) {
      timer = setTimeout(() => set(null), notif.duration);
    }
  }

  return { subscribe, show, dismiss };
}

export const jobNotification = createNotificationStore();
export const pendingNotification = createNotificationStore();
