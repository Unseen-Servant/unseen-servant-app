import { writable } from 'svelte/store';

/**
 * How many modal dialogs are open, and whether a given one is stacked.
 *
 * Two questions need answering that CSS cannot ask. "Is any dialog open?"
 * drives the chrome dim, since the Header and StatusBar stay outside the
 * scrim and must read inert rather than falsely live. "Am I the second
 * dialog?" drives the lighter stacked scrim, so a prompt does not
 * extinguish the modal it is asking about.
 *
 * `:has(dialog[open])` would answer the first and not the second, and this
 * app ships on both WKWebView and WebView2 with no minimum system version
 * pinned — it has already been bitten once assuming ::backdrop behaved
 * uniformly across engines. State is cheap and certain.
 *
 * See docs/frontend/2026-08-13-scrim-extent-and-depth-design.md.
 */
export function createDialogStack() {
  const { subscribe, update } = writable(0);

  /** Registers an opening dialog. Returns true if one was already open. */
  function register(): boolean {
    let stacked = false;
    update((n) => {
      stacked = n > 0;
      return n + 1;
    });
    return stacked;
  }

  /**
   * Releases a closing dialog. Floors at zero: Modal releases on both close
   * and destroy, and a dialog unmounted without closing fires both. A
   * negative count would report "no dialogs open" while one still is.
   */
  function release(): void {
    update((n) => (n > 0 ? n - 1 : 0));
  }

  return { subscribe, register, release };
}

export const openDialogs = createDialogStack();
