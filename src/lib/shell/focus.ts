// What every window-level key handler asks before it acts, answered once
// for both tools so they agree: is the user typing, and is a dialog up.

import { get } from 'svelte/store';
import { openDialogs } from './dialogStack';

// A text field, a select, or an editor: CodeMirror's content is
// contenteditable, and its wrapper is matched too for keys that land on
// its gutter or panels. Walked up from the target, so a key from inside a
// contenteditable's children counts as typing.
const TYPING = 'input, textarea, select, [contenteditable], .cm-editor';

/** True when the keystroke belongs to the field under it. */
export function isTyping(target: EventTarget | null): boolean {
  return target instanceof Element && target.closest(TYPING) !== null;
}

/** True while a modal dialog is up. Keydown bubbles through a modal to the
 *  window, past the inerted page, so window handlers stand down on this.
 *  Read from the dialog stack, which Modal registers on as it opens, not
 *  from the DOM, which flushes a microtask behind the state. */
export function dialogOpen(): boolean {
  return get(openDialogs) > 0;
}
