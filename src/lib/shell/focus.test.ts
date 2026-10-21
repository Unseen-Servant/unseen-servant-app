import { describe, expect, test } from 'vitest';
import { openDialogs } from './dialogStack';
import { dialogOpen, inEditor, isTyping } from './focus';

// A key's target as the DOM would hand it over: closest answers with a
// match for the selectors listed.
function targetIn(...matches: string[]): EventTarget {
  return {
    closest: (selector: string) =>
      selector.split(', ').some((s) => matches.includes(s)) ? {} : null,
  } as unknown as EventTarget;
}

describe('dialogOpen', () => {
  test('follows the dialog stack', () => {
    expect(dialogOpen()).toBe(false);
    openDialogs.register();
    expect(dialogOpen()).toBe(true);
    openDialogs.register();
    openDialogs.release();
    expect(dialogOpen()).toBe(true);
    openDialogs.release();
    expect(dialogOpen()).toBe(false);
  });
});

describe('isTyping', () => {
  test('a field, a select or the editor under the key is typing', () => {
    expect(isTyping(targetIn('input'))).toBe(true);
    expect(isTyping(targetIn('select'))).toBe(true);
    expect(isTyping(targetIn('.cm-editor'))).toBe(true);
  });
  test('a row, the window or nothing is not', () => {
    expect(isTyping(targetIn())).toBe(false);
    expect(isTyping({} as EventTarget)).toBe(false);
    expect(isTyping(null)).toBe(false);
  });
});

describe('inEditor', () => {
  test('only the editor counts, not any field', () => {
    expect(inEditor(targetIn('.cm-editor'))).toBe(true);
    expect(inEditor(targetIn('input'))).toBe(false);
    expect(inEditor(null)).toBe(false);
  });
});
