<script lang="ts">
  export let selectedFolder: string;
  export let sidecarConnected: boolean;
  export let selectedCount: number;
  export let indexedCount: number;
  export let gameSystemCount: number;
  export let storageBytes: number;
  export let isSyncing: boolean = false;
  export let lastSyncTime: Date | null = null;
  export let onSync: (() => void) | undefined = undefined;
  export let onShowLicense: () => void;

  $: syncTooltip = lastSyncTime
    ? `Last synced ${lastSyncTime.toLocaleTimeString()}`
    : 'Sync index';

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
      {#if onSync}
        <button class="sync-btn" class:spinning={isSyncing} on:click={onSync} title={syncTooltip} disabled={isSyncing}>
          <!-- Font Awesome "arrows-rotate" icon (static/icons/arrows-rotate-solid-full.svg) -->
          <svg class="sync-icon" viewBox="0 0 640 640" fill="currentColor">
            <path d="M129.9 292.5C143.2 199.5 223.3 128 320 128C373 128 421 149.5 455.8 184.2C456 184.4 456.2 184.6 456.4 184.8L464 192L416.1 192C398.4 192 384.1 206.3 384.1 224C384.1 241.7 398.4 256 416.1 256L544.1 256C561.8 256 576.1 241.7 576.1 224L576.1 96C576.1 78.3 561.8 64 544.1 64C526.4 64 512.1 78.3 512.1 96L512.1 149.4L500.8 138.7C454.5 92.6 390.5 64 320 64C191 64 84.3 159.4 66.6 283.5C64.1 301 76.2 317.2 93.7 319.7C111.2 322.2 127.4 310 129.9 292.6zM573.4 356.5C575.9 339 563.7 322.8 546.3 320.3C528.9 317.8 512.6 330 510.1 347.4C496.8 440.4 416.7 511.9 320 511.9C267 511.9 219 490.4 184.2 455.7C184 455.5 183.8 455.3 183.6 455.1L176 447.9L223.9 447.9C241.6 447.9 255.9 433.6 255.9 415.9C255.9 398.2 241.6 383.9 223.9 383.9L96 384C87.5 384 79.3 387.4 73.3 393.5C67.3 399.6 63.9 407.7 64 416.3L65 543.3C65.1 561 79.6 575.2 97.3 575C115 574.8 129.2 560.4 129 542.7L128.6 491.2L139.3 501.3C185.6 547.4 249.5 576 320 576C449 576 555.7 480.6 573.4 356.5z"/>
          </svg>
        </button>
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

  .sync-btn {
    background: none;
    border: none;
    color: var(--text-secondary);
    padding: 0;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    transition: color var(--transition-fast);
    line-height: 0;
  }
  .sync-btn:hover:not(:disabled) {
    color: var(--text-accent);
  }
  .sync-btn:disabled {
    cursor: default;
    opacity: 0.7;
  }
  .sync-icon {
    width: 12px;
    height: 12px;
  }
  .sync-btn.spinning .sync-icon {
    animation: spin 1s linear infinite;
  }
  @keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
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
