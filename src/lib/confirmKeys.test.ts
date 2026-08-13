import { describe, it, expect } from 'vitest';
import { commitKeyId, isCommitChord } from './confirmKeys';
import { KEYBINDINGS, chord, isDeleteChord, type ChordEvent } from './keybindings';

const ev = (over: Partial<ChordEvent> = {}): ChordEvent => ({
  key: 'a', code: 'KeyA', metaKey: false, ctrlKey: false, shiftKey: false, altKey: false, ...over,
});

describe('commitKeyId', () => {
  // Asserting the ternary returns its own literal can't fail. The real risk
  // is `chord()` returning '' silently for an unknown id — renaming a
  // binding out from under this function would blank the switch face with
  // every check here still green, so assert the coupling instead.
  it('names ids that resolve to a registered binding with a glyph', () => {
    for (const danger of [true, false]) {
      const id = commitKeyId(danger);
      expect(KEYBINDINGS.some(k => k.id === id)).toBe(true);
      expect(chord(id)).not.toBe('');
    }
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

  // The dialog calls isCommitChord(event, danger) with two arguments — every
  // other test here passes `mac` explicitly, so this is the only one
  // exercising the real call shape and its fall-through to isDeleteChord's
  // platform default. That comparison is deliberate, not a proxy for it:
  // `navigator.platform` reads "MacIntel" under vitest on macOS, so isMac
  // resolves true in a local run and false on Linux CI — the two
  // environments exercise different branches of every default-`mac` path in
  // this repo. Asserting against isDeleteChord(ev(over)) (also called with
  // no `mac`) is what catches a broken default on *either* platform; a test
  // that only checks "exactly one platform chord is live" would pass under
  // both `mac ?? true` and `mac ?? false`, since either mutation still
  // leaves exactly one branch true.
  it('forwards to isDeleteChord\'s own default when mac is omitted', () => {
    expect(isCommitChord(ev({ key: 'Enter' }), true)).toBe(false);
    for (const over of [{ key: 'Backspace', metaKey: true }, { key: 'Delete' }]) {
      expect(isCommitChord(ev(over), true)).toBe(isDeleteChord(ev(over)));
    }
  });
});
