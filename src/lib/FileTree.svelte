<script lang="ts">
  import { invoke } from '@tauri-apps/api/core';
  import { openPath } from '@tauri-apps/plugin-opener';
  import type { FileItem, KnownGameSystem } from './types';

  export let item: FileItem;
  export let level: number = 0;
  export let selectedPaths: Set<string>;
  export let foldersWithSelections: Set<string>;
  export let gameSystemMap: Map<string, string> = new Map();
  export let knownSystems: KnownGameSystem[] = [];
  export let indexedPaths: Set<string> = new Set();
  export let onToggle: (path: string, isDir: boolean, item: FileItem) => void;
  export let onSetGameSystem: (path: string, filename: string, tag: string) => void = () => {};

  let isExpanded: boolean = false;
  let showDropdown: boolean = false;

  // Check if this item is selected — O(1) Set lookup, works even for unloaded folders
  $: isSelected = item.is_dir
    ? foldersWithSelections.has(item.path)
    : selectedPaths.has(item.path);

  $: hasTag = !item.is_dir && gameSystemMap.has(item.path);
  $: isIndexed = !item.is_dir && indexedPaths.has(item.path);

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

  function toggleDropdown(event: MouseEvent) {
    event.stopPropagation();
    showDropdown = !showDropdown;
  }

  function selectSystem(tag: string) {
    onSetGameSystem(item.path, item.name, tag);
    showDropdown = false;
  }

  function clearSystem() {
    onSetGameSystem(item.path, item.name, 'unknown');
    showDropdown = false;
  }

  async function openFile() {
    if (item.is_dir) return;
    try {
      await openPath(item.path);
    } catch (e) {
      console.error('Failed to open file:', e);
    }
  }

  function handleClickOutside(event: MouseEvent) {
    showDropdown = false;
  }
</script>

<svelte:window on:click={handleClickOutside} />

<div class="item" style="padding-left: {level * 1.5}rem;">
  <div class="row-container">
    <input
      type="checkbox"
      bind:checked={isSelected}
      on:change={handleCheckboxChange}
      class="checkbox"
    />

    <button class="row" on:click={toggleExpand} on:dblclick={openFile}>
      {#if item.is_dir}
        <span>{isExpanded ? '📂' : '📁'}</span>
      {:else}
        <span class="icon">📄</span>
      {/if}
      <span>{item.name}</span>
    </button>

    {#if hasTag}
      <div class="badge-wrapper">
        <button class="game-system-badge" on:click={toggleDropdown}>
          {gameSystemMap.get(item.path)}
        </button>
        {#if showDropdown}
          <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
          <div class="dropdown" on:click|stopPropagation>
            {#each knownSystems as sys}
              <button class="dropdown-item" on:click={() => selectSystem(sys.tag)}>
                <span class="dropdown-tag">{sys.tag}</span>
                <span class="dropdown-family">{sys.game_system}</span>
              </button>
            {/each}
            <hr class="dropdown-divider" />
            <button class="dropdown-item dropdown-clear" on:click={clearSystem}>
              Clear tag
            </button>
          </div>
        {/if}
      </div>
    {:else if isIndexed}
      <div class="badge-wrapper">
        <button class="add-tag-btn" on:click={toggleDropdown}>+</button>
        {#if showDropdown}
          <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
          <div class="dropdown" on:click|stopPropagation>
            {#each knownSystems as sys}
              <button class="dropdown-item" on:click={() => selectSystem(sys.tag)}>
                <span class="dropdown-tag">{sys.tag}</span>
                <span class="dropdown-family">{sys.game_system}</span>
              </button>
            {/each}
          </div>
        {/if}
      </div>
    {/if}
  </div>

  {#if isExpanded && item.children}
    {#each item.children as child}
      <svelte:self
        item={child}
        level={level + 1}
        {selectedPaths}
        {foldersWithSelections}
        {gameSystemMap}
        {knownSystems}
        {indexedPaths}
        {onToggle}
        {onSetGameSystem}
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
    flex: 1;
    text-align: left;
    font-size: 1rem;
  }
  .row:hover {
    background: #f0f0f0;
  }
  .icon {
    margin-right: 0.5rem;
  }
  .badge-wrapper {
    position: relative;
    flex-shrink: 0;
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
    border: 1px solid transparent;
    cursor: pointer;
  }
  .game-system-badge:hover {
    border-color: #3949ab;
  }
  .add-tag-btn {
    display: inline-block;
    padding: 0 0.35rem;
    margin-left: 0.5rem;
    border-radius: 3px;
    font-size: 0.75rem;
    background: #f5f5f5;
    color: #999;
    border: 1px dashed #ccc;
    cursor: pointer;
    line-height: 1.4;
  }
  .add-tag-btn:hover {
    background: #e8eaf6;
    color: #3949ab;
    border-color: #3949ab;
  }
  .dropdown {
    position: absolute;
    top: 100%;
    right: 0;
    z-index: 100;
    background: white;
    border: 1px solid #ccc;
    border-radius: 4px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
    max-height: 300px;
    overflow-y: auto;
    min-width: 220px;
    margin-top: 2px;
  }
  .dropdown-item {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    width: 100%;
    padding: 0.35rem 0.6rem;
    border: none;
    background: none;
    cursor: pointer;
    text-align: left;
    font-size: 0.8rem;
  }
  .dropdown-item:hover {
    background: #f0f0f0;
  }
  .dropdown-tag {
    font-weight: 500;
    white-space: nowrap;
  }
  .dropdown-family {
    color: #888;
    font-size: 0.7rem;
    white-space: nowrap;
  }
  .dropdown-divider {
    margin: 0.25rem 0;
    border: none;
    border-top: 1px solid #eee;
  }
  .dropdown-clear {
    color: #c62828;
  }
</style>
