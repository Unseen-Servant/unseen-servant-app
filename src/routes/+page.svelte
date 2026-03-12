<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { invoke } from '@tauri-apps/api/core';
  import { listen } from '@tauri-apps/api/event';
  import { writeText } from '@tauri-apps/plugin-clipboard-manager';
  import { revealItemInDir } from '@tauri-apps/plugin-opener';
  import { load } from '@tauri-apps/plugin-store';
  import type { FileItem, IndexStatusResult, SyncResult, KnownGameSystem, KnownGameSystemsResult, StatsResult, CollectionInfo, CollectionsResult, CollectionMutationResult } from '../lib/types';
  import FileTree from '../lib/FileTree.svelte';
  import CollectionBar from '../lib/CollectionBar.svelte';
  import Header from '../lib/Header.svelte';
  import StatusBar from '../lib/StatusBar.svelte';
  import NotificationBanner from '../lib/NotificationBanner.svelte';
  import LicenseModal from '../lib/LicenseModal.svelte';
  import { notification } from '../lib/notificationStore';
  import { computeAncestorPaths, areAllDescendantsSelected } from '../lib/selectionUtils';

  let selectedFolder = '';
  let files: FileItem[] = [];
  let selectedPaths = new Set<string>;
  let syncedPaths = new Set<string>;
  let error = '';

  // Game system tag editing
  let knownSystems: KnownGameSystem[] = [];

  // Collections state
  let collections: Record<string, CollectionInfo> = {};
  let editingCollectionName: string | null = null;
  let isCreatingCollection = false;
  let collectionEditPaths = new Set<string>();
  let collectionEditName = '';
  let collectionEditDescription = '';
  let highlightedCollection: string | null = null;

  // Index sync state
  let indexStatus: IndexStatusResult | null = null;
  let isLoadingStatus = false;
  let isSyncing = false;
  let statusTimeout: ReturnType<typeof setTimeout> | null = null;

  // Sidecar stats
  let storageBytes = 0;
  let totalChunks = 0;
  let reclaimableBytes = 0;

  // Sidecar health
  let sidecarConnected = false;
  let lastSyncTime: Date | null = null;
  let autoSyncInterval: ReturnType<typeof setInterval> | null = null;
  let showLicense = false;
  let healthInterval: ReturnType<typeof setInterval> | null = null;

  onMount(async () => {
    try {
      const store = await load('settings.json');
      const savedFolder = await store.get<string>('selectedFolder');
      const savedPaths = await store.get<string[]>('syncedPaths')
        ?? await store.get<string[]>('selectedPaths');

      if (savedFolder) {
        selectedFolder = savedFolder;
        await loadFiles(savedFolder);
      }
      if (savedPaths) {
        selectedPaths = new Set(savedPaths);
        syncedPaths = new Set(savedPaths);
        if (savedPaths.length > 0) {
          await refreshIndexStatus();
        }
      }
      await loadCollections();
    } catch (e) {
      // No saved state on first run — that's fine
      console.log('No saved state:', e);
    }

    // Poll sidecar health
    checkSidecarHealth();
    healthInterval = setInterval(checkSidecarHealth, 10000);

    // Auto-sync: periodically check for filesystem changes
    autoSyncInterval = setInterval(() => {
      if (selectedPaths.size > 0 && sidecarConnected && !isSyncing) {
        refreshIndexStatus();
      }
    }, 60_000);
  });

  onDestroy(() => {
    if (healthInterval) clearInterval(healthInterval);
    if (autoSyncInterval) clearInterval(autoSyncInterval);
  });

  async function checkSidecarHealth() {
    try {
      sidecarConnected = await invoke<boolean>('check_sidecar_health');
    } catch {
      sidecarConnected = false;
    }
  }

  async function refreshIndexStatus() {
    isLoadingStatus = true;
    try {
      indexStatus = await invoke<IndexStatusResult>(
        'get_index_status',
        { paths: Array.from(selectedPaths) }
      );

      // Load known systems for tag editing (retry until loaded)
      if (knownSystems.length === 0) {
        const result = await invoke<KnownGameSystemsResult>('get_known_game_systems');
        knownSystems = result.systems.sort((a, b) =>
          a.tag.toLowerCase().localeCompare(b.tag.toLowerCase())
        );
      }

      // Fetch storage size in parallel (non-blocking)
      invoke<StatsResult>('get_stats')
        .then(r => { storageBytes = r.storage_bytes; totalChunks = r.total_chunks; reclaimableBytes = r.reclaimable_bytes; })
        .catch(() => { storageBytes = 0; totalChunks = 0; reclaimableBytes = 0; });

      // Auto-sync renames, deletions, and stale paths silently — no user interaction needed
      const { rename, auto_remove, stale } = indexStatus.summary;
      if ((rename > 0 || auto_remove > 0 || stale > 0) && !isSyncing) {
        handleSync();
        return;
      }

      lastSyncTime = new Date();
      showSyncPromptIfNeeded();
    } catch (e) {
      // Sidecar might not be ready yet on startup
      console.log('Could not fetch index status:', e);
      indexStatus = null;
    } finally {
      isLoadingStatus = false;
    }
  }

  function showSyncPromptIfNeeded() {
    if (!indexStatus || isCollectionEditMode) return;

    const { add, remove, update, errors } = indexStatus.summary;
    // Renames are auto-synced, so exclude them from the manual prompt
    const pending = add + remove + update;

    if (pending === 0 && errors === 0) {
      notification.dismiss();
      return;
    }

    const parts: string[] = [];
    if (add > 0) parts.push(`${add} to add`);
    if (remove > 0) parts.push(`${remove} to remove`);
    if (update > 0) parts.push(`${update} to update`);
    if (errors > 0) parts.push(`${errors} error(s)`);

    notification.show({
      type: 'action',
      message: parts.join(', '),
      actionLabel: isSyncing ? 'Syncing...' : 'Sync Now',
      onAction: isSyncing ? undefined : handleSync,
      onDismiss: revertToSyncedPaths,
      duration: null,
    });
  }

  async function revertToSyncedPaths() {
    selectedPaths = new Set(syncedPaths);
    await saveState();
    await refreshIndexStatus();
  }

  function scheduleStatusRefresh() {
    if (statusTimeout) clearTimeout(statusTimeout);
    statusTimeout = setTimeout(() => refreshIndexStatus(), 500);
  }

  async function saveState() {
    const store = await load('settings.json');
    await store.set('selectedFolder', selectedFolder);
    await store.set('selectedPaths', Array.from(selectedPaths));
    await store.save();
  }

  async function handleSelectFolder() {
    try {
      const folder = await invoke<string>('select_folder');
      selectedFolder = folder;
      await loadFiles(selectedFolder);
      error = '';
      await saveState();
    } catch (e) {
      // User cancelled the dialog — keep the current folder
      if (!selectedFolder) {
        error = String(e);
      }
    }
  }

  async function loadFiles(path: string) {
    try {
      files = await invoke<FileItem[]>('list_files', { folderPath: path });
      error = '';
    } catch (e) {
      error = String(e);
      files = [];
    }
  }

  async function toogleSelection(path: string, isDir: boolean, item: FileItem) {
    if (isDir) {
      // Toggle folder: recursively add/remove all PDFs
      await toggleFolderRecursive(item);
    } else {
      // Toggle single PDF file
      if (selectedPaths.has(path)) {
        selectedPaths.delete(path);
      } else {
        selectedPaths.add(path);
      }
      selectedPaths = selectedPaths; // Trigger reactivity
      await saveState();
      scheduleStatusRefresh();
    }
  }

  async function toggleFolderRecursive(folder: FileItem) {
    // If children are not loaded, load them first
    if (folder.children === null) {
      try {
        folder.children = await invoke<FileItem[]>('list_files', { folderPath: folder.path });
        files = files; // Trigger reactivity
      } catch (e) {
        console.error('Failed to load folder:', e);
        folder.children = [];
      }
    }
    
    // Deselect only when ALL descendants are selected; otherwise select all
    const allSelected = areAllDescendantsSelected(folder, selectedPaths);
    const shouldSelect = !allSelected;

    // Recursively add/remove all children
    if (folder.children) {
      for (const child of folder.children) {
        if (child.is_dir) {
          await setFolderSelection(child, shouldSelect);
        } else {
          // It's a PDF file
          if (shouldSelect) {
            selectedPaths.add(child.path);
          } else {
            selectedPaths.delete(child.path);
          }
        }
      }
    }
    selectedPaths = selectedPaths; // Trigger reactivity
    await saveState();
    scheduleStatusRefresh();
  }

  async function setFolderSelection(folder: FileItem, select: boolean) {
    if (!folder.is_dir) return;

    if (folder.children === null) {
      try {
        folder.children = await invoke<FileItem[]>('list_files', { folderPath: folder.path });
        files = files; // Trigger reactivity
      } catch (e) {
        console.error('Failed to load folder:', e);
        folder.children = [];
      }
    }

    if (folder.children) {
      for (const child of folder.children) {
        if (child.is_dir) {
          await setFolderSelection(child, select);
        } else {
          if (select) {
            selectedPaths.add(child.path);
          } else {
            selectedPaths.delete(child.path);
          }
        }
      }
    }
  }

  // Derive which folders contain selected items — purely from path strings, no tree walking
  $: foldersWithSelections = computeAncestorPaths(selectedPaths);

  // Build a map of file path → game system from index status data
  $: gameSystemMap = buildGameSystemMap(indexStatus);

  // Track which files are in the index (so untagged indexed files show the "+" button)
  $: indexedPaths = buildIndexedPaths(indexStatus);

  // Count files per game system, sorted by count descending
  $: gameSystemStats = (() => {
    if (!indexStatus) return [];
    const counts = new Map<string, number>();
    for (const e of [...indexStatus.up_to_date, ...indexStatus.to_update, ...indexStatus.to_remove]) {
      if (e.game_system && e.game_system !== 'unknown') {
        counts.set(e.game_system, (counts.get(e.game_system) ?? 0) + 1);
      }
    }
    return [...counts.entries()]
      .sort((a, b) => b[1] - a[1])
      .map(([name, count]) => ({ name, count }));
  })();
  $: gameSystemCount = gameSystemStats.length;
  $: gameSystemNames = gameSystemStats.map(s => s.name);
  $: topGameSystem = gameSystemStats.length > 0
    ? `Top system: ${gameSystemStats[0].name} with ${gameSystemStats[0].count} file${gameSystemStats[0].count === 1 ? '' : 's'}`
    : '';

  // Collection mode derived state
  $: isCollectionEditMode = editingCollectionName !== null || isCreatingCollection;
  $: treeMode = isCollectionEditMode ? 'collection' as const : 'index' as const;
  $: highlightPaths = highlightedCollection && collections[highlightedCollection]
    ? new Set(collections[highlightedCollection].file_paths)
    : new Set<string>();
  $: collectionFolders = computeAncestorPaths(collectionEditPaths);

  function buildGameSystemMap(status: IndexStatusResult | null): Map<string, string> {
    const map = new Map<string, string>();
    if (!status) return map;
    for (const entry of [...status.up_to_date, ...status.to_update, ...status.to_remove]) {
      if (entry.game_system && entry.game_system !== 'unknown') {
        map.set(entry.path, entry.game_system);
      }
    }
    return map;
  }

  function buildIndexedPaths(status: IndexStatusResult | null): Set<string> {
    const paths = new Set<string>();
    if (!status) return paths;
    for (const entry of [...status.up_to_date, ...status.to_update, ...status.to_remove]) {
      paths.add(entry.path);
    }
    return paths;
  }

  async function handleSetGameSystem(_path: string, filename: string, tag: string) {
    try {
      await invoke('set_game_system', { filename, gameSystem: tag });
      await refreshIndexStatus();
    } catch (e) {
      console.error('Failed to set game system:', e);
    }
  }


  // ---------------------------------------------------------------------------
  // Collections
  // ---------------------------------------------------------------------------

  async function loadCollections() {
    try {
      const result = await invoke<CollectionsResult>('get_collections');
      collections = result.collections;
    } catch (e) {
      console.log('Could not fetch collections:', e);
    }
  }

  function startCreateCollection() {
    collectionEditName = '';
    collectionEditDescription = '';
    collectionEditPaths = new Set();
    isCreatingCollection = true;
    editingCollectionName = null;
    highlightedCollection = null;
  }

  function startEditCollection(name: string) {
    const col = collections[name];
    if (!col) return;
    collectionEditName = col.name;
    collectionEditDescription = col.description;
    collectionEditPaths = new Set(col.file_paths);
    editingCollectionName = name;
    isCreatingCollection = false;
    highlightedCollection = null;
  }

  function cancelCollectionEdit() {
    editingCollectionName = null;
    isCreatingCollection = false;
    collectionEditPaths = new Set();
    collectionEditName = '';
    collectionEditDescription = '';
  }

  async function saveCollection() {
    const name = collectionEditName.trim();
    console.log('[saveCollection] called', { name, isCreatingCollection, editingCollectionName, pathCount: collectionEditPaths.size });
    if (!name) {
      console.warn('[saveCollection] name is empty, aborting');
      return;
    }
    const filePaths = Array.from(collectionEditPaths);

    try {
      if (isCreatingCollection) {
        console.log('[saveCollection] creating', { name, filePaths, description: collectionEditDescription });
        const result = await invoke<CollectionMutationResult>('create_collection', {
          name,
          filePaths,
          description: collectionEditDescription,
        });
        console.log('[saveCollection] created', result);
      } else if (editingCollectionName) {
        // If name changed, delete old and create new
        if (editingCollectionName !== name) {
          console.log('[saveCollection] renaming', editingCollectionName, '→', name);
          await invoke('delete_collection', { name: editingCollectionName });
          const result = await invoke<CollectionMutationResult>('create_collection', {
            name,
            filePaths,
            description: collectionEditDescription,
          });
          console.log('[saveCollection] renamed', result);
        } else {
          console.log('[saveCollection] updating', { name, filePaths, description: collectionEditDescription });
          const result = await invoke<CollectionMutationResult>('update_collection', {
            name,
            filePaths,
            description: collectionEditDescription,
          });
          console.log('[saveCollection] updated', result);
        }
      } else {
        console.warn('[saveCollection] neither creating nor editing — no-op');
      }
      cancelCollectionEdit();
      await loadCollections();
      console.log('[saveCollection] done');
    } catch (e) {
      console.error('[saveCollection] FAILED:', e);
    }
  }

  async function deleteCollection(name: string) {
    try {
      await invoke('delete_collection', { name });
      cancelCollectionEdit();
      await loadCollections();
    } catch (e) {
      console.error('Failed to delete collection:', e);
    }
  }

  function handleCollectionToggle(path: string, isDir: boolean, item: FileItem) {
    if (isDir) {
      toggleCollectionFolder(item);
    } else {
      if (collectionEditPaths.has(path)) {
        collectionEditPaths.delete(path);
      } else {
        collectionEditPaths.add(path);
      }
      collectionEditPaths = collectionEditPaths;
    }
  }

  function toggleCollectionFolder(folder: FileItem) {
    if (!folder.children) return;
    // Deselect only when ALL indexed descendants are in the collection
    const allIn = areAllDescendantsSelected(folder, collectionEditPaths, indexedPaths);
    const shouldAdd = !allIn;
    setCollectionFolderRecursive(folder, shouldAdd);
    collectionEditPaths = collectionEditPaths;
  }

  function setCollectionFolderRecursive(folder: FileItem, add: boolean) {
    if (!folder.children) return;
    for (const child of folder.children) {
      if (child.is_dir) {
        setCollectionFolderRecursive(child, add);
      } else if (indexedPaths.has(child.path)) {
        if (add) {
          collectionEditPaths.add(child.path);
        } else {
          collectionEditPaths.delete(child.path);
        }
      }
    }
  }

  function toggleCollectionHighlight(name: string | null) {
    highlightedCollection = name;
  }

  // Copy MCP config to clipboard
  async function handleCopyMcpConfig() {
    try {
      const config = await invoke<string>('get_mcp_config');
      await writeText(config);
      notification.show({
        type: 'success',
        message: 'MCP config copied to clipboard!',
        duration: 4000,
      });
    } catch (e) {
      notification.show({
        type: 'error',
        message: `Copy failed: ${String(e)}`,
        duration: 5000,
      });
    }
  }

  // Compact the database to reclaim unused space
  async function handleCompact() {
    try {
      const result = await invoke<{ reclaimed: number }>('compact_database');
      const msg = result.reclaimed > 0
        ? `Reclaimed ${formatSize(result.reclaimed)}`
        : 'Nothing to reclaim';
      notification.show({ type: 'success', message: msg, duration: 4000 });
      await refreshIndexStatus(); // refresh stats to update reclaimable_bytes
    } catch (e) {
      notification.show({ type: 'error', message: `Compact failed: ${String(e)}`, duration: 5000 });
    }
  }

  function formatSize(bytes: number): string {
    if (bytes >= 1_073_741_824) return (bytes / 1_073_741_824).toFixed(1) + ' GB';
    if (bytes >= 1_048_576) return (bytes / 1_048_576).toFixed(1) + ' MB';
    if (bytes >= 1_024) return (bytes / 1_024).toFixed(0) + ' KB';
    return bytes + ' B';
  }

  // Sync index: add new, remove deselected, re-index modified
  async function handleSync() {
    isSyncing = true;
    notification.dismiss();

    notification.show({
      type: 'progress',
      message: 'Starting sync...',
      filesCompleted: 0,
      filesTotal: 0,
      chunksProcessed: 0,
      duration: null,
    });

    const unlisten = await listen<{
      files_done: number;
      total_files: number;
      chunks_total: number;
      current_file: string;
      phase: string;
    }>('sync-progress', (event) => {
      const p = event.payload;
      notification.show({
        type: 'progress',
        message: `${p.files_done}/${p.total_files} files`,
        filesCompleted: p.files_done,
        filesTotal: p.total_files,
        chunksProcessed: p.chunks_total,
        duration: null,
      });
    });

    try {
      const result = await invoke<SyncResult>(
        'sync_index',
        { paths: Array.from(selectedPaths) }
      );
      // Apply renames to selectedPaths before persisting
      if (result.renames && result.renames.length > 0) {
        for (const { old_path, new_path } of result.renames) {
          selectedPaths.delete(old_path);
          selectedPaths.add(new_path);
        }
      }

      // Remove auto-removed paths (files deleted from disk)
      if (result.auto_removed_paths && result.auto_removed_paths.length > 0) {
        for (const path of result.auto_removed_paths) {
          selectedPaths.delete(path);
        }
      }

      // Remove stale paths (orphaned selections — not on disk, never indexed)
      if (result.stale_paths && result.stale_paths.length > 0) {
        for (const path of result.stale_paths) {
          selectedPaths.delete(path);
        }
      }

      // Trigger Svelte reactivity if paths changed
      if ((result.renames?.length > 0) || (result.auto_removed_paths?.length > 0) || (result.stale_paths?.length > 0)) {
        selectedPaths = selectedPaths;
      }

      const parts = [];
      if (result.added > 0) parts.push(`${result.added} added`);
      if (result.removed > 0) parts.push(`${result.removed} removed`);
      if (result.auto_removed > 0) parts.push(`${result.auto_removed} removed (deleted from disk)`);
      if (result.renamed > 0) parts.push(`${result.renamed} renamed`);
      if (result.updated > 0) parts.push(`${result.updated} updated`);
      if (result.errors.length > 0) parts.push(`${result.errors.length} error(s)`);
      const chunkStr = result.chunks_total > 0
        ? ` ${result.chunks_total.toLocaleString()} chunks.`
        : '';
      const msg = parts.length > 0
        ? `Synced: ${parts.join(', ')}.${chunkStr}`
        : 'Nothing to sync.';

      // Record successful sync time for status bar tooltip
      lastSyncTime = new Date();

      // Persist synced selection so uncommitted changes don't survive a restart
      syncedPaths = new Set(selectedPaths);
      const store = await load('settings.json');
      await store.set('syncedPaths', Array.from(selectedPaths));
      await store.save();

      await refreshIndexStatus();
      await loadCollections();

      // Refresh file tree if renames, auto-removals, or stale cleanups occurred
      if (((result.renames?.length > 0) || (result.auto_removed_paths?.length > 0) || (result.stale_paths?.length > 0)) && selectedFolder) {
        await loadFiles(selectedFolder);
      }

      notification.show({
        type: result.errors.length > 0 ? 'error' : 'success',
        message: msg,
        duration: 5000,
      });
    } catch (e) {
      const msg = `Sync failed: ${String(e)}`;
      notification.show({ type: 'error', message: msg, duration: 6000 });

    } finally {
      unlisten();
      isSyncing = false;
    }
  }

  function handleManualSync() {
    if (selectedPaths.size > 0 && sidecarConnected && !isSyncing) {
      refreshIndexStatus();
    }
  }

