import { describe, expect, test } from 'vitest';
import { filterTree, filterWords, markName, markPath, nameMatches, pathMatches } from './nameFilter';
import type { FileItem } from './types';

const file = (path: string): FileItem => ({ name: path.split('/').pop()!, path, is_dir: false, children: null });
const dir = (path: string, children: FileItem[]): FileItem => ({ name: path.split('/').pop()!, path, is_dir: true, children });

describe('filterWords', () => {
  test('lowercased words, blanks dropped', () => {
    expect(filterWords('  Dragon  MAG ')).toEqual(['dragon', 'mag']);
    expect(filterWords('   ')).toEqual([]);
  });
});

describe('nameMatches', () => {
  test('every word, anywhere, any order, any case', () => {
    expect(nameMatches('Monster Manual.pdf', ['manual', 'mon'])).toBe(true);
    expect(nameMatches('Monster Manual.pdf', ['monster', 'guide'])).toBe(false);
  });
});

describe('markName', () => {
  test('marks every occurrence of every word, merging overlaps', () => {
    expect(markName('Dragon Dragon.pdf', ['drag'])).toEqual([
      { text: 'Drag', hit: true }, { text: 'on ', hit: false },
      { text: 'Drag', hit: true }, { text: 'on.pdf', hit: false },
    ]);
    expect(markName('Monster', ['mons', 'nster'])).toEqual([{ text: 'Monster', hit: true }]);
  });

  test('a name that does not hold every word marks nothing', () => {
    expect(markName('Dragons', ['dragon', '12'])).toEqual([{ text: 'Dragons', hit: false }]);
    expect(markName('Dragons', [])).toEqual([{ text: 'Dragons', hit: false }]);
  });
});

describe('markPath', () => {
  test('marks only the segments that match, keeping separators', () => {
    expect(markPath('D&D 5e/Core/', ['5e'])).toEqual([
      { text: 'D&D ', hit: false }, { text: '5e', hit: true },
      { text: '/', hit: false }, { text: 'Core', hit: false }, { text: '/', hit: false },
    ]);
  });
});

describe('pathMatches', () => {
  test('passes on the file name or any folder under the root', () => {
    expect(pathMatches('/lib/D&D 5e/Monster Manual.pdf', '/lib', ['monster'])).toBe(true);
    expect(pathMatches('/lib/D&D 5e/Monster Manual.pdf', '/lib', ['5e'])).toBe(true);
  });

  test('folders above the root and words split across segments do not count', () => {
    expect(pathMatches('/lib/D&D 5e/Monster Manual.pdf', '/lib', ['lib'])).toBe(false);
    expect(pathMatches('/lib/D&D 5e/Monster Manual.pdf', '/lib', ['5e', 'monster'])).toBe(false);
  });
});

describe('filterTree', () => {
  const tree = [
    dir('/lib/Dragon', [
      file('/lib/Dragon/Issue 1.pdf'),
      dir('/lib/Dragon/Specials', [file('/lib/Dragon/Specials/Dragon Annual.pdf')]),
    ]),
    dir('/lib/OSR', [dir('/lib/OSR/Monsters', [file('/lib/OSR/Monsters/Fiend Folio.pdf')])]),
    file('/lib/Loose.pdf'),
  ];

  test('keeps a match with its ancestors open and its contents available', () => {
    const f = filterTree(tree, ['fiend']);
    expect([...f.show].sort()).toEqual(['/lib/OSR', '/lib/OSR/Monsters', '/lib/OSR/Monsters/Fiend Folio.pdf']);
    expect([...f.open].sort()).toEqual(['/lib/OSR', '/lib/OSR/Monsters']);
  });

  test('a matching folder keeps everything inside it but stays closed', () => {
    const f = filterTree(tree, ['monsters']);
    expect(f.show.has('/lib/OSR/Monsters/Fiend Folio.pdf')).toBe(true);
    expect(f.open.has('/lib/OSR/Monsters')).toBe(false);
    expect(f.open.has('/lib/OSR')).toBe(true);
  });

  test('a match nested inside a matching folder opens its way', () => {
    const f = filterTree(tree, ['dragon']);
    expect(f.show.has('/lib/Dragon/Issue 1.pdf')).toBe(true);
    expect([...f.open].sort()).toEqual(['/lib/Dragon', '/lib/Dragon/Specials']);
  });

  test('nothing matches, nothing shows', () => {
    const f = filterTree(tree, ['zzz']);
    expect(f.show.size).toBe(0);
    expect(f.open.size).toBe(0);
  });
});
