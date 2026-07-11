import { describe, expect, it } from 'vitest';
import {
  DEFAULT_SEARCH_SETTINGS,
  RERANK_POOL_MAX,
  RERANK_POOL_MIN,
  clampPoolSize,
  normalizeSearchSettings,
} from './searchSettings';

describe('normalizeSearchSettings', () => {
  it('returns defaults for junk input', () => {
    expect(normalizeSearchSettings(null)).toEqual(DEFAULT_SEARCH_SETTINGS);
    expect(normalizeSearchSettings(undefined)).toEqual(DEFAULT_SEARCH_SETTINGS);
    expect(normalizeSearchSettings('nope')).toEqual(DEFAULT_SEARCH_SETTINGS);
    expect(normalizeSearchSettings(42)).toEqual(DEFAULT_SEARCH_SETTINGS);
  });

  it('keeps valid fields and fills missing ones', () => {
    const result = normalizeSearchSettings({ rerank: false });
    expect(result.rerank).toBe(false);
    expect(result.spell_correction).toBe(true);
    expect(result.rerank_candidates).toBe(50);
  });

  it('ignores mistyped fields', () => {
    const result = normalizeSearchSettings({
      rerank: 'yes',
      rerank_candidates: 'many',
      hybrid: true,
    });
    expect(result.rerank).toBe(true);
    expect(result.rerank_candidates).toBe(50);
    expect(result.hybrid).toBe(true);
  });

  it('clamps out-of-range pool sizes', () => {
    expect(normalizeSearchSettings({ rerank_candidates: 1 }).rerank_candidates)
      .toBe(RERANK_POOL_MIN);
    expect(normalizeSearchSettings({ rerank_candidates: 9999 }).rerank_candidates)
      .toBe(RERANK_POOL_MAX);
  });
});

describe('clampPoolSize', () => {
  it('rounds and clamps', () => {
    expect(clampPoolSize(25.6)).toBe(26);
    expect(clampPoolSize(-5)).toBe(RERANK_POOL_MIN);
    expect(clampPoolSize(1e9)).toBe(RERANK_POOL_MAX);
  });

  it('falls back to the default on non-finite input', () => {
    expect(clampPoolSize(NaN)).toBe(DEFAULT_SEARCH_SETTINGS.rerank_candidates);
    expect(clampPoolSize(Infinity)).toBe(DEFAULT_SEARCH_SETTINGS.rerank_candidates);
  });
});
