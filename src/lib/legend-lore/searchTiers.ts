// Relevance-tier display helpers (issues #306/#310).
//
// Search results carry an ordinal `tier` computed server-side on the
// result's own score scale (cross-encoder sigmoid vs cosine similarity).
// The raw `relevance` number is not a calibrated probability on either
// scale, so the UI renders tiers; the legacy percent mapping survives
// only as a fallback for results from an older sidecar without `tier`.

export type Tier = 'strong' | 'good' | 'weak';

/** One gauge cell per tier: the meter shows exactly what it measures. */
export const GAUGE_CELLS = 3;

const TIER_CELLS: Record<Tier, number> = { strong: 3, good: 2, weak: 1 };
const TIER_LABELS: Record<Tier, string> = {
  strong: 'Strong match',
  good: 'Good match',
  weak: 'Weak match',
};

function isTier(tier: string | undefined): tier is Tier {
  return tier === 'strong' || tier === 'good' || tier === 'weak';
}

export function tierCells(tier: string | undefined, relevance: number): number {
  if (isTier(tier)) return TIER_CELLS[tier];
  if (relevance <= 0) return 0;
  return Math.max(1, Math.min(GAUGE_CELLS, Math.ceil(relevance * GAUGE_CELLS)));
}

export function tierLabel(tier: string | undefined, relevance: number): string {
  if (isTier(tier)) return TIER_LABELS[tier];
  return `${Math.round(relevance * 100)}% match`;
}

/** Index of the first weak result when at least one stronger result
 * precedes it; -1 otherwise (no weak results, all weak, or untiered). */
export function weakDividerIndex(results: { tier?: string }[]): number {
  const first = results.findIndex((r) => r.tier === 'weak');
  if (first <= 0) return -1;
  return results.slice(0, first).some((r) => isTier(r.tier)) ? first : -1;
}

/** True only for a non-empty result list where every result is weak. */
export function allWeak(results: { tier?: string }[]): boolean {
  return results.length > 0 && results.every((r) => r.tier === 'weak');
}
