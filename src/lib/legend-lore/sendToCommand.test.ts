import { describe, expect, it } from 'vitest';
import { sentNote, targetsFor } from './sendToCommand';
import type { SearchResultItem } from './types';

const hit = (over: Partial<SearchResultItem> = {}): SearchResultItem => ({
  text: '**Fire Drake** breathes fire in a 30-foot cone.',
  filename: 'Dragonbane Monsters.pdf',
  source: '/Books/Dragonbane Monsters.pdf',
  section_heading: '**Fire Drake**',
  page_start: 42,
  page_end: 43,
  game_system: 'Dragonbane',
  relevance: 0.9,
  matched_text: '',
  chunk_text: '',
  section_id: 's1',
  section_path: '',
  page_label_start: '40',
  page_label_end: '41',
  truncated: false,
  also_in: [],
  ...over,
});

describe('sentNote', () => {
  it('names the note after its section and cites the printed pages', () => {
    expect(sentNote(hit())).toEqual({
      name: 'Fire Drake',
      text: '**Fire Drake** breathes fire in a 30-foot cone.',
      source: 'file:///Books/Dragonbane%20Monsters.pdf#page=42',
      cite: 'Dragonbane Monsters, pp.40–41',
    });
  });

  it('falls back to the book for a section without a heading or pages', () => {
    const note = sentNote(hit({ section_heading: '', page_start: 0, page_end: 0, page_label_start: '', page_label_end: '' }));
    expect(note.name).toBe('Dragonbane Monsters');
    expect(note.source).toBe('file:///Books/Dragonbane%20Monsters.pdf');
    expect(note.cite).toBe('Dragonbane Monsters');
  });
});

describe('targetsFor', () => {
  it('offers a note the note tracks and an image the image tracks', () => {
    const targets = { campaign: 'Strahd', tracks: ['NPCs', 'Maps', 'Loot'], kinds: { NPCs: 'note', Maps: 'image' } as const };
    expect(targetsFor(targets, 'note').tracks).toEqual(['NPCs', 'Loot']);
    expect(targetsFor(targets, 'image').tracks).toEqual(['Maps']);
  });
});
