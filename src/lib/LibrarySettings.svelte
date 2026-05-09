<script lang="ts">
  import type { BackgroundCheckInterval, BucketPolicy, SyncPreferences } from './types';
  import { BACKGROUND_CHECK_OPTIONS, DEFAULT_SYNC_PREFERENCES } from './types';

  export let selectedFolder: string = '';
  export let indexedFileCount: number = 0;
  export let totalFilesFound: number = 0;
  export let totalChunks: number = 0;
  export let storageBytes: number = 0;
  export let reclaimableBytes: number = 0;
  export let gameSystemCount: number = 0;
  export let isSyncing: boolean = false;
  export let syncPreferences: SyncPreferences = { ...DEFAULT_SYNC_PREFERENCES };
  export let dataDir: string = '';
  export let lastSyncTime: Date | null = null;
  export let onSelectFolder: () => void = () => {};
  export let onDeselectFolder: () => void = () => {};
  export let onCompact: () => void = () => {};
  export let onReindexAll: () => void = () => {};
  export let onDeleteIndex: () => void = () => {};
  export let onSyncPreferencesChange: (partial: Partial<SyncPreferences>) => void = () => {};
  export let onOpenDataDir: () => void = () => {};
  export let onSync: () => void = () => {};

  type PolicyKey = 'diskEventsPolicy' | 'selectionPolicy' | 'deselectionPolicy' | 'modificationPolicy';
  const policyGroups: Array<{
    key: PolicyKey;
    title: string;
    desc: string;
  }> = [
    {
      key: 'diskEventsPolicy',
      title: 'Renames, missing files, and stale selections',
      desc: 'Same content, but the filename or location changed — or the file is no longer there.',
    },
    {
      key: 'selectionPolicy',
      title: 'New files you select',
      desc: 'Embedding work; defaults to asking so you can batch.',
    },
    {
      key: 'deselectionPolicy',
      title: 'Files you deselect',
      desc: 'Drops chunks. Re-selecting later requires re-embedding.',
    },
    {
      key: 'modificationPolicy',
      title: 'Files modified on disk',
      desc: 'Same filename, but the contents are different — needs reindexing.',
    },
  ];

  function setPolicy(key: PolicyKey, value: BucketPolicy) {
    onSyncPreferencesChange({ [key]: value } as Partial<SyncPreferences>);
  }

  function setCheckInterval(value: BackgroundCheckInterval) {
    onSyncPreferencesChange({ backgroundCheckInterval: value });
  }

  let confirmingReindex = false;
  let confirmingDelete = false;

  function handleReindexClick() {
    if (isSyncing || indexedFileCount === 0) return;
    if (!confirmingReindex) {
      confirmingReindex = true;
      confirmingDelete = false;
      return;
    }
    confirmingReindex = false;
    onReindexAll();
  }

  function cancelReindex() {
    confirmingReindex = false;
  }

  function handleDeleteClick() {
    if (isSyncing || indexedFileCount === 0) return;
    if (!confirmingDelete) {
      confirmingDelete = true;
      confirmingReindex = false;
      return;
    }
    confirmingDelete = false;
    onDeleteIndex();
  }

  function cancelDelete() {
    confirmingDelete = false;
  }

  function formatSize(bytes: number): string {
    if (bytes >= 1_073_741_824) return (bytes / 1_073_741_824).toFixed(1) + ' GB';
    if (bytes >= 1_048_576) return (bytes / 1_048_576).toFixed(1) + ' MB';
    if (bytes >= 1_024) return (bytes / 1_024).toFixed(0) + ' KB';
    return bytes + ' B';
  }

  $: coveragePct = totalFilesFound > 0
    ? Math.min(100, (indexedFileCount / totalFilesFound) * 100)
    : 0;

  function formatRelative(date: Date | null): string {
    if (!date) return 'Never';
    const seconds = Math.floor((Date.now() - date.getTime()) / 1000);
    if (seconds < 30) return 'just now';
    if (seconds < 60) return `${seconds}s ago`;
    const minutes = Math.floor(seconds / 60);
    if (minutes === 1) return '1 minute ago';
    if (minutes < 60) return `${minutes} minutes ago`;
    const hours = Math.floor(minutes / 60);
    if (hours === 1) return '1 hour ago';
    if (hours < 24) return `${hours} hours ago`;
    const days = Math.floor(hours / 24);
    if (days === 1) return '1 day ago';
    return `${days} days ago`;
  }

  $: lastSyncRelative = formatRelative(lastSyncTime);
  $: lastSyncAbsolute = lastSyncTime ? lastSyncTime.toLocaleString() : '';
