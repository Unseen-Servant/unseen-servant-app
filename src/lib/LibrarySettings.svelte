<script lang="ts">
  type SyncMode = 'automatic' | 'prompt' | 'manual';

  export let selectedFolder: string = '';
  export let indexedFileCount: number = 0;
  export let totalFilesFound: number = 0;
  export let totalChunks: number = 0;
  export let storageBytes: number = 0;
  export let reclaimableBytes: number = 0;
  export let gameSystemCount: number = 0;
  export let isSyncing: boolean = false;
  export let syncMode: SyncMode = 'automatic';
  export let dataDir: string = '';
  export let onSelectFolder: () => void = () => {};
  export let onCompact: () => void = () => {};
  export let onReindexAll: () => void = () => {};
  export let onDeleteIndex: () => void = () => {};
  export let onSyncModeChange: (mode: SyncMode) => void = () => {};
  export let onOpenDataDir: () => void = () => {};

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
        <!-- Font Awesome "book" icon -->
        <svg class="btn-icon-svg" viewBox="0 0 640 640" fill="currentColor" aria-hidden="true">
          <path d="M480 576L192 576C139 576 96 533 96 480L96 160C96 107 139 64 192 64L496 64C522.5 64 544 85.5 544 112L544 400C544 420.9 530.6 438.7 512 445.3L512 512C529.7 512 544 526.3 544 544C544 561.7 529.7 576 512 576L480 576zM192 448C174.3 448 160 462.3 160 480C160 497.7 174.3 512 192 512L448 512L448 448L192 448zM224 216C224 229.3 234.7 240 248 240L424 240C437.3 240 448 229.3 448 216C448 202.7 437.3 192 424 192L248 192C234.7 192 224 202.7 224 216zM248 288C234.7 288 224 298.7 224 312C224 325.3 234.7 336 248 336L424 336C437.3 336 448 325.3 448 312C448 298.7 437.3 288 424 288L248 288z"/>
        </svg>
      </button>
    </div>
  </section>

  <section class="field">
    <div class="field-head">
      <h3 class="field-title font-heading">Sync behavior</h3>
      <p class="field-desc">
        How Legend Lore keeps the index in sync with your library folder.
      </p>
    </div>

    <div class="radio-group" role="radiogroup" aria-label="Sync behavior">
      <label class="radio-option">
        <input
          type="radio"
          name="syncMode"
          value="automatic"
          checked={syncMode === 'automatic'}
          on:change={() => onSyncModeChange('automatic')}
        />
        <div class="radio-text">
          <div class="radio-title">Automatic</div>
          <div class="radio-desc">
            Checks for changes every minute. Applies renames and removals
            silently; asks before re-indexing new or modified files.
          </div>
        </div>
      </label>

      <label class="radio-option">
        <input
          type="radio"
          name="syncMode"
          value="prompt"
          checked={syncMode === 'prompt'}
          on:change={() => onSyncModeChange('prompt')}
        />
        <div class="radio-text">
          <div class="radio-title">Ask before every change</div>
          <div class="radio-desc">
            Checks for changes every minute. Always notifies you; nothing
            syncs without your click.
          </div>
        </div>
      </label>

      <label class="radio-option">
        <input
          type="radio"
          name="syncMode"
          value="manual"
          checked={syncMode === 'manual'}
          on:change={() => onSyncModeChange('manual')}
        />
        <div class="radio-text">
          <div class="radio-title">Manual only</div>
          <div class="radio-desc">
            No background checks. Use the sync button in the status bar
            when you want to update the index.
          </div>
        </div>
      </label>
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

  .radio-group {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .radio-option {
    display: flex;
    gap: 0.6rem;
    padding: 0.5rem 0.6rem;
    border-radius: 4px;
    cursor: pointer;
    transition: background var(--transition-fast);
  }
  .radio-option:hover {
    background: var(--bg-focused);
  }
  .radio-option:has(input:checked) {
    background: var(--bg-focused);
  }

  .radio-option input[type='radio'] {
    margin-top: 0.2rem;
    accent-color: var(--text-accent);
    cursor: pointer;
  }

  .radio-text {
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
    min-width: 0;
  }

  .radio-title {
    font-family: var(--font-heading, var(--font-body));
    font-size: 0.85rem;
    color: var(--text-primary);
  }

  .radio-option:has(input:checked) .radio-title {
    color: var(--text-accent);
  }

  .radio-desc {
    font-family: var(--font-body);
    font-size: 0.8rem;
    color: var(--text-secondary);
    line-height: 1.4;
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
