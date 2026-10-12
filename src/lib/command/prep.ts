// What Prep draws from a campaign index (design §5.1): the active session,
// its plan as launcher rows, the beats no plan holds yet, and the marks the
// grid puts on notes for the selected beat and the session.

import type { BeatEntry, CampaignIndex, SessionEntry } from './types';

/** The session named `wanted`, else the latest — what Prep opens on. */
export function activeSession(index: CampaignIndex, wanted: string | null): SessionEntry | null {
  return index.sessions.find((s) => s.name === wanted) ?? index.sessions[index.sessions.length - 1] ?? null;
}

export interface PlanRow {
  /** Position in the plan as written, which plan edits address. */
  at: number;
  link: string;
  /** The beat the entry resolves to; null for a beat not written yet. */
  beat: BeatEntry | null;
}

export function planRows(index: CampaignIndex, session: SessionEntry | null): PlanRow[] {
  if (!session) return [];
  const beats = new Map(index.beats.map((b) => [b.path, b]));
  return session.beats.map((ref, at) => ({ at, link: ref.link, beat: (ref.path && beats.get(ref.path)) || null }));
}

/** Beats in no plan of this session and not yet spent — potential scenes. */
export function unscheduled(index: CampaignIndex, session: SessionEntry | null): BeatEntry[] {
  const planned = new Set((session?.beats ?? []).map((r) => r.path).filter(Boolean));
  return index.beats
    .filter((b) => !planned.has(b.path) && !b.spent)
    .sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base', numeric: true }));
}

export function memberPaths(beat: BeatEntry | null): Set<string> {
  return new Set((beat?.notes ?? []).map((r) => r.path).filter((p): p is string => p !== null));
}

/** Every note some beat of the session's plan holds. */
export function sessionNotePaths(index: CampaignIndex, session: SessionEntry | null): Set<string> {
  const out = new Set<string>();
  for (const row of planRows(index, session)) for (const p of memberPaths(row.beat)) out.add(p);
  return out;
}
