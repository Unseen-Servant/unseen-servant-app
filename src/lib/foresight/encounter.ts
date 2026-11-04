// Foresight's encounter (docs/roadmap/2026-11-03-foresight-design.md): a note
// whose table is the tracker, read and written by the sidecar
// (sidecar/command/encounter.py) through Rust (command.rs). The turn logic is
// here, pure: whose turn comes next, the round, the rows out of the fight.

import { invoke } from '@tauri-apps/api/core';
import type { SaveOutcome } from '../command/types';

export interface EncounterRow {
  name: string;
  /** The note the name links to, as the link spells it; null for a name
   *  typed in. */
  link: string | null;
  /** Out of the fight: struck through on disk, passed over by the turn. */
  out: boolean;
  /** A cell for each column after the first. */
  cells: string[];
}

export interface Encounter {
  path: string;
  name: string;
  /** The version read, which a save is checked against. */
  hash: string;
  spent: string | null;
  round: number;
  /** The name of the row whose turn it is; null with no rows. */
  turn: string | null;
  /** The table's header row, the rows' names first. */
  columns: string[];
  rows: EncounterRow[];
}

export const encounterApi = {
  read: (campaign: string, path: string) => invoke<Encounter>('command_read_encounter', { campaign, path }),
  save: (campaign: string, e: Encounter) =>
    invoke<SaveOutcome>('command_save_encounter', {
      campaign,
      path: e.path,
      baseHash: e.hash,
      round: e.round,
      turn: e.turn,
      columns: e.columns,
      rows: e.rows,
    }),
  create: (campaign: string, columns: string[], rows: EncounterRow[]) =>
    invoke<Encounter>('command_create_encounter', { campaign, columns, rows }),
};

/** The turn passed `by` one row, forward or back, over the rows out of the
 *  fight. Past the last row it wraps to the first and the round counts up;
 *  back before the first it wraps to the last and the round counts down,
 *  never below 1. With no row in the fight, nothing moves. */
export function step(e: Pick<Encounter, 'rows' | 'turn' | 'round'>, by: 1 | -1): { turn: string | null; round: number } {
  const n = e.rows.length;
  if (!e.rows.some((r) => !r.out)) return { turn: e.turn, round: e.round };
  let at = e.rows.findIndex((r) => r.name === e.turn);
  let round = e.round;
  if (at < 0) return { turn: e.rows.find((r) => !r.out)!.name, round };
  do {
    at += by;
    if (at >= n) {
      at = 0;
      round += 1;
    } else if (at < 0) {
      at = n - 1;
      round = Math.max(1, round - 1);
    }
  } while (e.rows[at].out);
  return { turn: e.rows[at].name, round };
}

/** The row named `name` taken out of the fight, or back in. Taken out on its
 *  turn, the turn passes on; back in while the turn sits on a row out of
 *  the fight (every row was out), the turn is its. */
export function toggleOut(e: Encounter, name: string): Encounter {
  const rows = e.rows.map((r) => (r.name === name ? { ...r, out: !r.out } : r));
  const row = rows.find((r) => r.name === name);
  if (!row) return e;
  const next = { ...e, rows };
  if (row.out && e.turn === name) return { ...next, ...step(next, 1) };
  const holder = rows.find((r) => r.name === e.turn);
  if (!row.out && (!holder || holder.out)) return { ...next, turn: name };
  return next;
}

/** `wanted`, or with the next number when a row has the name already
 *  ("Goblin 2"), as Command numbers a note's name. */
export function freeName(wanted: string, rows: EncounterRow[]): string {
  const taken = new Set(rows.map((r) => r.name.toLocaleLowerCase()));
  let candidate = wanted;
  for (let n = 2; taken.has(candidate.toLocaleLowerCase()); n++) candidate = `${wanted} ${n}`;
  return candidate;
}

/** A row named `name` added at the end, with an empty cell for each column
 *  after the first. The turn is its when no row had it. */
export function addRow(e: Encounter, name: string): Encounter {
  const row: EncounterRow = { name: freeName(name, e.rows), link: null, out: false, cells: e.columns.slice(1).map(() => '') };
  const rows = [...e.rows, row];
  const holder = e.rows.find((r) => r.name === e.turn);
  return { ...e, rows, turn: holder && !holder.out ? e.turn : (rows.find((r) => !r.out)?.name ?? null) };
}
