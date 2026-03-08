<script lang="ts">
  export let selectedFolder: string;
  export let sidecarConnected: boolean;
  export let selectedCount: number;
  export let indexedCount: number;
  export let gameSystemCount: number;
  export let storageBytes: number;
  export let onShowLicense: () => void;

  function formatSize(bytes: number): string {
    if (bytes >= 1_073_741_824) return (bytes / 1_073_741_824).toFixed(1) + ' GB';
    if (bytes >= 1_048_576) return (bytes / 1_048_576).toFixed(1) + ' MB';
    if (bytes >= 1_024) return (bytes / 1_024).toFixed(0) + ' KB';
    return bytes + ' B';
  }
</script>

<footer class="statusbar">
  <div class="statusbar-left">
    {#if selectedFolder}
      <span class="indicator" class:connected={sidecarConnected} title={sidecarConnected ? 'Sidecar connected' : 'Sidecar disconnected'}></span>
      {#if indexedCount > 0}
        <span>{indexedCount} PDF{indexedCount === 1 ? '' : 's'} indexed</span>
        {#if gameSystemCount > 0}
          <span class="separator">&middot;</span>
          <span>{gameSystemCount} system{gameSystemCount === 1 ? '' : 's'}</span>
        {/if}
        {#if storageBytes > 0}
          <span class="separator">&middot;</span>
          <span>{formatSize(storageBytes)}</span>
        {/if}
      {:else}
        <span>{selectedCount} selected</span>
      {/if}
    {/if}
  </div>
  <div class="statusbar-right">
    {#if selectedFolder}
      <span class="folder-path" title={selectedFolder}>{selectedFolder}</span>
      <span class="separator">&middot;</span>
    {/if}
    <button class="license-link" on:click={onShowLicense}>License</button>
  </div>
</footer>

<style>
  .statusbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: var(--statusbar-height);
    padding: 0 1rem;
    background: var(--bg-container);
    border-top: 1px solid var(--border-subtle);
    flex-shrink: 0;
    font-size: 0.75rem;
    color: var(--text-secondary);
  }

  .statusbar-left {
    display: flex;
    align-items: center;
    gap: 0.4rem;
  }

  .statusbar-right {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    min-width: 0;
  }

  .indicator {
    display: inline-block;
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--text-tertiary);
  }
  .indicator.connected {
    background: var(--text-active);
  }

  .separator {
    opacity: 0.5;
  }

  .license-link {
    background: none;
    border: none;
    color: var(--text-secondary);
    font-size: inherit;
    font-family: inherit;
    padding: 0;
    cursor: pointer;
    transition: color var(--transition-fast);
  }
  .license-link:hover {
    color: var(--text-accent);
  }

  .folder-path {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    direction: rtl;
    text-align: right;
    max-width: 300px;
  }
</style>
