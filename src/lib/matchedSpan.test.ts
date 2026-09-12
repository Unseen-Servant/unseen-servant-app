import { describe, expect, it } from 'vitest';
import { findMatchedRange, splitAround } from './matchedSpan';

const TABLE = [
  '| Level | Damage | Range |',
  '| --- | --- | --- |',
  '| 1 | 1d6 | 60 ft |',
  '| 2 | 2d6 | 90 ft |',
].join('\n');

const TABLE_SECTION = [
  'Intro paragraph about the spell.',
  '',
  TABLE,
  '',
  'Closing paragraph after the table.',
].join('\n');

// What the sidecar actually embeds for a table row: the row linearised
// into a sentence, which is nowhere in the section's pipe markup.
const LINEARISED_ROW = 'Level: 2; Damage: 2d6; Range: 90 ft';

describe('findMatchedRange', () => {
  it('finds the matched unit as an exact substring', () => {
    const section = 'First block.\n\nThe matched unit.\n\nLast block.';
    const range = findMatchedRange(section, 'The matched unit.');
    expect(range).toEqual([14, 31]);
    expect(section.slice(range![0], range![1])).toBe('The matched unit.');
  });

  it('falls back to the first 60 characters when the unit was reshaped', () => {
    const head = 'A linearised table row that the sidecar rewrote a little bit before embedding, ';
    expect(head.length).toBeGreaterThan(60);
    const section = `Lead-in.\n\n${head}as stored in the section.`;
    const matched = `${head}but ending differently in the embed unit.`;
    const range = findMatchedRange(section, matched);
    expect(range).not.toBeNull();
    expect(range![1] - range![0]).toBe(60);
    expect(section.slice(range![0], range![1])).toBe(matched.slice(0, 60));
  });

  it('falls back to the parent chunk when the unit was linearised out of the markup', () => {
    // A table row's embed unit is a sentence; only the chunk it came
    // from is still findable in the section's pipe markup.
    expect(findMatchedRange(TABLE_SECTION, LINEARISED_ROW)).toBeNull();
    const range = findMatchedRange(TABLE_SECTION, LINEARISED_ROW, TABLE);
    expect(range).not.toBeNull();
    expect(TABLE_SECTION.slice(range![0], range![1])).toBe(TABLE);
    const { before, match, after } = splitAround(TABLE_SECTION, range!);
    expect(match).toBe(TABLE);
    expect(before).toBe('Intro paragraph about the spell.\n\n');
    expect(after).toBe('\n\nClosing paragraph after the table.');
  });

  it('refuses a parent chunk that is most of the section', () => {
    // Highlighting almost everything highlights nothing.
    const chunk = 'A parent chunk that is very nearly the whole section here.';
    const section = `Lead.\n\n${chunk}`;
    expect(chunk.length).toBeGreaterThanOrEqual(0.8 * section.length);
    expect(findMatchedRange(section, 'nowhere in the section', chunk)).toBeNull();
  });

  it('prefers the unit over the parent chunk when both are present', () => {
    const section = 'Lead-in paragraph.\n\nThe matched unit sits here, inside a longer parent chunk.';
    const range = findMatchedRange(section, 'The matched unit', section.slice(20));
    expect(section.slice(range![0], range![1])).toBe('The matched unit');
  });

  it('returns null when the unit is nowhere in the section', () => {
    expect(findMatchedRange('Some section text.', 'Nothing like it here at all.')).toBeNull();
  });

  it('returns null for an empty matched unit or an empty section', () => {
    expect(findMatchedRange('Some section text.', '')).toBeNull();
    expect(findMatchedRange('', 'anything')).toBeNull();
  });
});

describe('splitAround', () => {
  it('preserves the text exactly', () => {
    const section = 'First block.\n\nThe matched unit.\n\nLast block.';
    const { before, match, after } = splitAround(section, [14, 31]);
    expect(before + match + after).toBe(section);
  });

  it('snaps the range outward to the nearest blank lines', () => {
    const section = 'First block.\n\nThe matched unit.\n\nLast block.';
    // A range that starts and ends mid-word inside the middle block.
    const { before, match, after } = splitAround(section, [18, 25]);
    expect(before).toBe('First block.\n\n');
    expect(match).toBe('The matched unit.');
    expect(after).toBe('\n\nLast block.');
  });

  it('keeps a pipe table whole when the range lands inside it', () => {
    const row = '| 2 | 2d6 | 90 ft |';
    const at = TABLE_SECTION.indexOf(row);
    const { before, match, after } = splitAround(TABLE_SECTION, [at, at + row.length]);
    expect(before + match + after).toBe(TABLE_SECTION);
    expect(match).toContain('| Level | Damage | Range |');
    expect(match).toContain('| --- | --- | --- |');
    expect(match).toContain('| 1 | 1d6 | 60 ft |');
    expect(match).toContain(row);
    expect(before).toBe('Intro paragraph about the spell.\n\n');
    expect(after).toBe('\n\nClosing paragraph after the table.');
  });

  it('handles a match in the first block (no text before)', () => {
    const section = 'Opening block.\n\nSecond block.';
    const { before, match, after } = splitAround(section, [0, 7]);
    expect(before).toBe('');
    expect(match).toBe('Opening block.');
    expect(after).toBe('\n\nSecond block.');
  });

  it('handles a match in the last block (no text after)', () => {
    const section = 'Opening block.\n\nSecond block.';
    const { before, match, after } = splitAround(section, [16, 22]);
    expect(before).toBe('Opening block.\n\n');
    expect(match).toBe('Second block.');
    expect(after).toBe('');
  });

  it('spans every block the range touches', () => {
    const section = 'One.\n\nTwo.\n\nThree.\n\nFour.';
    const { before, match, after } = splitAround(section, [7, 14]);
    expect(before).toBe('One.\n\n');
    expect(match).toBe('Two.\n\nThree.');
    expect(after).toBe('\n\nFour.');
    expect(before + match + after).toBe(section);
  });
});
