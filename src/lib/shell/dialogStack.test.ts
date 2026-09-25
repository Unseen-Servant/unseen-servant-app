import { describe, it, expect } from 'vitest';
import { get } from 'svelte/store';
import { createDialogStack } from './dialogStack';

describe('dialog stack', () => {
  it('starts empty and is not stacked', () => {
    const s = createDialogStack();
    expect(get(s)).toBe(0);
  });

  // The return value is the whole point: a dialog learns whether it is
  // stacked from what was already open when it registered, and CSS has no
  // way to ask that question.
  it('tells the first dialog it is not stacked, and the second that it is', () => {
    const s = createDialogStack();
    expect(s.register()).toBe(false);
    expect(s.register()).toBe(true);
    expect(get(s)).toBe(2);
  });

  it('releases back down', () => {
    const s = createDialogStack();
    s.register();
    s.register();
    s.release();
    expect(get(s)).toBe(1);
    s.release();
    expect(get(s)).toBe(0);
  });

  // Modal releases on close AND on destroy, because DocumentStatsModal is
  // unmounted by {#if statsModalPath} rather than by flipping `visible` —
  // the same asymmetry that leaked focus restoration once before. Both
  // paths can therefore fire for one register, and a double release must
  // not drive the count negative: a negative count would leave
  // `$openDialogs > 0` false with a dialog still open, un-dimming the
  // chrome underneath it.
  it('never goes negative on a double release', () => {
    const s = createDialogStack();
    s.register();
    s.release();
    s.release();
    s.release();
    expect(get(s)).toBe(0);
  });

  it('is idle after a matched register/release cycle', () => {
    const s = createDialogStack();
    s.register();
    s.release();
    expect(get(s)).toBe(0);
    expect(s.register()).toBe(false);
  });
});
