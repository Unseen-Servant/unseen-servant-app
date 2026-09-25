import { describe, it, expect } from 'vitest';
import {
  indexedPathsUnder,
  collectionsContaining,
  collectionsFullyContaining,
  uniqueCollectionName,
  computeFolderMembership,
  memberStateFor,
  menuMemberState,
  groupMemberState,
  addMembers,
  removeMembers,
} from './collectionMembership';
import type { CollectionInfo } from './types';

function col(name: string, file_paths: string[], over: Partial<CollectionInfo> = {}): CollectionInfo {
  return {
    id: name,
    name,
    file_paths,
    file_count: file_paths.length,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    last_used_at: null,
    description: '',
    color: null,
    archived: false,
    ...over,
  };
}

function byName(list: CollectionInfo[]): Record<string, CollectionInfo> {
  return Object.fromEntries(list.map((c) => [c.name, c]));
}

describe('indexedPathsUnder', () => {
  const indexed = new Set(['/lib/Adventures/curse.pdf', '/lib/Adventures/dragons.pdf', '/lib/Core/phb.pdf']);

  it('resolves an indexed file to itself', () => {
    expect(indexedPathsUnder('/lib/Core/phb.pdf', indexed)).toEqual(['/lib/Core/phb.pdf']);
  });

  it('resolves a folder to every indexed path beneath it', () => {
    expect(indexedPathsUnder('/lib/Adventures', indexed).sort()).toEqual([
      '/lib/Adventures/curse.pdf',
      '/lib/Adventures/dragons.pdf',
    ]);
  });

  // The trailing slash in the prefix is what makes this pass. Without it
  // "/lib/Adv" swallows everything under "/lib/Adventures".
  it('does not match a sibling folder sharing a name prefix', () => {
    expect(indexedPathsUnder('/lib/Adv', indexed)).toEqual([]);
  });

  it('returns nothing when a folder holds no indexed material', () => {
    expect(indexedPathsUnder('/lib/Empty', indexed)).toEqual([]);
  });
});

describe('collectionsContaining / collectionsFullyContaining', () => {
  const indexed = new Set(['/lib/a.pdf', '/lib/b.pdf', '/lib/c.pdf']);
  const collections = byName([col('Partial', ['/lib/a.pdf']), col('Whole', ['/lib/a.pdf', '/lib/b.pdf', '/lib/c.pdf'])]);

  it('reports any overlap for a folder', () => {
    expect(collectionsContaining('/lib', true, collections, indexed).sort()).toEqual(['Partial', 'Whole']);
  });

  it('reports only total overlap as fully containing', () => {
    expect(collectionsFullyContaining('/lib', true, collections, indexed)).toEqual(['Whole']);
  });

  it('treats a single file as fully contained by anything holding it', () => {
    expect(collectionsFullyContaining('/lib/a.pdf', false, collections, indexed).sort()).toEqual([
      'Partial',
      'Whole',
    ]);
  });

  it('returns nothing for a folder with no indexed material', () => {
    expect(collectionsContaining('/nowhere', true, collections, indexed)).toEqual([]);
  });
});

describe('uniqueCollectionName', () => {
  it('keeps the base name when it is free', () => {
    expect(uniqueCollectionName('Strahd', {})).toBe('Strahd');
  });

  it('suffixes 2 on the first collision', () => {
    expect(uniqueCollectionName('Strahd', { Strahd: {} })).toBe('Strahd 2');
  });

  it('keeps counting past an existing suffix', () => {
    expect(uniqueCollectionName('Strahd', { Strahd: {}, 'Strahd 2': {} })).toBe('Strahd 3');
  });
});

describe('computeFolderMembership', () => {
  it('marks a folder full when its only indexed child is a member', () => {
    const { partial, full } = computeFolderMembership(new Set(['/lib/x/a.pdf']), new Set(['/lib/x/a.pdf']));
    expect(partial.has('/lib/x')).toBe(true);
    expect(full.has('/lib/x')).toBe(true);
  });

  it('marks a folder partial when only some children are members', () => {
    const { partial, full } = computeFolderMembership(
      new Set(['/lib/x/a.pdf', '/lib/x/b.pdf']),
      new Set(['/lib/x/a.pdf'])
    );
    expect(partial.has('/lib/x')).toBe(true);
    expect(full.has('/lib/x')).toBe(false);
  });

  it('leaves a folder with no members out of both sets', () => {
    const { partial, full } = computeFolderMembership(new Set(['/lib/x/a.pdf']), new Set());
    expect(partial.has('/lib/x')).toBe(false);
    expect(full.has('/lib/x')).toBe(false);
  });

  it('rolls up to grandparents, full only when every descendant is a member', () => {
    const indexed = new Set(['/lib/x/a.pdf', '/lib/y/b.pdf']);
    const one = computeFolderMembership(indexed, new Set(['/lib/x/a.pdf']));
    expect(one.partial.has('/lib')).toBe(true);
    expect(one.full.has('/lib')).toBe(false);
    expect(one.full.has('/lib/x')).toBe(true);

    const both = computeFolderMembership(indexed, new Set(['/lib/x/a.pdf', '/lib/y/b.pdf']));
    expect(both.full.has('/lib')).toBe(true);
  });

  // A sync can drop a path from the index while the collection still
  // lists it. Those stale members must not vote a folder full.
  it('ignores member paths that are no longer indexed', () => {
    const { partial, full } = computeFolderMembership(
      new Set(['/lib/x/a.pdf']),
      new Set(['/lib/x/a.pdf', '/lib/x/gone.pdf'])
    );
    expect(full.has('/lib/x')).toBe(true);
    expect(partial.has('/lib/x')).toBe(true);

    const stale = computeFolderMembership(new Set(['/lib/x/a.pdf']), new Set(['/lib/x/gone.pdf']));
    expect(stale.partial.has('/lib/x')).toBe(false);
    expect(stale.full.has('/lib/x')).toBe(false);
  });
});

