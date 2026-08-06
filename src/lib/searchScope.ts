// Search-scope filter resolution (issue #307).
//
// Chunks from files with no game-system tag store `game_system:
// "unknown"` in the backend, so the search include-list must name that
// bucket explicitly — omitting it silently drops every untagged file
// (homebrew, indie, French books) the moment any one system is muted.

export const UNTAGGED_KEY = 'unknown';

/** Display name for the untagged bucket. The backend key stays 'unknown'. */
export function displaySystem(tag: string): string {
  return tag === UNTAGGED_KEY ? 'untagged' : tag;
}

/** Resolve solo/mute state to the backend's `game_systems` include-list.
 *
 * DAW semantics: solo active → only solo'd systems pass (mute is
 * overridden, and untagged files don't pass — solo means "focus on
 * these systems"). Mute active → every non-muted system passes, plus
 * the untagged bucket unless it was muted itself. No narrowing → null.
 * An empty array means everything is filtered out. */
export function searchGameSystemsFilter(
  soloed: Set<string>,
  excluded: Set<string>,
  allTags: string[]
): string[] | null {
  if (soloed.size > 0) return Array.from(soloed);
  if (excluded.size === 0) return null;
  const include = allTags.filter((t) => !excluded.has(t));
  if (!excluded.has(UNTAGGED_KEY)) include.push(UNTAGGED_KEY);
  return include;
}
