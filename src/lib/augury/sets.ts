// The dice sets the browser loads onto the pads (design §6): a die size per
// pad, null for a dark one. Standard and Zocchi are fixed.

import { m } from '../paraglide/messages';

export const PADS = 16;
/** The bottom-right pad of every number set is the ±1 pad, so a set holds
 *  up to 15 dice. */
export const DICE_PADS = PADS - 1;

export interface DiceSet {
  id: string;
  name: () => string;
  pads: (number | null)[];
}

function onPads(sizes: number[]): (number | null)[] {
  return [...sizes, ...Array<null>(DICE_PADS - sizes.length).fill(null)];
}

export const SETS: DiceSet[] = [
  { id: 'standard', name: m.augury_set_standard, pads: onPads([4, 6, 8, 10, 12, 20, 100]) },
  // DCC's dice chain in order, row by row, so a step up or down the chain is
  // the next or previous pad.
  { id: 'zocchi', name: m.augury_set_zocchi, pads: onPads([3, 4, 5, 6, 7, 8, 10, 12, 14, 16, 20, 24, 30, 100]) },
];
