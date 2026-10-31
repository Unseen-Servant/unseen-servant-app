// The readout's seven-segment digits (design §5), drawn as SVG lamps in a
// 20×36 box: each segment lit, or a dark slot. Not a font — the app has no
// display fonts, and a segment is the lamp idiom already.

export type Segment = 'a' | 'b' | 'c' | 'd' | 'e' | 'f' | 'g';

const W = 20;
const H = 36;
const INSET = 1;
const THICK = 3.4;
const GAP = 0.6;

function points(ps: [number, number][]): string {
  return ps.map(([x, y]) => `${+x.toFixed(2)},${+y.toFixed(2)}`).join(' ');
}

// Mitred bars: each end comes to a point, so neighbours meet on a diagonal.
function across(y: number): string {
  const h = THICK / 2;
  const l = INSET + h + GAP;
  const r = W - INSET - h - GAP;
  return points([[l, y], [l + h, y - h], [r - h, y - h], [r, y], [r - h, y + h], [l + h, y + h]]);
}

function down(x: number, top: number, bottom: number): string {
  const h = THICK / 2;
  return points([[x, top], [x + h, top + h], [x + h, bottom - h], [x, bottom], [x - h, bottom - h], [x - h, top + h]]);
}

const LEFT = INSET + THICK / 2;
const RIGHT = W - INSET - THICK / 2;
const TOP = INSET + THICK / 2;
const MID = H / 2;
const BOTTOM = H - INSET - THICK / 2;

export const DIGIT_VIEWBOX = `0 0 ${W} ${H}`;

export const SEGMENTS: [Segment, string][] = [
  ['a', across(TOP)],
  ['b', down(RIGHT, TOP + GAP, MID - GAP)],
  ['c', down(RIGHT, MID + GAP, BOTTOM - GAP)],
  ['d', across(BOTTOM)],
  ['e', down(LEFT, MID + GAP, BOTTOM - GAP)],
  ['f', down(LEFT, TOP + GAP, MID - GAP)],
  ['g', across(MID)],
];

const LIT: Record<string, string> = {
  '0': 'abcdef',
  '1': 'bc',
  '2': 'abged',
  '3': 'abgcd',
  '4': 'fgbc',
  '5': 'afgcd',
  '6': 'afgedc',
  '7': 'abc',
  '8': 'abcdefg',
  '9': 'abcdfg',
  '-': 'g',
};

/** Whether a segment is lit for a cell's character; '' is a dark cell. */
export function isLit(char: string, segment: Segment): boolean {
  return (LIT[char] ?? '').includes(segment);
}

/** The readout's cells for a total, right-aligned in at least `min` cells:
 *  a digit, '-' or '' for a dark cell. No total is all dark: `888`, unlit. */
export function readoutCells(total: number | null, min = 3): string[] {
  const chars = total === null ? [] : [...String(total)];
  return [...Array<string>(Math.max(0, min - chars.length)).fill(''), ...chars];
}
