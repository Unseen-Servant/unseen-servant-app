// The window's one key listener. The hosts hang dispatchKey on the window,
// and whatever wants a key binds a handler here, at a place:
//
//   overlay   a menu or an inline edit, over everything while it's open
//   region    a pane's rows, while that region of that tool has the keyboard
//   tool      a tool's own chords, while it has the keyboard
//   global    whichever tool has it: the hosts' and the app's transport
//
// Handlers are tried a place at a time in that order, in binding order
// within a place, and a region's or a tool's only while it is on the focus
// path (focus.ts). The first to take the key ends the dispatch, with the
// default prevented. Nothing runs while a dialog is up: its keys bubble
// here past the inerted page, and they are the dialog's.
//
// Esc is a ladder these places make: a menu closes first, then a region
// lets go of its caret (a pane) or its arm, then a tool steps its own view
// back, and nothing below sees a key a place above took.

import { get } from 'svelte/store';
import { dialogOpen, focusPath, inEditor, isTyping, type FocusPath } from './focus';
import { menuSlotHeld } from './menuSlot';
import type { PanelId } from './panels';

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

/** Where a handler is bound: a tool's region, a tool, or over or under
 *  them all. */
export type KeyPlace = 'overlay' | 'global' | { tool: PanelId; region?: string };

interface Binding {
  at: KeyPlace;
  handler: KeyHandler;
}

const bindings: Binding[] = [];

/** Bind a handler for the window's life, or until the returned function
 *  is called. */
export function bindKeys(handler: KeyHandler, at: KeyPlace = 'global'): () => void {
  const binding = { at, handler };
  bindings.push(binding);
  return () => {
    const i = bindings.indexOf(binding);
    if (i >= 0) bindings.splice(i, 1);
  };
}

// The order places are tried in; a region before its tool.
function rank(at: KeyPlace): number {
  if (at === 'overlay') return 0;
  if (at === 'global') return 3;
  return at.region === undefined ? 2 : 1;
}

function onPath(at: KeyPlace, path: FocusPath): boolean {
  if (typeof at === 'string') return true;
  return at.tool === path.tool && (at.region === undefined || at.region === path.region);
}

export function dispatchKey(event: KeyboardEvent): void {
  if (dialogOpen()) return;
  const ctx: KeyContext = {
    typing: isTyping(event.target),
    editor: inEditor(event.target),
    menu: menuSlotHeld(),
  };
  const path = get(focusPath);
  for (let place = 0; place <= 3; place++) {
    for (const { at, handler } of bindings) {
      if (rank(at) !== place || !onPath(at, path)) continue;
      if (handler(event, ctx)) {
        event.preventDefault();
        return;
      }
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
