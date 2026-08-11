import { describe, expect, test } from 'vitest';
import {
  KEYBINDINGS,
  eventMatchKey,
  isBareKeyChord,
  keyShortcut,
  matchKey,
  type ChordEvent,
} from './keybindings';

const ev = (over: Partial<ChordEvent>): ChordEvent => ({
  key: '',
  code: '',
  metaKey: false,
  ctrlKey: false,
  shiftKey: false,
  altKey: false,
  ...over,
});

describe('eventMatchKey', () => {
  test('lowercases a bare letter', () => {
    expect(eventMatchKey(ev({ key: 'R', code: 'KeyR' }))).toBe('r');
  });

  test('normalizes Cmd and Ctrl to the same key so one table serves both platforms', () => {
    expect(eventMatchKey(ev({ key: 'o', code: 'KeyO', metaKey: true }))).toBe('meta+o');
    expect(eventMatchKey(ev({ key: 'o', code: 'KeyO', ctrlKey: true }))).toBe('meta+o');
  });

  test('treats the numpad period as a period regardless of layout', () => {
    expect(eventMatchKey(ev({ key: '.', code: 'Period' }))).toBe('.');
    // Some layouts (e.g. German) report ',' for the numpad decimal key.
    expect(eventMatchKey(ev({ key: ',', code: 'NumpadDecimal' }))).toBe('.');
  });

  test('rejects shift and alt combinations', () => {
    expect(eventMatchKey(ev({ key: 'R', code: 'KeyR', shiftKey: true }))).toBeNull();
    expect(eventMatchKey(ev({ key: 'r', code: 'KeyR', altKey: true }))).toBeNull();
  });

  test('rejects non-character keys', () => {
    expect(eventMatchKey(ev({ key: 'ArrowDown', code: 'ArrowDown' }))).toBeNull();
    expect(eventMatchKey(ev({ key: 'Enter', code: 'Enter' }))).toBeNull();
  });
});

describe('menu accelerators', () => {
  test('no two bindings claim the same match key', () => {
    const matches = KEYBINDINGS.filter((k) => k.match).map((k) => k.match);
    expect(new Set(matches).size).toBe(matches.length);
  });

  test('every declared match key is reachable from a real keypress', () => {
    for (const entry of KEYBINDINGS.filter((k) => k.match)) {
      const meta = entry.match!.startsWith('meta+');
      const char = meta ? entry.match!.slice(5) : entry.match!;
      expect(eventMatchKey(ev({ key: char, metaKey: meta }))).toBe(entry.match);
    }
  });

  test('match agrees with one of the displayed keys', () => {
    // A binding may advertise several keys ("↓ / J"), so the dispatched one
    // has to appear among them rather than equal the whole string. Rebinding
    // `keys` without updating `match` still fails, which is the point.
    for (const entry of KEYBINDINGS.filter((k) => k.match)) {
      const meta = entry.match!.startsWith('meta+');
      const base = meta ? entry.match!.slice(5) : entry.match!;
      const shown = entry.keys.other
        .split('/')
        .map((k) => k.trim().replace(/^Ctrl\+/, '').toLowerCase());
      expect(shown).toContain(base);
    }
  });

  test('matchKey resolves a known id and returns empty for an unknown one', () => {
    expect(matchKey('tree.rename')).toBe('r');
    expect(matchKey('nope.missing')).toBe('');
    expect(matchKey('sync.run')).toBe('');
  });
});

describe('keyShortcut', () => {
  test('a bare key is its own shortcut value, uppercased', () => {
    expect(keyShortcut('tree.rename')).toBe('R');
    expect(keyShortcut('tree.solo')).toBe('S');
  });

  test('punctuation survives uppercasing unchanged', () => {
    expect(keyShortcut('tree.hide')).toBe('.');
  });

  test('a modifier chord uses the spec modifier names, per platform', () => {
    // isMac decides Meta vs Control, so pin the shape rather than the platform.
    expect(keyShortcut('info.show')).toMatch(/^(Meta|Control)\+I$/);
    expect(keyShortcut('tree.open')).toMatch(/^(Meta|Control)\+O$/);
  });

  test('a binding with no accelerator has no shortcut to assert', () => {
    // collections.* chords are shown as hints but are not live in that menu,
    // and Reveal's ⌥⌘R carries a modifier eventMatchKey rejects — none of them
    // may claim aria-keyshortcuts.
    expect(keyShortcut('tree.openExternal')).toBe('');
    expect(keyShortcut('collections.rename')).toBe('');
    expect(keyShortcut('collections.archive')).toBe('');
    expect(keyShortcut('nope.missing')).toBe('');
  });

  test('every menu-dispatchable binding yields a shortcut', () => {
    for (const entry of KEYBINDINGS.filter((k) => k.match)) {
      expect(keyShortcut(entry.id)).not.toBe('');
    }
  });
});

describe('isBareKeyChord', () => {
  test('a lone character is bare — it needs framing to read as a key', () => {
    expect(isBareKeyChord('tree.solo')).toBe(true); // S
    expect(isBareKeyChord('tree.hide')).toBe(true); // .
    expect(isBareKeyChord('collections.archive')).toBe(true); // A
  });

  test('a modifier chord is not bare — the glyph already reads as a key', () => {
    expect(isBareKeyChord('info.show')).toBe(false); // ⌘I / Ctrl+I
    expect(isBareKeyChord('tree.openExternal')).toBe(false); // ⌥⌘R / Ctrl+Alt+R
  });

  test('a binding advertising several keys is not bare', () => {
    expect(isBareKeyChord('tree.next')).toBe(false); // ↓ / J
    expect(isBareKeyChord('collections.play')).toBe(false); // P / Space
  });

  test('an unknown id is not bare', () => {
    expect(isBareKeyChord('nope.missing')).toBe(false);
  });

  test('bareness does not flip between platforms for the chords menus render', () => {
    // chord() picks mac vs other, so a binding whose two spellings differ in
    // length would frame itself on one platform and not the other. None of the
    // menu-rendered bindings may do that.
    const rendered = [
      'info.show', 'tree.openExternal', 'tree.rename', 'tree.solo',
      'tree.mute', 'tree.hide', 'tree.addToCollection',
      'collections.rename', 'collections.arm', 'collections.archive',
    ];
    for (const id of rendered) {
      const entry = KEYBINDINGS.find((k) => k.id === id)!;
      expect(entry.keys.mac.length === 1).toBe(entry.keys.other.length === 1);
    }
  });
});
