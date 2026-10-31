// Augury's formulas (docs/roadmap/2026-10-30-augury-design.md §4). A formula
// is terms joined by + or -: `NdY`, `dY` or a whole number. Rolling draws
// from crypto.getRandomValues with rejection sampling, so no face is likelier
// than another.

export const MAX_DICE = 100;
export const MIN_SIZE = 2;
export const MAX_SIZE = 1000;
export const MAX_NUMBER = 999;

/** A dice term from a pigmented pad carries the pigment, so two pads of
 *  the same die stay two terms (design §8); the field's text doesn't show
 *  it, and a term typed by hand has none. */
export type Term =
  | { kind: 'dice'; sign: 1 | -1; count: number; size: number; pigment?: string }
  | { kind: 'number'; sign: 1 | -1; value: number };

/** Roll the formula twice and keep the higher total, or the lower. */
export type Edge = 'advantage' | 'disadvantage';

export interface Roll {
  terms: Term[];
  /** Each term's faces in roll order; empty for a number. */
  faces: number[][];
  total: number;
  /** The least and the greatest the formula can make. */
  min: number;
  max: number;
}

/** What a roll shows: the roll kept, and under an edge the one dropped. */
export interface Outcome {
  kept: Roll;
  dropped: Roll | null;
}

// One term with the spaces round it, its sign optional: the first term's may
// be left out. Spaces sit between tokens, never inside one, so `2d6 3` is
// two terms with no sign between them rather than `2d63`.
const TERM = /\s*([+-])?\s*(?:(\d*)d(\d+)|(\d+))\s*/iy;

/** The formula's terms, [] for an empty one, or null when it doesn't read or
 *  breaks a limit. `D` reads as `d`. */
export function parseFormula(text: string): Term[] | null {
  if (text.trim() === '') return [];
  const terms: Term[] = [];
  let dice = 0;
  let at = 0;
  while (at < text.length) {
    TERM.lastIndex = at;
    const match = TERM.exec(text);
    if (!match) return null;
    const [whole, signText, countText, sizeText, numberText] = match;
    if (!signText && terms.length > 0) return null;
    const sign = signText === '-' ? -1 : 1;
    if (numberText !== undefined) {
      const value = Number(numberText);
      if (value > MAX_NUMBER) return null;
      terms.push({ kind: 'number', sign, value });
    } else {
      const count = countText === '' ? 1 : Number(countText);
      const size = Number(sizeText);
      if (count < 1 || size < MIN_SIZE || size > MAX_SIZE) return null;
      dice += count;
      if (dice > MAX_DICE) return null;
      terms.push({ kind: 'dice', sign, count, size });
    }
    at += whole.length;
  }
  return terms;
}

/** The terms written back as a formula: `3d6+1d20-2`. */
export function formatFormula(terms: Term[]): string {
  return terms
    .map((t, i) => {
      const sign = t.sign < 0 ? '-' : i > 0 ? '+' : '';
      return sign + (t.kind === 'dice' ? `${t.count}d${t.size}` : String(t.value));
    })
    .join('');
}

const samePad = (t: Term, size: number, pigment: string | undefined) =>
  t.kind === 'dice' && t.size === size && t.pigment === pigment;

/** A pad's count: the dice of its size and pigment the formula adds, less
 *  those it takes away. */
export function diceOf(terms: Term[], size: number, pigment?: string): number {
  return terms.reduce((n, t) => (t.kind === 'dice' && samePad(t, size, pigment) ? n + t.sign * t.count : n), 0);
}

/** The formula's numbers summed: the ±1 pad's count. */
export function numberOf(terms: Term[]): number {
  return terms.reduce((n, t) => (t.kind === 'number' ? n + t.sign * t.value : n), 0);
}

/** A pad's press (`by` 1) or right-click (-1): its count moved by one die.
 *  A term of its size running the other way shrinks first, so each undoes
 *  the other; past zero a term running this way grows, or starts at the
 *  end. Null once the formula holds MAX_DICE. */
export function stepDie(terms: Term[], size: number, by: 1 | -1, pigment?: string): Term[] | null {
  const along = (sign: number) => terms.findIndex((t) => samePad(t, size, pigment) && t.sign === sign);
  const back = along(-by);
  if (back >= 0) {
    const t = terms[back] as Extract<Term, { kind: 'dice' }>;
    return t.count > 1
      ? terms.map((u, i) => (i === back ? { ...t, count: t.count - 1 } : u))
      : terms.filter((_, i) => i !== back);
  }
  if (terms.reduce((n, t) => (t.kind === 'dice' ? n + t.count : n), 0) >= MAX_DICE) return null;
  const at = along(by);
  if (at < 0) return [...terms, { kind: 'dice', sign: by, count: 1, size, ...(pigment ? { pigment } : {}) }];
  return terms.map((u, i) => (i === at && u.kind === 'dice' ? { ...u, count: u.count + 1 } : u));
}