</script>

<main class="app-layout">
  <Header />

  {#if selectedFolder}
    <div class="collections-area">
      <CollectionBar
        {collections}
        editingName={editingCollectionName}
        isCreating={isCreatingCollection}
        bind:editName={collectionEditName}
        bind:editDescription={collectionEditDescription}
        editFileCount={collectionEditPaths.size}
        highlightedName={highlightedCollection}
        onStartCreate={startCreateCollection}
        onStartEdit={startEditCollection}
        onSave={saveCollection}
        onCancel={cancelCollectionEdit}
        onDelete={deleteCollection}
        onHighlight={toggleCollectionHighlight}
      />
    </div>

    <div class="file-tree-area">
      {#each files as file (file.path)}
        <FileTree
          item={file}
          level={0}
          {selectedPaths}
          {foldersWithSelections}
          {gameSystemMap}
          {knownSystems}
          {indexedPaths}
          onToggle={toogleSelection}
          onSetGameSystem={handleSetGameSystem}
          mode={treeMode}
          collectionPaths={collectionEditPaths}
          {collectionFolders}
          {highlightPaths}
          onCollectionToggle={handleCollectionToggle}
        />
      {/each}
      <NotificationBanner />
    </div>
  {:else}
    <div class="empty-state">
      <p class="empty-title font-heading">Select a folder to begin</p>
      <p class="empty-subtitle">Choose your TTRPG library folder to browse and index your collection.</p>
      <button class="empty-btn" on:click={handleSelectFolder}>
        Choose Library Folder
      </button>
    </div>
  {/if}

  {#if error}
    <div class="error-banner">Error: {error}</div>
  {/if}

  <StatusBar
    {selectedFolder}
    {sidecarConnected}
    selectedCount={selectedPaths.size}
    indexedCount={(indexStatus?.summary?.up_to_date ?? 0) + (indexStatus?.summary?.update ?? 0) + (indexStatus?.summary?.remove ?? 0)}
    {gameSystemCount}
    {topGameSystem}
    {totalChunks}
    {storageBytes}
    {reclaimableBytes}
    {isSyncing}
    {lastSyncTime}
    onSync={handleManualSync}
    onCompact={handleCompact}
    onCopyMcpConfig={handleCopyMcpConfig}
    onSelectFolder={handleSelectFolder}
    onOpenFolder={() => { if (selectedFolder) revealItemInDir(selectedFolder); }}
    onShowLicense={() => { showLicense = true; }}
  />
</main>

<LicenseModal visible={showLicense} onClose={() => { showLicense = false; }} />

<style>
  .app-layout {
    display: flex;
    flex-direction: column;
    height: 100vh;
    overflow: hidden;
    background: var(--bg-app);
  }

  .collections-area {
    flex-shrink: 0;
    padding: 0.5rem 1rem;
    border-bottom: 1px solid var(--border-subtle);
    background: var(--bg-container);
  }

  .file-tree-area {
    flex: 1;
    overflow-y: auto;
    padding: 0.25rem 0.75rem;
  }

  .empty-state {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    color: var(--text-secondary);
  }

  .empty-title {
    font-size: 1.4rem;
    color: var(--text-accent);
    margin: 0;
  }

  .empty-subtitle {
    font-size: 0.95rem;
    margin: 0;
  }

  .empty-btn {
    margin-top: 0.75rem;
    padding: 0.5rem 1.25rem;
    border-radius: 4px;
    border: 1px solid var(--border-accent);
    background: transparent;
    color: var(--text-accent);
    font-family: var(--font-heading);
    font-size: 1rem;
    transition: all var(--transition-fast);
  }
  .empty-btn:hover {
    background: rgba(182, 159, 129, 0.1);
  }
  .empty-btn:active {
    transform: scale(0.97);
  }

  .error-banner {
    padding: 0.4rem 1rem;
    background: rgba(239, 68, 68, 0.1);
    color: var(--text-danger);
    border-top: 1px solid rgba(239, 68, 68, 0.3);
    font-size: 0.85rem;
    flex-shrink: 0;
  }
</style>
