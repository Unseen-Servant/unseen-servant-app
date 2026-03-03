<script lang="ts">
  import type { IndexStatusResult } from './types';

  export let selectedFolder: string;
  export let indexStatus: IndexStatusResult | null;
  export let isLoadingStatus: boolean;
  export let isSyncing: boolean;
  export let syncResult: string;
  export let isCollectionEditMode: boolean;
  export let mcpCopyStatus: string;
  export let onSelectFolder: () => void;
  export let onSync: () => void;
  export let onCopyMcpConfig: () => void;

  $: pending = indexStatus
    ? indexStatus.summary.add + indexStatus.summary.remove + indexStatus.summary.update
    : 0;
  $: indexEmpty = indexStatus
    ? indexStatus.summary.up_to_date === 0 && indexStatus.summary.remove === 0 && indexStatus.summary.update === 0
    : true;
  $: showSync = !isCollectionEditMode && indexStatus && (pending > 0 || indexStatus.summary.errors > 0 || (indexEmpty && indexStatus.summary.add > 0));
</script>

<header class="header">
  <div class="header-left">
    <span class="app-title">Unseen Servant</span>
  </div>

  <div class="header-center">
    {#if !isCollectionEditMode && isLoadingStatus}
      <span class="status-text">Checking index...</span>
    {:else if !isCollectionEditMode && indexStatus}
      {#if pending === 0 && indexStatus.summary.up_to_date > 0}
        <span class="sync-badge ok" title="{indexStatus.summary.up_to_date} PDFs indexed and up to date">
          {indexStatus.summary.up_to_date} up to date
        </span>
      {:else}
        {#if indexStatus.summary.add > 0}
          <span class="sync-badge add" title="{indexStatus.summary.add} new PDFs to add to the index">
            {indexStatus.summary.add} to add
          </span>
        {/if}
        {#if indexStatus.summary.remove > 0}
          <span class="sync-badge remove" title="{indexStatus.summary.remove} PDFs to remove from the index">
            {indexStatus.summary.remove} to remove
          </span>
        {/if}
        {#if indexStatus.summary.update > 0}
          <span class="sync-badge update" title="{indexStatus.summary.update} PDFs modified since last index">
            {indexStatus.summary.update} modified
          </span>
        {/if}
        {#if indexStatus.summary.up_to_date > 0}
          <span class="sync-badge ok" title="{indexStatus.summary.up_to_date} PDFs indexed and up to date">
            {indexStatus.summary.up_to_date} ok
          </span>
        {/if}
        {#if indexStatus.summary.errors > 0}
          <span class="sync-badge error" title="{indexStatus.summary.errors} PDFs could not be found">
            {indexStatus.summary.errors} errors
          </span>
        {/if}
      {/if}

      {#if showSync}
        <button
          class="sync-btn"
          on:click={onSync}
          disabled={isSyncing}
          title={isSyncing ? 'Syncing in progress...' : 'Sync the index with your current selection'}
        >
          {#if isSyncing}
            Syncing...
          {:else if indexEmpty && indexStatus.summary.add > 0}
            Index {indexStatus.summary.add} PDFs
          {:else}
            Sync
          {/if}
        </button>
      {/if}

      {#if syncResult && !isCollectionEditMode}
        <span class="sync-result">{syncResult}</span>
      {/if}
    {/if}
  </div>

  <div class="header-right">
    <button
      class="icon-btn"
      on:click={onSelectFolder}
      title={selectedFolder ? `Library: ${selectedFolder}` : 'Select TTRPG library folder'}
    >
      {#if selectedFolder}
        <span class="icon-folder">&#9776;</span>
      {:else}
        <span class="icon-folder">&#9776;</span>
      {/if}
    </button>

    <button
      class="icon-btn"
      on:click={onCopyMcpConfig}
      title="Copy MCP config for Claude Desktop"
    >
      <span class="icon-mcp">MCP</span>
    </button>

    {#if mcpCopyStatus}
      <span class="mcp-toast">{mcpCopyStatus}</span>
    {/if}
  </div>
</header>

<style>
  .header {
    display: flex;
    align-items: center;
    height: var(--header-height);
    padding: 0 1rem;
    background: var(--bg-header);
    border-bottom: 1px solid var(--border-subtle);
    flex-shrink: 0;
    gap: 1rem;
  }

  .header-left {
    flex-shrink: 0;
  }

  .app-title {
    font-family: var(--font-heading);
    font-size: 1.25rem;
    font-weight: 700;
    color: var(--text-accent);
    letter-spacing: 0.02em;
  }

  .header-center {
    flex: 1;
    display: flex;
    align-items: center;
    gap: 0.4rem;
    min-width: 0;
    overflow: hidden;
  }

  .status-text {
    font-size: 0.8rem;
    color: var(--text-secondary);
    font-style: italic;
  }

  .sync-badge {
    display: inline-block;
    padding: 0.1rem 0.5rem;
    border-radius: 3px;
    font-size: 0.75rem;
    white-space: nowrap;
  }
  .sync-badge.add {
    background: rgba(72, 89, 70, 0.3);
    color: var(--text-active);
  }
  .sync-badge.remove {
    background: rgba(239, 68, 68, 0.15);
    color: var(--text-danger);
  }
  .sync-badge.update {
    background: rgba(182, 159, 129, 0.2);
    color: var(--text-accent);
  }
  .sync-badge.ok {
    background: rgba(72, 89, 70, 0.3);
    color: var(--text-active);
  }
  .sync-badge.error {
    background: rgba(239, 68, 68, 0.15);
    color: var(--text-danger);
  }

  .sync-btn {
    padding: 0.2rem 0.75rem;
    border-radius: 4px;
    border: none;
    font-size: 0.8rem;
    font-family: var(--font-body);
    background: var(--bg-active);
    color: var(--text-primary);
    white-space: nowrap;
    transition: background var(--transition-fast);
  }
  .sync-btn:hover:not(:disabled) {
    background: var(--bg-active-focused);
  }
  .sync-btn:disabled {
    opacity: 0.5;
    cursor: default;
  }
  .sync-btn:active:not(:disabled) {
    transform: scale(0.97);
  }

  .sync-result {
    font-size: 0.75rem;
    color: var(--text-secondary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .header-right {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-shrink: 0;
  }

  .icon-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0.25rem 0.5rem;
    background: none;
    border: 1px solid transparent;
    border-radius: 4px;
    color: var(--text-secondary);
    font-size: 0.85rem;
    transition: all var(--transition-fast);
  }
  .icon-btn:hover {
    color: var(--text-accent);
    border-color: var(--border-subtle);
    background: var(--bg-focused);
  }
  .icon-btn:active {
    transform: scale(0.97);
  }

  .icon-folder {
    font-size: 1rem;
  }

  .icon-mcp {
    font-family: var(--font-display);
    font-size: 0.7rem;
    letter-spacing: 0.05em;
  }

  .mcp-toast {
    font-size: 0.7rem;
    color: var(--text-active);
    white-space: nowrap;
  }
</style>
