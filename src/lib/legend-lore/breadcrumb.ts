// Section-path display helpers shared by the result rows and the inspector.

function stripBold(s: string): string {
  return s.replace(/\*\*(.+?)\*\*/g, '$1');
}

/** The sidecar's `A > B > C` heading path, as display segments. */
export function breadcrumbSegments(s: string): string[] {
  return s.split(' > ').map(stripBold).filter(Boolean);
}

/** A segment set in capitals in the source ("MAGIC SWORDS"). The
 * breadcrumb renders these in small caps so they sit level with the
 * mixed-case segments beside them instead of shouting over them. */
export function isAllCaps(s: string): boolean {
  return /\p{Lu}/u.test(s) && s === s.toUpperCase();
}
