<script lang="ts">
  import type { KnownGameSystem } from './types';
  import GameSystemsSettings from './GameSystemsSettings.svelte';
  import LibrarySettings from './LibrarySettings.svelte';

  export let visible = false;
  export let onClose: () => void;
  export let knownSystems: KnownGameSystem[] = [];
  export let onSystemsChanged: () => void = () => {};
  export let selectedFolder: string = '';
  export let indexedFileCount: number = 0;
  export let totalFilesFound: number = 0;
  export let totalChunks: number = 0;
  export let storageBytes: number = 0;
  export let reclaimableBytes: number = 0;
  export let gameSystemCount: number = 0;
  export let isSyncing: boolean = false;
  export let syncMode: 'automatic' | 'prompt' | 'manual' = 'automatic';
  export let dataDir: string = '';
  export let lastSyncTime: Date | null = null;
  export let onSelectFolder: () => void = () => {};
  export let onCompact: () => void = () => {};
  export let onReindexAll: () => void = () => {};
  export let onDeleteIndex: () => void = () => {};
  export let onSyncModeChange: (mode: 'automatic' | 'prompt' | 'manual') => void = () => {};
  export let onOpenDataDir: () => void = () => {};
  export let onSync: () => void = () => {};

  let activeTab = 'library';

  const tabs = [
    { id: 'library', label: 'Library' },
    { id: 'game-systems', label: 'Game Systems' },
  ];

  function handleBackdrop(e: MouseEvent) {
    if (e.target === e.currentTarget) onClose();
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Escape') onClose();
  }
</script>

{#if visible}
  <!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
  <div class="backdrop" role="dialog" aria-modal="true" aria-label="Settings" tabindex="-1" on:click={handleBackdrop} on:keydown={handleKeydown}>
    <div class="panel">
      <div class="panel-header">
        <span class="panel-title font-heading">Settings</span>
        <button class="close-btn" on:click={onClose} aria-label="Close">&times;</button>
      </div>
      <div class="panel-content">
        <nav class="tab-nav">
          {#each tabs as tab}
            <button
              class="tab-btn"
              class:active={activeTab === tab.id}
              on:click={() => { activeTab = tab.id; }}
            >
              {tab.label}
            </button>
          {/each}
        </nav>
        <div class="tab-body">
          {#if activeTab === 'game-systems'}
            <GameSystemsSettings {knownSystems} {onSystemsChanged} />
          {:else if activeTab === 'library'}
            <LibrarySettings
              {selectedFolder}
              {indexedFileCount}
              {totalFilesFound}
              {totalChunks}
              {storageBytes}
              {reclaimableBytes}
              {gameSystemCount}
              {isSyncing}
              {syncMode}
              {dataDir}
              {lastSyncTime}
              {onSelectFolder}
              {onCompact}
              {onReindexAll}
              {onDeleteIndex}
              {onSyncModeChange}
              {onOpenDataDir}
              {onSync}
            />
          {/if}
        </div>
      </div>
    </div>
  </div>
{/if}

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.6);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 100;
  }

  .panel {
    background: var(--bg-container);
    border: 1px solid var(--border-subtle);
    border-radius: 8px;
    width: min(640px, 90vw);
    height: min(520px, 80vh);
    display: flex;
    flex-direction: column;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
  }

  .panel-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.75rem 1rem;
    border-bottom: 1px solid var(--border-subtle);
    flex-shrink: 0;
  }

  .panel-title {
    font-size: 1.1rem;
    color: var(--text-accent);
  }

  .close-btn {
    background: none;
    border: none;
    color: var(--text-secondary);
    font-size: 1.4rem;
    line-height: 1;
    padding: 0.1rem 0.4rem;
    border-radius: 4px;
    cursor: pointer;
    transition: color var(--transition-fast);
  }
  .close-btn:hover {
    color: var(--text-primary);
  }

  .panel-content {
    display: flex;
    flex: 1;
    min-height: 0;
  }

  .tab-nav {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    padding: 0.5rem;
    border-right: 1px solid var(--border-subtle);
    flex-shrink: 0;
    width: 140px;
  }

  .tab-btn {
    background: none;
    border: none;
    color: var(--text-secondary);
    font-family: var(--font-body);
    font-size: 0.8rem;
    text-align: left;
    padding: 0.4rem 0.6rem;
    border-radius: 4px;
    cursor: pointer;
    transition: all var(--transition-fast);
  }
  .tab-btn:hover {
    color: var(--text-primary);
    background: var(--bg-focused);
  }
  .tab-btn.active {
    color: var(--text-accent);
    background: var(--bg-focused);
  }

  .tab-body {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }
</style>
