<script lang="ts">
  import { invoke } from '@tauri-apps/api/core';
  import type { FileItem } from '../lib/types';
  import FileTree from '../lib/FileTree.svelte';

  let selectedFolder = '';
  let files: FileItem[] = [];
  let selectedPaths = new Set<string>;
  let error = '';

  async function handleSelectFolder() {
    try {
      selectedFolder = await invoke<string>('select_folder');
      await loadFiles(selectedFolder);
      error = '';
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
    
    // Check if any children are currently selected
    const anySelected = isFolderSelected(folder);
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

  function isFolderSelected(folder: FileItem): boolean {
    if (!folder.is_dir || !folder.children) return false;

    // Check if any child is selected
    for (const child of folder.children) {
      if (child.is_dir) {
        if (isFolderSelected(child)) return true;
      } else {
        if (selectedPaths.has(child.path)) return true;
      }
    }
    return false;
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

    <div class="file-tree">
      {#each files as file}
        <FileTree 
          item={file} 
          level={0}
          {selectedPaths}
          onToggle={toogleSelection} 
        />
      {/each}
    </div>
  {/if}

  {#if error}
    <p style="color: red;">Error: {error}</p>
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
</style>
