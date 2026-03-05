import { writable } from 'svelte/store';

export type NotificationType = 'success' | 'info' | 'error' | 'action';

export interface Notification {
  id: string;
  type: NotificationType;
  message: string;
  actionLabel?: string;
  onAction?: () => void;
  onDismiss?: () => void;
  duration: number | null;
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

export const notification = createNotificationStore();
