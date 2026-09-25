// Serialization of the scope console (solo/mute/play/lens state) for
// full console recall across launches — spec: docs/frontend/
// 2026-08-08-solo-mute-play-doctrine-design.md. One store key holds
// the whole console; parsing is defensive per field, so one corrupt
// field falls back to empty without nuking the rest. Stale collection
// names and paths are kept as-is: resolution intersects them away, and
// their chips stay visible and removable rather than silently ignored.

import { parseStringArray, parseRecord } from '../shell/storeParsers';
import type { CurationKey, ScopeRef } from './searchScope';

export interface ScopeConsoleState {
  playing: string[];
  mutedCollections: string[];
  soloedSystems: string[];
  mutedSystems: string[];
  scopeSolos: [string, ScopeRef][];
  scopeMutes: [string, ScopeRef][];
  curationSolos: CurationKey[];
  curationMutes: CurationKey[];
  hideOutOfScope: boolean;
}

function parseScopeRefEntries(v: unknown): [string, ScopeRef][] {
  if (!Array.isArray(v)) return [];
  const out: [string, ScopeRef][] = [];
  for (const entry of v) {
    if (!Array.isArray(entry) || entry.length !== 2) continue;
    const [path, ref] = entry;
    if (typeof path !== 'string') continue;
    const rec = parseRecord(ref);
    if (!rec) continue;
    if (rec.kind !== 'folder' && rec.kind !== 'file') continue;
    if (typeof rec.label !== 'string') continue;
    out.push([path, { kind: rec.kind, label: rec.label }]);
  }
  return out;
}

function parseCurationKeys(v: unknown): CurationKey[] {
  const arr = parseStringArray(v) ?? [];
  return arr.filter((k): k is CurationKey => k === 'collected' || k === 'loose');
}

/** Parse a stored console. Returns undefined only when the value is
 * absent or not an object; individual malformed fields fall back to
 * empty on their own. */
export function parseScopeConsoleState(v: unknown): ScopeConsoleState | undefined {
  const rec = parseRecord(v);
  if (!rec) return undefined;
  return {
    playing: parseStringArray(rec.playing) ?? [],
    mutedCollections: parseStringArray(rec.mutedCollections) ?? [],
    soloedSystems: parseStringArray(rec.soloedSystems) ?? [],
    mutedSystems: parseStringArray(rec.mutedSystems) ?? [],
    scopeSolos: parseScopeRefEntries(rec.scopeSolos),
    scopeMutes: parseScopeRefEntries(rec.scopeMutes),
    curationSolos: parseCurationKeys(rec.curationSolos),
    curationMutes: parseCurationKeys(rec.curationMutes),
    hideOutOfScope: rec.hideOutOfScope === true,
  };
}
