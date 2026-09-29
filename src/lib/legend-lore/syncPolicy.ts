import type { IndexStatusSummary, SyncAction, SyncPreferences } from './types';

// What a status check should do with the library's pending changes: nothing,
// a sync without asking (every non-empty bucket's policy is silent), or a
// prompt counting the buckets whose policy asks. Errors always prompt.
export function decideSyncAction(
  summary: IndexStatusSummary,
  prefs: SyncPreferences,
  userTriggered: boolean
): SyncAction {
  if (prefs.backgroundCheckInterval === 0 && !userTriggered) {
    return { kind: 'noop' };
  }

  const { add, remove, update, errors, rename, auto_remove, stale } = summary;
  const diskTotal = rename + auto_remove + stale;

  const askDisk = prefs.diskEventsPolicy === 'ask' && diskTotal > 0;
  const askAdd = prefs.selectionPolicy === 'ask' && add > 0;
  const askRemove = prefs.deselectionPolicy === 'ask' && remove > 0;
  const askUpdate = prefs.modificationPolicy === 'ask' && update > 0;
  const anyAsk = askDisk || askAdd || askRemove || askUpdate;

  const silentDisk = prefs.diskEventsPolicy === 'silent' && diskTotal > 0;
  const silentAdd = prefs.selectionPolicy === 'silent' && add > 0;
  const silentRemove = prefs.deselectionPolicy === 'silent' && remove > 0;
  const silentUpdate = prefs.modificationPolicy === 'silent' && update > 0;
  const anySilent = silentDisk || silentAdd || silentRemove || silentUpdate;

  if (!anyAsk && !anySilent && errors === 0) {
    return { kind: 'noop' };
  }

  if (!anyAsk && errors === 0) {
    return { kind: 'silent' };
  }

  return {
    kind: 'prompt',
    counts: {
      moved: askDisk ? rename : 0,
      missing: askDisk ? auto_remove + stale : 0,
      add: askAdd ? add : 0,
      remove: askRemove ? remove : 0,
      update: askUpdate ? update : 0,
      errors,
    },
  };
}
