<script lang="ts">
  export let selectedFolder: string;
  export let sidecarConnected: boolean;
  export let selectedCount: number;
  export let indexedCount: number;
</script>

<footer class="statusbar">
  <div class="statusbar-left">
    {#if selectedFolder}
      <span class="indicator" class:connected={sidecarConnected} title={sidecarConnected ? 'Sidecar connected' : 'Sidecar disconnected'}></span>
      {#if indexedCount > 0}
        <span>{indexedCount} PDF{indexedCount === 1 ? '' : 's'} indexed</span>
      {:else}
        <span>{selectedCount} selected</span>
      {/if}
    {/if}
  </div>
  <div class="statusbar-right">
    {#if selectedFolder}
      <span class="folder-path" title={selectedFolder}>{selectedFolder}</span>
    {/if}
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

  .folder-path {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    direction: rtl;
    text-align: right;
    max-width: 300px;
  }
</style>
