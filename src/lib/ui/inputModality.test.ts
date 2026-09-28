import { describe, it, expect } from 'vitest';
import { trackInputModality, watchHoverModality } from './inputModality';

/** A keydown carrying a `key`, which bare Event does not have. */
const keydown = (key: string) => Object.assign(new Event('keydown'), { key });

describe('input modality', () => {
  it('assumes pointer before the user has done anything', () => {
    const target = new EventTarget();

    expect(trackInputModality(target).lastWasKeyboard()).toBe(false);
  });

  it('reads a keypress as keyboard', () => {
    const target = new EventTarget();
    const modality = trackInputModality(target);

    target.dispatchEvent(keydown('Delete'));

    expect(modality.lastWasKeyboard()).toBe(true);
  });

  it('reads a pointer press as pointer, even after a keypress', () => {
    const target = new EventTarget();
    const modality = trackInputModality(target);
    target.dispatchEvent(keydown('Delete'));

    target.dispatchEvent(new Event('pointerdown'));

    expect(modality.lastWasKeyboard()).toBe(false);
  });

  // Shift-clicking a row is the mouse driving, not the keyboard — the held
  // modifier alone must not flip the answer, or every range-select would
  // leave the next prompt thinking it was raised by a chord.
  it('ignores a modifier held on its own', () => {
    const target = new EventTarget();
    const modality = trackInputModality(target);

    target.dispatchEvent(keydown('Shift'));

    expect(modality.lastWasKeyboard()).toBe(false);
  });

  it('stops listening once detached', () => {
    const target = new EventTarget();
    const modality = trackInputModality(target);

    modality.stop();
    target.dispatchEvent(keydown('Delete'));

    expect(modality.lastWasKeyboard()).toBe(false);
  });
});

/** A pointermove at a spot, which bare Event does not carry. */
const pointermove = (clientX: number, clientY: number) =>
  Object.assign(new Event('pointermove'), { clientX, clientY });

describe('hover modality', () => {
  function watch() {
    const target = new EventTarget();
    let live: boolean | undefined;
    const stop = watchHoverModality(target, (v) => (live = v));
    return { target, stop, live: () => live };
  }

  it('hides hover once a key drives', () => {
    const { target, live } = watch();
    target.dispatchEvent(pointermove(10, 10));

    target.dispatchEvent(keydown('ArrowDown'));

    expect(live()).toBe(false);
  });

  // The arrow scrolls the list under a resting pointer, and WebKit follows
  // the scroll with a move at the same coordinates. That is the pane moving,
  // not the hand — hover stays dark or it lights a second row.
  it('stays hidden through a move that goes nowhere', () => {
    const { target, live } = watch();
    target.dispatchEvent(pointermove(10, 10));
    target.dispatchEvent(keydown('ArrowDown'));

    target.dispatchEvent(pointermove(10, 10));

    expect(live()).toBe(false);
  });

  it('shows hover again when the pointer really moves', () => {
    const { target, live } = watch();
    target.dispatchEvent(pointermove(10, 10));
    target.dispatchEvent(keydown('ArrowDown'));

    target.dispatchEvent(pointermove(10, 11));

    expect(live()).toBe(true);
  });

  it('shows hover again on a pointer press', () => {
    const { target, live } = watch();
    target.dispatchEvent(keydown('ArrowDown'));

    target.dispatchEvent(new Event('pointerdown'));

    expect(live()).toBe(true);
  });

  it('ignores a modifier held on its own', () => {
    const { target, live } = watch();
    target.dispatchEvent(pointermove(10, 10));

    target.dispatchEvent(keydown('Shift'));

    expect(live()).toBe(true);
  });

  it('stops listening once detached', () => {
    const { target, stop, live } = watch();
    target.dispatchEvent(pointermove(10, 10));

    stop();
    target.dispatchEvent(keydown('ArrowDown'));

    expect(live()).toBe(true);
  });
});
