<script lang="ts">
  export let indexedFileCount: number = 0;
  export let isSyncing: boolean = false;
  export let onReindexAll: () => void = () => {};

  let confirming = false;

  function handleClick() {
    if (isSyncing || indexedFileCount === 0) return;
    if (!confirming) {
      confirming = true;
      return;
    }
    confirming = false;
    onReindexAll();
  }

  function handleCancel() {
    confirming = false;
  }
</script>

<div class="library-settings">
  <section class="field">
    <div class="field-head">
      <h3 class="field-title font-heading">Reindex all files</h3>
      <p class="field-desc">
        Re-extracts and re-embeds every file already in your index. Use after the
        extractor has been upgraded, or if search results look stale. Adds and
        removals happen during normal sync — this only reprocesses files that
        are already up-to-date.
      </p>
    </div>

    <div class="actions">
      {#if confirming}
        <button
          type="button"
          class="btn-danger"
          on:click={handleClick}
          disabled={isSyncing}
        >
          Reprocess {indexedFileCount} {indexedFileCount === 1 ? 'file' : 'files'}?
        </button>
        <button
          type="button"
          class="btn-ghost"
          on:click={handleCancel}
          disabled={isSyncing}
        >
          Cancel
        </button>
      {:else}
        <button
          type="button"
          class="btn-primary"
          on:click={handleClick}
          disabled={isSyncing || indexedFileCount === 0}
          title={indexedFileCount === 0 ? 'No indexed files' : ''}
        >
          {isSyncing ? 'Sync in progress…' : 'Reindex all'}
        </button>
      {/if}
    </div>
  </section>
</div>

<style>
  .library-settings {
    padding: 1rem;
    overflow-y: auto;
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
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

  .actions {
    display: flex;
    gap: 0.5rem;
    align-items: center;
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

  .btn-danger {
    background: var(--bg-focused);
    border: 1px solid var(--text-danger, #c0392b);
    color: var(--text-danger, #c0392b);
  }
  .btn-danger:hover:not(:disabled) {
    background: var(--text-danger, #c0392b);
    color: var(--bg-container);
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
</style>
