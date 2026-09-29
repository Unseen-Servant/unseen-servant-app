import { describe, expect, it } from 'vitest';
import { decideSyncAction } from './syncPolicy';
import { DEFAULT_SYNC_PREFERENCES, type IndexStatusSummary, type SyncPreferences } from './types';

function summary(overrides: Partial<IndexStatusSummary> = {}): IndexStatusSummary {
  return {
    add: 0, remove: 0, auto_remove: 0, rename: 0, update: 0,
    up_to_date: 10, errors: 0, stale: 0, outdated: 0,
    ...overrides,
  };
}

const allAsk: SyncPreferences = {
  backgroundCheckInterval: 60,
  diskEventsPolicy: 'ask',
  selectionPolicy: 'ask',
  deselectionPolicy: 'ask',
  modificationPolicy: 'ask',
};

const allSilent: SyncPreferences = {
  ...allAsk,
  diskEventsPolicy: 'silent',
  selectionPolicy: 'silent',
  deselectionPolicy: 'silent',
  modificationPolicy: 'silent',
};

const noCounts = { moved: 0, missing: 0, add: 0, remove: 0, update: 0, errors: 0 };

// Each bucket: the summary that fills it, the policy key that governs it,
// and the prompt counts it produces when that policy asks.
const BUCKETS: [string, Partial<IndexStatusSummary>, keyof SyncPreferences, Partial<typeof noCounts>][] = [
  ['rename', { rename: 2 }, 'diskEventsPolicy', { moved: 2 }],
  ['auto_remove', { auto_remove: 2 }, 'diskEventsPolicy', { missing: 2 }],
  ['stale', { stale: 2 }, 'diskEventsPolicy', { missing: 2 }],
  ['add', { add: 2 }, 'selectionPolicy', { add: 2 }],
  ['remove', { remove: 2 }, 'deselectionPolicy', { remove: 2 }],
  ['update', { update: 2 }, 'modificationPolicy', { update: 2 }],
];

describe('decideSyncAction', () => {
  it('does nothing when the library is up to date', () => {
    expect(decideSyncAction(summary(), allAsk, false)).toEqual({ kind: 'noop' });
    expect(decideSyncAction(summary(), allSilent, true)).toEqual({ kind: 'noop' });
  });

  it('ignores outdated books: re-extraction is reindex-all\'s job, not sync\'s', () => {
    expect(decideSyncAction(summary({ outdated: 5 }), allAsk, true)).toEqual({ kind: 'noop' });
  });

  describe.each(BUCKETS)('the %s bucket', (_name, filled, policyKey, counts) => {
    it('prompts with its count when its policy asks', () => {
      expect(decideSyncAction(summary(filled), allAsk, false)).toEqual({
        kind: 'prompt',
        counts: { ...noCounts, ...counts },
      });
    });

    it('syncs silently when its policy is silent', () => {
      const prefs = { ...allAsk, [policyKey]: 'silent' };
      expect(decideSyncAction(summary(filled), prefs, false)).toEqual({ kind: 'silent' });
    });
  });

  it('adds stale to auto_remove under "missing", apart from "moved"', () => {
    const action = decideSyncAction(summary({ rename: 1, auto_remove: 2, stale: 3 }), allAsk, false);
    expect(action).toEqual({ kind: 'prompt', counts: { ...noCounts, moved: 1, missing: 5 } });
  });

  it('never checks in the background when the interval is 0', () => {
    const never = { ...allAsk, backgroundCheckInterval: 0 as const };
    expect(decideSyncAction(summary({ add: 3, errors: 1 }), never, false)).toEqual({ kind: 'noop' });
  });

  it('still answers a user-triggered check when the interval is 0', () => {
    const never = { ...allAsk, backgroundCheckInterval: 0 as const };
    expect(decideSyncAction(summary({ add: 3 }), never, true)).toEqual({
      kind: 'prompt',
      counts: { ...noCounts, add: 3 },
    });
  });

  it('prompts for errors even when every bucket is silent', () => {
    expect(decideSyncAction(summary({ errors: 2 }), allSilent, false)).toEqual({
      kind: 'prompt',
      counts: { ...noCounts, errors: 2 },
    });
    expect(decideSyncAction(summary({ add: 1, errors: 2 }), allSilent, false)).toEqual({
      kind: 'prompt',
      counts: { ...noCounts, errors: 2 },
    });
  });

  it('prompts when any bucket asks, counting only the asking buckets', () => {
    // Default prefs: disk events silent, the rest ask. The silent moves
    // ride along with whatever sync the prompt starts.
    const action = decideSyncAction(summary({ rename: 4, add: 1 }), DEFAULT_SYNC_PREFERENCES, false);
    expect(action).toEqual({ kind: 'prompt', counts: { ...noCounts, add: 1 } });
  });
});
