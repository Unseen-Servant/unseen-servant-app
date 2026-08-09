import { describe, expect, test } from 'vitest';
import { KEYBINDINGS, eventMatchKey, matchKey, type ChordEvent } from './keybindings';

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

  test('match agrees with the displayed key', () => {
    for (const entry of KEYBINDINGS.filter((k) => k.match)) {
      const meta = entry.match!.startsWith('meta+');
      const base = meta ? entry.match!.slice(5) : entry.match!;
      const displayed = entry.keys.other.replace(/^Ctrl\+/, '').toLowerCase();
      expect(displayed).toBe(base);
    }
  });

  test('matchKey resolves a known id and returns empty for an unknown one', () => {
    expect(matchKey('tree.rename')).toBe('r');
    expect(matchKey('nope.missing')).toBe('');
    expect(matchKey('sync.run')).toBe('');
  });
});
