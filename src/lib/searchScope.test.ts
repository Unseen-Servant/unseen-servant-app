// Mutation-verified 2026-07-09: dropping the UNTAGGED_KEY push from
// searchGameSystemsFilter's mute branch fails the untagged-bucket test
// below — the #307 regression it exists to catch.
import { describe, expect, it } from 'vitest';
import {
  searchCurationFilter,
  searchGameSystemsFilter,
  searchSourcePathsFilter,
  resolveMix,
  passesSystemsAxis,
  resolveScopeSet,
  emptyScopeMessage,
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

  it('nonexistent collection names resolve away entirely — even for the null decision', () => {
    expect(resolveMix(new Set(['Missing']), new Set(), COLS, INDEXED)).toBeNull();
    expect(resolveMix(new Set(), new Set(['Missing']), COLS, INDEXED)).toBeNull();
  });

  it('a muted collection with some stale file_paths carves only what is still indexed', () => {
    const cols = { Partial: { file_paths: ['/lib/strahd.pdf', '/gone/stale.pdf'] } };
    const out = resolveMix(new Set(), new Set(['Partial']), cols, INDEXED);
    expect([...out!].sort()).toEqual(['/lib/brew.pdf', '/lib/loose.pdf', '/lib/shared.pdf']);
  });
});

describe('passesSystemsAxis', () => {
  const none = new Set<string>();

  it('everything passes when nothing is engaged', () => {
    expect(passesSystemsAxis(['D&D 5E'], none, none)).toBe(true);
    expect(passesSystemsAxis([], none, none)).toBe(true);
  });

  it('under solos only files with a soloed tag pass', () => {
    const solo = new Set(['D&D 5E']);
    expect(passesSystemsAxis(['D&D 5E', 'Dragonbane'], solo, none)).toBe(true);
    expect(passesSystemsAxis(['Dragonbane'], solo, none)).toBe(false);
  });

  it('untagged files never pass under solos', () => {
    expect(passesSystemsAxis([], new Set(['D&D 5E']), none)).toBe(false);
  });

  it('under mutes a file passes while it keeps one unmuted tag', () => {
    const muted = new Set(['Dragonbane']);
    expect(passesSystemsAxis(['Dragonbane', 'D&D 5E'], none, muted)).toBe(true);
    expect(passesSystemsAxis(['Dragonbane'], none, muted)).toBe(false);
  });

  it('untagged files pass under mutes unless the Untagged bucket is muted (#307)', () => {
    expect(passesSystemsAxis([], none, new Set(['Dragonbane']))).toBe(true);
    expect(passesSystemsAxis([], none, new Set([UNTAGGED_KEY]))).toBe(false);
  });

  it('solo overrides mute', () => {
    const solo = new Set(['Dragonbane']);
    const muted = new Set(['Dragonbane']);
    expect(passesSystemsAxis(['Dragonbane'], solo, muted)).toBe(true);
  });
});

