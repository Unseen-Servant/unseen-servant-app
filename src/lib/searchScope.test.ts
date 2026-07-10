// Mutation-verified 2026-07-09: dropping the UNTAGGED_KEY push from
// searchGameSystemsFilter's mute branch fails the untagged-bucket test
// below — the #307 regression it exists to catch.
import { describe, expect, it } from 'vitest';
import { searchGameSystemsFilter, UNTAGGED_KEY } from './searchScope';

const TAGS = ['D&D 5E', 'Dragonbane', 'Pathfinder 2E'];

describe('searchGameSystemsFilter', () => {
  it('returns null when nothing is soloed or muted (no narrowing)', () => {
    expect(searchGameSystemsFilter(new Set(), new Set(), TAGS)).toBeNull();
  });

  it('solo returns only the soloed systems — untagged excluded by design', () => {
    const out = searchGameSystemsFilter(new Set(['D&D 5E']), new Set(), TAGS);
    expect(out).toEqual(['D&D 5E']);
  });

  it('muting one system keeps the others AND the untagged bucket', () => {
    const out = searchGameSystemsFilter(new Set(), new Set(['Pathfinder 2E']), TAGS);
    expect(out).toContain('D&D 5E');
    expect(out).toContain('Dragonbane');
    expect(out).not.toContain('Pathfinder 2E');
    expect(out).toContain(UNTAGGED_KEY);
  });

  it('muting only the untagged bucket keeps all tagged systems', () => {
    const out = searchGameSystemsFilter(new Set(), new Set([UNTAGGED_KEY]), TAGS);
    expect(out).toEqual(TAGS);
  });

  it('muting all systems but not untagged searches only untagged files', () => {
    const out = searchGameSystemsFilter(new Set(), new Set(TAGS), TAGS);
    expect(out).toEqual([UNTAGGED_KEY]);
  });

  it('muting everything including untagged returns an empty include-list', () => {
    const out = searchGameSystemsFilter(new Set(), new Set([...TAGS, UNTAGGED_KEY]), TAGS);
    expect(out).toEqual([]);
  });

  it('solo overrides mute', () => {
    const out = searchGameSystemsFilter(
      new Set(['Dragonbane']),
      new Set(['Dragonbane', UNTAGGED_KEY]),
      TAGS
    );
    expect(out).toEqual(['Dragonbane']);
  });
});
