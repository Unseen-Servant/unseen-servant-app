<script lang="ts">
  import type { KnownGameSystem, SyncPreferences } from './types';
  import { DEFAULT_SYNC_PREFERENCES } from './types';
  import Modal from './Modal.svelte';
  import GameSystemsSettings from './GameSystemsSettings.svelte';
  import LibrarySettings from './LibrarySettings.svelte';
  import GettingStartedSteps from './GettingStartedSteps.svelte';

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
  export let syncPreferences: SyncPreferences = { ...DEFAULT_SYNC_PREFERENCES };
  export let dataDir: string = '';
  export let lastSyncTime: Date | null = null;
  export let onSelectFolder: () => void = () => {};
  export let onCompact: () => void = () => {};
  export let onReindexAll: () => void = () => {};
  export let onDeleteIndex: () => void = () => {};
  export let onSyncPreferencesChange: (partial: Partial<SyncPreferences>) => void = () => {};
  export let onOpenDataDir: () => void = () => {};
  export let onSync: () => void = () => {};
  export let onCopyMcpConfig: () => void = () => {};
  export let ollamaRunning: boolean = false;
  export let ollamaModelReady: boolean = false;
  export let filesIndexed: boolean = false;
  export let collectionsCreated: boolean = false;
  export let mcpConnected: boolean = false;
  export let hideSetupButton: boolean = false;
  export let onHideSetupButtonChange: (value: boolean) => void = () => {};
  export let initialTab: 'library' | 'game-systems' | 'setup' = 'library';

  let activeTab: 'library' | 'game-systems' | 'setup' = initialTab;
  $: if (visible) activeTab = initialTab;

  const tabs = [
    { id: 'library' as const, label: 'Library' },
    { id: 'game-systems' as const, label: 'Game Systems' },
    { id: 'setup' as const, label: 'Setup' },
  ];
</script>

<Modal {visible} {onClose} title="Settings" width="min(640px, 90vw)" height="min(520px, 80vh)">
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
          {syncPreferences}
          {dataDir}
          {lastSyncTime}
          {onSelectFolder}
          {onCompact}
          {onReindexAll}
          {onDeleteIndex}
          {onSyncPreferencesChange}
          {onOpenDataDir}
          {onSync}
        />
      {:else if activeTab === 'setup'}
        <div class="setup-pane">
          <label class="setup-toggle">
            <span class="setup-toggle-text">
              <span class="setup-toggle-title">Hide setup shortcut in the status bar</span>
              <span class="setup-toggle-hint">
                You can still reopen this tab from the gear icon.
              </span>
            </span>
            <input
              class="app-checkbox"
              type="checkbox"
              checked={hideSetupButton}
              on:change={(e) => onHideSetupButtonChange(e.currentTarget.checked)}
            />
          </label>
          <GettingStartedSteps
            {ollamaRunning}
            {ollamaModelReady}
            folderSelected={!!selectedFolder}
            {filesIndexed}
            {collectionsCreated}
            {mcpConnected}
            {onSelectFolder}
            {onCopyMcpConfig}
          />
        </div>
      {/if}
    </div>
  </div>
</Modal>

<style>
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

  .setup-pane {
    overflow-y: auto;
    padding: 1rem;
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
  }
  .setup-toggle {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 0.75rem;
    padding-bottom: 1.1rem;
    border-bottom: 1px solid var(--border-subtle);
    cursor: pointer;
  }
  .setup-toggle-text {
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
    min-width: 0;
  }
  .setup-toggle-title {
    font-family: var(--font-heading, var(--font-body));
    font-size: 0.85rem;
    color: var(--text-primary);
  }
  .setup-toggle-hint {
    font-family: var(--font-body);
    font-size: 0.75rem;
    color: var(--text-secondary);
    line-height: 1.35;
  }
</style>