describe('resolveScopeSet', () => {
  const INDEXED = new Set([
    '/lib/strahd/map.pdf',
    '/lib/bestiary/dragons.pdf',
    '/lib/bestiary/undead.pdf',
    '/lib/loose.pdf',
  ]);
  const TAGS = new Map<string, string[]>([
    ['/lib/strahd/map.pdf', ['D&D 5E']],
    ['/lib/bestiary/dragons.pdf', ['D&D 5E']],
    ['/lib/bestiary/undead.pdf', ['Dragonbane']],
  ]);
  const COLLECTED = new Set(['/lib/strahd/map.pdf', '/lib/bestiary/undead.pdf']);
  const BESTIARY = ['/lib/bestiary/dragons.pdf', '/lib/bestiary/undead.pdf'];
  const noStr = new Set<string>();
  const noCur = new Set<CurationKey>();

  const resolve = (
    mix: Set<string> | null,
    soloSets: string[][] = [],
    muteSets: string[][] = [],
    opts: Partial<{
      curationSolos: Set<CurationKey>;
      curationMutes: Set<CurationKey>;
      soloedSystems: Set<string>;
      mutedSystems: Set<string>;
    }> = {}
  ) =>
    resolveScopeSet(
      mix,
      soloSets,
      muteSets,
      opts.curationSolos ?? noCur,
      opts.curationMutes ?? noCur,
      COLLECTED,
      opts.soloedSystems ?? noStr,
      opts.mutedSystems ?? noStr,
      TAGS,
      INDEXED
    );

  it('returns null when nothing is engaged anywhere', () => {
    expect(resolve(null)).toBeNull();
  });

  it('a mix alone IS the scope', () => {
    const mix = new Set(['/lib/strahd/map.pdf']);
    expect(resolve(mix)).toEqual(mix);
  });

  it('a folder solo intersects the playing mix — the Strahd/Bestiary case', () => {
    const mix = new Set(['/lib/strahd/map.pdf', '/lib/bestiary/undead.pdf']);
    const out = resolve(mix, [BESTIARY]);
    expect(out).toEqual(new Set(['/lib/bestiary/undead.pdf']));
  });

  it('a solo with nothing inside the mix resolves empty, not to the solo', () => {
    const mix = new Set(['/lib/strahd/map.pdf']);
    expect(resolve(mix, [BESTIARY])).toEqual(new Set());
  });

  it('mutes carve within the mix', () => {
    const mix = new Set(['/lib/strahd/map.pdf', '/lib/bestiary/dragons.pdf']);
    const out = resolve(mix, [], [['/lib/bestiary/dragons.pdf']]);
    expect(out).toEqual(new Set(['/lib/strahd/map.pdf']));
  });

  it('the curation axis intersects within the mix', () => {
    const mix = new Set(['/lib/strahd/map.pdf', '/lib/bestiary/dragons.pdf']);
    const out = resolve(mix, [], [], { curationSolos: new Set<CurationKey>(['collected']) });
    expect(out).toEqual(new Set(['/lib/strahd/map.pdf']));
  });

  it('the systems axis intersects within the mix', () => {
    const mix = new Set(['/lib/bestiary/dragons.pdf', '/lib/bestiary/undead.pdf']);
    const out = resolve(mix, [], [], { soloedSystems: new Set(['Dragonbane']) });
    expect(out).toEqual(new Set(['/lib/bestiary/undead.pdf']));
  });

  it('axes narrow the whole library when no mix is armed', () => {
    const out = resolve(null, [BESTIARY]);
    expect(out).toEqual(new Set(BESTIARY));
  });

  it('with empty system sets and an untagged file, the file survives (runSearch mode)', () => {
    const out = resolve(null, [], [['/lib/strahd/map.pdf']]);
    expect(out!.has('/lib/loose.pdf')).toBe(true);
  });
});

describe('emptyScopeMessage', () => {
  const NONE_EMPTY = {
    mixEmpty: false,
    anyLivePlaying: false,
    pathScopeEmpty: false,
    anySolosEngaged: false,
    systemsEmpty: false,
  };

  it('returns null when the scope is not empty anywhere', () => {
    expect(emptyScopeMessage(NONE_EMPTY)).toBeNull();
  });

  it('mix empty + a live playing collection → "Nothing indexed is playing."', () => {
    expect(
      emptyScopeMessage({ ...NONE_EMPTY, mixEmpty: true, anyLivePlaying: true })
    ).toBe('Nothing indexed is playing.');
  });

  it('mix empty + no live playing collection → "Everything is muted." (the ghost-name case: a stale play-name must not claim playing over a live mute)', () => {
    expect(
      emptyScopeMessage({ ...NONE_EMPTY, mixEmpty: true, anyLivePlaying: false })
    ).toBe('Everything is muted.');
  });

  it('path scope empty + a solo engaged → "Nothing under the soloed items."', () => {
    expect(
      emptyScopeMessage({ ...NONE_EMPTY, pathScopeEmpty: true, anySolosEngaged: true })
    ).toBe('Nothing under the soloed items.');
  });

  it('path scope empty + no solo engaged → "Everything is muted."', () => {
    expect(
      emptyScopeMessage({ ...NONE_EMPTY, pathScopeEmpty: true, anySolosEngaged: false })
    ).toBe('Everything is muted.');
  });

  it('systems empty → "Everything is muted."', () => {
    expect(emptyScopeMessage({ ...NONE_EMPTY, systemsEmpty: true })).toBe('Everything is muted.');
  });

  it('priority: mixEmpty wins over pathScopeEmpty and systemsEmpty when all are true', () => {
    expect(
      emptyScopeMessage({
        mixEmpty: true,
        anyLivePlaying: true,
        pathScopeEmpty: true,
        anySolosEngaged: true,
        systemsEmpty: true,
      })
    ).toBe('Nothing indexed is playing.');
  });

  it('priority: pathScopeEmpty wins over systemsEmpty when both are true', () => {
    expect(
      emptyScopeMessage({
        ...NONE_EMPTY,
        pathScopeEmpty: true,
        anySolosEngaged: true,
        systemsEmpty: true,
      })
    ).toBe('Nothing under the soloed items.');
  });
});
