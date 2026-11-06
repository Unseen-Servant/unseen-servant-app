// Dragging a note from the grid or the shelf onto a beat (design §5.1), as
// Legend Lore drags books onto a collection (legend-lore/dragPayload.ts),
// or onto another track's column to move it there.
// A dragover can read only the drag's types, never its data, so the private
// type is what tells a note drag from the beat column's own reordering; the
// note itself waits here for the drop.

import type { NoteEntry } from './types';

/** Lowercase on purpose: browsers lowercase custom types in `.types`. */
const NOTE_MIME = 'application/x-command-note';
/** A track carried by its nameplate; the data is its name. */
export const TRACK_MIME = 'application/x-command-track';
/** A card carried from the tray or off the board; the data is its note's
 *  path, one a line. */
export const CARD_MIME = 'application/x-command-tray-card';

let current: NoteEntry | null = null;

const carries = (e: DragEvent, type: string) =>
  Array.from(e.dataTransfer?.types ?? []).some((t) => t.toLowerCase() === type);

export const isTrackDrag = (e: DragEvent) => carries(e, TRACK_MIME);
export const isCardDrag = (e: DragEvent) => carries(e, CARD_MIME);

export function startNoteDrag(e: DragEvent, note: NoteEntry) {
  current = note;
  if (!e.dataTransfer) return;
  // Copy onto a beat (it's linked, not moved); move onto another track.
  e.dataTransfer.effectAllowed = 'copyMove';
  e.dataTransfer.setData(NOTE_MIME, note.path);
  // Anywhere else that takes text, a note drops as its link, and an image
  // as its embed, as Obsidian drops one.
  e.dataTransfer.setData('text/plain', `${note.type === 'image' ? '!' : ''}[[${note.name}]]`);
}

export function isNoteDrag(e: DragEvent): boolean {
  return carries(e, NOTE_MIME);
}

export function draggedNote(): NoteEntry | null {
  return current;
}

export function endNoteDrag() {
  current = null;
}

// A board card is Svelte Flow's to drag, and no drag event leaves the board.
// Past its edge the board speaks a card drag's events here (grab.ts speaks
// the same ones for a row), so another tool in the window takes a board
// card as it takes a tray card.

let over: Element | null = null;

function fire(type: string, target: Element, paths: string[], x: number, y: number, related: Element | null = null): boolean {
  const dataTransfer = new DataTransfer();
  dataTransfer.setData(CARD_MIME, paths.join('\n'));
  const init = { bubbles: true, cancelable: true, composed: true, clientX: x, clientY: y, dataTransfer, relatedTarget: related };
  return !target.dispatchEvent(new DragEvent(type, init));
}

/** Cards carried to (x, y): whether what's under the pointer, past the
 *  board's edge, takes them. */
export function carryCards(paths: string[], x: number, y: number): boolean {
  const under = document.elementFromPoint(x, y);
  const past = under && !under.closest('.svelte-flow') ? under : null;
  if (past !== over) {
    if (over) fire('dragleave', over, paths, x, y, past);
    if (past) fire('dragenter', past, paths, x, y, over);
    over = past;
  }
  return !!past && fire('dragover', past, paths, x, y);
}

/** Cards released at (x, y): whether something past the board took them. */
export function dropCards(paths: string[], x: number, y: number): boolean {
  const taken = carryCards(paths, x, y);
  const at = over;
  over = null;
  if (at) fire(taken ? 'drop' : 'dragleave', at, paths, x, y);
  return taken;
}

