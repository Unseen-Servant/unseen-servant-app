// Where a popover lands once it has been measured.
//
// Menus used to clamp against hardcoded size constants that duplicated — or
// quietly contradicted — their own CSS, which put a menu wherever its
// declared ceiling said rather than where its actual content sits. A short
// tag dropdown reserving the full 320px scroll ceiling opened a couple of
// hundred pixels above the badge it belongs to. So: render hidden, measure,
// clamp against the real box, then show.

export interface Point {
  x: number;
  y: number;
}

export interface Size {
  width: number;
  height: number;
}

/** Keep a menu of `size` inside `viewport` while staying as close to `pos` as
 *  it can. `padding` is the breathing room held at every edge. */
export function clampToViewport(
  pos: Point,
  size: Size,
  viewport: Size,
  padding = 8,
): Point {
  // Math.max last: when the menu is bigger than the viewport the far-edge
  // pull goes negative, and anchoring at the near edge shows the top-left —
  // where the rows start — instead of the overhang.
  return {
    x: Math.max(padding, Math.min(pos.x, viewport.width - size.width - padding)),
    y: Math.max(padding, Math.min(pos.y, viewport.height - size.height - padding)),
  };
}
