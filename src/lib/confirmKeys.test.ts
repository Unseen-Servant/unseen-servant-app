import { describe, it, expect } from 'vitest';
import { commitKeyId, isCommitChord } from './confirmKeys';
import type { ChordEvent } from './keybindings';

const ev = (over: Partial<ChordEvent> = {}): ChordEvent => ({
  key: 'a', code: 'KeyA', metaKey: false, ctrlKey: false, shiftKey: false, altKey: false, ...over,
});

describe('commitKeyId', () => {
  it('names the safe binding for an activation prompt', () => {
    expect(commitKeyId(false)).toBe('confirm.commitSafe');
  });

  it('names the delete binding for a removal prompt', () => {
    expect(commitKeyId(true)).toBe('confirm.commit');
  });
});

describe('isCommitChord', () => {
  // The whole point of F1's fix: an activation prompt keeps focus on its
  // commit button and lets the button take Enter natively. If this module
  // ever returned true for Enter, the dialog would grow the listener the
  // audit deleted.
  it('never matches on an activation prompt, including Enter', () => {
    expect(isCommitChord(ev({ key: 'Enter' }), false, true)).toBe(false);
    expect(isCommitChord(ev({ key: 'Backspace', metaKey: true }), false, true)).toBe(false);
  });

  it('matches the mac delete chord on a removal prompt', () => {
    expect(isCommitChord(ev({ key: 'Backspace', metaKey: true }), true, true)).toBe(true);
  });

  it('matches the non-mac delete key on a removal prompt', () => {
    expect(isCommitChord(ev({ key: 'Delete' }), true, false)).toBe(true);
  });

  // Enter must be inert on a removal prompt: focus sits on the dialog
  // element, so there is no button for it to activate either.
  it('does not match Enter on a removal prompt', () => {
    expect(isCommitChord(ev({ key: 'Enter' }), true, true)).toBe(false);
  });

  it('rejects a bare Backspace on mac', () => {
    expect(isCommitChord(ev({ key: 'Backspace' }), true, true)).toBe(false);
  });

  it('rejects Shift+Delete — that means "delete permanently" elsewhere', () => {
    expect(isCommitChord(ev({ key: 'Delete', shiftKey: true }), true, false)).toBe(false);
  });
});
