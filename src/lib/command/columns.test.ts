import { describe, expect, it } from 'vitest';
import { columns, folderOrder, isAmbiguous, linkableNames } from './columns';
import { insertion, openTarget } from './wikilinks';
import type { CampaignIndex, NoteEntry } from './types';

const note = (path: string): NoteEntry => {
  const parts = path.split('/');
  const name = parts[parts.length - 1].replace(/\.md$/, '');
  const folders = parts.slice(0, -1);
  return { name, path, track: folders[0] ?? null, group: folders.slice(1).join('/') || null, spent: null, source: null };
};

const index: CampaignIndex = {
  name: 'Strahd',
  tracks: ['PCs', 'NPCs', 'Locations'],
  notes: [
    'NPCs/Vallaki/Lady Wachter.md',
    'NPCs/Ismark.md',
    'NPCs/ireena.md',
    'NPCs/Barovia/Doru.md',
    'Locations/Tser Pool.md',
    'Beats/Ambush.md',
    'Overview.md',
    'NPCs/Session 10.md',
    'NPCs/Session 9.md',
  ].map(note),
  note_order: {},
  pigments: {},
  ambiguous: ['doru'],
  beats: [],
  sessions: [],
};

describe('columns', () => {
  it('lays out every track in campaign order, empty ones included', () => {
    const cols = columns(index);
    expect(cols.map((c) => [c.track, c.count])).toEqual([
      ['PCs', 0],
      ['NPCs', 6],
      ['Locations', 1],
    ]);
  });

  it('puts notes directly in the track first, then subfolder groups, all by name', () => {
    const npcs = columns(index)[1];
    expect(npcs.groups.map((g) => [g.group, g.notes.map((n) => n.name)])).toEqual([
      [null, ['ireena', 'Ismark', 'Session 9', 'Session 10']],
      ['Barovia', ['Doru']],
      ['Vallaki', ['Lady Wachter']],
    ]);
  });

  it('puts the notes a folder\'s saved order names first, in it, the rest after by name', () => {
    const ordered = { ...index, note_order: { NPCs: ['Session 10', 'ismark', 'Gone'], 'NPCs/Vallaki': [] } };
    const npcs = columns(ordered)[1];
    expect(npcs.groups.map((g) => [g.folder, g.notes.map((n) => n.name)])).toEqual([
      ['NPCs', ['Session 10', 'Ismark', 'ireena', 'Session 9']],
      ['NPCs/Barovia', ['Doru']],
      ['NPCs/Vallaki', ['Lady Wachter']],
    ]);
  });

  it('moves spent notes out of their groups to the track\'s spent list, in grid order', () => {
    const spent = (path: string) => (n: NoteEntry) => (n.path === path ? { ...n, spent: '2026-10-14' } : n);
    const played = {
      ...index,
      notes: index.notes.map(spent('NPCs/Barovia/Doru.md')).map(spent('NPCs/Session 9.md')),
    };
    const npcs = columns(played)[1];
    // Barovia held only Doru: a group with nothing left to play goes.
    expect(npcs.groups.map((g) => [g.group, g.notes.map((n) => n.name)])).toEqual([
      [null, ['ireena', 'Ismark', 'Session 10']],
      ['Vallaki', ['Lady Wachter']],
    ]);
    expect(npcs.spent.map((n) => n.name)).toEqual(['Session 9', 'Doru']);
    expect(npcs.count).toBe(6);
  });

  it('keeps a folder\'s spent notes in its saved order, after the ones dragged', () => {
    const played = {
      ...index,
      notes: index.notes.map((n) => (n.name === 'Ismark' ? { ...n, spent: '2026-10-14' } : n)),
      note_order: { NPCs: ['Ismark', 'Session 10', 'ireena'] },
    };
    const npcs = columns(played)[1];
    expect(folderOrder(npcs, 'NPCs', ['ireena', 'Session 10', 'Session 9'])).toEqual([
      'ireena',
      'Session 10',
      'Session 9',
      'Ismark',
    ]);
    expect(folderOrder(npcs, 'NPCs/Vallaki', ['Lady Wachter'])).toEqual(['Lady Wachter']);
  });

  it('leaves Beats, Sessions and loose notes out of the grid but linkable', () => {
    const inGrid = columns(index).flatMap((c) => c.groups.flatMap((g) => g.notes.map((n) => n.path)));
    expect(inGrid).not.toContain('Beats/Ambush.md');
    expect(inGrid).not.toContain('Overview.md');
    expect(linkableNames(index)).toContain('Ambush');
    expect(linkableNames(index)).toContain('Overview');
  });

  it('flags names more than one note answers to', () => {
    expect(isAmbiguous(index, 'Doru')).toBe(true);
    expect(isAmbiguous(index, 'Ismark')).toBe(false);
  });
});

describe('wikilink completion', () => {
  it('finds the link target being typed', () => {
    expect(openTarget('Brother of [[Ire')).toEqual({ from: 13, typed: 'Ire' });
    expect(openTarget('[[')).toEqual({ from: 2, typed: '' });
  });

  it('stays out of closed links, aliases and headings', () => {
    expect(openTarget('[[Ireena]] and more')).toBeNull();
    expect(openTarget('[[Ireena|sis')).toBeNull();
    expect(openTarget('[[Ireena#Goals')).toBeNull();
    expect(openTarget('no link here')).toBeNull();
  });

  it('closes the link unless the brackets are already there', () => {
    expect(insertion('Ireena', '')).toBe('Ireena]]');
    expect(insertion('Ireena', ']] lives')).toBe('Ireena');
  });
});
