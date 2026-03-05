<script lang="ts">
  import { invoke } from '@tauri-apps/api/core';
  import { openPath } from '@tauri-apps/plugin-opener';
  import { slide } from 'svelte/transition';
  import type { FileItem, KnownGameSystem } from './types';
  import { areAllDescendantsSelected } from './selectionUtils';

  export let item: FileItem;
  export let level: number = 0;
  export let selectedPaths: Set<string>;
  export let foldersWithSelections: Set<string>;
  export let gameSystemMap: Map<string, string> = new Map();
  export let knownSystems: KnownGameSystem[] = [];
  export let indexedPaths: Set<string> = new Set();
  export let onToggle: (path: string, isDir: boolean, item: FileItem) => void;
  export let onSetGameSystem: (path: string, filename: string, tag: string) => void = () => {};

  // Collection mode props
  export let mode: 'index' | 'collection' = 'index';
  export let collectionPaths: Set<string> = new Set();
  export let collectionFolders: Set<string> = new Set();
  export let highlightPaths: Set<string> = new Set();
  export let onCollectionToggle: (path: string, isDir: boolean, item: FileItem) => void = () => {};

  let isExpanded: boolean = false;
  let showDropdown: boolean = false;

  // Check if this item has any selection — O(1) Set lookup, works even for unloaded folders
  $: isSelected = item.is_dir
    ? foldersWithSelections.has(item.path)
    : selectedPaths.has(item.path);

  // For folders: computed locally from item.children (which has correct data in this component)
  $: isFullySelected = item.is_dir && item.children !== null &&
    areAllDescendantsSelected(item, selectedPaths);

  // Collection mode: check against collectionPaths instead
  $: isInCollection = item.is_dir
    ? collectionFolders.has(item.path)
    : collectionPaths.has(item.path);

  $: isCollectionFullySelected = item.is_dir && item.children !== null &&
    areAllDescendantsSelected(item, collectionPaths, indexedPaths);

  // Which checked state to show depends on mode
  $: isChecked = mode === 'collection'
    ? (item.is_dir ? isCollectionFullySelected : isInCollection)
    : (item.is_dir ? isFullySelected : isSelected);

  // Indeterminate: has some selections but not all (folders only)
  $: isIndeterminate = item.is_dir && (
    mode === 'collection'
      ? (isInCollection && !isCollectionFullySelected)
      : (isSelected && !isFullySelected)
  );

  // In collection mode, only indexed files get checkboxes
  $: showCheckbox = mode === 'index' || item.is_dir || indexedPaths.has(item.path);

  // Dimmed in collection mode when file is not indexed
  $: isDimmed = mode === 'collection' && !item.is_dir && !indexedPaths.has(item.path);

  // Highlighted when previewing a collection
  $: isHighlighted = mode === 'index' && !item.is_dir && highlightPaths.size > 0 && highlightPaths.has(item.path);

  $: hasTag = !item.is_dir && gameSystemMap.has(item.path);
  $: isIndexed = !item.is_dir && indexedPaths.has(item.path);

  function setIndeterminate(node: HTMLInputElement, value: boolean) {
    node.indeterminate = value;
    return {
      update(newValue: boolean) {
        node.indeterminate = newValue;
      }
    };
  }

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
    if (mode === 'collection') {
      onCollectionToggle(item.path, item.is_dir, item);
    } else {
      onToggle(item.path, item.is_dir, item);
    }
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

