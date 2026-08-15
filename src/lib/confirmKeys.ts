// Which key a confirmation's commit switch wears, and answers to.
//
// The split is the design's safety mechanism, not a style choice:
//
// - An **activation** prompt (re-index — nothing is destroyed) keeps focus
//   on its commit button, so Enter is handled natively by the button.
//   `isCommitChord` therefore never matches for one: a dialog-level Enter
//   listener is exactly what made Cancel unsafe (F1 in the modal audit),
//   and it must not come back.
// - A **removal** prompt focuses the dialog element itself, so Enter has no
//   button to activate and is inert. It commits on the delete chord —
//   the key that raised the deletion is the key that commits it.
//
// See docs/frontend/2026-08-12-modal-rack-units-design.md#the-keyboard.

import { isDeleteChord, type ChordEvent } from './keybindings';

/** The binding id for this prompt's commit switch. */
export function commitKeyId(danger: boolean): 'confirm.commit' | 'confirm.commitSafe' {
  return danger ? 'confirm.commit' : 'confirm.commitSafe';
}

/**
 * True when this keydown should fire the commit.
 *
 * `mac` is forwarded straight to `isDeleteChord` rather than read from a
 * closed-over constant: `isMac` is module-private to keybindings.ts and not
 * exported, so this module has no way to default to it directly. Omitting
 * `mac` here (as the dialog does, calling with two arguments) falls through
 * to `isDeleteChord`'s own default.
 *
 * After the `danger &&` guard this is one line — the kind of wrapper
 * CLAUDE.md's "no abstractions for single-use code" rule would normally
 * have inlined into the caller. It survives because the caller is
 * `ConfirmDialog.svelte`, and this repo has no jsdom, so that component can
 * never be unit-tested. This function is the only place the F1 property —
 * never commit on Enter when `danger` is false — can be asserted by an
 * automated test at all.
 */
export function isCommitChord(event: ChordEvent, danger: boolean, mac?: boolean): boolean {
  return danger && isDeleteChord(event, mac);
}
