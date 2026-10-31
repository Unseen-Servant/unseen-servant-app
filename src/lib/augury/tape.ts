// Augury's tape (design §13): each roll as it leaves the readout, newest on
// top, as a printing calculator's paper keeps them. Kept in the panel, not
// saved.

import type { Edge, Outcome } from './dice';
import type { WordPad } from './sets';

export const TAPE_LINES = 50;

export type TapeLine =
  | { id: number; kind: 'dice'; edge: Edge | null; outcome: Outcome }
  | { id: number; kind: 'word'; die: WordPad; face: string };

/** The tape with a line printed on top; the oldest falls off past
 *  TAPE_LINES. */
export function print(tape: TapeLine[], line: TapeLine): TapeLine[] {
  return [line, ...tape].slice(0, TAPE_LINES);
}
