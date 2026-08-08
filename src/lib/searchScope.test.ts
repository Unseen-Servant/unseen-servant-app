// Mutation-verified 2026-07-09: dropping the UNTAGGED_KEY push from
// searchGameSystemsFilter's mute branch fails the untagged-bucket test
// below — the #307 regression it exists to catch.
import { describe, expect, it } from 'vitest';
import {
  searchCurationFilter,
  searchGameSystemsFilter,
  searchSourcePathsFilter,
  resolveMix,
  UNTAGGED_KEY,
} from './searchScope';
import type { CurationKey } from './searchScope';

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

const ALL = ['/lib/a.pdf', '/lib/b.pdf', '/lib/sub/c.pdf', '/other/d.pdf'];

describe('searchSourcePathsFilter', () => {
  it('returns null when nothing is soloed or muted (no narrowing)', () => {
    expect(searchSourcePathsFilter([], [], ALL)).toBeNull();
  });

  it('solos union within the axis, deduplicated', () => {
    const out = searchSourcePathsFilter(
      [['/lib/a.pdf', '/lib/b.pdf'], ['/lib/b.pdf', '/lib/sub/c.pdf']],
      [],
      ALL
    );
    expect(out?.sort()).toEqual(['/lib/a.pdf', '/lib/b.pdf', '/lib/sub/c.pdf']);
  });

  it('solo overrides mute — muted files inside a soloed set still pass', () => {
    const out = searchSourcePathsFilter(
      [['/lib/a.pdf', '/lib/b.pdf']],
      [['/lib/b.pdf']],
      ALL
    );
    expect(out).toContain('/lib/b.pdf');
  });

  it('a solo with no indexed files narrows to nothing, not to everything', () => {
    expect(searchSourcePathsFilter([[]], [], ALL)).toEqual([]);
  });

  it('mutes subtract their union from the indexed universe', () => {
    const out = searchSourcePathsFilter(
      [],
      [['/lib/a.pdf'], ['/lib/sub/c.pdf']],
      ALL
    );
    expect(out).toEqual(['/lib/b.pdf', '/other/d.pdf']);
  });

  it('muting everything returns an empty include-list', () => {
    expect(searchSourcePathsFilter([], [ALL], ALL)).toEqual([]);
  });
});

describe('searchCurationFilter', () => {
  const COLLECTED = new Set(['/lib/a.pdf', '/lib/sub/c.pdf']);
  const none = new Set<CurationKey>();

  it('returns null when nothing is soloed or muted (no narrowing)', () => {
    expect(searchCurationFilter(none, none, COLLECTED, ALL)).toBeNull();
  });

  it('soloing Collected narrows to files in some collection', () => {
    const out = searchCurationFilter(new Set<CurationKey>(['collected']), none, COLLECTED, ALL);
    expect(out?.sort()).toEqual(['/lib/a.pdf', '/lib/sub/c.pdf']);
  });

  it('soloing Loose narrows to files in no collection', () => {
    const out = searchCurationFilter(new Set<CurationKey>(['loose']), none, COLLECTED, ALL);
    expect(out?.sort()).toEqual(['/lib/b.pdf', '/other/d.pdf']);
  });

  it('soloing both buckets unions to the whole universe', () => {
    const out = searchCurationFilter(
      new Set<CurationKey>(['collected', 'loose']),
      none,
      COLLECTED,
      ALL
    );
    expect(out?.sort()).toEqual([...ALL].sort());
  });

  it('muting Loose keeps only collected files', () => {
    const out = searchCurationFilter(none, new Set<CurationKey>(['loose']), COLLECTED, ALL);
    expect(out?.sort()).toEqual(['/lib/a.pdf', '/lib/sub/c.pdf']);
  });

  it('muting both buckets returns an empty include-list', () => {
    const out = searchCurationFilter(
      none,
      new Set<CurationKey>(['collected', 'loose']),
      COLLECTED,
      ALL
    );
    expect(out).toEqual([]);
  });

  it('solo overrides mute', () => {
    const out = searchCurationFilter(
      new Set<CurationKey>(['loose']),
      new Set<CurationKey>(['loose']),
      COLLECTED,
      ALL
    );
    expect(out?.sort()).toEqual(['/lib/b.pdf', '/other/d.pdf']);
  });
});

describe('resolveMix', () => {
  const COLS = {
    Strahd: { file_paths: ['/lib/strahd.pdf', '/lib/shared.pdf'] },
    Homebrew: { file_paths: ['/lib/brew.pdf', '/lib/shared.pdf'] },
    Ghost: { file_paths: ['/gone/x.pdf'] },
  };
  const INDEXED = new Set([
    '/lib/strahd.pdf',
    '/lib/shared.pdf',
    '/lib/brew.pdf',
    '/lib/loose.pdf',
  ]);

  it('returns null when the transport is idle and nothing is muted', () => {
    expect(resolveMix(new Set(), new Set(), COLS, INDEXED)).toBeNull();
  });

  it('playing collections union their indexed files', () => {
    const out = resolveMix(new Set(['Strahd', 'Homebrew']), new Set(), COLS, INDEXED);
    expect([...out!].sort()).toEqual(['/lib/brew.pdf', '/lib/shared.pdf', '/lib/strahd.pdf']);
  });

  it('idle transport with a muted collection carves it from the whole library', () => {
    const out = resolveMix(new Set(), new Set(['Homebrew']), COLS, INDEXED);
    expect([...out!].sort()).toEqual(['/lib/loose.pdf', '/lib/strahd.pdf']);
  });

  it('mute wins over play — a playing, muted collection contributes nothing', () => {
    const out = resolveMix(new Set(['Strahd']), new Set(['Strahd']), COLS, INDEXED);
    expect(out).toEqual(new Set());
  });

  it('a file in both a playing and a muted collection is carved out', () => {
    const out = resolveMix(new Set(['Strahd']), new Set(['Homebrew']), COLS, INDEXED);
    expect([...out!]).toEqual(['/lib/strahd.pdf']);
  });

  it('playing a collection with no indexed files yields an empty mix, not the library', () => {
    expect(resolveMix(new Set(['Ghost']), new Set(), COLS, INDEXED)).toEqual(new Set());
  });

  it('stale collection names resolve away harmlessly', () => {
    expect(resolveMix(new Set(['Missing']), new Set(), COLS, INDEXED)).toEqual(new Set());
    const idleMuted = resolveMix(new Set(), new Set(['Missing']), COLS, INDEXED);
    expect(idleMuted).toEqual(INDEXED);
  });
});
