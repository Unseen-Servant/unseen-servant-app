import { describe, it, expect } from 'vitest';
import { trackInputModality } from './inputModality';

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
