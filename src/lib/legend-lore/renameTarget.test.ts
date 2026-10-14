import { describe, expect, test } from 'vitest';
import { renameTarget } from './renameTarget';

describe('renameTarget', () => {
  test("a file keeps its extension, which the field doesn't show", () => {
    expect(renameTarget('Players Handbook.pdf', 'PHB', false)).toBe('PHB.pdf');
  });

  test('the typed name is trimmed', () => {
    expect(renameTarget('A.pdf', '  B  ', false)).toBe('B.pdf');
    expect(renameTarget('A.pdf', 'B .pdf', false)).toBe('B.pdf');
  });

  test('an extension typed anyway is not doubled, and keeps its case', () => {
    expect(renameTarget('A.pdf', 'B.pdf', false)).toBe('B.pdf');
    expect(renameTarget('A.pdf', 'B.PDF', false)).toBe('B.PDF');
  });

  test('a name with nothing before the extension does nothing', () => {
    expect(renameTarget('A.pdf', '', false)).toBeNull();
    expect(renameTarget('A.pdf', '   ', false)).toBeNull();
    expect(renameTarget('A.pdf', '.pdf', false)).toBeNull();
  });

  test('the name as it was does nothing', () => {
    expect(renameTarget('A.pdf', 'A', false)).toBeNull();
    expect(renameTarget('A.pdf', ' A ', false)).toBeNull();
    expect(renameTarget('Modules', 'Modules', true)).toBeNull();
  });

  test('a change of case alone is a rename', () => {
    expect(renameTarget('players handbook.pdf', 'Players Handbook', false)).toBe('Players Handbook.pdf');
  });

  test('a folder takes the name as typed, dots and all', () => {
    expect(renameTarget('Modules', 'Adventures', true)).toBe('Adventures');
    expect(renameTarget('Mods.v2', 'Mods.v3', true)).toBe('Mods.v3');
    expect(renameTarget('Modules', '  ', true)).toBeNull();
  });

  test('a file without an extension takes the name as typed', () => {
    expect(renameTarget('README', 'NOTES', false)).toBe('NOTES');
  });
});
