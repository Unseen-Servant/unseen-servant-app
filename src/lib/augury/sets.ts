// The dice sets the browser loads onto the pads (design §6). Standard,
// Zocchi and Oracle are fixed; Tracks follows the campaign open in Command;
// the GM's own sets keep their pads in the settings store, per machine.

import { PIGMENTS } from '../legend-lore/palette';
import { m } from '../paraglide/messages';
import { parseRecord } from '../shell/storeParsers';
import { MAX_SIZE, MIN_SIZE, parseFormula } from './dice';
import type { DrawTrack } from './tracks';

export const PADS = 16;
/** The bottom-right pad of every number set is the ±1 pad, so a set holds
 *  up to 15 dice. */
export const DICE_PADS = PADS - 1;

/** A pad's die: a size, or a word die's name and faces (design §7). A
 *  pigment tells two pads of the same die apart (§8). */
export type Pad =
  | { kind: 'die'; size: number; pigment?: string }
  | { kind: 'word'; name: string; faces: string[]; pigment?: string };

export type WordPad = Extract<Pad, { kind: 'word' }>;

export interface DiceSet {
  id: string;
  name: () => string;
  pads: (Pad | null)[];
  /** The GM's own sets: the GM edits their pads. */
  editable: boolean;
  /** The ±1 pad in the corner. Oracle's words take no numbers. */
  bonus: boolean;
}

/** A set the GM made, as the store keeps it. */
export interface CustomSet {
  id: string;
  name: string;
  pads: (Pad | null)[];
}

/** What the store keeps: the GM's sets. */
export interface StoredSets {
  custom: CustomSet[];
}

export const ORACLE = 'oracle';
export const TRACKS = 'tracks';

function onPads(pads: (Pad | null)[]): (Pad | null)[] {
  return [...pads, ...Array<null>(Math.max(0, DICE_PADS - pads.length)).fill(null)];
}

const dice = (sizes: number[]) => onPads(sizes.map((size): Pad => ({ kind: 'die', size })));

const STANDARD: DiceSet = {
  id: 'standard',
  name: m.augury_set_standard,
  pads: dice([4, 6, 8, 10, 12, 20, 100]),
  editable: false,
  bonus: true,
};

// DCC's dice chain in order, row by row, so a step up or down the chain is
// the next or previous pad.
const ZOCCHI: DiceSet = {
  id: 'zocchi',
  name: m.augury_set_zocchi,
  pads: dice([3, 4, 5, 6, 7, 8, 10, 12, 14, 16, 20, 24, 30, 100]),
  editable: false,
  bonus: true,
};

// Oracle's word dice are messages, so they translate; a die's faces are one
// message, a face a line. The GM's own word dice go in a set of their own.
function oracle(): (Pad | null)[] {
  const word = (name: () => string, faces: () => string): Pad => ({
    kind: 'word',
    name: name(),
    faces: faces().split('\n'),
  });
  return onPads([
    word(m.augury_oracle_yes_no, m.augury_oracle_yes_no_faces),
    word(m.augury_oracle_weather, m.augury_oracle_weather_faces),
    word(m.augury_oracle_mood, m.augury_oracle_mood_faces),
    word(m.augury_oracle_direction, m.augury_oracle_direction_faces),
  ]);
}

// A track is a word die whose faces are its unspent notes: a press draws one,
// in the track's pigment. The first fifteen tracks, in Command's order.
function tracks(open: DrawTrack[]): (Pad | null)[] {
  return onPads(
    open.slice(0, DICE_PADS).map((t): Pad => ({
      kind: 'word',
      name: t.name,
      faces: t.notes,
      ...(t.pigment ? { pigment: t.pigment } : {}),
    })),
  );
}

/** Every set in the browser's order: the fixed two, Oracle, Tracks, then
 *  the GM's. */
