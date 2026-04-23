<script lang="ts">
  export let selectedFolder: string = '';
  export let indexedFileCount: number = 0;
  export let totalChunks: number = 0;
  export let storageBytes: number = 0;
  export let reclaimableBytes: number = 0;
  export let gameSystemCount: number = 0;
  export let isSyncing: boolean = false;
  export let onSelectFolder: () => void = () => {};
  export let onCompact: () => void = () => {};
  export let onReindexAll: () => void = () => {};
  export let onDeleteIndex: () => void = () => {};

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
</script>

<div class="library-settings">
  <section class="field">
    <div class="field-head">
      <h3 class="field-title font-heading">Library stats</h3>
    </div>

    {#if indexedFileCount > 0}
      <div class="stat-block" role="group" aria-label="Library stats">
        <div class="stat-cell">
          <div class="stat-label">FILES</div>
          <div class="stat-value">{indexedFileCount.toLocaleString()}</div>
        </div>
        <div class="stat-cell">
          <div class="stat-label">CHUNKS</div>
          <div class="stat-value">{totalChunks.toLocaleString()}</div>
        </div>
        <div class="stat-cell">
          <div class="stat-label">SIZE</div>
          <div class="stat-value">{storageBytes > 0 ? formatSize(storageBytes) : '—'}</div>
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
      <h3 class="field-title font-heading">Compact database</h3>
      <p class="field-desc">
        Reclaims disk space left behind by removed or re-indexed chunks. Safe to
        run at any time.
      </p>
    </div>

    <div class="actions">
      <button
        type="button"
        class="btn-primary"
        on:click={onCompact}
        disabled={isSyncing || reclaimableBytes === 0}
      >
        Compact database{reclaimableBytes > 0 ? ` (${formatSize(reclaimableBytes)} reclaimable)` : ''}
      </button>
      {#if reclaimableBytes === 0}
        <span class="hint">Nothing to reclaim.</span>
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
    font-size: 0.75rem;
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
    grid-template-columns: repeat(4, 1fr);
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
    font-size: 0.75rem;
    color: var(--text-primary);
    font-variant-numeric: tabular-nums;
  }

  .actions {
    display: flex;
    gap: 0.5rem;
    align-items: center;
  }

  .hint {
    font-family: var(--font-body);
    font-size: 0.8rem;
    color: var(--text-secondary);
    font-style: italic;
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

  .btn-primary {
    background: var(--bg-focused);
    border: 1px solid var(--border-subtle);
    color: var(--text-primary);
  }
  .btn-primary:hover:not(:disabled) {
    color: var(--text-accent);
    border-color: var(--text-accent);
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
