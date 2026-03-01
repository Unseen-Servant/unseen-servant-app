<script lang="ts">
  import { onMount } from 'svelte';
  import { invoke } from '@tauri-apps/api/core';
  import { load } from '@tauri-apps/plugin-store';
  import type { FileItem } from '../lib/types';
  import FileTree from '../lib/FileTree.svelte';

  let selectedFolder = '';
  let files: FileItem[] = [];
  let selectedPaths = new Set<string>;
  let error = '';
  let isIndexing = false;
  let indexResult = '';
  let mcpCopyStatus = '';

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
      }
    } catch (e) {
      // No saved state on first run — that's fine
      console.log('No saved state:', e);
    }
  });

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

  // Index selected PDFs via the Python sidecar
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

    <button
      on:click={handleIndex}
      disabled={selectedPaths.size === 0 || isIndexing}
    >
      {isIndexing ? 'Indexing...' : `Index ${selectedPaths.size} PDFs`}
    </button>

    {#if indexResult}
      <p class="index-result">{indexResult}</p>
    {/if}

    <div class="file-tree">
      {#each files as file}
        <FileTree
          item={file}
          level={0}
          {selectedPaths}
          {foldersWithSelections}
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
  .index-result {
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
