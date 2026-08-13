import { isDeleteChord, type ChordEvent } from './keybindings';

/**
 * Which key a confirmation's commit switch wears, and answers to.
 *
 * The split is the design's safety mechanism, not a style choice:
 *
 * - An **activation** prompt (re-index — nothing is destroyed) keeps focus
 *   on its commit button, so Enter is handled natively by the button.
 *   `isCommitChord` therefore never matches for one: a dialog-level Enter
 *   listener is exactly what made Cancel unsafe (F1 in the modal audit),
 *   and it must not come back.
 * - A **removal** prompt focuses the dialog element itself, so Enter has no
 *   button to activate and is inert. It commits on the delete chord —
 *   the key that raised the deletion is the key that commits it.
 *
 * See docs/specs/ui/2026-08-12-modal-rack-units-design.md#the-keyboard.
 */
export function commitKeyId(danger: boolean): 'confirm.commit' | 'confirm.commitSafe' {
  return danger ? 'confirm.commit' : 'confirm.commitSafe';
}

/**
 * True when this keydown should fire the commit. `mac` is a parameter rather
 * than a closed-over constant so tests can exercise both platforms, matching
 * isDeleteChord's own shape.
 */
export function isCommitChord(event: ChordEvent, danger: boolean, mac?: boolean): boolean {
  if (!danger) return false;
  return mac === undefined ? isDeleteChord(event) : isDeleteChord(event, mac);
}
