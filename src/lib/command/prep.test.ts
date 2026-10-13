import { describe, expect, it } from 'vitest';
import { activeSession, beatOrder, memberPaths, planMoveTo, planRows, sessionNotePaths, unscheduled } from './prep';
import type { CampaignIndex } from './types';

const index: CampaignIndex = {
  name: 'Strahd',
  tracks: ['NPCs'],
  note_order: {},
  ambiguous: [],
  notes: [],
  beats: [
    { name: 'Ambush', path: 'Beats/Ambush.md', spent: null, notes: [
      { link: 'Ismark', path: 'NPCs/Ismark.md' },
      { link: 'Wolves', path: null },
    ] },
    { name: 'Tser Pool', path: 'Beats/Tser Pool.md', spent: null, notes: [{ link: 'Madam Eva', path: 'NPCs/Madam Eva.md' }] },
    { name: 'Played', path: 'Beats/Played.md', spent: '2026-10-04', notes: [] },
    { name: 'Bonegrinder', path: 'Beats/Bonegrinder.md', spent: null, notes: [] },
    { name: 'Abbey', path: 'Beats/Abbey.md', spent: null, notes: [] },
  ],
  sessions: [
    { name: 'Session 12', path: 'Sessions/Session 12.md', date: '2026-10-11', beats: [{ link: 'Played', path: 'Beats/Played.md' }], log: [] },
    { name: 'Session 13', path: 'Sessions/Session 13.md', date: '2026-10-18', beats: [
      { link: 'Ambush', path: 'Beats/Ambush.md' },
      { link: 'Not written yet', path: null },
      { link: 'Tser Pool', path: 'Beats/Tser Pool.md' },
    ], log: [] },
  ],
};

describe('prep', () => {
  it('opens on the session asked for, else the latest', () => {
    expect(activeSession(index, 'Session 12')?.name).toBe('Session 12');
    expect(activeSession(index, null)?.name).toBe('Session 13');
    expect(activeSession(index, 'Gone')?.name).toBe('Session 13');
    expect(activeSession({ ...index, sessions: [] }, null)).toBeNull();
  });

  it('lays the plan out in order, keeping beats not written yet', () => {
    const rows = planRows(index, activeSession(index, null));
    expect(rows.map((r) => [r.at, r.link, r.beat?.path ?? null])).toEqual([
      [0, 'Ambush', 'Beats/Ambush.md'],
      [1, 'Not written yet', null],
      [2, 'Tser Pool', 'Beats/Tser Pool.md'],
    ]);
  });

  it('lists unplanned, unplayed beats as potential scenes, in the campaign\'s order', () => {
    expect(unscheduled(index, activeSession(index, null)).map((b) => b.name)).toEqual(['Bonegrinder', 'Abbey']);
  });

  it('saves the dragged beats first, every other beat after in its place', () => {
    expect(beatOrder(index, ['Abbey', 'Bonegrinder'])).toEqual(['Abbey', 'Bonegrinder', 'Ambush', 'Tser Pool', 'Played']);
  });

  it('turns a drop between plan rows into the position to move to', () => {
    // Plan [A, B, C]; slots 0–3 sit before A, B, C and after C.
    expect(planMoveTo(0, 2)).toBe(1); // A between B and C
    expect(planMoveTo(0, 3)).toBe(2); // A to the end
    expect(planMoveTo(2, 0)).toBe(0); // C to the top
    expect(planMoveTo(1, 1)).toBeNull(); // B dropped just above itself
    expect(planMoveTo(1, 2)).toBeNull(); // or just below
  });

  it('keeps spent beats too when asked', () => {
    expect(unscheduled(index, activeSession(index, null), true).map((b) => b.name)).toEqual(['Played', 'Bonegrinder', 'Abbey']);
  });

  it('marks a beat\'s notes and every note the session holds', () => {
    expect([...memberPaths(index.beats[0])]).toEqual(['NPCs/Ismark.md']);
    expect([...sessionNotePaths(index, activeSession(index, null))].sort()).toEqual(['NPCs/Ismark.md', 'NPCs/Madam Eva.md']);
    expect(memberPaths(null).size).toBe(0);
  });
});
