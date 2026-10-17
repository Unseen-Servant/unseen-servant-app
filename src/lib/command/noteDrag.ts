// Dragging a note from the grid or the shelf onto a beat (design §5.1), as
// Legend Lore drags books onto a collection (legend-lore/dragPayload.ts),
// or onto another track's column to move it there.
// A dragover can read only the drag's types, never its data, so the private
// type is what tells a note drag from the beat column's own reordering; the
// note itself waits here for the drop.

import type { NoteEntry } from './types';

/** Lowercase on purpose: browsers lowercase custom types in `.types`. */
const NOTE_MIME = 'application/x-command-note';

let current: NoteEntry | null = null;

export function startNoteDrag(e: DragEvent, note: NoteEntry) {
  current = note;
  if (!e.dataTransfer) return;
  // Copy onto a beat (it's linked, not moved); move onto another track.
  e.dataTransfer.effectAllowed = 'copyMove';
  e.dataTransfer.setData(NOTE_MIME, note.path);
  // Anywhere else that takes text, a note drops as its link.
  e.dataTransfer.setData('text/plain', `[[${note.name}]]`);
}

export function isNoteDrag(e: DragEvent): boolean {
  return Array.from(e.dataTransfer?.types ?? []).some((t) => t.toLowerCase() === NOTE_MIME);
}

export function draggedNote(): NoteEntry | null {
  return current;
}

export function endNoteDrag() {
  current = null;
}
