// One menu open at a time.
//
// Every popover in the app (the tree context menu, the tag dropdowns, the
// collections sort and context menus) already closes itself on an outside
// window click, but that alone can't keep them exclusive: each opener calls
// stopPropagation, so the click never reaches the incumbent's listener, and a
// right-click fires no click at all. Ownership lives here instead — a menu
// claims the slot as it opens, which closes whoever held it.

let holder: (() => void) | null = null;

/** Claim the single menu slot, closing whatever menu held it. */
export function claimMenuSlot(close: () => void): void {
  const incumbent = holder;
  // Point the slot at the newcomer before evicting: the incumbent's close
  // runs synchronously and releases on its way out, which would otherwise
  // hand back the slot we just took.
  holder = close;
  if (incumbent && incumbent !== close) incumbent();
}

/** Give the slot up. A no-op once another menu has claimed it. */
export function releaseMenuSlot(close: () => void): void {
  if (holder === close) holder = null;
}

/** Whether any menu currently holds the slot. This is the state-based
 * answer to "is a popover open?" — key handlers yield on it instead of
 * querying the DOM for menu class names, which races Svelte's microtask
 * flush in both directions (a menu just opened isn't in the DOM yet; a
 * menu just closed still is). Claims happen synchronously at open and
 * releases at close, so this is current within the same event dispatch. */
export function menuSlotHeld(): boolean {
  return holder !== null;
}