describe('memberStateFor', () => {
  const indexed = new Set(['/lib/x/a.pdf', '/lib/x/b.pdf']);
  const members = new Set(['/lib/x/a.pdf']);
  const folders = computeFolderMembership(indexed, members);

  it('answers all/none for files', () => {
    expect(memberStateFor('/lib/x/a.pdf', false, members, folders)).toBe('all');
    expect(memberStateFor('/lib/x/b.pdf', false, members, folders)).toBe('none');
  });

  it('answers some for a partially enrolled folder', () => {
    expect(memberStateFor('/lib/x', true, members, folders)).toBe('some');
  });

  it('answers none for a folder outside the index', () => {
    expect(memberStateFor('/other', true, members, folders)).toBe('none');
  });
});

describe('groupMemberState', () => {
  const group = [{ path: '/a.pdf' }, { path: '/b.pdf' }];

  it('reads none when nothing in the group is a member', () => {
    expect(groupMemberState(group, new Set())).toBe('none');
  });

  it('reads some when part of the group is a member', () => {
    expect(groupMemberState(group, new Set(['/a.pdf']))).toBe('some');
  });

  it('reads all when the whole group is', () => {
    expect(groupMemberState(group, new Set(['/a.pdf', '/b.pdf']))).toBe('all');
  });

  // The header used to latch: unticking the last file left it looking
  // selected, because the tri-state never re-read membership.
  it('falls back to none when the last member is removed', () => {
    expect(groupMemberState(group, new Set(['/a.pdf']))).toBe('some');
    expect(groupMemberState(group, new Set())).toBe('none');
  });

  it('ignores members outside the group', () => {
    expect(groupMemberState(group, new Set(['/elsewhere.pdf']))).toBe('none');
  });

  it('reads an empty group as none, not all', () => {
    expect(groupMemberState([], new Set(['/a.pdf']))).toBe('none');
  });
});

describe('menuMemberState', () => {
  it('reads all when the collection holds every target file', () => {
    expect(menuMemberState('Homebrew', new Set(['Homebrew']), new Set(['Homebrew']))).toBe('all');
  });

  it('reads some for a folder the collection only partly holds', () => {
    expect(menuMemberState('Homebrew', new Set(['Homebrew']), new Set())).toBe('some');
  });

  it('reads none for a collection the target is absent from', () => {
    expect(menuMemberState('Homebrew', new Set(['Other']), new Set(['Other']))).toBe('none');
  });

  // Both props come off the same target, so a file — which is binary —
  // appears in both sets or neither. 'some' is unreachable for files.
  it('never reads some for a file', () => {
    expect(menuMemberState('Homebrew', new Set(['Homebrew']), new Set(['Homebrew']))).toBe('all');
    expect(menuMemberState('Homebrew', new Set(), new Set())).toBe('none');
  });

  // Guards the routing: only 'all' sends the click to remove, so a folder
  // that is merely overlapping can still be topped up.
  it('separates the two states that route to add from the one that removes', () => {
    const add = ['none', 'some'];
    expect(add).toContain(menuMemberState('C', new Set(), new Set()));
    expect(add).toContain(menuMemberState('C', new Set(['C']), new Set()));
    expect(menuMemberState('C', new Set(['C']), new Set(['C']))).toBe('all');
  });
});

describe('addMembers / removeMembers', () => {
  it('dedupes on add and reports how many landed', () => {
    const { next, added } = addMembers(['/a'], ['/a', '/b', '/b']);
    expect(next).toEqual(['/a', '/b']);
    expect(added).toBe(1);
  });

  it('reports zero when everything is already a member', () => {
    expect(addMembers(['/a', '/b'], ['/a']).added).toBe(0);
  });

  it('reports zero when removing an absent path', () => {
    expect(removeMembers(['/a'], new Set(['/zzz'])).removed).toBe(0);
  });

  it('removes and counts', () => {
    const { next, removed } = removeMembers(['/a', '/b', '/c'], new Set(['/a', '/c']));
    expect(next).toEqual(['/b']);
    expect(removed).toBe(2);
  });

  it('never mutates the input array', () => {
    const current = ['/a', '/b'];
    addMembers(current, ['/c']);
    removeMembers(current, new Set(['/a']));
    expect(current).toEqual(['/a', '/b']);
  });
});
