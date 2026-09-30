import { describe, expect, test } from 'vitest';
import { holdsQuery, mentionAt, removeMention, searchText, stripMentions, viewFilter } from './mention';

describe('mentionAt', () => {
  test('finds the @-word around the caret', () => {
    expect(mentionAt('troll @mon', 10)).toEqual({ start: 6, end: 10, query: 'mon' });
    expect(mentionAt('@mon troll', 2)).toEqual({ start: 0, end: 4, query: 'mon' });
    expect(mentionAt('troll @', 7)).toEqual({ start: 6, end: 7, query: '' });
  });

  test('null when the caret is in a plain word or past the mention', () => {
    expect(mentionAt('troll @mon', 3)).toBeNull();
    expect(mentionAt('@mon troll', 10)).toBeNull();
    expect(mentionAt('@mon ', 5)).toBeNull();
  });

  test('an @ inside a word is text, not a mention', () => {
    expect(mentionAt('a@b', 3)).toBeNull();
  });
});

describe('removeMention', () => {
  test('takes one adjacent space with the token', () => {
    expect(removeMention('troll @mon regen', { start: 6, end: 10, query: 'mon' })).toEqual({ value: 'troll regen', caret: 6 });
    expect(removeMention('@mon troll', { start: 0, end: 4, query: 'mon' })).toEqual({ value: 'troll', caret: 0 });
    expect(removeMention('troll @mon', { start: 6, end: 10, query: 'mon' })).toEqual({ value: 'troll ', caret: 6 });
  });
});

describe('stripMentions', () => {
  test('removes every @-word, leaving the query as if they were never typed', () => {
    expect(stripMentions('@mon troll @sp regen')).toBe('troll regen');
    expect(stripMentions('troll @')).toBe('troll ');
    expect(stripMentions('troll')).toBe('troll');
  });

  test('typing or picking a mention leaves the stripped query unchanged', () => {
    expect(stripMentions('troll @mon')).toBe(stripMentions('troll '));
    expect(stripMentions('@mon troll')).toBe(stripMentions('troll'));
  });

  test('leaves mid-word @ alone', () => {
    expect(stripMentions('a@b c')).toBe('a@b c');
  });
});

describe('holdsQuery', () => {
  test('false for an empty bar, whitespace, or @-words alone', () => {
    expect(holdsQuery('')).toBe(false);
    expect(holdsQuery('   ')).toBe(false);
    expect(holdsQuery('@')).toBe(false);
    expect(holdsQuery('@mon')).toBe(false);
    expect(holdsQuery('@mon @sp ')).toBe(false);
  });

  test('true once a word outside an @-word is typed', () => {
    expect(holdsQuery('t')).toBe(true);
    expect(holdsQuery('@mon troll')).toBe(true);
    expect(holdsQuery('troll @mon')).toBe(true);
    expect(holdsQuery('a@b')).toBe(true);
  });

  test('false while the bar is a / filter', () => {
    expect(holdsQuery('/')).toBe(false);
    expect(holdsQuery('/dragon')).toBe(false);
    expect(holdsQuery('@mon /dragon')).toBe(false);
  });
});

describe('viewFilter', () => {
  test('a leading / makes the rest of the bar a filter', () => {
    expect(viewFilter('/')).toBe('');
    expect(viewFilter('/dragon mag')).toBe('dragon mag');
    expect(viewFilter('  /dragon')).toBe('dragon');
  });

  test('@-words are not part of the filter, wherever they sit', () => {
    expect(viewFilter('/dragon @mon')).toBe('dragon ');
    expect(viewFilter('@mon /dragon')).toBe('dragon');
  });

  test('null for a search, including a / inside it', () => {
    expect(viewFilter('')).toBeNull();
    expect(viewFilter('troll')).toBeNull();
    expect(viewFilter('1/2 cover')).toBeNull();
    expect(viewFilter('troll /regen')).toBeNull();
  });
});

describe('searchText', () => {
  test('the query without @-words, or nothing for a filter', () => {
    expect(searchText('troll @mon')).toBe('troll ');
    expect(searchText('/dragon')).toBe('');
    expect(searchText('@mon /dragon')).toBe('');
  });
});
