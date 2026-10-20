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

/** Beats in no plan of this session and not yet spent — potential scenes —
 *  in the campaign's beat order (the order the GM dragged them, then by
 *  name, as the index lists them). `withSpent` keeps the spent ones too, for
 *  the column to show on request. */
export function unscheduled(index: CampaignIndex, session: SessionEntry | null, withSpent = false): BeatEntry[] {
  const planned = new Set((session?.beats ?? []).map((r) => r.path).filter(Boolean));
  return index.beats.filter((b) => !planned.has(b.path) && (withSpent || !b.spent));
}

/** The campaign's beat order after the beats on show outside the plan were
 *  dragged into `visible`: those first, then every other beat in its current
 *  place, as Legend Lore keeps the collections a view hides. */
export function beatOrder(index: CampaignIndex, visible: string[]): string[] {
  const shown = new Set(visible);
  return [...visible, ...index.beats.map((b) => b.name).filter((n) => !shown.has(n))];
}

/** Where a plan entry dragged from `from` lands when dropped at `slot`, an
 *  insertion point between rows (0 to the plan's length): the position to
 *  move it to, or null when the drop leaves it where it was. */
export function planMoveTo(from: number, slot: number): number | null {
  const to = slot > from ? slot - 1 : slot;
  return to === from ? null : to;
}

export function memberPaths(beat: BeatEntry | null): Set<string> {
  return new Set((beat?.notes ?? []).map((r) => r.path).filter((p): p is string => p !== null));
}

/** What Arrange by beat names the frame of the notes several planned
 *  beats hold (board toolbar design §6). */
export const THROUGHOUT = 'Throughout';

/** The session's notes as Arrange lays them out, as the sidecar's
 *  board.plan_groups does: Throughout first, with the notes several
 *  planned beats hold, then each planned beat with the rest of its notes,
 *  in plan order and the beat's own order. Throughout is left out when no
 *  note is shared. */
export function beatGroups(index: CampaignIndex, session: SessionEntry | null): { name: string; notes: string[] }[] {
  const planned: BeatEntry[] = [];
  for (const row of planRows(index, session)) if (row.beat && !planned.includes(row.beat)) planned.push(row.beat);
  const held = planned.map((b) => [...memberPaths(b)]);
  const count = new Map<string, number>();
  for (const notes of held) for (const p of notes) count.set(p, (count.get(p) ?? 0) + 1);
  const shared = [...new Set(held.flat().filter((p) => count.get(p)! > 1))];
  return [
    ...(shared.length ? [{ name: THROUGHOUT, notes: shared }] : []),
    ...planned.map((b, i) => ({ name: b.name, notes: held[i].filter((p) => count.get(p) === 1) })),
  ];
}

/** Every note some beat of the session's plan holds. */
export function sessionNotePaths(index: CampaignIndex, session: SessionEntry | null): Set<string> {
  const out = new Set<string>();
  for (const row of planRows(index, session)) for (const p of memberPaths(row.beat)) out.add(p);
  return out;
}
