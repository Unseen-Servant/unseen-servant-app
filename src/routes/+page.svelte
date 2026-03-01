<script lang="ts">
  import { onMount } from 'svelte';
  import { invoke } from '@tauri-apps/api/core';
  import { load } from '@tauri-apps/plugin-store';
  import type { FileItem, IndexStatusResult, SyncResult } from '../lib/types';
  import FileTree from '../lib/FileTree.svelte';

  let selectedFolder = '';
  let files: FileItem[] = [];
  let selectedPaths = new Set<string>;
  let error = '';
  let isIndexing = false;
  let indexResult = '';
  let mcpCopyStatus = '';

  // Index sync state
  let indexStatus: IndexStatusResult | null = null;
  let isLoadingStatus = false;
  let isSyncing = false;
  let syncResult = '';
  let statusTimeout: ReturnType<typeof setTimeout> | null = null;

  onMount(async () => {
    try {
      const store = await load('settings.json');
      const savedFolder = await store.get<string>('selectedFolder');
      const savedPaths = await store.get<string[]>('selectedPaths');

      if (savedFolder) {
        selectedFolder = savedFolder;
        await loadFiles(savedFolder);
      }
      if (savedPaths) {
        selectedPaths = new Set(savedPaths);
        if (savedPaths.length > 0) {
          await refreshIndexStatus();
        }
      }
    } catch (e) {
      // No saved state on first run — that's fine
      console.log('No saved state:', e);
    }
  });

  async function refreshIndexStatus() {
    isLoadingStatus = true;
    try {
      indexStatus = await invoke<IndexStatusResult>(
        'get_index_status',
        { paths: Array.from(selectedPaths) }
      );
    } catch (e) {
      // Sidecar might not be ready yet on startup
      console.log('Could not fetch index status:', e);
      indexStatus = null;
    } finally {
      isLoadingStatus = false;
    }
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
      selectedFolder = await invoke<string>('select_folder');
      await loadFiles(selectedFolder);
      error = '';
      await saveState();
    } catch (e) {
      error = String(e);
      selectedFolder = '';
      files = [];
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
    
    // Check if any descendants are currently selected (O(1) lookup)
    const anySelected = foldersWithSelections.has(folder.path);
    const shouldSelect = !anySelected;

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

  function computeAncestorPaths(paths: Set<string>): Set<string> {
    const ancestors = new Set<string>();
    for (const p of paths) {
      let dir = p;
      while ((dir = dir.substring(0, dir.lastIndexOf('/'))) !== '') {
        if (ancestors.has(dir)) break; // Already traced this branch
        ancestors.add(dir);
      }
    }
    return ancestors;
  }

  // Copy MCP config to clipboard
  async function handleCopyMcpConfig() {
    try {
      const config = await invoke<string>('get_mcp_config');
      await navigator.clipboard.writeText(config);
      mcpCopyStatus = 'Copied to clipboard!';
    } catch (e) {
      mcpCopyStatus = `Failed: ${String(e)}`;
    }
  }

  // Sync index: add new, remove deselected, re-index modified
  async function handleSync() {
    isSyncing = true;
    syncResult = '';
    try {
      const result = await invoke<SyncResult>(
        'sync_index',
        { paths: Array.from(selectedPaths) }
      );
      const parts = [];
      if (result.added > 0) parts.push(`${result.added} added`);
      if (result.removed > 0) parts.push(`${result.removed} removed`);
      if (result.updated > 0) parts.push(`${result.updated} updated`);
      if (result.errors.length > 0) parts.push(`${result.errors.length} error(s)`);
      syncResult = parts.length > 0
        ? `Synced: ${parts.join(', ')}.`
        : 'Nothing to sync.';
      await refreshIndexStatus();
    } catch (e) {
      syncResult = `Sync failed: ${String(e)}`;
    } finally {
      isSyncing = false;
    }
  }

  // Legacy index for backward compatibility (kept but no longer primary)
  async function handleIndex() {
    isIndexing = true;
    indexResult = '';
    try {
      const result = await invoke<{ indexed: number; total: number; errors: string[] }>(
        'index_files',
        { paths: Array.from(selectedPaths) }
      );
      if (result.errors.length > 0) {
        indexResult = `Indexed ${result.indexed}/${result.total} PDFs. ${result.errors.length} error(s).`;
      } else {
        indexResult = `Successfully indexed ${result.indexed} PDFs.`;
      }
      await refreshIndexStatus();
    } catch (e) {
      indexResult = `Indexing failed: ${String(e)}`;
    } finally {
      isIndexing = false;
    }
  }
</script>

<main>
  <h1>Unseen Server</h1>

  <button on:click={handleSelectFolder}>
    Select TTRPG Folder
  </button>

  {#if selectedFolder}
    <h2>Folder: {selectedFolder}</h2>

    <p>Selected: {selectedPaths.size} items</p>

    {#if isLoadingStatus}
      <p class="sync-status">Checking index status...</p>
    {:else if indexStatus}
      {@const pending = indexStatus.summary.add + indexStatus.summary.remove + indexStatus.summary.update}
      {@const indexEmpty = indexStatus.summary.up_to_date === 0 && indexStatus.summary.remove === 0 && indexStatus.summary.update === 0}
      {#if pending === 0 && indexStatus.summary.up_to_date > 0}
        <p class="sync-status sync-ok">Index up to date ({indexStatus.summary.up_to_date} PDFs)</p>
      {:else if indexEmpty && indexStatus.summary.add > 0}
        <div class="sync-status sync-empty">
          <p>No PDFs indexed yet. {indexStatus.summary.add} selected PDF{indexStatus.summary.add === 1 ? '' : 's'} ready to index.</p>
          <button
            on:click={handleSync}
            disabled={isSyncing}
          >
            {isSyncing ? 'Syncing...' : `Index ${indexStatus.summary.add} PDFs`}
          </button>
        </div>
      {:else if pending > 0 || indexStatus.summary.errors > 0}
        <div class="sync-status sync-pending">
          <p>
            {#if indexStatus.summary.add > 0}
              <span class="sync-badge add">{indexStatus.summary.add} to add</span>
            {/if}
            {#if indexStatus.summary.remove > 0}
              <span class="sync-badge remove">{indexStatus.summary.remove} to remove</span>
            {/if}
            {#if indexStatus.summary.update > 0}
              <span class="sync-badge update">{indexStatus.summary.update} modified</span>
            {/if}
            {#if indexStatus.summary.up_to_date > 0}
              <span class="sync-badge ok">{indexStatus.summary.up_to_date} up to date</span>
            {/if}
            {#if indexStatus.summary.errors > 0}
              <span class="sync-badge error">{indexStatus.summary.errors} not found</span>
            {/if}
          </p>
          <button
            on:click={handleSync}
            disabled={isSyncing}
          >
            {isSyncing ? 'Syncing...' : 'Sync Index'}
          </button>
        </div>
      {/if}
    {/if}

    {#if syncResult}
      <p class="sync-result">{syncResult}</p>
    {/if}

    <div class="file-tree">
      {#each files as file}
        <FileTree
          item={file}
          level={0}
          {selectedPaths}
          {foldersWithSelections}
          {gameSystemMap}
          onToggle={toogleSelection}
        />
      {/each}
    </div>
  {/if}

  {#if error}
    <p style="color: red;">Error: {error}</p>
  {/if}

  <hr />
  <button on:click={handleCopyMcpConfig}>
    Copy MCP Config
  </button>
  {#if mcpCopyStatus}
    <p class="mcp-status">{mcpCopyStatus}</p>
  {/if}
</main>

<style>
  main {
    padding: 2rem;
  }
  .file-tree {
    margin-top: 1rem;
    border: 1px solid #ccc;
    border-radius: 4px;
    padding: 1rem;
    background: white;
  }
  .sync-status {
    margin-top: 0.5rem;
    padding: 0.5rem;
    border-radius: 4px;
  }
  .sync-ok {
    background: #f0fff0;
    color: #2d7d2d;
  }
  .sync-empty {
    background: #f3f4f6;
    color: #4b5563;
  }
  .sync-pending {
    background: #fff8f0;
  }
  .sync-badge {
    display: inline-block;
    padding: 0.15rem 0.5rem;
    border-radius: 3px;
    margin-right: 0.4rem;
    font-size: 0.85rem;
  }
  .sync-badge.add { background: #e3f2fd; color: #1565c0; }
  .sync-badge.remove { background: #fce4ec; color: #c62828; }
  .sync-badge.update { background: #fff3e0; color: #e65100; }
  .sync-badge.ok { background: #e8f5e9; color: #2e7d32; }
  .sync-badge.error { background: #fbe9e7; color: #bf360c; }
  .sync-result {
    margin-top: 0.5rem;
    padding: 0.5rem;
    background: #f0f7ff;
    border-radius: 4px;
  }
  .mcp-status {
    margin-top: 0.5rem;
    padding: 0.5rem;
    background: #f0f7ff;
    border-radius: 4px;
  }
</style>
