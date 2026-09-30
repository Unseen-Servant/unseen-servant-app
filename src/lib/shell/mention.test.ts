import { describe, expect, test } from 'vitest';
import { mentionAt, removeMention, stripMentions } from './mention';

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
