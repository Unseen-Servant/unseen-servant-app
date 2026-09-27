import { describe, expect, test } from 'vitest';
import {
  KEYBINDINGS,
  commitKeyShortcut,
  eventMatchKey,
  isBareKeyChord,
  isDeleteChord,
  keyShortcut,
  matchKey,
  systemsRowScopeKey,
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

describe('isDeleteChord', () => {
  test('mac takes Cmd+Backspace, and Ctrl+Backspace as the same normalization', () => {
    expect(isDeleteChord(ev({ key: 'Backspace', metaKey: true }), true)).toBe(true);
    expect(isDeleteChord(ev({ key: 'Backspace', ctrlKey: true }), true)).toBe(true);
  });

  test('mac leaves bare Backspace alone — it is a text key there, not a file one', () => {
    expect(isDeleteChord(ev({ key: 'Backspace' }), true)).toBe(false);
  });

  test('elsewhere takes bare Del and not the modified form', () => {
    expect(isDeleteChord(ev({ key: 'Delete' }), false)).toBe(true);
    expect(isDeleteChord(ev({ key: 'Delete', metaKey: true }), false)).toBe(false);
    expect(isDeleteChord(ev({ key: 'Delete', ctrlKey: true }), false)).toBe(false);
  });

  test('neither platform answers to the other platform key', () => {
    expect(isDeleteChord(ev({ key: 'Delete' }), true)).toBe(false);
    expect(isDeleteChord(ev({ key: 'Backspace', metaKey: true }), false)).toBe(false);
  });

  test('Shift is rejected — Shift+Del means delete permanently in file managers', () => {
    expect(isDeleteChord(ev({ key: 'Backspace', metaKey: true, shiftKey: true }), true)).toBe(false);
    expect(isDeleteChord(ev({ key: 'Delete', shiftKey: true }), false)).toBe(false);
  });

  test('Alt is rejected on both platforms', () => {
    expect(isDeleteChord(ev({ key: 'Backspace', metaKey: true, altKey: true }), true)).toBe(false);
    expect(isDeleteChord(ev({ key: 'Delete', altKey: true }), false)).toBe(false);
  });

  test('the chord cannot round-trip through eventMatchKey, so menus only hint it', () => {
    // Named keys are longer than one character — a menu can display '⌘⌫' but
    // will never dispatch it, which is why neither delete binding has a match.
    expect(eventMatchKey(ev({ key: 'Backspace', metaKey: true }))).toBeNull();
    expect(KEYBINDINGS.find((k) => k.id === 'tree.delete')!.match).toBeUndefined();
    expect(KEYBINDINGS.find((k) => k.id === 'collections.delete')!.match).toBeUndefined();
  });
});

describe('commitKeyShortcut', () => {
  test('names a key isDeleteChord actually accepts, on both platforms', () => {
    // Coupling test, not a pinned literal: parse the aria name back into a
    // keydown and confirm isDeleteChord fires for it. If the two functions
    // ever disagreed, aria-keyshortcuts would advertise a key that doesn't
    // actually commit anything.
    for (const mac of [true, false]) {
      const shortcut = commitKeyShortcut(mac);
      const [modifier, key] = shortcut.includes('+') ? shortcut.split('+') : [undefined, shortcut];
      expect(isDeleteChord(ev({ key, metaKey: modifier === 'Meta' }), mac)).toBe(true);
    }
  });

  // confirm.commitSafe fires by native <button> activation (focus sits on
  // the button, and Enter is browser behavior, not a dispatched chord) — see
  // confirmKeys.ts. That means this module can't derive the fact from
  // isDeleteChord the way it does above; pin it directly instead, so a
  // retune of the binding (e.g. to ⌘↵) can't drift from what the button
  // actually honours.
  test('confirm.commitSafe stays Enter', () => {
    const entry = KEYBINDINGS.find((k) => k.id === 'confirm.commitSafe')!;
    expect(entry.keys.mac).toBe('↵');
    expect(entry.keys.other).toBe('Enter');
  });
});

describe('menu accelerators', () => {
  test('no two bindings claim the same match key', () => {
    const matches = KEYBINDINGS.filter((k) => k.match).map((k) => k.match);
    expect(new Set(matches).size).toBe(matches.length);
  });

  test('no two bindings share an id — BY_ID last-wins silently otherwise', () => {
    const ids = KEYBINDINGS.map((k) => k.id);
    expect(new Set(ids).size).toBe(ids.length);
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
      'tree.mute', 'tree.hide', 'tree.addToCollection', 'tree.delete',
      'collections.rename', 'collections.arm', 'collections.archive',
      'collections.play', 'collections.mute', 'collections.delete',
    ];
    for (const id of rendered) {
      const entry = KEYBINDINGS.find((k) => k.id === id)!;
      expect(entry.keys.mac.length === 1).toBe(entry.keys.other.length === 1);
    }
  });
});

