// What every window-level key handler asks before it acts, answered once
// for both tools so they agree: is the user typing, and is a dialog up.

import { get } from 'svelte/store';
import { openDialogs } from './dialogStack';

// A text field, a select, or an editor: CodeMirror's content is
// contenteditable, and its wrapper is matched too for keys that land on
// its gutter or panels. Walked up from the target, so a key from inside a
// contenteditable's children counts as typing.
const TYPING = 'input, textarea, select, [contenteditable], .cm-editor';

// Element.closest from a key's target, which may be the window or the
// document and have no closest at all. Duck-typed rather than instanceof:
// the tests run under node, with no Element.
function within(target: EventTarget | null, selector: string): boolean {
  const el = target as Element | null;
  return !!el && typeof el.closest === 'function' && el.closest(selector) !== null;
}

/** True when the keystroke belongs to the field under it. */
export function isTyping(target: EventTarget | null): boolean {
  return within(target, TYPING);
}

/** True when the keystroke lands in the note editor, whose own chords
 *  (⌘/ comments) outrank the window's. */
export function inEditor(target: EventTarget | null): boolean {
  return within(target, '.cm-editor');
}

/** True while a modal dialog is up. Keydown bubbles through a modal to the
 *  window, past the inerted page, so window handlers stand down on this.
 *  Read from the dialog stack, which Modal registers on as it opens, not
 *  from the DOM, which flushes a microtask behind the state. */
export function dialogOpen(): boolean {
  return get(openDialogs) > 0;
}
