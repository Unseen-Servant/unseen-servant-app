// Which hand raised the last interaction — a keypress or a pointer.
//
// The confirm prompt asks so it can decide whether auto-focusing a decision
// button means anything. Raised from a context-menu click there is a mouse
// user in front of it, and ringing a button they never asked to focus reads
// as a stray highlight — the same rule the panes already follow, where
// nothing is ringed until the user actually navigates. Raised by a chord
// there is a keyboard user, who needs the ring to know what Enter will do.
//
// :focus-visible cannot answer this on its own: a programmatic .focus() does
// not match it when the preceding interaction was a click, so the dialog is
// left choosing between painting the ring always or never.
//
// Capture phase because rows stop propagation on their own pointer handlers.

export interface InputModality {
  /** True when the most recent interaction was a keypress. */
  lastWasKeyboard(): boolean;
  /** Detach the listeners. */
  stop(): void;
}

const MODIFIERS = new Set(['Shift', 'Control', 'Alt', 'Meta']);

export function trackInputModality(target: EventTarget): InputModality {
  let keyboard = false;

  const onKeyDown = (event: Event) => {
    if (!MODIFIERS.has((event as KeyboardEvent).key)) keyboard = true;
  };
  const onPointerDown = () => {
    keyboard = false;
  };

  const options = { capture: true };
  target.addEventListener('keydown', onKeyDown, options);
  target.addEventListener('pointerdown', onPointerDown, options);

  return {
    lastWasKeyboard: () => keyboard,
    stop() {
      target.removeEventListener('keydown', onKeyDown, options);
      target.removeEventListener('pointerdown', onPointerDown, options);
    },
  };
}
