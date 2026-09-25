import { describe, expect, test } from 'vitest';
import {
  CHILD_SEP,
  childNavKey,
  computeCollectionNav,
  parseNavKey,
  stepNavKey,
} from './collectionsNav';

const childrenOf = (name: string) =>
  name === 'Curse of Strahd' ? ['/lib/a.pdf', '/lib/b.pdf'] : [];

describe('computeCollectionNav', () => {
  test('collapsed collections contribute only their head row', () => {
    const nav = computeCollectionNav(['Curse of Strahd', 'One-shots'], new Set(), childrenOf);
    expect(nav.map((e) => e.key)).toEqual(['Curse of Strahd', 'One-shots']);
  });

  test('an expanded collection interleaves its children in render order', () => {
    const nav = computeCollectionNav(
      ['Curse of Strahd', 'One-shots'],
      new Set(['Curse of Strahd']),
      childrenOf,
    );
    expect(nav.map((e) => e.key)).toEqual([
      'Curse of Strahd',
      childNavKey('Curse of Strahd', '/lib/a.pdf'),
      childNavKey('Curse of Strahd', '/lib/b.pdf'),
      'One-shots',
    ]);
    expect(nav[1]).toEqual({
      key: `Curse of Strahd${CHILD_SEP}/lib/a.pdf`,
      name: 'Curse of Strahd',
      path: '/lib/a.pdf',
    });
  });

  test('an expanded but empty collection stays a lone head row', () => {
    const nav = computeCollectionNav(['One-shots'], new Set(['One-shots']), childrenOf);
    expect(nav.map((e) => e.key)).toEqual(['One-shots']);
  });
});

describe('parseNavKey', () => {
  test('round-trips a child key', () => {
    expect(parseNavKey(childNavKey('Curse of Strahd', '/lib/a.pdf'))).toEqual({
      name: 'Curse of Strahd',
      path: '/lib/a.pdf',
    });
  });

  test('a head key has no path', () => {
    expect(parseNavKey('Curse of Strahd')).toEqual({ name: 'Curse of Strahd', path: null });
  });
});

describe('stepNavKey', () => {
  const nav = computeCollectionNav(
    ['Curse of Strahd', 'One-shots'],
    new Set(['Curse of Strahd']),
    childrenOf,
  );

  test('walks from a head row into its children and on to the next head', () => {
    const fromHead = stepNavKey(nav, 'Curse of Strahd', 1);
    expect(fromHead).toBe(childNavKey('Curse of Strahd', '/lib/a.pdf'));
    const fromLastChild = stepNavKey(nav, childNavKey('Curse of Strahd', '/lib/b.pdf'), 1);
    expect(fromLastChild).toBe('One-shots');
  });

  test('clamps at both ends rather than wrapping', () => {
    expect(stepNavKey(nav, 'Curse of Strahd', -1)).toBe('Curse of Strahd');
    expect(stepNavKey(nav, 'One-shots', 1)).toBe('One-shots');
  });

  test('a stale key re-enters from the end the user was heading toward', () => {
    expect(stepNavKey(nav, childNavKey('Gone', '/x.pdf'), 1)).toBe('Curse of Strahd');
    expect(stepNavKey(nav, childNavKey('Gone', '/x.pdf'), -1)).toBe('One-shots');
  });

  test('an empty list yields nothing', () => {
    expect(stepNavKey([], 'anything', 1)).toBeNull();
  });
});
