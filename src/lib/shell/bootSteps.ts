/**
 * What the launch splash says about the cold start.
 *
 * Rust owns the steps: their ids, order, states and the sentence for a
 * failed or skipped one (src-tauri/src/boot.rs). The splash owns the rest —
 * each lamp's code and name, which tool it sits under, and the line shown
 * while a step runs.
 */

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
  name: string;
  running: string;
}

export const STEP_COPY: Record<string, StepCopy> = {
  settings: { lamp: 'CFG', name: 'Settings', running: 'Reading settings' },
  sidecar: { lamp: 'SDC', name: 'Sidecar', running: 'Starting the sidecar' },
  store: { lamp: 'STO', name: 'Library store', running: 'Opening the library store' },
  embedder: { lamp: 'EMB', name: 'Embedder', running: 'Waking the embedder' },
  reranker: { lamp: 'RRK', name: 'Reranker', running: 'Loading the reranker' },
  spelling: { lamp: 'SPL', name: 'Spelling vocabulary', running: 'Building the spelling vocabulary' },
  library: { lamp: 'LIB', name: 'Library folder', running: 'Checking the library folder' },
};

/** Lamps grouped by the tool they serve, in lamp order. Core is the app
 *  itself; each tool that joins the suite adds a group. */
export const TOOL_GROUPS: { name: string; steps: string[] }[] = [
  { name: 'Core', steps: ['settings', 'sidecar', 'store'] },
  { name: 'Legend Lore', steps: ['embedder', 'reranker', 'spelling', 'library'] },
];

export interface StatusLine {
  text: string;
  tone: 'running' | 'ready' | 'warning';
}

export function statusLine(snap: BootSnapshot | null): StatusLine {
  if (snap?.finished) {
    const failed = snap.steps.filter((s) => s.state === 'failed');
    if (failed.length === 0) return { text: 'Ready', tone: 'ready' };
    const first = failed[0];
    const text = first.detail ?? `${STEP_COPY[first.id]?.name ?? first.id} failed`;
    const more = failed.length > 1 ? ` (+${failed.length - 1} more)` : '';
    return { text: text + more, tone: 'warning' };
  }
  const running = snap?.steps.find((s) => s.state === 'running');
  if (!running) return { text: 'Starting…', tone: 'running' };
  const group = TOOL_GROUPS.find((g) => g.steps.includes(running.id));
  const prefix = group && group.name !== 'Core' ? `${group.name} · ` : '';
  return { text: `${prefix}${STEP_COPY[running.id]?.running ?? running.id}…`, tone: 'running' };
}

/** The splash pulls a snapshot on mount while updates are already being
 *  pushed; whichever lands last may be the older one. */
export function newerSnapshot(current: BootSnapshot | null, incoming: BootSnapshot): BootSnapshot {
  return current && current.seq >= incoming.seq ? current : incoming;
}
