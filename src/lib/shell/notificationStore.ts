import { writable } from 'svelte/store';

// Two notification channels feed the status bar's two regions:
//
//   jobNotification     — owned by runSyncJob and discrete-action handlers.
//                         Renders progress, terminal success/error, transient
//                         info. Lives in the left region.
//   pendingNotification — owned by polling and selection-change handlers
//                         (showSyncPrompt). Renders the standing "N to add,
//                         M to remove [Sync]" prompt. Lives in the right
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
  // Tooltip: the full story behind a one-line message (e.g. which books failed).
  detail?: string;
  // Sticky notes the user may close by hand.
  dismissible?: boolean;
  // Progress only: the book being worked on, shown after the message,
  // and how far into embedding it the job is.
  book?: string;
  meter?: { done: number; total: number };
}

function createNotificationStore() {
  const { subscribe, set } = writable<Notification | null>(null);

  let timer: ReturnType<typeof setTimeout> | null = null;
  let current: Notification | null = null;

  // Mirror the writable's value into a local snapshot so dismissByUser()
  // can reach the current notification's onDismiss without external code
  // having to subscribe + read internal shape.
  subscribe((n) => { current = n; });

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

  function show(notif: Omit<Notification, 'id'>): string {
    clearTimer();
    const id = Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
    set({ ...notif, id });

    if (notif.duration !== null) {
      timer = setTimeout(() => set(null), notif.duration);
    }

    return id;
  }

  // Dismiss only if the current notification is the one matching `id`.
  // Lets a long-lived sticky toast clear itself when its underlying
  // condition resolves, without clobbering whatever the user is seeing
  // now if another notification has displaced ours in the meantime.
  function dismissIf(id: string) {
    if (current?.id === id) dismiss();
  }

  return { subscribe, show, dismiss, dismissIf };
}

export const jobNotification = createNotificationStore();
export const pendingNotification = createNotificationStore();
