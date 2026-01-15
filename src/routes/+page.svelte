<script lang="ts">
  import { invoke } from '@tauri-apps/api/core';
  import type { FileItem } from '../lib/types';
  import FileTree from '../lib/FileTree.svelte';

  let selectedFolder = '';
  let files: FileItem[] = [];
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
</script>

<main>
  <h1>Unseen Server</h1>

  <button on:click={handleSelectFolder}>
    Select TTRPG Folder
  </button>

  {#if selectedFolder}
    <h2>Folder: {selectedFolder}</h2>

    <ul>
      {#each files as file}
        <FileTree item={file} level={0} />
      {/each}
    </ul>
  {/if}

  {#if error}
    <p style="color: red;">Error: {error}</p>
  {/if}
</main>

<style>
  main {
    padding: 2rem;
  }
  ul {
    list-style: none;
    padding: 0;
  }
  li {
    padding: 0.5rem;
    cursor: pointer;
  }
  li:hover {
    background: #f0f0f0;
  }
</style>
