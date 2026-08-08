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

/** A folder or file narrowing on the collection axis, keyed by absolute
 * path. Collections themselves narrow through the play/stop transport,
 * which is a plain name-set, not a ScopeRef. */
export interface ScopeRef {
  kind: 'folder' | 'file';
  label: string;
}

/** Resolve the collection axis (folder/file solos and mutes, playing
 * collections' file-sets) to the backend's `source_paths` include-list.
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

/** Resolve the transport layer to the mix — the universe every
 * narrowing axis filters within.
 *
 * base = union of playing collections' indexed files (the whole library
 * when the transport is idle); muted collections' files subtract from
 * the base. Mute wins over play while lit — a playing, muted collection
 * contributes nothing, and a file reached by both a playing and a muted
 * collection is out (mute is a carve on the mix, not a per-track
 * fader). Returns null when the transport is idle and no collection is
 * muted: no mix narrowing, the universe is the whole indexed library. */
export function resolveMix(
  playing: Set<string>,
  mutedNames: Set<string>,
  collections: Record<string, { file_paths: string[] }>,
  allIndexed: Set<string>
): Set<string> | null {
  if (playing.size === 0 && mutedNames.size === 0) return null;
  const base = new Set<string>();
  if (playing.size > 0) {
    for (const name of playing) {
      const col = collections[name];
      if (!col) continue;
      for (const p of col.file_paths) if (allIndexed.has(p)) base.add(p);
    }
  } else {
    for (const p of allIndexed) base.add(p);
  }
  for (const name of mutedNames) {
    const col = collections[name];
    if (!col) continue;
    for (const p of col.file_paths) base.delete(p);
  }
  return base;
}

/** Frontend mirror of the systems-axis include-list semantics for a
 * single file's tags: under solos only soloed systems pass (untagged
 * files never do); under mutes a file passes while it keeps at least
 * one unmuted tag, and untagged files pass unless the Untagged bucket
 * itself is muted (issue #307). */
export function passesSystemsAxis(
  tags: string[],
  soloed: Set<string>,
  muted: Set<string>
): boolean {
  if (soloed.size > 0) return tags.some((t) => soloed.has(t));
  if (tags.length === 0) return !muted.has(UNTAGGED_KEY);
  return tags.some((t) => !muted.has(t));
}
