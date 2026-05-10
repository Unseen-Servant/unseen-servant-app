import { describe, expect, it } from 'vitest';
import {
  parseString,
  parseBoolean,
  parseStringArray,
  parseEnum,
  parseRecord,
} from './storeParsers';

describe('parseString', () => {
  it('returns the string unchanged when type matches', () => {
    expect(parseString('hello')).toBe('hello');
    expect(parseString('')).toBe('');
  });

  it.each([null, undefined, 42, true, [], {}, () => {}])(
    'returns undefined for non-string %p',
    (v) => {
      expect(parseString(v)).toBeUndefined();
    },
  );
});

describe('parseBoolean', () => {
  it('returns the boolean unchanged when type matches', () => {
    expect(parseBoolean(true)).toBe(true);
    expect(parseBoolean(false)).toBe(false);
  });

  it.each([null, undefined, 0, 1, 'true', 'false', [], {}])(
    'returns undefined for non-boolean %p',
    (v) => {
      expect(parseBoolean(v)).toBeUndefined();
    },
  );
});

describe('parseStringArray', () => {
  it('returns the array when every element is a string', () => {
    expect(parseStringArray([])).toEqual([]);
    expect(parseStringArray(['a', 'b'])).toEqual(['a', 'b']);
  });

  it.each([null, undefined, 'abc', 42, {}, [1, 2], ['a', 1], [null]])(
    'returns undefined for non-string-array %p',
    (v) => {
      expect(parseStringArray(v)).toBeUndefined();
    },
  );
});

describe('parseEnum', () => {
  const options = ['tree', 'systems'] as const;

  it('returns the value when it matches an allowed option', () => {
    expect(parseEnum('tree', options)).toBe('tree');
    expect(parseEnum('systems', options)).toBe('systems');
  });

  it.each(['nope', '', 'TREE', null, undefined, 42, true])(
    'returns undefined for disallowed value %p',
    (v) => {
      expect(parseEnum(v, options)).toBeUndefined();
    },
  );

  it('preserves the literal type via the const-array param', () => {
    const v: 'tree' | 'systems' | undefined = parseEnum('tree', options);
    expect(v).toBe('tree');
  });
});

describe('parseRecord', () => {
  it('returns the object when shape matches', () => {
    expect(parseRecord({})).toEqual({});
    expect(parseRecord({ a: 1 })).toEqual({ a: 1 });
  });

  it.each([null, undefined, 'abc', 42, [], [1, 2], true])(
    'returns undefined for non-record %p',
    (v) => {
      expect(parseRecord(v)).toBeUndefined();
    },
  );
});
