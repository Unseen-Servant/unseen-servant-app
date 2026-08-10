import { describe, it, expect, beforeEach, vi } from 'vitest';
import { claimMenuSlot, releaseMenuSlot } from './menuSlot';

describe('menuSlot', () => {
  // The slot is module state — empty it between cases by claiming with a
  // throwaway close and immediately handing it back.
  beforeEach(() => {
    const noop = () => {};
    claimMenuSlot(noop);
    releaseMenuSlot(noop);
  });

  it('closes the incumbent when another menu claims the slot', () => {
    const first = vi.fn();
    const second = vi.fn();
    claimMenuSlot(first);
    claimMenuSlot(second);
    expect(first).toHaveBeenCalledTimes(1);
    expect(second).not.toHaveBeenCalled();
  });

  it('does not close a menu that re-claims its own slot', () => {
    const only = vi.fn();
    claimMenuSlot(only);
    claimMenuSlot(only);
    expect(only).not.toHaveBeenCalled();
  });

  it('leaves the slot empty once the holder releases it', () => {
    const first = vi.fn();
    claimMenuSlot(first);
    releaseMenuSlot(first);
    claimMenuSlot(vi.fn());
    expect(first).not.toHaveBeenCalled();
  });

  it('ignores a release from a menu that no longer holds the slot', () => {
    const first = vi.fn();
    const second = vi.fn();
    claimMenuSlot(first);
    claimMenuSlot(second);
    // `first` closed on eviction and releases on its way out; that must not
    // empty the slot `second` just took.
    releaseMenuSlot(first);
    claimMenuSlot(vi.fn());
    expect(second).toHaveBeenCalledTimes(1);
  });

  it('survives an incumbent that releases from inside its own close', () => {
    const first = vi.fn(() => releaseMenuSlot(first));
    const second = vi.fn();
    claimMenuSlot(first);
    claimMenuSlot(second);
    claimMenuSlot(vi.fn());
    expect(second).toHaveBeenCalledTimes(1);
  });

  it('closes only the current holder, never an earlier one', () => {
    const first = vi.fn();
    const second = vi.fn();
    claimMenuSlot(first);
    claimMenuSlot(second);
    claimMenuSlot(vi.fn());
    expect(first).toHaveBeenCalledTimes(1);
    expect(second).toHaveBeenCalledTimes(1);
  });
});
