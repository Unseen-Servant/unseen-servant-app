import { describe, it, expect, vi } from 'vitest';
import { createHoldLatch, HOLD_MS } from './holdLatch';

/** Hand-cranked clock — the latch only ever asks for `now`. */
function makeClock() {
  let t = 0;
  return { now: () => t, advance: (ms: number) => { t += ms; } };
}

describe('hold latch', () => {
  it('engages on press', () => {
    const clock = makeClock();
    const latch = createHoldLatch(clock.now);
    const toggle = vi.fn();

    latch.press('m', toggle);

    expect(toggle).toHaveBeenCalledTimes(1);
  });

  it('latches on a tap — a quick release leaves it engaged', () => {
    const clock = makeClock();
    const latch = createHoldLatch(clock.now);
    const toggle = vi.fn();

    latch.press('m', toggle);
    clock.advance(HOLD_MS - 1);
    latch.release('m');

    expect(toggle).toHaveBeenCalledTimes(1);
  });

  it('reverts on a hold — releasing past the threshold toggles back', () => {
    const clock = makeClock();
    const latch = createHoldLatch(clock.now);
    const toggle = vi.fn();

    latch.press('m', toggle);
    clock.advance(HOLD_MS);
    latch.release('m');

    expect(toggle).toHaveBeenCalledTimes(2);
  });

  it('ignores a release of some other key', () => {
    const clock = makeClock();
    const latch = createHoldLatch(clock.now);
    const toggle = vi.fn();

    latch.press('m', toggle);
    clock.advance(HOLD_MS * 2);
    latch.release('s');

    expect(toggle).toHaveBeenCalledTimes(1);
  });

  it('ignores a release with nothing held', () => {
    const latch = createHoldLatch(makeClock().now);

    expect(() => latch.release('m')).not.toThrow();
  });

  it('does not revert twice on a repeated release', () => {
    const clock = makeClock();
    const latch = createHoldLatch(clock.now);
    const toggle = vi.fn();

    latch.press('m', toggle);
    clock.advance(HOLD_MS);
    latch.release('m');
    latch.release('m');

    expect(toggle).toHaveBeenCalledTimes(2);
  });

  // The window lost focus mid-hold, so no keyup is coming. Leaving the
  // control engaged is the safe direction — the alternative is reverting
  // something the user can no longer see.
  it('cancel abandons the hold, leaving it engaged', () => {
    const clock = makeClock();
    const latch = createHoldLatch(clock.now);
    const toggle = vi.fn();

    latch.press('m', toggle);
    clock.advance(HOLD_MS * 2);
    latch.cancel();
    latch.release('m');

    expect(toggle).toHaveBeenCalledTimes(1);
  });

  it('a second press abandons the first, which stays engaged', () => {
    const clock = makeClock();
    const latch = createHoldLatch(clock.now);
    const first = vi.fn();
    const second = vi.fn();

    latch.press('m', first);
    clock.advance(HOLD_MS);
    latch.press('s', second);
    clock.advance(HOLD_MS);
    latch.release('m');

    expect(first).toHaveBeenCalledTimes(1);
    expect(second).toHaveBeenCalledTimes(1);
  });
});
