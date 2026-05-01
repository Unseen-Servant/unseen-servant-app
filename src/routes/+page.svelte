<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { invoke } from '@tauri-apps/api/core';
  import { writeText } from '@tauri-apps/plugin-clipboard-manager';
  import { openPath, openUrl, revealItemInDir } from '@tauri-apps/plugin-opener';
  import { pdfFileUrl } from '../lib/pdfUrl';
  import { confirm } from '@tauri-apps/plugin-dialog';
  import { load } from '@tauri-apps/plugin-store';
  import type { FileItem, IndexStatusResult, SyncResult, KnownGameSystem, KnownGameSystemsResult, StatsResult, CollectionInfo, CollectionsResult, CollectionMutationResult, ActiveContextResult, SearchResultItem, SearchResponse, SyncPreferences, PromptCounts, SyncAction } from '../lib/types';
  import { DEFAULT_SYNC_PREFERENCES } from '../lib/types';
  import FileTree from '../lib/FileTree.svelte';
  import ContextMenu from '../lib/ContextMenu.svelte';
  import CollectionBar from '../lib/CollectionBar.svelte';
  import Header from '../lib/Header.svelte';
  import SearchResults from '../lib/SearchResults.svelte';
  import StatusBar from '../lib/StatusBar.svelte';
  import NotificationBanner from '../lib/NotificationBanner.svelte';
  import LicenseModal from '../lib/LicenseModal.svelte';
  import GettingStartedModal from '../lib/GettingStartedModal.svelte';
  import GettingStartedPage from '../lib/GettingStartedPage.svelte';
  import SettingsModal from '../lib/SettingsModal.svelte';
  import DocumentStatsModal from '../lib/DocumentStatsModal.svelte';
  import ConfirmDialog from '../lib/ConfirmDialog.svelte';
  import { notification } from '../lib/notificationStore';
  import { computeAncestorPaths, areAllDescendantsSelected } from '../lib/selectionUtils';
  import { runSyncJob } from '../lib/syncJob';

  let selectedFolder = '';
  let files: FileItem[] = [];
  let selectedPaths = new Set<string>;
  let syncedPaths = new Set<string>;
  let expandedPaths = new Set<string>();
  let error = '';

  let totalFilesFound = 0;

  async function refreshTotalFilesFound() {
    if (!selectedFolder) {
      totalFilesFound = 0;
      return;
    }
    try {
      totalFilesFound = await invoke<number>('count_pdfs_recursive', { folderPath: selectedFolder });
    } catch (e) {
      console.log('Could not count PDFs:', e);
      totalFilesFound = 0;
    }
  }

  // File focus & context menu
  let focusedFilePath: string | null = null;
  let contextMenu: { x: number; y: number; item: FileItem; isIndexed: boolean } | null = null;
  let renamingFilePath: string | null = null;
  let statsModalPath: string | null = null;

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
  let activeContextName: string | null = null;

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
  let showGuide = false;
  let showSettings = false;
  let healthInterval: ReturnType<typeof setInterval> | null = null;

  // User-configurable behavior
  let syncPreferences: SyncPreferences = { ...DEFAULT_SYNC_PREFERENCES };
  let dataDir = '';

  // Ollama health
  let ollamaRunning = false;
  let ollamaModelReady = false;

  // In-app search state
  let searchQuery = '';
  let committedQuery = '';
  let searchResults: SearchResultItem[] = [];
  let isSearching = false;
  let searchError: string | null = null;
  let searchSeq = 0;
  $: searchActive = committedQuery.trim() !== '';
  $: indexedPathsSet = new Set<string>(
    (indexStatus?.up_to_date ?? []).map((e) => e.path)
      .concat((indexStatus?.to_update ?? []).map((e) => e.path))
  );

  async function runSearch(q: string) {
    const trimmed = q.trim();
    if (!trimmed) {
      searchResults = [];
      searchError = null;
      isSearching = false;
      return;
    }
    if (!sidecarConnected) {
      searchError = 'Indexer not running';
      searchResults = [];
      isSearching = false;
      return;
    }
    searchSeq += 1;
    const seq = searchSeq;
    isSearching = true;
    searchError = null;
    try {
      const response = await invoke<SearchResponse>('search_index', {
        query: trimmed,
        nResults: 10,
      });
      if (seq !== searchSeq) return;
      searchResults = response.results ?? [];
    } catch (e) {
      if (seq !== searchSeq) return;
      searchError = String(e);
      searchResults = [];
    } finally {
      if (seq === searchSeq) {
        isSearching = false;
      }
    }
  }

  function handleSearchDebounced(q: string) {
    committedQuery = q.trim();
    runSearch(q);
  }

  function handleSearchSubmit(q: string) {
    committedQuery = q.trim();
    runSearch(q);
  }

  function handleSearchClear() {
    searchQuery = '';
    committedQuery = '';
    searchResults = [];
    searchError = null;
    isSearching = false;
    searchSeq += 1;
  }

  function resolvePathForFilename(filename: string): string | null {
    const target = filename.toLowerCase();
    for (const entry of indexStatus?.up_to_date ?? []) {
      if (entry.filename?.toLowerCase() === target) return entry.path;
    }
    for (const entry of indexStatus?.to_update ?? []) {
      if (entry.filename?.toLowerCase() === target) return entry.path;
    }
    return null;
  }

  async function handleOpenResult(filename: string, page?: number | null) {
    const path = resolvePathForFilename(filename);
    if (!path) {
      notification.show({
        type: 'error',
        message: `Could not locate "${filename}" on disk.`,
        duration: 4000,
      });
      return;
    }
    try {
      // With a page anchor, open via file:// URL so PDF viewers honouring
      // the standard `#page=N` fragment land on the right page (#113).
      // Viewers that ignore the fragment (notably macOS Preview) silently
      // open at page 1 — page 1 is also the openPath fallback below.
      if (page && page > 0) {
        await openUrl(pdfFileUrl(path, page));
      } else {
        await openPath(path);
      }
    } catch (e) {
      notification.show({
        type: 'error',
        message: `Failed to open ${filename}: ${e}`,
        duration: 4000,
      });
    }
  }

  onMount(async () => {
    try {
      const store = await load('settings.json');
      const savedFolder = await store.get<string>('selectedFolder');
      const savedPaths = await store.get<string[]>('syncedPaths')
        ?? await store.get<string[]>('selectedPaths');
      syncPreferences = await loadSyncPreferences(store);

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

    try {
      dataDir = await invoke<string>('get_data_dir');
    } catch (e) {
      console.log('Could not fetch data dir:', e);
    }

    // Poll sidecar + Ollama health
    checkSidecarHealth();
    checkOllamaHealth();
    healthInterval = setInterval(() => {
      checkSidecarHealth();
      checkOllamaHealth();
    }, 10000);

    restartAutoSyncInterval();
  });

  function restartAutoSyncInterval() {
    if (autoSyncInterval) {
      clearInterval(autoSyncInterval);
      autoSyncInterval = null;
    }
    const seconds = syncPreferences.backgroundCheckInterval;
    if (seconds <= 0) return;
    autoSyncInterval = setInterval(async () => {
      if (!sidecarConnected || isSyncing) return;
      // Skip during inline rename — re-rendering the tree would wipe the input
      if (renamingFilePath !== null) return;
      if (selectedFolder) await loadFiles(selectedFolder);
      if (selectedPaths.size > 0) refreshIndexStatus();
    }, seconds * 1000);
  }

  async function loadSyncPreferences(store: Awaited<ReturnType<typeof load>>): Promise<SyncPreferences> {
    const saved = await store.get<Record<string, unknown>>('syncPreferences');
    if (saved && typeof saved === 'object') {
      // Migrate prior boolean shape if present
      const merged: SyncPreferences = { ...DEFAULT_SYNC_PREFERENCES, ...(saved as Partial<SyncPreferences>) };
      if ('backgroundChecks' in saved && !('backgroundCheckInterval' in saved)) {
        merged.backgroundCheckInterval = saved.backgroundChecks ? 60 : 0;
      }
      return merged;
    }
    // Migrate legacy syncMode if present, then persist new shape and remove old key
    const legacy = await store.get<string>('syncMode');
    let migrated: SyncPreferences = { ...DEFAULT_SYNC_PREFERENCES };
    if (legacy === 'prompt') {
      migrated = { ...migrated, diskEventsPolicy: 'ask' };
    } else if (legacy === 'manual') {
      migrated = { ...migrated, backgroundCheckInterval: 0 };
    }
    if (legacy) {
      try {
        await store.set('syncPreferences', migrated);
        await store.delete('syncMode');
        await store.save();
      } catch (e) {
        console.log('Could not migrate syncMode:', e);
      }
    }
    return migrated;
  }

  async function handleSyncPreferencesChange(partial: Partial<SyncPreferences>) {
    syncPreferences = { ...syncPreferences, ...partial };
    try {
      const store = await load('settings.json');
      await store.set('syncPreferences', syncPreferences);
      await store.save();
    } catch (e) {
      console.log('Could not persist sync preferences:', e);
    }
    restartAutoSyncInterval();
    if (syncPreferences.backgroundCheckInterval === 0) {
      notification.dismiss();
    }
  }

  function handleOpenDataDir() {
    if (dataDir) openPath(dataDir);
  }

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

  async function checkOllamaHealth() {
    try {
      const status = await invoke<{ running: boolean; has_model: boolean }>('check_ollama_health');
      ollamaRunning = status.running;
      ollamaModelReady = status.has_model;
    } catch {
      ollamaRunning = false;
      ollamaModelReady = false;
    }
  }

  async function fetchIndexStatus(): Promise<IndexStatusResult | null> {
    isLoadingStatus = true;
    try {
      const status = await invoke<IndexStatusResult>(
        'get_index_status',
        { paths: Array.from(selectedPaths) }
      );
      indexStatus = status;

      if (knownSystems.length === 0) {
        await refreshKnownSystems();
      }

      invoke<StatsResult>('get_stats')
        .then(r => { storageBytes = r.storage_bytes; totalChunks = r.total_chunks; reclaimableBytes = r.reclaimable_bytes; })
        .catch(() => { storageBytes = 0; totalChunks = 0; reclaimableBytes = 0; });

      lastSyncTime = new Date();
      return status;
    } catch (e) {
      console.log('Could not fetch index status:', e);
      indexStatus = null;
      return null;
    } finally {
      isLoadingStatus = false;
    }
  }

  function decideSyncAction(
    status: IndexStatusResult,
    prefs: SyncPreferences,
    userTriggered: boolean
  ): SyncAction {
    if (prefs.backgroundCheckInterval === 0 && !userTriggered) {
      return { kind: 'noop' };
    }

    const { add, remove, update, errors, rename, auto_remove, stale } = status.summary;
    const diskTotal = rename + auto_remove + stale;

    const askDisk = prefs.diskEventsPolicy === 'ask' && diskTotal > 0;
    const askAdd = prefs.selectionPolicy === 'ask' && add > 0;
    const askRemove = prefs.deselectionPolicy === 'ask' && remove > 0;
    const askUpdate = prefs.modificationPolicy === 'ask' && update > 0;
    const anyAsk = askDisk || askAdd || askRemove || askUpdate;

    const silentDisk = prefs.diskEventsPolicy === 'silent' && diskTotal > 0;
    const silentAdd = prefs.selectionPolicy === 'silent' && add > 0;
    const silentRemove = prefs.deselectionPolicy === 'silent' && remove > 0;
    const silentUpdate = prefs.modificationPolicy === 'silent' && update > 0;
    const anySilent = silentDisk || silentAdd || silentRemove || silentUpdate;

    if (!anyAsk && !anySilent && errors === 0) {
      return { kind: 'noop' };
    }

    if (!anyAsk && errors === 0) {
      return { kind: 'silent' };
    }

    return {
      kind: 'prompt',
      counts: {
        disk: askDisk ? diskTotal : 0,
        add: askAdd ? add : 0,
        remove: askRemove ? remove : 0,
        update: askUpdate ? update : 0,
        errors,
      },
    };
  }

  async function applySyncAction(action: SyncAction) {
    if (action.kind === 'noop') {
      notification.dismiss();
      return;
    }
    if (action.kind === 'silent') {
      if (!isSyncing) handleSync();
      return;
    }
    showSyncPrompt(action.counts);
  }

  async function refreshIndexStatus(options: { userTriggered?: boolean } = {}) {
    const status = await fetchIndexStatus();
    if (!status) return;
    if (isCollectionEditMode) return;
    const action = decideSyncAction(status, syncPreferences, options.userTriggered ?? false);
    await applySyncAction(action);
  }

  function showSyncPrompt(counts: PromptCounts) {
    if (!indexStatus || isCollectionEditMode) return;

    const parts: string[] = [];
    if (counts.disk > 0) parts.push(`${counts.disk} disk change${counts.disk === 1 ? '' : 's'}`);
    if (counts.add > 0) parts.push(`${counts.add} to add`);
    if (counts.remove > 0) parts.push(`${counts.remove} to remove`);
    if (counts.update > 0) parts.push(`${counts.update} to update`);
    if (counts.errors > 0) parts.push(`${counts.errors} error${counts.errors === 1 ? '' : 's'}`);

    if (parts.length === 0) {
      notification.dismiss();
      return;
    }

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
      expandedPaths = new Set();
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
      refreshTotalFilesFound();
    } catch (e) {
      error = String(e);
      files = [];
      totalFilesFound = 0;
    }
  }

  let lastIndexClickedPath: string | null = null;
  let lastCollectionClickedPath: string | null = null;

  function flattenVisibleFilePaths(items: FileItem[]): string[] {
    const out: string[] = [];
    function walk(list: FileItem[]) {
      for (const item of list) {
        if (item.is_dir) {
          if (expandedPaths.has(item.path) && item.children) {
            walk(item.children);
          }
        } else {
          out.push(item.path);
        }
      }
    }
    walk(items);
    return out;
  }

  function applyRangeToggle(
    target: Set<string>,
    anchor: string,
    current: string,
    requireIndexed: boolean,
  ): boolean {
    const flat = flattenVisibleFilePaths(files);
    const a = flat.indexOf(anchor);
    const b = flat.indexOf(current);
    if (a === -1 || b === -1) return false;
    const lo = Math.min(a, b);
    const hi = Math.max(a, b);
    const shouldSelect = !target.has(current);
    for (let i = lo; i <= hi; i++) {
      const p = flat[i];
      if (requireIndexed && !indexedPaths.has(p)) continue;
      if (shouldSelect) target.add(p);
      else target.delete(p);
    }
    return true;
  }

  async function toogleSelection(path: string, isDir: boolean, item: FileItem, shiftKey: boolean = false) {
    if (shiftKey && !isDir && lastIndexClickedPath) {
      const ok = applyRangeToggle(selectedPaths, lastIndexClickedPath, path, false);
      if (ok) {
        selectedPaths = selectedPaths;
        lastIndexClickedPath = path;
        await saveState();
        scheduleStatusRefresh();
        return;
      }
    }

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
      lastIndexClickedPath = path;
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

  // Track which files are in the index (so untagged indexed files show the "+" button).
  // Stabilize identity: a refresh that returns the same content keeps the same Set
  // reference, so FileTree (which receives indexedPaths as a prop) doesn't re-render
  // every node on no-op refreshes.
  let indexedPaths = new Set<string>();
  $: indexedPaths = reuseIfSame(indexedPaths, buildIndexedPaths(indexStatus));

  function reuseIfSame(prev: Set<string>, next: Set<string>): Set<string> {
    if (prev.size !== next.size) return next;
    for (const p of next) if (!prev.has(p)) return next;
    return prev;
  }

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

  // Active context filter — narrows the tree to one collection's files plus
  // ancestor folders. Disabled while editing a collection (so the user can
  // still see the full tree to manage membership).
  $: displayPaths = (() => {
    if (isCollectionEditMode) return null;
    if (!activeContextName) return null;
    const col = collections[activeContextName];
    if (!col) return null;
    const filePaths = new Set(col.file_paths);
    const ancestors = computeAncestorPaths(filePaths);
    return new Set<string>([...filePaths, ...ancestors]);
  })();

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

  async function refreshKnownSystems() {
    try {
      const result = await invoke<KnownGameSystemsResult>('get_known_game_systems');
      knownSystems = result.systems.sort((a, b) =>
        a.tag.toLowerCase().localeCompare(b.tag.toLowerCase())
      );
    } catch (e) {
      console.error('Failed to load known systems:', e);
    }
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
  // File focus, context menu & file operations
  // ---------------------------------------------------------------------------

  function handleToggleExpand(path: string) {
    if (expandedPaths.has(path)) {
      expandedPaths.delete(path);
    } else {
      expandedPaths.add(path);
    }
    expandedPaths = expandedPaths;
  }

  function handleGlobalKeydown(event: KeyboardEvent) {
    if (event.key === 'Escape') {
      if (contextMenu) { contextMenu = null; return; }
      if (renamingFilePath) { renamingFilePath = null; return; }
      if (focusedFilePath) { focusedFilePath = null; }
    }
  }

  function handleContextMenu(event: MouseEvent, item: FileItem) {
    focusedFilePath = item.is_dir ? null : item.path;
    // Snapshot isIndexed at click time so the open menu doesn't keep a live
    // reactive dependency on indexedPaths.
    contextMenu = {
      x: event.clientX,
      y: event.clientY,
      item,
      isIndexed: indexedPaths.has(item.path),
    };
  }

  async function handleContextOpen() {
    if (contextMenu) {
      await openPath(contextMenu.item.path);
      contextMenu = null;
    }
  }

  function handleContextReveal() {
    if (contextMenu) {
      revealItemInDir(contextMenu.item.path);
      contextMenu = null;
    }
  }

  function handleContextRename() {
    if (contextMenu) {
      renamingFilePath = contextMenu.item.path;
      contextMenu = null;
    }
  }

  async function handleContextReindex() {
    if (!contextMenu) return;
    const item = contextMenu.item;
    contextMenu = null;
    const confirmed = await confirm(`Re-index "${item.name}"? This rebuilds its chunks.`, { title: 'Re-index file' });
    if (!confirmed) return;
    try {
      await invoke('reindex_file', { path: item.path });
      await refreshIndexStatus();
      notification.show({ type: 'success', message: `Re-indexed ${item.name}`, duration: 3000 });
    } catch (e) {
      notification.show({ type: 'error', message: `Re-index failed: ${String(e)}`, duration: 5000 });
    }
  }

  function handleContextShowStats() {
    if (!contextMenu) return;
    statsModalPath = contextMenu.item.path;
    contextMenu = null;
  }

  function handleContextAddToCollection(name: string) {
    if (!contextMenu) return;
    const item = contextMenu.item;
    contextMenu = null;
    addToCollection(name, item);
  }

  function handleContextRemoveFromCollection(name: string) {
    if (!contextMenu) return;
    const item = contextMenu.item;
    contextMenu = null;
    removeFromCollection(name, item);
  }

  function handleContextCreateCollectionFromFolder() {
    if (!contextMenu) return;
    const item = contextMenu.item;
    contextMenu = null;
    startCreateCollectionFromFolder(item);
  }

  function handleContextAddToNewCollection() {
    if (!contextMenu) return;
    const item = contextMenu.item;
    contextMenu = null;
    startCreateCollectionWithItem(item);
  }

  async function handleContextDelete() {
    if (!contextMenu) return;
    const item = contextMenu.item;
    contextMenu = null;

    const label = item.is_dir ? 'folder' : 'file';
    const confirmed = await confirm(`Move "${item.name}" to Trash?`, { title: `Delete ${label}`, kind: 'warning' });
    if (!confirmed) return;

    try {
      if (item.is_dir) {
        await invoke('delete_folder', { path: item.path });
        const prefix = item.path + '/';
        for (const p of selectedPaths) {
          if (p.startsWith(prefix)) selectedPaths.delete(p);
        }
        selectedPaths = selectedPaths;
        for (const p of syncedPaths) {
          if (p.startsWith(prefix)) syncedPaths.delete(p);
        }
        for (const p of expandedPaths) {
          if (p.startsWith(prefix) || p === item.path) expandedPaths.delete(p);
        }
        expandedPaths = expandedPaths;
      } else {
        await invoke('delete_file', { path: item.path });
        if (focusedFilePath === item.path) focusedFilePath = null;
      }
      if (selectedFolder) await loadFiles(selectedFolder);
      refreshIndexStatus();
    } catch (e) {
      notification.show({ type: 'error', message: `Delete failed: ${String(e)}`, duration: 5000 });
    }
  }

  function updatePathPrefix(paths: Set<string>, oldPrefix: string, newPrefix: string): Set<string> {
    const childPrefix = oldPrefix + '/';
    const updated = new Set<string>();
    for (const p of paths) {
      updated.add(p.startsWith(childPrefix) ? newPrefix + p.slice(oldPrefix.length) : p);
    }
    return updated;
  }

  async function handleRenameSubmit(oldPath: string, newName: string, isDir: boolean = false) {
    try {
      if (isDir) {
        const newPath = await invoke<string>('rename_folder', { oldPath, newName });
        selectedPaths = updatePathPrefix(selectedPaths, oldPath, newPath);
        syncedPaths = updatePathPrefix(syncedPaths, oldPath, newPath);
        expandedPaths = updatePathPrefix(expandedPaths, oldPath, newPath);
      } else {
        const newPath = await invoke<string>('rename_file', { oldPath, newName });
        if (focusedFilePath === oldPath) focusedFilePath = newPath;
        // Swap the path in selectedPaths so compute_diff can match old→new by content hash
        if (selectedPaths.has(oldPath)) {
          selectedPaths.delete(oldPath);
          selectedPaths.add(newPath);
          selectedPaths = selectedPaths;
        }
      }
      renamingFilePath = null;
      if (selectedFolder) await loadFiles(selectedFolder);
      refreshIndexStatus();
    } catch (e) {
      notification.show({ type: 'error', message: `Rename failed: ${String(e)}`, duration: 5000 });
      renamingFilePath = null;
    }
  }

  function handleRenameCancel() {
    renamingFilePath = null;
  }

  // ---------------------------------------------------------------------------
  // Collections
  // ---------------------------------------------------------------------------

  async function loadCollections() {
    try {
      const result = await invoke<CollectionsResult>('get_collections');
      collections = result.collections;
      activeContextName = result.active_context;
    } catch (e) {
      console.log('Could not fetch collections:', e);
    }
  }

  async function setActiveContext(name: string) {
    try {
      const result = await invoke<ActiveContextResult>('set_active_context', { name });
      activeContextName = result.active_context;
      notification.show({
        type: 'info',
        message: `Active context: ${name}`,
        duration: 3000,
      });
      await loadCollections();
    } catch (e) {
      notification.show({
        type: 'error',
        message: `Couldn't set active context: ${e}`,
        duration: 5000,
      });
    }
  }

  async function clearActiveContext() {
    try {
      await invoke<ActiveContextResult>('clear_active_context');
      activeContextName = null;
      notification.show({
        type: 'info',
        message: 'Active context cleared',
        duration: 3000,
      });
    } catch (e) {
      notification.show({
        type: 'error',
        message: `Couldn't clear active context: ${e}`,
        duration: 5000,
      });
    }
  }

  function toggleActiveContext(name: string) {
    if (activeContextName === name) {
      clearActiveContext();
    } else {
      setActiveContext(name);
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
    if (!name) return;
    const filePaths = Array.from(collectionEditPaths);

    try {
      if (isCreatingCollection) {
        await invoke<CollectionMutationResult>('create_collection', {
          name,
          filePaths,
          description: collectionEditDescription,
        });
        notification.show({ type: 'success', message: `Created "${name}"`, duration: 4000 });
      } else if (editingCollectionName) {
        if (editingCollectionName !== name) {
          await invoke('delete_collection', { name: editingCollectionName });
          await invoke<CollectionMutationResult>('create_collection', {
            name,
            filePaths,
            description: collectionEditDescription,
          });
          notification.show({ type: 'success', message: `Renamed to "${name}"`, duration: 4000 });
        } else {
          await invoke<CollectionMutationResult>('update_collection', {
            name,
            filePaths,
            description: collectionEditDescription,
          });
          notification.show({ type: 'success', message: `Updated "${name}"`, duration: 4000 });
        }
      }
      cancelCollectionEdit();
      await loadCollections();
    } catch (e) {
      notification.show({ type: 'error', message: `Save failed: ${String(e)}`, duration: 5000 });
    }
  }

  let pendingDeleteCollection: string | null = null;

  function requestDeleteCollection(name: string) {
    pendingDeleteCollection = name;
  }

  async function confirmDeleteCollection() {
    if (!pendingDeleteCollection) return;
    const name = pendingDeleteCollection;
    pendingDeleteCollection = null;
    try {
      await invoke('delete_collection', { name });
      cancelCollectionEdit();
      await loadCollections();
      notification.show({ type: 'success', message: `Deleted "${name}"`, duration: 4000 });
    } catch (e) {
      notification.show({ type: 'error', message: `Delete failed: ${String(e)}`, duration: 5000 });
    }
  }

  // ---------------------------------------------------------------------------
  // Bulk collection actions (right-click menu)
  // ---------------------------------------------------------------------------

  function indexedPdfsUnderPath(target: string): string[] {
    if (indexedPaths.has(target)) return [target];
    const prefix = target + '/';
    return [...indexedPaths].filter(p => p.startsWith(prefix));
  }

  function collectionsContaining(target: string, isDir: boolean): string[] {
    const targets = isDir ? new Set(indexedPdfsUnderPath(target)) : new Set([target]);
    if (targets.size === 0) return [];
    return Object.values(collections)
      .filter(c => c.file_paths.some(p => targets.has(p)))
      .map(c => c.name);
  }

  async function addToCollection(name: string, item: FileItem) {
    const col = collections[name];
    if (!col) return;
    const candidates = item.is_dir ? indexedPdfsUnderPath(item.path) : [item.path];
    if (candidates.length === 0) {
      notification.show({
        type: 'info',
        message: `No indexed PDFs under "${item.name}"`,
        duration: 4000,
      });
      return;
    }
    const before = col.file_paths.length;
    const merged = Array.from(new Set([...col.file_paths, ...candidates]));
    const added = merged.length - before;
    if (added === 0) {
      notification.show({
        type: 'info',
        message: `Already in "${name}"`,
        duration: 3000,
      });
      return;
    }
    try {
      await invoke<CollectionMutationResult>('update_collection', {
        name,
        filePaths: merged,
        description: col.description,
      });
      await loadCollections();
      notification.show({
        type: 'success',
        message: `Added ${added} file${added === 1 ? '' : 's'} to "${name}"`,
        duration: 4000,
      });
    } catch (e) {
      notification.show({
        type: 'error',
        message: `Could not add to "${name}": ${String(e)}`,
        duration: 5000,
      });
    }
  }

  async function removeFromCollection(name: string, item: FileItem) {
    const col = collections[name];
    if (!col) return;
    const targets = new Set(item.is_dir ? indexedPdfsUnderPath(item.path) : [item.path]);
    const remaining = col.file_paths.filter(p => !targets.has(p));
    const removed = col.file_paths.length - remaining.length;
    if (removed === 0) return;
    try {
      await invoke<CollectionMutationResult>('update_collection', {
        name,
        filePaths: remaining,
        description: col.description,
      });
      await loadCollections();
      notification.show({
        type: 'success',
        message: `Removed ${removed} file${removed === 1 ? '' : 's'} from "${name}"`,
        duration: 4000,
      });
    } catch (e) {
      notification.show({
        type: 'error',
        message: `Could not remove from "${name}": ${String(e)}`,
        duration: 5000,
      });
    }
  }

  function startCreateCollectionFromFolder(folder: FileItem) {
    const candidates = indexedPdfsUnderPath(folder.path);
    if (candidates.length === 0) {
      notification.show({
        type: 'info',
        message: `No indexed PDFs under "${folder.name}"`,
        duration: 4000,
      });
      return;
    }
    collectionEditName = folder.name;
    collectionEditDescription = '';
    collectionEditPaths = new Set(candidates);
    isCreatingCollection = true;
    editingCollectionName = null;
    highlightedCollection = null;
  }

  function startCreateCollectionWithItem(item: FileItem) {
    const candidates = item.is_dir
      ? indexedPdfsUnderPath(item.path)
      : [item.path];
    if (candidates.length === 0) {
      notification.show({
        type: 'info',
        message: `No indexed PDFs under "${item.name}"`,
        duration: 4000,
      });
      return;
    }
    collectionEditName = '';
    collectionEditDescription = '';
    collectionEditPaths = new Set(candidates);
    isCreatingCollection = true;
    editingCollectionName = null;
    highlightedCollection = null;
  }

  function handleCollectionToggle(path: string, isDir: boolean, item: FileItem, shiftKey: boolean = false) {
    if (shiftKey && !isDir && lastCollectionClickedPath) {
      const ok = applyRangeToggle(collectionEditPaths, lastCollectionClickedPath, path, true);
      if (ok) {
        collectionEditPaths = collectionEditPaths;
        lastCollectionClickedPath = path;
        return;
      }
    }
    if (isDir) {
      toggleCollectionFolder(item);
    } else {
      if (collectionEditPaths.has(path)) {
        collectionEditPaths.delete(path);
      } else {
        collectionEditPaths.add(path);
      }
      collectionEditPaths = collectionEditPaths;
      lastCollectionClickedPath = path;
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

  async function refreshIndexAndCollections() {
    await refreshIndexStatus();
    await loadCollections();
  }

  function buildSyncResultMessage(result: SyncResult): { message: string; isError: boolean } {
    const parts: string[] = [];
    if (result.added > 0) parts.push(`${result.added} added`);
    if (result.removed > 0) parts.push(`${result.removed} removed`);
    if (result.auto_removed > 0) parts.push(`${result.auto_removed} removed (deleted from disk)`);
    if (result.renamed > 0) parts.push(`${result.renamed} renamed`);
    if (result.updated > 0) parts.push(`${result.updated} updated`);
    if (result.errors.length > 0) parts.push(`${result.errors.length} error(s)`);
    const chunkStr = result.chunks_total > 0
      ? ` ${result.chunks_total.toLocaleString()} chunks.`
      : '';
    const message = parts.length > 0
      ? `Synced: ${parts.join(', ')}.${chunkStr}`
      : 'Nothing to sync.';
    return { message, isError: result.errors.length > 0 };
  }

  // Sync index: add new, remove deselected, re-index modified
  async function handleSync() {
    if (isSyncing) return;
    isSyncing = true;
    try {
      const result = await runSyncJob<SyncResult>({
        command: 'sync_index',
        args: { paths: Array.from(selectedPaths) },
        startMessage: 'Starting sync...',
        errorPrefix: 'Sync failed',
        streamsProgress: true,
        buildResultMessage: buildSyncResultMessage,
        onComplete: async (r) => {
          // Reconcile selectedPaths with renames / auto-removals / stale paths
          for (const { old_path, new_path } of r.renames ?? []) {
            selectedPaths.delete(old_path);
            selectedPaths.add(new_path);
          }
          for (const path of r.auto_removed_paths ?? []) selectedPaths.delete(path);
          for (const path of r.stale_paths ?? []) selectedPaths.delete(path);
          if ((r.renames?.length || 0) + (r.auto_removed_paths?.length || 0) + (r.stale_paths?.length || 0) > 0) {
            selectedPaths = selectedPaths;
          }

          // Persist synced selection so uncommitted changes don't survive a restart
          syncedPaths = new Set(selectedPaths);
          const store = await load('settings.json');
          await store.set('syncedPaths', Array.from(selectedPaths));
          await store.save();
        },
      }, refreshIndexAndCollections);

      if (result) {
        lastSyncTime = new Date();
        refreshTotalFilesFound();
        // Refresh file tree if renames, auto-removals, or stale cleanups occurred
        if (((result.renames?.length || 0) + (result.auto_removed_paths?.length || 0) + (result.stale_paths?.length || 0) > 0) && selectedFolder) {
          await loadFiles(selectedFolder);
        }
      }
    } finally {
      isSyncing = false;
    }
  }

  function handleManualSync() {
    if (!sidecarConnected || isSyncing) return;
    if (selectedFolder) loadFiles(selectedFolder);
    if (selectedPaths.size > 0) refreshIndexStatus({ userTriggered: true });
  }

  async function handleReindexAll() {
    if (isSyncing) return;
    isSyncing = true;
    try {
      const result = await runSyncJob<SyncResult>({
        command: 'reindex_all',
        startMessage: 'Starting reindex...',
        errorPrefix: 'Reindex failed',
        streamsProgress: true,
        buildResultMessage: (r) => {
          const parts: string[] = [];
          if (r.updated > 0) parts.push(`${r.updated} reprocessed`);
          if (r.errors.length > 0) parts.push(`${r.errors.length} error(s)`);
          const chunkStr = r.chunks_total > 0
            ? ` ${r.chunks_total.toLocaleString()} chunks.`
            : '';
          const message = parts.length > 0
            ? `Reindexed: ${parts.join(', ')}.${chunkStr}`
            : 'Nothing to reindex.';
          return { message, isError: r.errors.length > 0 };
        },
      }, refreshIndexAndCollections);
      if (result) lastSyncTime = new Date();
    } finally {
      isSyncing = false;
    }
  }

  async function handleDeleteIndex() {
    if (isSyncing) return;
    isSyncing = true;
    try {
      await runSyncJob<{ removed_files: number; removed_chunks: number }>({
        command: 'delete_index',
        startMessage: 'Deleting index...',
        errorPrefix: 'Delete failed',
        streamsProgress: false,
        buildResultMessage: (r) => {
          const fileWord = r.removed_files === 1 ? 'file' : 'files';
          const chunkWord = r.removed_chunks === 1 ? 'chunk' : 'chunks';
          return {
            message: `Index cleared: ${r.removed_files} ${fileWord}, ${r.removed_chunks.toLocaleString()} ${chunkWord} removed.`,
            isError: false,
          };
        },
      }, refreshIndexAndCollections);
    } finally {
      isSyncing = false;
    }
  }

</script>

<svelte:window on:keydown={handleGlobalKeydown} on:contextmenu|preventDefault />

<main class="app-layout">
  <Header
    bind:searchQuery
    {isSearching}
    disabled={!selectedFolder || editingCollectionName !== null || isCreatingCollection}
    onSubmit={handleSearchSubmit}
    onDebouncedChange={handleSearchDebounced}
    onClear={handleSearchClear}
  />

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
        activeName={activeContextName}
        onStartCreate={startCreateCollection}
        onStartEdit={startEditCollection}
        onSave={saveCollection}
        onCancel={cancelCollectionEdit}
        onDelete={requestDeleteCollection}
        onHighlight={toggleCollectionHighlight}
        onToggleActive={toggleActiveContext}
      />
    </div>

    <div class="file-tree-area">
      {#if activeContextName && !isCollectionEditMode}
        <div class="active-context-strip">
          <span class="ac-label">Active context:</span>
          <span class="ac-name">{activeContextName}</span>
          <button class="ac-clear" on:click={clearActiveContext} title="Clear active context">
            &#10005;
          </button>
        </div>
      {/if}
      {#if searchActive}
        <SearchResults
          results={searchResults}
          isLoading={isSearching}
          query={committedQuery}
          error={searchError}
          indexedFileCount={indexedPathsSet.size}
          onOpenResult={handleOpenResult}
        />
      {:else}
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
            {expandedPaths}
            onToggleExpand={handleToggleExpand}
            {focusedFilePath}
            onFocusFile={(path) => { focusedFilePath = path; }}
            onContextMenu={handleContextMenu}
            {renamingFilePath}
            onRenameSubmit={handleRenameSubmit}
            onRenameCancel={handleRenameCancel}
            mode={treeMode}
            collectionPaths={collectionEditPaths}
            {collectionFolders}
            {highlightPaths}
            {displayPaths}
            onCollectionToggle={handleCollectionToggle}
          />
        {/each}
      {/if}
      <NotificationBanner />
    </div>
  {:else}
    <GettingStartedPage
      {ollamaRunning}
      {ollamaModelReady}
      folderSelected={false}
      filesIndexed={false}
      collectionsCreated={false}
      onSelectFolder={handleSelectFolder}
      onCopyMcpConfig={handleCopyMcpConfig}
    />
  {/if}

  {#if error}
    <div class="error-banner">Error: {error}</div>
  {/if}

  {#if contextMenu}
    <ContextMenu
      x={contextMenu.x}
      y={contextMenu.y}
      item={contextMenu.item}
      isIndexed={contextMenu.isIndexed}
      {collections}
      canAddToCollection={contextMenu.item.is_dir
        ? indexedPdfsUnderPath(contextMenu.item.path).length > 0
        : indexedPaths.has(contextMenu.item.path)}
      containingCollections={collectionsContaining(contextMenu.item.path, contextMenu.item.is_dir)}
      onOpen={handleContextOpen}
      onReveal={handleContextReveal}
      onRename={handleContextRename}
      onDelete={handleContextDelete}
      onReindex={handleContextReindex}
      onShowStats={handleContextShowStats}
      onAddToCollection={handleContextAddToCollection}
      onAddToNewCollection={handleContextAddToNewCollection}
      onRemoveFromCollection={handleContextRemoveFromCollection}
      onCreateCollectionFromFolder={handleContextCreateCollectionFromFolder}
      onClose={() => { contextMenu = null; }}
    />
  {/if}

  {#if statsModalPath}
    <DocumentStatsModal
      path={statsModalPath}
      onClose={() => { statsModalPath = null; }}
    />
  {/if}

  {#if pendingDeleteCollection}
    <ConfirmDialog
      title="Delete collection"
      message={`Delete "${pendingDeleteCollection}"? Files in your library are not affected.`}
      confirmLabel="Delete"
      danger
      onConfirm={confirmDeleteCollection}
      onCancel={() => { pendingDeleteCollection = null; }}
    />
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
    onCopyMcpConfig={handleCopyMcpConfig}
    onOpenFolder={() => { if (selectedFolder) revealItemInDir(selectedFolder); }}
    onShowLicense={() => { showLicense = true; }}
    onShowGuide={() => { showGuide = true; }}
    onOpenSettings={() => { showSettings = true; }}
  />
</main>

<LicenseModal visible={showLicense} onClose={() => { showLicense = false; }} />

<SettingsModal
  visible={showSettings}
  onClose={() => { showSettings = false; }}
  {knownSystems}
  onSystemsChanged={refreshKnownSystems}
  {selectedFolder}
  indexedFileCount={(indexStatus?.summary?.up_to_date ?? 0) + (indexStatus?.summary?.update ?? 0) + (indexStatus?.summary?.remove ?? 0)}
  {totalFilesFound}
  {totalChunks}
  {storageBytes}
  {reclaimableBytes}
  {gameSystemCount}
  {isSyncing}
  {syncPreferences}
  {dataDir}
  {lastSyncTime}
  onSelectFolder={handleSelectFolder}
  onCompact={handleCompact}
  onReindexAll={handleReindexAll}
  onDeleteIndex={handleDeleteIndex}
  onSyncPreferencesChange={handleSyncPreferencesChange}
  onOpenDataDir={handleOpenDataDir}
  onSync={handleManualSync}
/>

<GettingStartedModal
  visible={showGuide}
  onClose={() => { showGuide = false; }}
  {ollamaRunning}
  {ollamaModelReady}
  folderSelected={selectedFolder !== ''}
  filesIndexed={(indexStatus?.summary?.up_to_date ?? 0) > 0}
  collectionsCreated={Object.keys(collections).length > 0}
  onSelectFolder={handleSelectFolder}
  onCopyMcpConfig={handleCopyMcpConfig}
/>

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

  .active-context-strip {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.4rem 0.6rem;
    margin: 0 0 0.5rem 0;
    background: rgba(182, 159, 129, 0.12);
    border: 1px solid var(--text-accent);
    border-radius: 4px;
    font-size: 0.8rem;
    color: var(--text-accent);
    position: sticky;
    top: 0;
    z-index: 5;
  }
  .ac-label {
    color: var(--text-secondary);
  }
  .ac-name {
    font-weight: 600;
    flex: 1;
  }
  .ac-clear {
    background: none;
    border: none;
    color: var(--text-accent);
    cursor: pointer;
    font-size: 0.85rem;
    padding: 0.1rem 0.4rem;
    border-radius: 3px;
    line-height: 1;
  }
  .ac-clear:hover {
    background: rgba(182, 159, 129, 0.2);
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
