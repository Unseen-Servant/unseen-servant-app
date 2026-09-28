import { readable } from 'svelte/store';

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

// Whether hover may light a row — the panes' half of the same question.
//
// Hover and the keyboard cursor are two pointers at the list, so only the
// hand that last drove gets to paint. A keypress darkens hover; the pointer
// earns it back by pressing or by actually moving. "Actually" matters: an
// arrow scrolls the list under a resting pointer and WebKit follows with a
// move at the same coordinates, which re-enters whatever row slid beneath
// it. Rows keep latching pointerenter as before; this only gates the paint,
// so the row under the pointer is already right when hover comes back.
//
// Moves rather than presses bring it back, unlike trackInputModality: a
// prompt cares who raised it, a pane cares where the hand is now.

export function watchHoverModality(
  target: EventTarget,
  set: (live: boolean) => void,
): () => void {
  let lastX: number | null = null;
  let lastY: number | null = null;

  const onKeyDown = (event: Event) => {
    if (!MODIFIERS.has((event as KeyboardEvent).key)) set(false);
  };
  const onPointerMove = (event: Event) => {
    const { clientX, clientY } = event as PointerEvent;
    if (clientX === lastX && clientY === lastY) return;
    lastX = clientX;
    lastY = clientY;
    set(true);
  };
  const onPointerDown = () => set(true);

  const options = { capture: true };
  target.addEventListener('keydown', onKeyDown, options);
  target.addEventListener('pointermove', onPointerMove, options);
  target.addEventListener('pointerdown', onPointerDown, options);

  return () => {
    target.removeEventListener('keydown', onKeyDown, options);
    target.removeEventListener('pointermove', onPointerMove, options);
    target.removeEventListener('pointerdown', onPointerDown, options);
  };
}

/** True while the pointer is driving; rows gate their latched .hovered on it. */
export const hoverLive = readable(true, (set) => watchHoverModality(window, set));
