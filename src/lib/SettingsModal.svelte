<script lang="ts">
  import type { KnownGameSystem, SyncPreferences } from './types';
  import { DEFAULT_SYNC_PREFERENCES } from './types';
  import Modal from './Modal.svelte';
  import GameSystemsSettings from './GameSystemsSettings.svelte';
  import LibrarySettings from './LibrarySettings.svelte';
  import GuidesPane from './help/GuidesPane.svelte';
  import ReferencePane from './help/ReferencePane.svelte';
  import AboutPane from './help/AboutPane.svelte';
  import GeneralSettings from './GeneralSettings.svelte';

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
  export let onDeselectFolder: () => void = () => {};
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
  export let initialTab: 'general' | 'library' | 'game-systems' | 'help' = 'library';
  export let initialHelpSubTab: 'guides' | 'reference' | 'about' = 'guides';
  export let skipLaunchSplash: boolean = false;
  export let onSkipLaunchSplashChange: (value: boolean) => void = () => {};

  let activeTab: 'general' | 'library' | 'game-systems' | 'help' = initialTab;
  let activeHelpSubTab: 'guides' | 'reference' | 'about' = initialHelpSubTab;
  $: if (visible) {
    activeTab = initialTab;
    activeHelpSubTab = initialHelpSubTab;
  }

  const tabs = [
    { id: 'general' as const, label: 'General' },
    { id: 'library' as const, label: 'Library' },
    { id: 'game-systems' as const, label: 'Game Systems' },
    { id: 'help' as const, label: 'Help' },
  ];

  const helpSubTabs = [
    { id: 'guides' as const, label: 'Guides' },
    { id: 'reference' as const, label: 'Reference' },
    { id: 'about' as const, label: 'About' },
  ];
</script>

<Modal {visible} {onClose} title="Settings" width="min(640px, 90vw)" height="min(520px, 80vh)" autofocus={false}>
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
      {#if activeTab === 'general'}
        <GeneralSettings {skipLaunchSplash} {onSkipLaunchSplashChange} />
      {:else if activeTab === 'game-systems'}
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
          {onDeselectFolder}
          {onCompact}
          {onReindexAll}
          {onDeleteIndex}
          {onSyncPreferencesChange}
          {onOpenDataDir}
          {onSync}
        />
      {:else if activeTab === 'help'}
        <div class="help-pane">
          <nav class="subtab-nav">
            {#each helpSubTabs as sub}
              <button
                class="subtab-btn"
                class:active={activeHelpSubTab === sub.id}
                on:click={() => { activeHelpSubTab = sub.id; }}
              >
                {sub.label}
              </button>
            {/each}
          </nav>
          <div class="subtab-body">
            {#if activeHelpSubTab === 'guides'}
              <GuidesPane
                {ollamaRunning}
                {ollamaModelReady}
                folderSelected={!!selectedFolder}
                {filesIndexed}
                {collectionsCreated}
                {mcpConnected}
                {onSelectFolder}
                {onCopyMcpConfig}
              />
            {:else if activeHelpSubTab === 'reference'}
              <ReferencePane />
            {:else if activeHelpSubTab === 'about'}
              <AboutPane
                {dataDir}
                {onOpenDataDir}
              />
            {/if}
          </div>
        </div>
      {/if}
    </div>
  </div>
</Modal>

<style>
  .panel-content {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
  }

  .tab-nav {
    display: flex;
    gap: 0.25rem;
    padding: 0.5rem 1rem 0;
    border-bottom: 1px solid var(--border-subtle);
    flex-shrink: 0;
  }

  .tab-btn {
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    padding: 0.4rem 0.85rem 0.55rem;
    font-family: var(--font-heading, var(--font-body));
    font-size: 0.85rem;
    color: var(--text-secondary);
    cursor: pointer;
    transition: color var(--transition-fast), border-color var(--transition-fast);
  }
  .tab-btn:hover:not(.active) {
    color: var(--text-primary);
  }
  .tab-btn.active {
    color: var(--text-accent);
    border-bottom-color: var(--text-accent);
  }

  .tab-body {
    flex: 1;
    min-height: 0;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }

  .help-pane {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
  }

  .subtab-nav {
    display: flex;
    gap: 0.15rem;
    padding: 0.5rem 1rem 0;
    border-bottom: 1px solid var(--border-subtle);
    flex-shrink: 0;
  }

  .subtab-btn {
    background: transparent;
    border: none;
    border-bottom: 1px solid transparent;
    padding: 0.3rem 0.6rem 0.4rem;
    font-family: var(--font-heading, var(--font-body));
    font-size: 0.78rem;
    letter-spacing: 0.04em;
    color: var(--text-tertiary);
    cursor: pointer;
    transition: color var(--transition-fast), border-color var(--transition-fast);
  }
  .subtab-btn:hover:not(.active) {
    color: var(--text-secondary);
  }
  .subtab-btn.active {
    color: var(--text-accent);
    border-bottom-color: var(--text-accent);
  }

  .subtab-body {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding: 1rem;
  }
</style>