describe('switch bindings', () => {
  // A key cap in the legend means "there is a square in the window for this".
  test('marks the keys that light a switch', () => {
    const ids = KEYBINDINGS.filter(k => k.switch).map(k => k.id);
    expect(ids).toContain('tree.solo');
    expect(ids).toContain('tree.mute');
    expect(ids).toContain('collections.play');
    expect(ids).toContain('collections.arm');
    expect(ids).toContain('scope.bypass');
    expect(ids).toContain('systems.solo');
    expect(ids).toContain('systems.mute');
    expect(ids).toContain('systems.soloGroup');
    expect(ids).toContain('systems.muteGroup');
  });

  test('does not mark bare keys with no switch behind them', () => {
    const byId = new Map(KEYBINDINGS.map(k => [k.id, k]));
    expect(byId.get('tree.rename')?.switch).toBeUndefined();
    expect(byId.get('collections.archive')?.switch).toBeUndefined();
  });

  // Shift is the one modifier that can still land on a square: ⇧S/⇧M throw
  // the systems view's group squares from a file row, and ⇧X ticks a run of
  // the same checkboxes X does. That is a fact about these entries, not
  // about shift, so it is pinned by id rather than waved through.
  const SHIFT_SWITCHES = new Set([
    'systems.soloGroup', 'systems.muteGroup', 'tree.tickRange', 'systems.tickRange',
  ]);

  test('never marks a meta or alt chord, and shift only where a square really is', () => {
    for (const k of KEYBINDINGS.filter(e => e.switch)) {
      expect(k.keys.mac).not.toMatch(/[⌘⌥⌃]/);
      expect(k.keys.other).not.toMatch(/Ctrl\+|Alt\+/);
      if (k.keys.mac.includes('⇧')) expect(SHIFT_SWITCHES.has(k.id)).toBe(true);
    }
  });
});

describe('systemsRowScopeKey', () => {
  test('bare S and M act on the file', () => {
    expect(systemsRowScopeKey(ev({ key: 's' }), false)).toEqual({ axis: 'file', kind: 'solo' });
    expect(systemsRowScopeKey(ev({ key: 'm' }), false)).toEqual({ axis: 'file', kind: 'mute' });
  });

  test('shifted S and M lift to the system', () => {
    expect(systemsRowScopeKey(ev({ key: 'S', shiftKey: true }), false)).toEqual({ axis: 'system', kind: 'solo' });
    expect(systemsRowScopeKey(ev({ key: 'M', shiftKey: true }), false)).toEqual({ axis: 'system', kind: 'mute' });
  });

  test('a capital letter without shift (CapsLock) still acts on the file', () => {
    expect(systemsRowScopeKey(ev({ key: 'S' }), false)).toEqual({ axis: 'file', kind: 'solo' });
  });

  test('untagged: bare S solos the file, shift+S is inert, shift+M still mutes the system', () => {
    expect(systemsRowScopeKey(ev({ key: 's' }), true)).toEqual({ axis: 'file', kind: 'solo' });
    expect(systemsRowScopeKey(ev({ key: 'm' }), true)).toEqual({ axis: 'file', kind: 'mute' });
    expect(systemsRowScopeKey(ev({ key: 'S', shiftKey: true }), true)).toBeNull();
    expect(systemsRowScopeKey(ev({ key: 'M', shiftKey: true }), true)).toEqual({ axis: 'system', kind: 'mute' });
  });

  test("meta, ctrl, and alt combinations are someone else's chord", () => {
    // ⌘S is sync.commit — it must never read as a scope gesture.
    expect(systemsRowScopeKey(ev({ key: 's', metaKey: true }), false)).toBeNull();
    expect(systemsRowScopeKey(ev({ key: 's', ctrlKey: true }), false)).toBeNull();
    expect(systemsRowScopeKey(ev({ key: 'm', altKey: true }), false)).toBeNull();
  });

  test('other keys are not scope chords', () => {
    expect(systemsRowScopeKey(ev({ key: 'x' }), false)).toBeNull();
    expect(systemsRowScopeKey(ev({ key: 'Enter' }), false)).toBeNull();
  });
});
