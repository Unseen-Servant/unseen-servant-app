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

/** The curation axis's two-value domain: every indexed file is either in
 * some collection ('collected') or in none ('loose'). */
export type CurationKey = 'collected' | 'loose';

/** Resolve the curation axis (Collected/Loose solos and mutes) to a
 * source-path include-list.
 *
 * Same DAW semantics as the other axes: solo active → only files in a
 * soloed bucket pass, mutes overridden. Mute active → files outside every
 * muted bucket pass. No narrowing → null. An empty array means nothing
 * survives. The caller intersects the result with the collection axis
 * (axes intersect; the backend takes one `source_paths` list). */
export function searchCurationFilter(
  soloed: Set<CurationKey>,
  muted: Set<CurationKey>,
  collectedPaths: Set<string>,
  allIndexed: Iterable<string>
): string[] | null {
  if (soloed.size === 0 && muted.size === 0) return null;
  const passes = (bucket: CurationKey) =>
    soloed.size > 0 ? soloed.has(bucket) : !muted.has(bucket);
  const out: string[] = [];
  for (const p of allIndexed) {
    if (passes(collectedPaths.has(p) ? 'collected' : 'loose')) out.push(p);
  }
  return out;
}

/** A folder, file, or collection narrowing on the collection axis. */
export interface ScopeRef {
  kind: 'folder' | 'file';
  label: string;
}

/** Resolve the collection axis (folder/file/collection solos and mutes)
 * to the backend's `source_paths` include-list.
 *
 * Same DAW semantics as the systems axis: any solo active → the union of
 * the soloed file-sets passes, mutes overridden (solos union within an
 * axis; axes intersect because the backend ANDs `source_paths` with the
 * `game_systems` filter). Mutes only → every indexed file outside the
 * muted union. No narrowing → null. An empty array means nothing
 * survives the narrowing. */
export function searchSourcePathsFilter(
  soloSets: string[][],
  muteSets: string[][],
  allIndexed: Iterable<string>
): string[] | null {
  if (soloSets.length > 0) {
    return [...new Set(soloSets.flat())];
  }
  if (muteSets.length === 0) return null;
  const muted = new Set(muteSets.flat());
  const out: string[] = [];
  for (const p of allIndexed) {
    if (!muted.has(p)) out.push(p);
  }
  return out;
}
