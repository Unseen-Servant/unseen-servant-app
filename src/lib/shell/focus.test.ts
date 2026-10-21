import { describe, expect, test } from 'vitest';
import { openDialogs } from './dialogStack';
import { dialogOpen } from './focus';

// isTyping walks the DOM and has no test: this repo runs vitest under node,
// with no jsdom (see confirmKeys.ts).
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