</script>

<div class="library-settings">
  <section class="field">
    <div class="field-head">
      <h3 class="field-title font-heading">Library stats</h3>
    </div>

    {#if indexedFileCount > 0 || totalFilesFound > 0}
      <div class="stat-block" role="group" aria-label="Library stats">
        <div class="stat-cell">
          <div class="stat-label">INDEXED</div>
          <div class="stat-value">
            {indexedFileCount.toLocaleString()}{#if totalFilesFound > 0}&nbsp;<span class="stat-muted">/&nbsp;{totalFilesFound.toLocaleString()}</span>&nbsp;<span class="stat-pct">{coveragePct.toFixed(1)}%</span>{/if}
          </div>
        </div>
        <div class="stat-cell">
          <div class="stat-label">CHUNKS</div>
          <div class="stat-value">{totalChunks.toLocaleString()}</div>
        </div>
        <div class="stat-cell">
          <div class="stat-label">SYS</div>
          <div class="stat-value">{gameSystemCount}</div>
        </div>
      </div>
    {:else}
      <p class="field-desc">No files indexed yet.</p>
    {/if}
  </section>

  <section class="field">
    <div class="field-head">
      <h3 class="field-title font-heading">Library folder</h3>
      <p class="field-desc">
        Legend Lore indexes PDFs from this folder. Changing the folder doesn't
        remove anything that's already indexed — use Reindex all below to rebuild.
      </p>
    </div>

    <div class="path-row">
      <input
        type="text"
        class="path-input"
        readonly
        value={selectedFolder}
        placeholder="No folder selected"
        title={selectedFolder}
      />
      <button
        type="button"
        class="btn-icon"
        on:click={onSelectFolder}
        disabled={isSyncing}
        title="Change library folder"
        aria-label="Change library folder"
      >
        <!-- Font Awesome "folder-open" icon -->
        <svg class="btn-icon-svg" viewBox="0 0 576 512" fill="currentColor" aria-hidden="true">
          <path d="M88.7 223.8L0 375.8L0 96C0 60.7 28.7 32 64 32L181.5 32C198.5 32 214.8 38.7 226.7 50.7L269.3 93.3C281.3 105.3 297.6 112 314.5 112L448 112C483.3 112 512 140.7 512 176L512 208L144 208C121.4 208 100.6 220 88.7 223.8zM144 240L560 240C572.1 240 583.3 246.8 588.9 257.6C594.5 268.4 593.5 281.4 586.4 291.2L501.9 467.2C495.3 480.6 481.6 488 467.2 488L48 488C36 488 24.8 481.2 19.2 470.4C13.6 459.6 14.6 446.6 21.7 436.8L106.2 260.8C112.8 247.4 126.5 240 144 240z"/>
        </svg>
      </button>
    </div>

    {#if selectedFolder}
      <div class="meta-row">
        <button
          type="button"
          class="btn-link"
          on:click={onDeselectFolder}
          disabled={isSyncing}
          title="Clear the library folder and return to the Getting Started screen"
        >
          Deselect folder
        </button>
      </div>
    {/if}
  </section>

  <section class="field">
    <div class="field-head">
      <h3 class="field-title font-heading">Sync behavior</h3>
      <p class="field-desc">
        How Legend Lore keeps the index in sync with your library folder.
      </p>
    </div>

    <div class="setting-row">
      <div class="setting-row-head">
        <div class="setting-row-title">Check for changes</div>
        <div class="setting-row-desc">
          How often to scan the library folder. "Never" means the index only
          updates when you click Sync.
        </div>
      </div>
      <select
        class="setting-select"
        value={syncPreferences.backgroundCheckInterval}
        on:change={(e) => setCheckInterval(Number(e.currentTarget.value) as BackgroundCheckInterval)}
      >
        {#each BACKGROUND_CHECK_OPTIONS as opt}
          <option value={opt.value}>{opt.label}</option>
        {/each}
      </select>
    </div>

    <fieldset class="policy-group" disabled={syncPreferences.backgroundCheckInterval === 0}>
      <legend class="policy-legend">When changes are detected</legend>

      {#each policyGroups as group}
        <div class="setting-row">
          <div class="setting-row-head">
            <div class="setting-row-title">{group.title}</div>
            <div class="setting-row-desc">{group.desc}</div>
          </div>
          <select
            class="setting-select"
            value={syncPreferences[group.key]}
            on:change={(e) => setPolicy(group.key, e.currentTarget.value as BucketPolicy)}
          >
            <option value="silent">Apply silently</option>
            <option value="ask">Show a notification</option>
          </select>
        </div>
      {/each}
    </fieldset>

    <div class="meta-row">
      <span class="meta-label">Last sync</span>
      <span class="meta-value" title={lastSyncAbsolute}>
        {isSyncing ? 'Syncing…' : lastSyncRelative}
      </span>
      <button
        type="button"
        class="btn-link"
        on:click={onSync}
        disabled={isSyncing}
        title="Check the library folder for changes"
      >
        Sync now
      </button>
    </div>
  </section>

  <section class="field">
    <div class="field-head">
      <h3 class="field-title font-heading">Database</h3>
      <p class="field-desc">
        Where the index is stored on disk, and maintenance to reclaim space
        from removed or re-indexed chunks.
      </p>
    </div>

    <div class="path-row">
      <input
        type="text"
        class="path-input"
        readonly
        value={dataDir}
        placeholder="Resolving…"
        title={dataDir}
      />
      <button
        type="button"
        class="btn-icon"
        on:click={onOpenDataDir}
        disabled={!dataDir}
        title="Open database folder"
        aria-label="Open database folder"
      >
        <!-- Font Awesome "folder-open" icon -->
        <svg class="btn-icon-svg" viewBox="0 0 576 512" fill="currentColor" aria-hidden="true">
          <path d="M88.7 223.8L0 375.8L0 96C0 60.7 28.7 32 64 32L181.5 32C198.5 32 214.8 38.7 226.7 50.7L269.3 93.3C281.3 105.3 297.6 112 314.5 112L448 112C483.3 112 512 140.7 512 176L512 208L144 208C121.4 208 100.6 220 88.7 223.8zM144 240L560 240C572.1 240 583.3 246.8 588.9 257.6C594.5 268.4 593.5 281.4 586.4 291.2L501.9 467.2C495.3 480.6 481.6 488 467.2 488L48 488C36 488 24.8 481.2 19.2 470.4C13.6 459.6 14.6 446.6 21.7 436.8L106.2 260.8C112.8 247.4 126.5 240 144 240z"/>
        </svg>
      </button>
    </div>

    <div class="meta-row">
      <span class="meta-label">Storage</span>
      <span class="meta-value">
        {storageBytes > 0 ? formatSize(storageBytes) : '—'}
        {#if reclaimableBytes > 0}
          <span class="meta-muted"> · {formatSize(reclaimableBytes)} reclaimable</span>
        {/if}
      </span>
      {#if reclaimableBytes > 0}
        <button
          type="button"
          class="btn-link"
          on:click={onCompact}
          disabled={isSyncing}
          title="Reclaim {formatSize(reclaimableBytes)}"
        >
          Compact
        </button>
      {/if}
    </div>
  </section>

  <section class="danger-zone" aria-label="Danger Zone">
    <h3 class="danger-title font-heading">Danger Zone</h3>

    <div class="danger-row">
      <div class="danger-row-text">
        <div class="danger-row-title">Reindex all files</div>
        <div class="danger-row-desc">
          Re-extracts and re-embeds every file in your index. Use after the
          extractor has been upgraded, or if search results look stale.
        </div>
      </div>
      <div class="danger-row-action">
        {#if confirmingReindex}
          <button
            type="button"
            class="btn-danger-solid"
            on:click={handleReindexClick}
            disabled={isSyncing}
          >
            Reprocess {indexedFileCount} {indexedFileCount === 1 ? 'file' : 'files'}?
          </button>
          <button
            type="button"
            class="btn-ghost"
            on:click={cancelReindex}
            disabled={isSyncing}
          >
            Cancel
          </button>
        {:else}
          <button
            type="button"
            class="btn-danger-outline"
            on:click={handleReindexClick}
            disabled={isSyncing || indexedFileCount === 0}
            title={indexedFileCount === 0 ? 'No indexed files' : ''}
          >
            {isSyncing ? 'Sync in progress…' : 'Reindex all'}
          </button>
        {/if}
      </div>
    </div>

    <div class="danger-row">
      <div class="danger-row-text">
        <div class="danger-row-title">Delete the index</div>
        <div class="danger-row-desc">
          Removes every chunk from the database and clears the manifest.
          Your library folder, game systems, and collections are kept — the
          next sync rebuilds the index from scratch.
        </div>
      </div>
      <div class="danger-row-action">
        {#if confirmingDelete}
          <button
            type="button"
            class="btn-danger-solid"
            on:click={handleDeleteClick}
            disabled={isSyncing}
          >
            Delete {indexedFileCount} {indexedFileCount === 1 ? 'file' : 'files'}?
          </button>
          <button
            type="button"
            class="btn-ghost"
            on:click={cancelDelete}
            disabled={isSyncing}
          >
            Cancel
          </button>
        {:else}
          <button
            type="button"
            class="btn-danger-outline"
            on:click={handleDeleteClick}
            disabled={isSyncing || indexedFileCount === 0}
            title={indexedFileCount === 0 ? 'No indexed files' : ''}
          >
            Delete the index
          </button>
        {/if}
      </div>
    </div>
  </section>
</div>

<style>
  .library-settings {
    padding: 1rem;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
  }

  .field-title {
    font-size: 0.95rem;
    color: var(--text-primary);
    margin: 0 0 0.35rem;
  }

  .field-desc {
    font-family: var(--font-body);
    font-size: 0.85rem;
    color: var(--text-secondary);
    line-height: 1.45;
    margin: 0;
  }

  .path-row {
    display: flex;
    gap: 0.5rem;
    align-items: center;
  }

  .path-input {
    flex: 1;
    min-width: 0;
    font-family: var(--font-mono, ui-monospace, monospace);
    font-size: 0.7rem;
    padding: 0.4rem 0.6rem;
    background: var(--bg-focused);
    color: var(--text-primary);
    border: 1px solid var(--border-subtle);
    border-radius: 4px;
  }
  .path-input:focus {
    outline: 1px solid var(--text-accent);
    outline-offset: -1px;
  }
  .path-input::placeholder {
    color: var(--text-secondary);
    font-style: italic;
  }

  .stat-block {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0.5rem;
    padding: 0.5rem 0.25rem;
    border-top: 1px solid var(--border-subtle);
    border-bottom: 1px solid var(--border-subtle);
  }

  .stat-cell {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.1rem;
  }

  .stat-label {
    font-family: var(--font-heading, var(--font-body));
    font-size: 0.7rem;
    letter-spacing: 0.08em;
    color: var(--text-secondary);
    text-transform: uppercase;
  }

  .stat-value {
    font-family: var(--font-mono, ui-monospace, monospace);
    font-size: 0.7rem;
    color: var(--text-primary);
    font-variant-numeric: tabular-nums;
  }

  .stat-muted {
    color: var(--text-secondary);
  }

  .stat-pct {
    color: var(--text-accent);
  }
  .stat-pct::before,
  .stat-pct::after {
    color: var(--text-secondary);
  }
  .stat-pct::before {
    content: '[';
    margin-right: 0.15rem;
  }
  .stat-pct::after {
    content: ']';
    margin-left: 0.15rem;
  }

  .meta-row {
    display: flex;
    align-items: baseline;
    gap: 0.6rem;
    padding: 0.15rem 0.1rem;
  }

  .meta-label {
    font-family: var(--font-heading, var(--font-body));
    font-size: 0.7rem;
    letter-spacing: 0.08em;
    color: var(--text-secondary);
    text-transform: uppercase;
    flex-shrink: 0;
  }

  .meta-value {
    font-family: var(--font-mono, ui-monospace, monospace);
    font-size: 0.7rem;
    color: var(--text-primary);
    font-variant-numeric: tabular-nums;
    min-width: 0;
  }

  .meta-muted {
    color: var(--text-secondary);
  }

  /*
   * Compact action — Option B: bracketed terminal-style affordance.
   * Brackets in muted color, label in accent. Hover brightens the
   * brackets so the whole token feels reactive.
   */
  .btn-link {
    background: transparent;
    border: none;
    padding: 0;
    font-family: var(--font-mono, ui-monospace, monospace);
    font-size: 0.7rem;
    color: var(--text-accent);
    cursor: pointer;
    flex-shrink: 0;
    transition: filter var(--transition-fast);
  }
  .btn-link::before,
  .btn-link::after {
    color: var(--text-secondary);
    transition: color var(--transition-fast);
  }
  .btn-link::before {
    content: '[';
    margin-right: 0.15rem;
  }
  .btn-link::after {
    content: ']';
    margin-left: 0.15rem;
  }
  .btn-link:hover:not(:disabled) {
    filter: brightness(1.25);
  }
  .btn-link:hover:not(:disabled)::before,
  .btn-link:hover:not(:disabled)::after {
    color: var(--text-accent);
  }
  .btn-link:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .setting-row {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 0.75rem;
    align-items: center;
    padding: 0.4rem 0.1rem;
  }

  .setting-row-head {
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
    min-width: 0;
  }

  .setting-row-title {
    font-family: var(--font-heading, var(--font-body));
    font-size: 0.8rem;
    color: var(--text-primary);
  }

  .setting-row-desc {
    font-family: var(--font-body);
    font-size: 0.75rem;
    color: var(--text-secondary);
    line-height: 1.35;
  }

  .setting-select {
    font-family: var(--font-body);
    font-size: 0.8rem;
    padding: 0.3rem 0.5rem;
    background: var(--bg-focused);
    color: var(--text-primary);
    border: 1px solid var(--border-subtle);
    border-radius: 4px;
    cursor: pointer;
    min-width: 11rem;
  }
  .setting-select:focus {
    outline: 1px solid var(--text-accent);
    outline-offset: -1px;
  }
  .setting-select:disabled {
    cursor: not-allowed;
  }

  .policy-group {
    border: 1px solid var(--border-subtle);
    border-radius: 4px;
    padding: 0.4rem 0.6rem 0.6rem;
    margin: 0;
    width: 100%;
    box-sizing: border-box;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 0.1rem;
    transition: opacity var(--transition-fast);
  }
  .policy-group:disabled {
    opacity: 0.45;
  }
  .policy-group .setting-row + .setting-row {
    border-top: 1px solid var(--border-subtle);
  }

  .policy-legend {
    font-family: var(--font-heading, var(--font-body));
    font-size: 0.7rem;
    letter-spacing: 0.08em;
    color: var(--text-secondary);
    text-transform: uppercase;
    padding: 0 0.3rem;
  }

  button {
    font-family: var(--font-body);
    font-size: 0.85rem;
    padding: 0.4rem 0.75rem;
    border-radius: 4px;
    cursor: pointer;
    transition: all var(--transition-fast);
  }

  button:disabled {
    cursor: not-allowed;
    opacity: 0.5;
  }

  .btn-danger-outline {
    background: transparent;
    border: 1px solid var(--text-danger, #c0392b);
    color: var(--text-danger, #c0392b);
  }
  .btn-danger-outline:hover:not(:disabled) {
    background: var(--text-danger, #c0392b);
    color: var(--bg-container);
  }

  .btn-danger-solid {
    background: var(--text-danger, #c0392b);
    border: 1px solid var(--text-danger, #c0392b);
    color: var(--bg-container);
  }
  .btn-danger-solid:hover:not(:disabled) {
    filter: brightness(1.1);
  }

  .danger-zone {
    border: 1px solid var(--text-danger, #c0392b);
    border-radius: 6px;
    margin-top: 0.25rem;
    display: flex;
    flex-direction: column;
  }

  .danger-title {
    font-size: 0.9rem;
    color: var(--text-danger, #c0392b);
    margin: 0;
    padding: 0.6rem 0.85rem;
    border-bottom: 1px solid var(--border-subtle);
  }

  .danger-row {
    display: flex;
    gap: 1rem;
    align-items: center;
    justify-content: space-between;
    padding: 0.75rem 0.85rem;
  }
  .danger-row + .danger-row {
    border-top: 1px solid var(--border-subtle);
  }

  .danger-row-text {
    flex: 1;
    min-width: 0;
  }

  .danger-row-title {
    font-family: var(--font-heading, var(--font-body));
    font-size: 0.85rem;
    color: var(--text-primary);
    margin-bottom: 0.2rem;
  }

  .danger-row-desc {
    font-family: var(--font-body);
    font-size: 0.8rem;
    color: var(--text-secondary);
    line-height: 1.4;
  }

  .danger-row-action {
    display: flex;
    gap: 0.5rem;
    align-items: center;
    flex-shrink: 0;
  }

  .btn-ghost {
    background: transparent;
    border: 1px solid var(--border-subtle);
    color: var(--text-secondary);
  }
  .btn-ghost:hover:not(:disabled) {
    color: var(--text-primary);
    border-color: var(--text-primary);
  }

  .btn-icon {
    background: transparent;
    border: none;
    color: var(--text-secondary);
    padding: 0.35rem;
    line-height: 0;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }
  .btn-icon:hover:not(:disabled) {
    color: var(--text-accent);
  }
  .btn-icon-svg {
    width: 16px;
    height: 16px;
  }
</style>
