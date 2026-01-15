<script lang="ts">
  import { invoke } from '@tauri-apps/api/core';
  import type { FileItem } from './types';
  export let item: FileItem;
  export let level: number = 0;

  let isExpanded: boolean = false;

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
</script>

<div class="item" style="padding-left: {level * 1.5}rem;">
  <button class="row" on:click={toggleExpand}>
    {#if item.is_dir}
      <span>{isExpanded ? '📂' : '📁'}</span>
    {:else}
      <span class="icon">📄</span>
    {/if}
    <span>{item.name}</span>
  </button>

  {#if isExpanded && item.children}
    {#each item.children as child}
      <svelte:self item={child} level={level + 1} />
    {/each}
  {/if}
</div>

<style>
  .item {
    user-select: none;
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
</style>