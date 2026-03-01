<script lang="ts">
  import { invoke } from '@tauri-apps/api/core';
  import type { FileItem } from './types';
  
  export let item: FileItem;
  export let level: number = 0;
  export let selectedPaths: Set<string>;
  export let foldersWithSelections: Set<string>;
  export let gameSystemMap: Map<string, string> = new Map();
  export let onToggle: (path: string, isDir: boolean, item: FileItem) => void;

  let isExpanded: boolean = false;

  // Check if this item is selected — O(1) Set lookup, works even for unloaded folders
  $: isSelected = item.is_dir
    ? foldersWithSelections.has(item.path)
    : selectedPaths.has(item.path);

  async function toggleExpand() {
    if (!item.is_dir) return;

    isExpanded = !isExpanded;

    if (isExpanded && item.children === null) {
      try {
        const children = await invoke<FileItem[]>('list_files', { folderPath: item.path });
        item = { ...item, children };
      } catch (e) {
        console.error('Failed to load folder:', e);
        item = { ...item, children: [] };
      }
    }
  }

  function handleCheckboxChange() {
    onToggle(item.path, item.is_dir, item);
  }
</script>

<div class="item" style="padding-left: {level * 1.5}rem;">
  <div class="row-container">
    <input 
      type="checkbox" 
      bind:checked={isSelected} 
      on:change={handleCheckboxChange}
      class="checkbox"
    />

    <button class="row" on:click={toggleExpand}>
      {#if item.is_dir}
        <span>{isExpanded ? '📂' : '📁'}</span>
      {:else}
        <span class="icon">📄</span>
      {/if}
      <span>{item.name}</span>
      {#if !item.is_dir && gameSystemMap.has(item.path)}
        <span class="game-system-badge">{gameSystemMap.get(item.path)}</span>
      {/if}
    </button>
  </div>

  {#if isExpanded && item.children}
    {#each item.children as child}
      <svelte:self
        item={child}
        level={level + 1}
        {selectedPaths}
        {foldersWithSelections}
        {gameSystemMap}
        {onToggle}
      />
    {/each}
  {/if}
</div>

<style>
  .item {
    user-select: none;
  }
  .row-container {
    display: flex;
    align-items: center;
  }
  .checkbox {
    margin-right: 0.5rem;
    cursor: pointer;
  }
  .row {
    display: flex;
    align-items: center;
    padding: 0.25rem;
    cursor: pointer;
    background: none;
    border: none;
    width: 100%;
    text-align: left;
    font-size: 1rem;
  }
  .row:hover {
    background: #f0f0f0;
  }
  .icon {
    margin-right: 0.5rem;
  }
  .name {
    font-family: monospace;
  }
  .game-system-badge {
    display: inline-block;
    padding: 0.1rem 0.4rem;
    margin-left: 0.5rem;
    border-radius: 3px;
    font-size: 0.75rem;
    background: #e8eaf6;
    color: #3949ab;
    white-space: nowrap;
  }
</style>