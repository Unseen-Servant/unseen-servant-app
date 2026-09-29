import { describe, expect, it } from 'vitest';
import { allWeak, tierCells, tierLabel, weakDividerIndex } from './searchTiers';

describe('tierCells', () => {
  it('maps tiers to gauge cells', () => {
    expect(tierCells('strong', 0.9)).toBe(3);
    expect(tierCells('good', 0.5)).toBe(2);
    expect(tierCells('weak', 0.2)).toBe(1);
  });

  it('falls back to the legacy relevance mapping when tier is missing', () => {
    expect(tierCells(undefined, 1.0)).toBe(3);
    expect(tierCells(undefined, 0.45)).toBe(2);
    expect(tierCells(undefined, 0)).toBe(0);
  });
});

describe('tierLabel', () => {
  it('describes the tier instead of a fake percentage', () => {
    expect(tierLabel('strong', 0.999)).toBe('Strong match');
    expect(tierLabel('good', 0.5)).toBe('Good match');
    expect(tierLabel('weak', 0.01)).toBe('Weak match');
  });

  it('falls back to the legacy percent label when tier is missing', () => {
    expect(tierLabel(undefined, 0.85)).toBe('85% match');
  });
});

describe('weakDividerIndex', () => {
  it('finds the first weak result after at least one stronger one', () => {
    const results = [{ tier: 'strong' }, { tier: 'good' }, { tier: 'weak' }, { tier: 'weak' }];
    expect(weakDividerIndex(results)).toBe(2);
  });

  it('returns -1 when nothing is weak', () => {
    expect(weakDividerIndex([{ tier: 'strong' }, { tier: 'good' }])).toBe(-1);
  });

  it('returns -1 when everything is weak (the all-weak callout handles it)', () => {
    expect(weakDividerIndex([{ tier: 'weak' }, { tier: 'weak' }])).toBe(-1);
  });

  it('returns -1 for empty or untiered results', () => {
    expect(weakDividerIndex([])).toBe(-1);
    expect(weakDividerIndex([{}, {}])).toBe(-1);
  });
});

describe('allWeak', () => {
  it('is true only for a non-empty list of weak results', () => {
    expect(allWeak([{ tier: 'weak' }, { tier: 'weak' }])).toBe(true);
    expect(allWeak([{ tier: 'weak' }, { tier: 'good' }])).toBe(false);
    expect(allWeak([])).toBe(false);
    expect(allWeak([{}])).toBe(false);
  });
});
