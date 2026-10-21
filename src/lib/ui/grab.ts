// Dragging by hand: rows, plates and books carried with a closed hand.
//
// A native drag hands the cursor to macOS, which draws its arrow or green
// copy badge whatever CSS asks, so drags here are driven by the pointer
// instead. The drop targets don't know: the drag still speaks in the
// browser's own events (dragstart on the source, dragenter, dragover and
// dragleave on what's under the pointer, drop where a dragover was taken,
// dragend on the source), built by hand around a DataTransfer of its own.
// Each surface keeps its handlers, its private types and its rules for
// what lands where.
//
// As a native drag: it starts a few pixels from the press, a dragstart
// whose default is prevented refuses it, a translucent copy of the source
// follows the pointer, hover stays on the source until the drop, Esc
// cancels, and an editable spot (CodeMirror) takes the text/plain drop
// without a dragover of its own.

const THRESHOLD = 4;
/** WebKit's own drag image is about this see-through. */
const GHOST_OPACITY = '0.75';

interface Drag {
  source: HTMLElement;
  pointerId: number;
  data: DataTransfer;
  ghost: HTMLElement;
  /** The press's offset into the source, so the copy rides where it was taken. */
  dx: number;
  dy: number;
  x: number;
  y: number;
  over: Element | null;
  accepted: boolean;
}

let drag: Drag | null = null;

function fire(type: string, target: EventTarget, d: Pick<Drag, 'x' | 'y' | 'data'>, related: Element | null = null): DragEvent {
  const e = new DragEvent(type, {
    bubbles: true,
    cancelable: type !== 'dragleave' && type !== 'dragend',
    composed: true,
    clientX: d.x,
    clientY: d.y,
    dataTransfer: d.data,
    relatedTarget: related,
  });
  target.dispatchEvent(e);
  return e;
}

/** Where the browser would take the drop itself: text into an editable spot. */
function takesText(el: Element, data: DataTransfer): boolean {
  return el instanceof HTMLElement && el.isContentEditable && data.types.includes('text/plain');
}

/** The source as its drag image: a copy at its place and size, stripped of
 *  what other code finds rows by, letting the pointer through. A snapshot:
 *  it moves as the pointer does, not on the source's hover transition (a
 *  key's `transition: all` had it swimming behind the hand), and its text
 *  never reflows — set to its measured width, WebKit can still break a
 *  line a hair short of it. */
function ghostOf(source: HTMLElement): HTMLElement {
  const box = source.getBoundingClientRect();
  const ghost = source.cloneNode(true) as HTMLElement;
  for (const el of [ghost, ...ghost.querySelectorAll('*')]) {
    el.removeAttribute('id');
    for (const a of [...el.attributes]) if (a.name.startsWith('data-')) el.removeAttribute(a.name);
  }
  ghost.setAttribute('aria-hidden', 'true');
  Object.assign(ghost.style, {
    position: 'fixed',
    left: '0',
    top: '0',
    width: `${box.width}px`,
    height: `${box.height}px`,
    margin: '0',
    boxSizing: 'border-box',
    whiteSpace: 'nowrap',
    transition: 'none',
    opacity: GHOST_OPACITY,
    pointerEvents: 'none',
    zIndex: '10000',
  });
  document.body.appendChild(ghost);
  return ghost;
}

function follow(d: Drag, x: number, y: number) {
  d.x = x;
  d.y = y;
  d.ghost.style.transform = `translate(${x - d.dx}px, ${y - d.dy}px)`;
  const under = document.elementFromPoint(x, y);
  if (under !== d.over) {
    if (under) fire('dragenter', under, d, d.over);
    if (d.over) fire('dragleave', d.over, d, under);
    d.over = under;
  }
  d.accepted = !!under && (fire('dragover', under, d).defaultPrevented || takesText(under, d.data));
}

const onMove = (e: PointerEvent) => {
  if (drag && e.pointerId === drag.pointerId) follow(drag, e.clientX, e.clientY);
};

const onUp = (e: PointerEvent) => {
  if (!drag || e.pointerId !== drag.pointerId) return;
  follow(drag, e.clientX, e.clientY);
  const d = drag;
  const dropped = d.over && d.accepted ? d.over : null;
  if (dropped) fire('drop', dropped, d);
  else if (d.over) fire('dragleave', d.over, d);
  finish(d);
  swallowClick();
};

