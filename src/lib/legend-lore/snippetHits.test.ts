import { describe, expect, it } from 'vitest';
import { markSnippet, queryTerms } from './snippetHits';

const hits = (text: string, query: string) =>
  markSnippet(text, queryTerms(query))
    .filter((p) => p.hit)
    .map((p) => p.text);

describe('queryTerms', () => {
  it('lowercases, dedupes and drops short words and stopwords', () => {
    expect(queryTerms('Sword of the Ancients sword')).toEqual(['sword', 'ancients']);
  });

  it('keeps accented letters and digits', () => {
    expect(queryTerms('épée d20')).toEqual(['épée', 'd20']);
  });
});

describe('markSnippet', () => {
  it('marks whole words starting with a term, case-insensitively', () => {
    expect(hits('d20: 19-20; Result: Swords', 'sword')).toEqual(['Swords']);
    expect(hits('Two-Handed Sword and a swordsman', 'Sword')).toEqual(['Sword', 'swordsman']);
  });

  it('does not mark a term inside a word', () => {
    expect(hits('Broadsword', 'sword')).toEqual([]);
  });

  it('reassembles to the original text when the hit is visible', () => {
    const text = 'Weapon: Swords, short and long';
    expect(markSnippet(text, ['sword']).map((p) => p.text).join('')).toBe(text);
  });

  it('returns the text whole when there are no terms', () => {
    expect(markSnippet('Anything at all', [])).toEqual([{ text: 'Anything at all', hit: false }]);
  });

  it('starts near a hit that would sit past the visible width', () => {
    const text =
      'This is the final step in the creation of an intelligent weapon, and each attribute of the sword adds to its ego';
    const joined = markSnippet(text, ['sword']).map((p) => p.text).join('');
    expect(joined.startsWith('…')).toBe(true);
    expect(joined.endsWith('the sword adds to its ego')).toBe(true);
    expect(joined.indexOf('sword')).toBeLessThan(48);
  });
});
