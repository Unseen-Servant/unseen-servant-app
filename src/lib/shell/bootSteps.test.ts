import { describe, it, expect } from 'vitest';
import { newerSnapshot, statusLine, STEP_COPY, TOOL_GROUPS, type BootSnapshot, type BootStep } from './bootSteps';

const IDS = ['settings', 'sidecar', 'store', 'embedder', 'reranker', 'spelling', 'library'];

function snapshot(states: Partial<Record<string, Partial<BootStep>>>, finished = false, seq = 1): BootSnapshot {
  return {
    seq,
    finished,
    steps: IDS.map((id) => ({ id, state: 'pending', detail: null, ...states[id] })),
  };
}

describe('lamp groups', () => {
  // Rust owns the ids (src-tauri/src/boot.rs); a step without copy or a
  // group would render no lamp at all.
  it('give every step a lamp in exactly one group', () => {
    const grouped = TOOL_GROUPS.flatMap((g) => g.steps);
    expect([...grouped].sort()).toEqual([...IDS].sort());
    for (const id of IDS) expect(STEP_COPY[id]).toBeDefined();
  });
});

describe('statusLine', () => {
  it('names the running step, prefixed by its tool', () => {
    const line = statusLine(snapshot({ settings: { state: 'done' }, sidecar: { state: 'done' }, store: { state: 'done' }, reranker: { state: 'running' } }));
    expect(line).toEqual({ text: 'Legend Lore · Loading the reranker…', tone: 'running' });
  });

  it('leaves core steps unprefixed; the card already names the app', () => {
    expect(statusLine(snapshot({ sidecar: { state: 'running' } })).text).toBe('Starting the sidecar…');
  });

  it('reads the first running step in lamp order when several run at once', () => {
    const line = statusLine(snapshot({ sidecar: { state: 'running' }, library: { state: 'running' } }));
    expect(line.text).toBe('Starting the sidecar…');
  });

  it('says Ready once finished without a failure, skips included', () => {
    const line = statusLine(snapshot({ library: { state: 'skipped', detail: 'No library folder chosen yet' } }, true));
    expect(line).toEqual({ text: 'Ready', tone: 'ready' });
  });

  it('holds on the first failure, counting the rest', () => {
    const line = statusLine(
      snapshot(
        {
          embedder: { state: 'failed', detail: "Embedder isn't running. Search waits for it" },
          library: { state: 'failed', detail: "Library folder isn't reachable: /Volumes/Tomes" },
        },
        true,
      ),
    );
    expect(line).toEqual({ text: "Embedder isn't running. Search waits for it (+1 more)", tone: 'warning' });
  });

  it('has a line before the first snapshot arrives', () => {
    expect(statusLine(null)).toEqual({ text: 'Starting…', tone: 'running' });
  });
});

describe('newerSnapshot', () => {
  it('keeps a pushed update over an older pulled snapshot', () => {
    const pushed = snapshot({}, false, 5);
    const pulled = snapshot({}, false, 3);
    expect(newerSnapshot(pushed, pulled)).toBe(pushed);
    expect(newerSnapshot(pulled, pushed)).toBe(pushed);
    expect(newerSnapshot(null, pulled)).toBe(pulled);
  });
});