/** The formula as typed, with each dice term keeping the pigment of the
 *  term it stands in for: the same place among the dice terms, the same
 *  die and sign. A typed `+1d6` stays plain. */
export function reattach(typed: Term[], was: Term[]): Term[] {
  const before = was.filter((t) => t.kind === 'dice');
  let next = 0;
  return typed.map((t) => {
    if (t.kind !== 'dice') return t;
    const old = before[next++];
    return old?.kind === 'dice' && old.pigment && old.size === t.size && old.sign === t.sign ? { ...t, pigment: old.pigment } : t;
  });
}

/** The ±1 pad: the formula's last number moved by one, dropped at zero,
 *  or a new number at the end. Null past MAX_NUMBER. */
export function bump(terms: Term[], by: 1 | -1): Term[] | null {
  let at = -1;
  terms.forEach((t, i) => {
    if (t.kind === 'number') at = i;
  });
  if (at < 0) return [...terms, { kind: 'number', sign: by, value: 1 }];
  const t = terms[at] as Extract<Term, { kind: 'number' }>;
  const value = t.sign * t.value + by;
  if (Math.abs(value) > MAX_NUMBER) return null;
  if (value === 0) return terms.filter((_, i) => i !== at);
  return terms.map((u, i) => (i === at ? { kind: 'number', sign: value < 0 ? -1 : 1, value: Math.abs(value) } : u));
}

export function bounds(terms: Term[]): { min: number; max: number } {
  let min = 0;
  let max = 0;
  for (const t of terms) {
    if (t.kind === 'number') {
      min += t.sign * t.value;
      max += t.sign * t.value;
    } else if (t.sign > 0) {
      min += t.count;
      max += t.count * t.size;
    } else {
      min -= t.count * t.size;
      max -= t.count;
    }
  }
  return { min, max };
}

/** A face from 1 to `sides`, each as likely: a draw at or past the largest
 *  multiple of `sides` under 2³² is thrown back, so the modulo can't favour
 *  the low faces. */
export function drawFace(sides: number): number {
  const word = new Uint32Array(1);
  const limit = 2 ** 32 - (2 ** 32 % sides);
  do {
    crypto.getRandomValues(word);
  } while (word[0] >= limit);
  return (word[0] % sides) + 1;
}

function figure(terms: Term[], faces: number[][]): Roll {
  const total = terms.reduce(
    (sum, t, i) => sum + t.sign * (t.kind === 'dice' ? faces[i].reduce((a, b) => a + b, 0) : t.value),
    0,
  );
  return { terms, faces, total, ...bounds(terms) };
}

export function roll(terms: Term[], draw: (sides: number) => number = drawFace): Roll {
  return figure(
    terms,
    terms.map((t) => (t.kind === 'dice' ? Array.from({ length: t.count }, () => draw(t.size)) : [])),
  );
}

/** Under an edge the formula rolls twice, and the higher total (advantage)
 *  or the lower (disadvantage) is kept; a tie keeps the first. */
export function rollOutcome(terms: Term[], edge: Edge | null, draw: (sides: number) => number = drawFace): Outcome {
  const first = roll(terms, draw);
  if (!edge) return { kept: first, dropped: null };
  const second = roll(terms, draw);
  const better = edge === 'advantage' ? second.total > first.total : second.total < first.total;
  return better ? { kept: second, dropped: first } : { kept: first, dropped: second };
}

/** A roll's dice under a formula whose numbers alone changed (the ±1 pad
 *  after a roll): the faces stay and the total moves. */
export function refigure(r: Roll, terms: Term[]): Roll {
  const dice = r.faces.filter((_, i) => r.terms[i].kind === 'dice');
  let next = 0;
  return figure(
    terms,
    terms.map((t) => (t.kind === 'dice' ? dice[next++] : [])),
  );
}

/** A word die's face, each as likely (design §7). */
export function pickFace(faces: string[], draw: (sides: number) => number = drawFace): string {
  return faces.length === 1 ? faces[0] : faces[draw(faces.length) - 1];
}

/** How many of the level meter's cells a roll lights: where its total fell
 *  between the least and the greatest. One possible result lights them all. */
export function level(r: Pick<Roll, 'total' | 'min' | 'max'>, cells = 10): number {
  if (r.max === r.min) return cells;
  return Math.round(((r.total - r.min) / (r.max - r.min)) * cells);
}