<div class="item" class:dimmed={isDimmed} class:highlighted={isHighlighted} style="padding-left: {level * 1.5}rem;">
  <div class="row-container">
    {#if showCheckbox}
      <input
        type="checkbox"
        checked={isChecked}
        use:setIndeterminate={isIndeterminate}
        on:change={handleCheckboxChange}
        class="checkbox"
        class:collection-checkbox={mode === 'collection'}
      />
    {:else}
      <span class="checkbox-spacer"></span>
    {/if}

    <button class="row" on:click={toggleExpand} on:dblclick={openFile}>
      {#if item.is_dir}
        <span class="icon folder-icon">{isExpanded ? '\u25BE' : '\u25B8'}</span>
      {/if}
      <span class="name">{item.name}</span>
    </button>

    {#if hasTag}
      <div class="badge-wrapper">
        {#if mode === 'index'}
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
        {:else}
          <span class="game-system-badge readonly">{gameSystemMap.get(item.path)}</span>
        {/if}
      </div>
    {:else if isIndexed && mode === 'index'}
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
    <div transition:slide={{ duration: 150 }}>
      {#each item.children as child (child.path)}
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
          {mode}
          {collectionPaths}
          {collectionFolders}
          {highlightPaths}
          {onCollectionToggle}
        />
      {/each}
    </div>
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
    accent-color: var(--text-accent);
  }
  .checkbox.collection-checkbox {
    accent-color: var(--text-active);
  }
  .checkbox-spacer {
    display: inline-block;
    width: 13px;
    margin-right: 0.5rem;
  }
  .dimmed {
    opacity: 0.35;
  }
  .highlighted {
    background: rgba(182, 159, 129, 0.12);
    border-left: 3px solid var(--text-accent);
    margin-left: -3px;
  }
  .row {
    display: flex;
    align-items: center;
    padding: 0.2rem 0.25rem;
    cursor: pointer;
    background: none;
    border: none;
    border-radius: 3px;
    flex: 1;
    text-align: left;
    font-size: 0.95rem;
    font-family: var(--font-body);
    color: var(--text-primary);
    transition: background var(--transition-fast);
  }
  .row:hover {
    background: var(--bg-focused);
  }
  .icon {
    margin-right: 0.3rem;
    flex-shrink: 0;
  }
  .folder-icon {
    color: var(--text-accent);
    font-size: 0.85rem;
    width: 1rem;
    display: inline-block;
    text-align: center;
  }
  .name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
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
    font-family: var(--font-body);
    background: rgba(182, 159, 129, 0.15);
    color: var(--text-accent);
    white-space: nowrap;
    border: 1px solid transparent;
    cursor: pointer;
    transition: border-color var(--transition-fast);
  }
  .game-system-badge:hover {
    border-color: var(--text-accent);
  }
  .game-system-badge.readonly {
    cursor: default;
  }
  .game-system-badge.readonly:hover {
    border-color: transparent;
  }
  .add-tag-btn {
    display: inline-block;
    padding: 0 0.35rem;
    margin-left: 0.5rem;
    border-radius: 3px;
    font-size: 0.75rem;
    background: transparent;
    color: var(--text-tertiary);
    border: 1px dashed var(--bg-category);
    cursor: pointer;
    line-height: 1.4;
    transition: all var(--transition-fast);
  }
  .add-tag-btn:hover {
    background: rgba(182, 159, 129, 0.1);
    color: var(--text-accent);
    border-color: var(--text-accent);
  }
  .dropdown {
    position: absolute;
    top: 100%;
    right: 0;
    z-index: 100;
    background: var(--bg-focused);
    border: 1px solid var(--bg-category);
    border-radius: 4px;
    box-shadow: var(--shadow-dropdown);
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
    font-family: var(--font-body);
    color: var(--text-primary);
    transition: background var(--transition-fast);
  }
  .dropdown-item:hover {
    background: var(--bg-container);
  }
  .dropdown-tag {
    font-weight: 600;
    color: var(--text-accent);
    white-space: nowrap;
  }
  .dropdown-family {
    color: var(--text-secondary);
    font-size: 0.7rem;
    white-space: nowrap;
  }
  .dropdown-divider {
    margin: 0.25rem 0;
    border: none;
    border-top: 1px solid var(--bg-category);
  }
  .dropdown-clear {
    color: var(--text-danger);
  }
</style>
