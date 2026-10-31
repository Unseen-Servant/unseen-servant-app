import { describe, expect, test } from 'vitest';
import { allSets, DICE_PADS, newSet, ORACLE, padFromEntry, parseSets, TRACKS, type CustomSet, type Pad } from './sets';

const OCHRE = '#e6c667';

describe('the browser', () => {
  test('lists the fixed sets, Oracle, Tracks, then the GM’s, each with fifteen pads', () => {
    const custom: CustomSet = { id: 'custom-1', name: 'Duality', pads: Array(DICE_PADS).fill(null) };
    const sets = allSets({ custom: [custom] });
    expect(sets.map((s) => s.id)).toEqual(['standard', 'zocchi', ORACLE, TRACKS, 'custom-1']);
    expect(sets.every((s) => s.pads.length === DICE_PADS)).toBe(true);
    expect(sets.map((s) => [s.editable, s.bonus])).toEqual([
      [false, true],
      [false, true],
      [false, false],
      [false, false],
      [true, true],
    ]);
  });

  test('each track is a word die of its unspent notes, in its pigment', () => {
    const open = [
      { name: 'NPCs', pigment: OCHRE, notes: ['Ireena', 'Ismark'] },
      { name: 'Secrets', pigment: null, notes: [] },
    ];
    const pads = allSets({ custom: [] }, open)[3].pads;
    expect(pads.slice(0, 3)).toEqual([
      { kind: 'word', name: 'NPCs', faces: ['Ireena', 'Ismark'], pigment: OCHRE },
      { kind: 'word', name: 'Secrets', faces: [] },
      null,
    ]);
  });

  test('Oracle holds its four word dice', () => {
    const oracle = allSets({ custom: [] })[2];
    const words = oracle.pads.filter((p) => p?.kind === 'word');
    expect(words).toHaveLength(4);
    expect(words.every((p) => p?.kind === 'word' && p.faces.length > 1)).toBe(true);
  });

  test('Yes/No is a d12 weighted toward yes', () => {
    const yesNo = allSets({ custom: [] })[2].pads[0];
    const faces = yesNo?.kind === 'word' ? yesNo.faces : [];
    const count = (face: string) => faces.filter((f) => f === face).length;
    expect(faces).toHaveLength(12);
    expect(['Yes, and…', 'Yes', 'Yes, but…', 'No, but…', 'No', 'No, and…'].map(count)).toEqual([1, 3, 3, 2, 2, 1]);
  });

  test('a new set takes the first Custom number free', () => {
    const taken = (name: string): CustomSet => ({ id: name, name, pads: [] });
    expect(newSet([], 'custom-a').name).toBe('Custom 1');
    expect(newSet([taken('Custom 1'), taken('Custom 3')], 'custom-b').name).toBe('Custom 2');
  });
});

describe('a pad’s entry', () => {
  test('a size, with or without its d, is a die', () => {
    expect(padFromEntry('25', null)).toEqual({ pad: { kind: 'die', size: 25 } });
    expect(padFromEntry('D12', null)).toEqual({ pad: { kind: 'die', size: 12 } });
  });

  test('a size out of range, a die begun or a formula is refused', () => {
    expect(padFromEntry('d', null)).toHaveProperty('refused');
    expect(padFromEntry(' D ', null)).toHaveProperty('refused');
    expect(padFromEntry('1', null)).toHaveProperty('refused');
    expect(padFromEntry('1001', null)).toHaveProperty('refused');
    expect(padFromEntry('2d6', null)).toHaveProperty('refused');
  });

  test('other words name a word die, which keeps its faces and pigment when renamed', () => {
    expect(padFromEntry('Weather', null)).toEqual({ pad: { kind: 'word', name: 'Weather', faces: [] } });
    const was: Pad = { kind: 'word', name: 'Mood', faces: ['Calm'], pigment: OCHRE };
    expect(padFromEntry('Temper', was)).toEqual({ pad: { kind: 'word', name: 'Temper', faces: ['Calm'], pigment: OCHRE } });
    expect(padFromEntry('12', was)).toEqual({ pad: { kind: 'die', size: 12, pigment: OCHRE } });
  });
});

describe('parseSets', () => {
  test('reads back what was saved', () => {
    const pads = [{ kind: 'die', size: 12, pigment: OCHRE }, null, { kind: 'word', name: 'Omen', faces: ['Ill', 'Fair'] }];
    const saved = { custom: [{ id: 'custom-1', name: 'Duality', pads }] };
    const got = parseSets(JSON.parse(JSON.stringify(saved)));
    expect(got.custom[0].name).toBe('Duality');
    expect(got.custom[0].pads.slice(0, 3)).toEqual(pads);
    expect(got.custom[0].pads).toHaveLength(DICE_PADS);
  });

  test('a pad that doesn’t read back is empty, and a set that doesn’t is left out', () => {
    const got = parseSets({
      custom: [
        { id: 'standard', name: 'Mine', pads: [] },
        { id: 'custom-2', name: '', pads: [] },
        { id: 'custom-3', name: 'Ok', pads: 'no' },
        {
          id: 'custom-4',
          name: 'Odd',
          pads: [{ kind: 'die', size: 1 }, { kind: 'word', name: ' ', faces: [] }, { kind: 'die', size: 6, pigment: '#ff0000' }],
        },
      ],
    });
    expect(got.custom.map((c) => c.id)).toEqual(['custom-4']);
    expect(got.custom[0].pads.slice(0, 3)).toEqual([null, null, { kind: 'die', size: 6 }]);
  });

  test('anything else is no saved sets', () => {
    expect(parseSets(undefined)).toEqual({ custom: [] });
    expect(parseSets([1, 2])).toEqual({ custom: [] });
  });
});
