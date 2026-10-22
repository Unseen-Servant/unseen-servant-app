/**
 * What the launch splash says about the cold start.
 *
 * Rust owns the steps: their ids, order, states and the sentence for a
 * failed or skipped one (src-tauri/src/boot.rs). The splash owns the rest —
 * each lamp's code and name, which tool it sits under, and the line shown
 * while a step runs.
 */

import { m } from '../paraglide/messages';

export type StepState = 'pending' | 'running' | 'done' | 'failed' | 'skipped';

export interface BootStep {
  id: string;
  state: StepState;
  detail: string | null;
}

export interface BootSnapshot {
  seq: number;
  steps: BootStep[];
  finished: boolean;
}

interface StepCopy {
  /** Three letters under the lamp, the way a console labels its channels. */
  lamp: string;
  name: () => string;
  running: () => string;
}

export const STEP_COPY: Record<string, StepCopy> = {
  settings: { lamp: 'CFG', name: m.boot_settings, running: m.boot_settings_running },
  sidecar: { lamp: 'SDC', name: m.boot_sidecar, running: m.boot_sidecar_running },
  store: { lamp: 'STO', name: m.boot_store, running: m.boot_store_running },
  embedder: { lamp: 'EMB', name: m.boot_embedder, running: m.boot_embedder_running },
  reranker: { lamp: 'RRK', name: m.boot_reranker, running: m.boot_reranker_running },
  spelling: { lamp: 'SPL', name: m.boot_spelling, running: m.boot_spelling_running },
  library: { lamp: 'LIB', name: m.boot_library, running: m.boot_library_running },
};

/** Lamps grouped by the tool they serve, in lamp order. Core is the app
 *  itself; each tool that joins the suite adds a group. */
export const TOOL_GROUPS: { id: string; name: () => string; steps: string[] }[] = [
  { id: 'core', name: m.boot_group_core, steps: ['settings', 'sidecar', 'store'] },
  { id: 'legend-lore', name: () => 'Legend Lore', steps: ['embedder', 'reranker', 'spelling', 'library'] },
];

export interface StatusLine {
  text: string;
  tone: 'running' | 'ready' | 'warning';
}

export function statusLine(snap: BootSnapshot | null): StatusLine {
  if (snap?.finished) {
    const failed = snap.steps.filter((s) => s.state === 'failed');
    if (failed.length === 0) return { text: m.boot_ready(), tone: 'ready' };
    const first = failed[0];
    const text = first.detail ?? m.boot_failed({ step: STEP_COPY[first.id]?.name() ?? first.id });
    return { text: failed.length > 1 ? m.boot_failed_more({ text, count: failed.length - 1 }) : text, tone: 'warning' };
  }
  const running = snap?.steps.find((s) => s.state === 'running');
  if (!running) return { text: m.boot_starting(), tone: 'running' };
  const group = TOOL_GROUPS.find((g) => g.steps.includes(running.id));
  const prefix = group && group.id !== 'core' ? `${group.name()} · ` : '';
  return { text: `${prefix}${STEP_COPY[running.id]?.running() ?? running.id}…`, tone: 'running' };
}

/** The splash pulls a snapshot on mount while updates are already being
 *  pushed; whichever lands last may be the older one. */
export function newerSnapshot(current: BootSnapshot | null, incoming: BootSnapshot): BootSnapshot {
  return current && current.seq >= incoming.seq ? current : incoming;
}