const onCancel = () => {
  if (!drag) return;
  if (drag.over) fire('dragleave', drag.over, drag);
  finish(drag);
};

// A native drag keeps Esc from the page; so does this one. The button is
// still down: its release ends nothing, so it clicks nothing either.
const onKey = (e: KeyboardEvent) => {
  if (e.key !== 'Escape') return;
  e.preventDefault();
  e.stopImmediatePropagation();
  onCancel();
  window.addEventListener('pointerup', swallowClick, { capture: true, once: true });
  // Released outside the window, that pointerup never comes: the next
  // press mustn't lose its click to it.
  window.addEventListener('pointerdown', () => window.removeEventListener('pointerup', swallowClick, { capture: true }), {
    capture: true,
    once: true,
  });
};

function swallow(e: Event) {
  e.preventDefault();
  e.stopImmediatePropagation();
}

/** The release would click whatever it landed on, or the row it left. */
function swallowClick() {
  window.addEventListener('click', swallow, { capture: true, once: true });
  setTimeout(() => window.removeEventListener('click', swallow, { capture: true }));
}

function finish(d: Drag) {
  drag = null;
  d.ghost.remove();
  document.documentElement.classList.remove('grabbing');
  window.removeEventListener('pointermove', onMove);
  window.removeEventListener('pointerup', onUp);
  window.removeEventListener('pointercancel', onCancel);
  window.removeEventListener('blur', onCancel);
  window.removeEventListener('keydown', onKey, true);
  if (d.source.hasPointerCapture?.(d.pointerId)) d.source.releasePointerCapture(d.pointerId);
  fire('dragend', d.source, d);
  // A source the drop re-rendered away is no longer under the window.
  if (!d.source.isConnected) fire('dragend', window, d);
}

function begin(source: HTMLElement, press: PointerEvent, now: PointerEvent) {
  const data = new DataTransfer();
  if (fire('dragstart', source, { x: press.clientX, y: press.clientY, data }).defaultPrevented) return;
  const box = source.getBoundingClientRect();
  drag = {
    source,
    pointerId: press.pointerId,
    data,
    ghost: ghostOf(source),
    dx: press.clientX - box.left,
    dy: press.clientY - box.top,
    x: press.clientX,
    y: press.clientY,
    over: null,
    accepted: false,
  };
  // Captured, the pointer leaves hover on the source, as a native drag does.
  try {
    source.setPointerCapture(press.pointerId);
  } catch {
    // The pointer is already gone; pointerup ends the drag anyway.
  }
  document.documentElement.classList.add('grabbing');
  window.addEventListener('pointermove', onMove);
  window.addEventListener('pointerup', onUp);
  window.addEventListener('pointercancel', onCancel);
  window.addEventListener('blur', onCancel);
  window.addEventListener('keydown', onKey, true);
  follow(drag, now.clientX, now.clientY);
}

/** `use:grab={enabled}`: the element drags by hand; its `on:dragstart`
 *  fills the drag's DataTransfer, or prevents the default to refuse it. */
export function grab(node: HTMLElement, enabled: boolean = true) {
  function press(e: PointerEvent) {
    // A Ctrl-click is the Mac's right-click.
    if (!enabled || drag || e.button !== 0 || e.ctrlKey) return;
    const pending = (m: PointerEvent) => {
      if (m.pointerId !== e.pointerId) return;
      if (Math.hypot(m.clientX - e.clientX, m.clientY - e.clientY) < THRESHOLD) return;
      stop();
      begin(node, e, m);
    };
    const stop = () => {
      window.removeEventListener('pointermove', pending);
      window.removeEventListener('pointerup', stop);
      window.removeEventListener('pointercancel', stop);
    };
    window.addEventListener('pointermove', pending);
    window.addEventListener('pointerup', stop);
    window.addEventListener('pointercancel', stop);
  }

  node.addEventListener('pointerdown', press);
  return {
    update(next: boolean = true) {
      enabled = next;
    },
    destroy() {
      node.removeEventListener('pointerdown', press);
    },
  };
}
