<script lang="ts">
  import type { KnownGameSystem, SyncPreferences } from '../legend-lore/types';
  import { DEFAULT_SYNC_PREFERENCES } from '../legend-lore/types';
  import Modal from './Modal.svelte';
  import GameSystemsSettings from '../legend-lore/GameSystemsSettings.svelte';
  import GeneralSettings from '../legend-lore/GeneralSettings.svelte';
  import LibrarySettings from '../legend-lore/LibrarySettings.svelte';
  import GuidesPane from './help/GuidesPane.svelte';
  import ReferencePane from './help/ReferencePane.svelte';
  import AboutPane from './help/AboutPane.svelte';

  export let visible = false;
  export let onClose: () => void;
  export let knownSystems: KnownGameSystem[] = [];
  export let onSystemsChanged: () => void = () => {};
  export let selectedFolder: string = '';
  export let indexedFileCount: number = 0;
  export let outdatedFileCount: number = 0;
  export let totalFilesFound: number = 0;
  export let totalChunks: number = 0;
  export let storageBytes: number = 0;
  export let gameSystemCount: number = 0;
  export let isSyncing: boolean = false;
  export let syncPreferences: SyncPreferences = { ...DEFAULT_SYNC_PREFERENCES };
  export let dataDir: string = '';
  export let lastSyncTime: Date | null = null;
  export let onSelectFolder: () => void = () => {};
  export let onDeselectFolder: () => void = () => {};
  export let onReindexAll: () => void = () => {};
  export let onDeleteIndex: () => void = () => {};
  export let onSyncPreferencesChange: (partial: Partial<SyncPreferences>) => void = () => {};
  export let dimWeakResults: boolean = true;
  export let onDimWeakResultsChange: (value: boolean) => void = () => {};
  export let onOpenDataDir: () => void = () => {};
  export let onSync: () => void = () => {};
  export let onCopyMcpConfig: () => void = () => {};
  export let ollamaRunning: boolean = false;
  export let ollamaModelReady: boolean = false;
  export let filesIndexed: boolean = false;
  export let collectionsCreated: boolean = false;
  export let mcpConnected: boolean = false;
  export let initialTab: 'general' | 'library' | 'game-systems' | 'help' = 'general';
  export let initialHelpSubTab: 'guides' | 'reference' | 'about' = 'guides';

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

<Modal {visible} {onClose} title="Settings" size="lg" height="min(486px, 80vh)" autofocus={false} escapeWord="close">
  <!-- The picker rides the rail beside the nameplate, the way the header
       carries its view switch: which section you are in is part of the unit's
       identity, not the first row of its contents. -->
  <svelte:fragment slot="rail">
    <span class="rail-rule" aria-hidden="true"></span>
    <nav class="seg" aria-label="Settings sections">
      {#each tabs as tab}
        <button
          class="seg-btn"
          class:current={activeTab === tab.id}
          aria-current={activeTab === tab.id ? 'page' : undefined}
          on:click={() => { activeTab = tab.id; }}
        >{tab.label}</button>
      {/each}
    </nav>
  </svelte:fragment>

  <div class="tab-body">
    {#if activeTab === 'general'}
      <GeneralSettings {dimWeakResults} {onDimWeakResultsChange} />
    {:else if activeTab === 'game-systems'}
      <GameSystemsSettings {knownSystems} {onSystemsChanged} />
    {:else if activeTab === 'library'}
      <LibrarySettings
        {selectedFolder}
        {indexedFileCount}
        {outdatedFileCount}
        {totalFilesFound}
        {totalChunks}
        {storageBytes}
        {gameSystemCount}
        {isSyncing}
        {syncPreferences}
        {dataDir}
        {lastSyncTime}
        {onSelectFolder}
        {onDeselectFolder}
        {onReindexAll}
        {onDeleteIndex}
        {onSyncPreferencesChange}
        {onOpenDataDir}
        {onSync}
      />
    {:else if activeTab === 'help'}
      <div class="help-pane">
        <nav class="seg subtab-seg" aria-label="Help sections">
          {#each helpSubTabs as sub}
            <button
              class="seg-btn"
              class:current={activeHelpSubTab === sub.id}
              aria-current={activeHelpSubTab === sub.id ? 'page' : undefined}
              on:click={() => { activeHelpSubTab = sub.id; }}
            >{sub.label}</button>
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
</Modal>

<style>
  /* One picker vocabulary, reusing the header's view switch: a segmented
     control recessed into a darker well, the current segment raised. Never
     purple — it is a position, not a mode.

     Deliberately a local copy of `.view-switch`'s recipe rather than a shared
     class: the header's segments are 24×22px icon cells and these are text
     cells sized to the rail, so the two share a shape and nothing else. A
     shared class would have to carry both sizings. */
  .seg {
    display: flex;
    gap: 2px;
    padding: 2px;
    background: var(--bg-app);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-well);
    flex-shrink: 0;
  }
  .seg-btn {
    display: inline-flex;
    align-items: center;
    height: 20px;
    padding: 0.1rem 0.55rem;
    background: transparent;
    border: none;
    border-radius: var(--radius-sm);
    font-family: var(--font-heading);
    font-size: 0.72rem;
    letter-spacing: 0.03em;
    color: var(--text-tertiary);
    cursor: pointer;
    transition: color var(--transition-fast), background var(--transition-fast);
  }
  .seg-btn:hover:not(.current) {
    color: var(--text-primary);
  }
  .seg-btn.current {
    background: var(--bg-header);
    color: var(--text-primary);
  }
  .seg-btn:focus-visible {
    outline: 1px solid var(--text-accent);
    outline-offset: 1px;
  }

  /* The sub-picker sits inside the pane rather than on the rail, so it needs
     its own top margin. Same size and colours — nesting is the only difference,
     which is what the hierarchy actually is. */
  .seg.subtab-seg {
    align-self: flex-start;
    margin: 0.5rem 1rem 0;
  }

  /* `.rail-rule` is global (Task 3). */

  /* The pane region. It used to sit inside a `.panel-content` column that also
     held the tab band; with the band on the rail that wrapper was a flex item
     whose only child was this one, so it is gone and this is the dialog's
     middle child directly. */
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

  .subtab-body {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding: var(--modal-pad);
  }
</style>
