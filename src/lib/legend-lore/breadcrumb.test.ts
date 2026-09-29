import { describe, expect, it } from 'vitest';
import { breadcrumbSegments, isAllCaps } from './breadcrumb';

describe('breadcrumbSegments', () => {
  it('splits the heading path and strips bold markers', () => {
    expect(breadcrumbSegments('**PART 7: TREASURE** > Magic Weapons')).toEqual([
      'PART 7: TREASURE',
      'Magic Weapons',
    ]);
  });

  it('drops empty segments', () => {
    expect(breadcrumbSegments('Spells > ')).toEqual(['Spells']);
  });
});

describe('isAllCaps', () => {
  it('is true for a capitalised heading, digits and punctuation included', () => {
    expect(isAllCaps('INTRODUCTION AND PURPOSE')).toBe(true);
    expect(isAllCaps('PART 2: PLAYER CHARACTERS')).toBe(true);
  });

  it('is false for mixed case and for text without letters', () => {
    expect(isAllCaps('Sword Intelligence and Capabilities')).toBe(false);
    expect(isAllCaps('Level 5 Cleric Spells')).toBe(false);
    expect(isAllCaps('1.2')).toBe(false);
  });
});
