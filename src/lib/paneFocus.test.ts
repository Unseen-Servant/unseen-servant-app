import { describe, it, expect } from 'vitest';
import { materializeKey } from './paneFocus';

describe('materializeKey', () => {
  const keys = ['a', 'b', 'c'];

  it('returns null for an empty pane', () => {
    expect(materializeKey([], 'a', 1)).toBeNull();
    expect(materializeKey([], null, -1)).toBeNull();
  });

  it('restores the last-focused row when it still exists', () => {
    expect(materializeKey(keys, 'b', 1)).toBe('b');
  });

  it('restores the same row regardless of direction', () => {
    expect(materializeKey(keys, 'b', -1)).toBe('b');
  });

  it('enters at the first row when moving down with no memory', () => {
    expect(materializeKey(keys, null, 1)).toBe('a');
  });

  it('enters at the last row when moving up with no memory', () => {
    expect(materializeKey(keys, null, -1)).toBe('c');
  });

  it('falls back to the direction-aware end when the remembered row is gone', () => {
    expect(materializeKey(keys, 'vanished', 1)).toBe('a');
    expect(materializeKey(keys, 'vanished', -1)).toBe('c');
  });

  it('handles a single-row pane', () => {
    expect(materializeKey(['only'], null, 1)).toBe('only');
    expect(materializeKey(['only'], 'only', -1)).toBe('only');
  });
});
