// The window's one key listener. The hosts hang dispatchKey on the window,
// and whatever wants a key binds a handler here. Handlers are tried in
// binding order; the first to take the key ends the dispatch, with the
// default prevented. Nothing runs while a dialog is up: its keys bubble
// here past the inerted page, and they are the dialog's.
//
// What binds here are the chords that work whichever tool has the
// keyboard: the hosts' own (the shortcut sheet, settings, the rack's
// views) and the ones that make Legend Lore the app's transport. A tool's
// and a pane's own keys still hang on their own window listeners, gated on
// `active` (PANELS.md), until they move here.

import { dialogOpen, inEditor, isTyping } from './focus';
import { menuSlotHeld } from './menuSlot';

export interface KeyContext {
  /** The keystroke belongs to a field (focus.ts). */
  typing: boolean;
  /** It lands in the note editor, whose own chords come first. */
  editor: boolean;
  /** A menu holds the slot (menuSlot.ts). */
  menu: boolean;
}

/** Returns true to take the key. */
export type KeyHandler = (event: KeyboardEvent, ctx: KeyContext) => boolean;

const handlers = new Set<KeyHandler>();

/** Bind a handler for the window's life, or until the returned function
 *  is called. */
export function bindKeys(handler: KeyHandler): () => void {
  handlers.add(handler);
  return () => {
    handlers.delete(handler);
  };
}

export function dispatchKey(event: KeyboardEvent): void {
  if (dialogOpen()) return;
  const ctx: KeyContext = {
    typing: isTyping(event.target),
    editor: inEditor(event.target),
    menu: menuSlotHeld(),
  };
  for (const handler of handlers) {
    if (handler(event, ctx)) {
      event.preventDefault();
      return;
    }
  }
}

/** The chords both hosts answer. `?` and ⌘/ open the shortcut sheet: `?`
 *  on the produced character, so a layout that puts it on another key
 *  still reaches the sheet, and off fields, where it has to type; ⌘/ from
 *  a field too (the one way there from the search bar), but not from the
 *  editor, where it's CodeMirror's comment. ⌘, opens settings. */
export function hostKeys(open: { settings: () => void; shortcuts: () => void }): KeyHandler {
  return (event, ctx) => {
    if (event.altKey) return false;
    const meta = event.metaKey || event.ctrlKey;
    if (event.key === '?' && !meta && !ctx.typing) {
      open.shortcuts();
      return true;
    }
    if (meta && event.key === '/' && !ctx.editor) {
      open.shortcuts();
      return true;
    }
    if (meta && !event.shiftKey && event.key === ',') {
      open.settings();
      return true;
    }
    return false;
  };
}
