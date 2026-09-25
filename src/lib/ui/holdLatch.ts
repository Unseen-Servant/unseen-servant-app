// Tap latches, hold is momentary — how a hardware solo button behaves.
//
// Press engages immediately. Releasing after HOLD_MS engages *again*,
// which inverts back to where it started; releasing before then leaves it
// latched. Reverting by re-running the same toggle is what keeps this
// generic: the latch never learns what it toggled, so the collections
// transport, the systems axis, the tree rows and the filter channels all
// use one implementation.
//
// The GM case this serves: peek at one book alone mid-search without
// dismantling a scope that took prep time to build.

export const HOLD_MS = 250;

export interface HoldLatch {
  /** Engage now, and remember how to undo it if the key is held. */
  press(key: string, toggle: () => void): void;
  /** Undo, if this key is the held one and it was held long enough. */
  release(key: string): void;
  /** Forget the hold, leaving whatever it engaged latched. */
  cancel(): void;
}

export function createHoldLatch(
  now: () => number = () => performance.now(),
  holdMs: number = HOLD_MS,
): HoldLatch {
  let held: { key: string; at: number; toggle: () => void } | null = null;

  return {
    press(key, toggle) {
      // Only one key is physically held at a time in practice. A second
      // press abandons the first and leaves it engaged — the safe
      // direction, since the alternative reverts a control the user has
      // since moved away from.
      held = { key, at: now(), toggle };
      toggle();
    },

    release(key) {
      if (held?.key !== key) return;
      const { at, toggle } = held;
      held = null;
      if (now() - at >= holdMs) toggle();
    },

    cancel() {
      held = null;
    },
  };
}

// One latch for the app: one pair of hands, one key held at a time. Each
// pane presses it from its own keydown handler; +page.svelte owns the
// window keyup and blur that release and cancel it.
export const holdLatch = createHoldLatch();