export function allSets(stored: StoredSets, open: DrawTrack[] = []): DiceSet[] {
  return [
    STANDARD,
    ZOCCHI,
    { id: ORACLE, name: m.augury_set_oracle, pads: oracle(), editable: false, bonus: false },
    { id: TRACKS, name: m.augury_set_tracks, pads: tracks(open), editable: false, bonus: false },
    ...stored.custom.map((c) => ({ id: c.id, name: () => c.name, pads: c.pads, editable: true, bonus: true })),
  ];
}

/** A new set of the GM's: empty, named Custom N with the first N free. */
export function newSet(custom: CustomSet[], id: string): CustomSet {
  const names = new Set(custom.map((c) => c.name));
  let n = 1;
  while (names.has(m.augury_custom_name({ n }))) n++;
  return { id, name: m.augury_custom_name({ n }), pads: onPads([]) };
}

/** What a pad's field makes of its entry (design §6): `25` or `d25` is a
 *  die of that size, any other words name a word die. A lone `d` is a die
 *  begun, not a name. A word die keeps its faces when renamed, and any pad
 *  its pigment. A refusal says why. */
export function padFromEntry(text: string, was: Pad | null): { pad: Pad } | { refused: string } {
  const entry = text.trim();
  const pigment = was?.pigment ? { pigment: was.pigment } : {};
  if (/^d$/i.test(entry)) return { refused: m.augury_pad_unfinished_refused() };
  const size = /^d?(\d+)$/i.exec(entry);
  if (size) {
    const n = Number(size[1]);
    if (n < MIN_SIZE || n > MAX_SIZE) return { refused: m.augury_pad_size_refused({ min: MIN_SIZE, max: MAX_SIZE }) };
    return { pad: { kind: 'die', size: n, ...pigment } };
  }
  // A formula would roll as dice when typed, never as this word die.
  if (parseFormula(entry)) return { refused: m.augury_pad_formula_refused() };
  return { pad: { kind: 'word', name: entry, faces: was?.kind === 'word' ? was.faces : [], ...pigment } };
}

/** A pad's text: its die, or its word die's name. */
export function padLabel(pad: Pad): string {
  return pad.kind === 'die' ? `d${pad.size}` : pad.name;
}

// ---- the settings store -----------------------------------------------------

function parsePad(v: unknown): Pad | null {
  const r = parseRecord(v);
  if (!r) return null;
  const pigment = typeof r.pigment === 'string' && PIGMENTS.some((p) => p.hex === r.pigment) ? { pigment: r.pigment } : {};
  if (r.kind === 'die' && typeof r.size === 'number' && Number.isInteger(r.size) && r.size >= MIN_SIZE && r.size <= MAX_SIZE) {
    return { kind: 'die', size: r.size, ...pigment };
  }
  if (r.kind === 'word' && typeof r.name === 'string' && r.name.trim() && Array.isArray(r.faces)) {
    const faces = r.faces.filter((f): f is string => typeof f === 'string' && f.trim() !== '');
    return { kind: 'word', name: r.name.trim(), faces, ...pigment };
  }
  return null;
}

function parsePads(v: unknown): (Pad | null)[] | null {
  return Array.isArray(v) ? onPads(v.slice(0, DICE_PADS).map(parsePad)) : null;
}

/** The sets as saved. A pad that doesn't read back is an empty pad, and a
 *  set that doesn't read back is left out, rather than either breaking the
 *  rest. */
export function parseSets(v: unknown): StoredSets {
  const r = parseRecord(v);
  const custom = (Array.isArray(r?.custom) ? r.custom : []).flatMap((c): CustomSet[] => {
    const rec = parseRecord(c);
    const pads = parsePads(rec?.pads);
    if (!rec || typeof rec.id !== 'string' || !rec.id.startsWith('custom-')) return [];
    if (typeof rec.name !== 'string' || !rec.name.trim() || !pads) return [];
    return [{ id: rec.id, name: rec.name.trim(), pads }];
  });
  return { custom };
}
