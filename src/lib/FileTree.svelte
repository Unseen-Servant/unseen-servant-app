<script lang="ts">
  import { afterUpdate } from 'svelte';
  import { invoke } from '@tauri-apps/api/core';
  import { openPath } from '@tauri-apps/plugin-opener';
  import { slide } from 'svelte/transition';
  import type { FileItem, KnownGameSystem } from './types';
  import { areAllDescendantsSelected, isPathOrAncestorIn } from './selectionUtils';

  export let item: FileItem;
  export let level: number = 0;
  export let selectedPaths: Set<string>;
  export let foldersWithSelections: Set<string>;
  export let gameSystemMap: Map<string, string[]> = new Map();
  export let knownSystems: KnownGameSystem[] = [];
  export let indexedPaths: Set<string> = new Set();
  export let onToggle: (path: string, isDir: boolean, item: FileItem, shiftKey: boolean) => void;
  export let onSetGameSystems: (path: string, filename: string, tags: string[]) => void = () => {};

  // Focus & context menu props
  export let focusedFilePath: string | null = null;
  export let onFocusFile: (path: string | null) => void = () => {};
  export let onContextMenu: (event: MouseEvent, item: FileItem) => void = () => {};

  // Inline rename props
  export let renamingFilePath: string | null = null;
  export let onRenameSubmit: (oldPath: string, newName: string, isDir: boolean) => void = () => {};
  export let onRenameCancel: () => void = () => {};

  // Expand state (lifted to page level)
  export let expandedPaths: Set<string> = new Set();
  export let onToggleExpand: (path: string) => void = () => {};

  // Collection-preview prop — paths get an accent stripe when previewing a
  // collection's contents from the panel (separate from collection-edit,
  // which now lives entirely in SystemsView).
  export let highlightPaths: Set<string> = new Set();

  // Active-context filter — when set, only paths in this Set render.
  // Includes ancestor folders of every shown file so the tree structure
  // remains intact.
  export let displayPaths: Set<string> | null = null;

  // User-hidden files/folders. Stores explicit hides; descendants of a
  // hidden folder are hidden via prefix match. When `showHidden` is true,
  // hidden rows still render but with a dimmed style.
  export let hiddenPaths: Set<string> = new Set();
  export let showHidden: boolean = false;

  $: isHiddenItem = isPathOrAncestorIn(item.path, hiddenPaths);
  $: hidden = (displayPaths !== null && !displayPaths.has(item.path)) ||
              (isHiddenItem && !showHidden);

  $: isExpanded = item.is_dir && expandedPaths.has(item.path);
  let showDropdown: boolean = false;
  let dropdownX: number = 0;
  let dropdownY: number = 0;
  const DROPDOWN_WIDTH = 200;
  const DROPDOWN_MAX_HEIGHT = 320;
  let childrenLoading = false;
  // Auto-fetch children when a folder is expanded but tree data was reloaded
  afterUpdate(() => {
    if (isExpanded && item.children === null && !childrenLoading) {
      childrenLoading = true;
      invoke<FileItem[]>('list_files', { folderPath: item.path })
        .then(children => { item = { ...item, children }; childrenLoading = false; })
        .catch(() => { item = { ...item, children: [] }; childrenLoading = false; });
    }
  });

  // Check if this item has any selection — O(1) Set lookup, works even for unloaded folders
  $: isSelected = item.is_dir
    ? foldersWithSelections.has(item.path)
    : selectedPaths.has(item.path);

  // For folders: computed locally from item.children (which has correct data in this component)
  $: isFullySelected = item.is_dir && item.children !== null &&
    areAllDescendantsSelected(item, selectedPaths);

  $: isChecked = item.is_dir ? isFullySelected : isSelected;
  $: isIndeterminate = item.is_dir && isSelected && !isFullySelected;
  $: isHighlighted = highlightPaths.size > 0 && highlightPaths.has(item.path);

  $: isFocused = item.path === focusedFilePath;
  $: isRenaming = item.path === renamingFilePath;

  $: tags = (!item.is_dir && gameSystemMap.get(item.path)) || [];
  $: hasTag = tags.length > 0;
  $: visibleTags = tags.slice(0, 2);
  $: hiddenTagCount = Math.max(0, tags.length - visibleTags.length);
  $: isIndexed = !item.is_dir && indexedPaths.has(item.path);

  // Tag → color lookup, derived from knownSystems on each render.
  $: tagColors = (() => {
    const m = new Map<string, string>();
    for (const sys of knownSystems) {
      if (sys.color) m.set(sys.tag, sys.color);
    }
    return m;
  })();
  function colorFor(tag: string): string | null {
    return tagColors.get(tag) ?? null;
  }

  async function toggleExpand() {
    if (!item.is_dir) return;

    const willExpand = !expandedPaths.has(item.path);
    onToggleExpand(item.path);

    if (willExpand && item.children === null) {
      try {
        const children = await invoke<FileItem[]>('list_files', { folderPath: item.path });
        item = { ...item, children };
      } catch (e) {
        console.error('Failed to load folder:', e);
        item = { ...item, children: [] };
      }
    }
  }

  function handleCheckboxChange(event: MouseEvent | KeyboardEvent) {
    onToggle(item.path, item.is_dir, item, event.shiftKey);
  }

  function toggleDropdown(event: MouseEvent) {
    event.stopPropagation();
    if (showDropdown) {
      showDropdown = false;
      return;
    }
    // Anchor the menu under the badge button using viewport coords so it
    // doesn't get pulled around by the file tree's own layout shifts.
    const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
    dropdownX = Math.min(rect.right - DROPDOWN_WIDTH, window.innerWidth - DROPDOWN_WIDTH - 4);
    dropdownX = Math.max(4, dropdownX);
    dropdownY = Math.min(rect.bottom + 2, window.innerHeight - DROPDOWN_MAX_HEIGHT - 4);
    showDropdown = true;
  }

  function toggleSystem(tag: string) {
    const next = tags.includes(tag)
      ? tags.filter((t) => t !== tag)
      : [...tags, tag];
    onSetGameSystems(item.path, item.name, next);
  }

  function clearSystem() {
    onSetGameSystems(item.path, item.name, []);
    showDropdown = false;
  }

  function handleRowClick() {
    onFocusFile(item.path);
    if (item.is_dir) toggleExpand();
  }

  async function openFile() {
    if (item.is_dir) return;
    try {
      await openPath(item.path);
    } catch (e) {
      console.error('Failed to open file:', e);
    }
  }

  function handleMouseDown(event: MouseEvent) {
    if (event.button === 2) {
      event.preventDefault();
      event.stopPropagation();
      onContextMenu(event, item);
    }
  }

  function handleRenameKeydown(event: KeyboardEvent) {
    if (event.key === 'Enter') {
      const input = event.currentTarget as HTMLInputElement;
      const ext = item.is_dir ? '' : (item.name.match(/\.[^.]+$/)?.[0] ?? '');
      onRenameSubmit(item.path, input.value + ext, item.is_dir);
    } else if (event.key === 'Escape') {
      // The global Escape ladder owns cancel (it nulls renamingFilePath
      // and returns before the focus-clear branch). What it doesn't
      // address is WebKit's delayed scroll reset: ~2 frames after the
      // rename input is removed, the engine fires a scroll event that
      // nudges scrollTop (likely its "scroll on focus removal"
      // heuristic). A single rAF restore runs before that fires and is
      // futile; restoring across frame 1 AND frame 2 wins.
      const scroller = (event.currentTarget as HTMLElement).closest('.file-tree-area') as HTMLElement | null;
      if (scroller) {
        const saved = scroller.scrollTop;
        const restore = () => { scroller.scrollTop = saved; };
        requestAnimationFrame(restore);
        requestAnimationFrame(() => requestAnimationFrame(restore));
      }
    }
  }

  function autofocus(node: HTMLInputElement) {
    // preventScroll: true so mounting the rename input doesn't nudge the
    // .file-tree-area scrollTop. R is only ever pressed on a focused row,
    // which is by construction visible — focus() doesn't need to scroll
    // anything into view, and letting it do so means Esc-cancel restores
    // to the post-nudge position, which the user reads as "drift."
    node.focus({ preventScroll: true });
    node.select();
  }

  function closeDropdown() {
    showDropdown = false;
  }

  function handleWindowKeydown(event: KeyboardEvent) {
    if (showDropdown && event.key === 'Escape') {
      closeDropdown();
    }
  }
</script>

<svelte:window on:click={closeDropdown} on:keydown={handleWindowKeydown} />

{#if !hidden}
<div class="item" class:highlighted={isHighlighted} class:focused={isFocused} class:hidden-item={isHiddenItem} style="padding-left: {level * 1.5}rem;" data-tree-row={item.path}>
  <div class="row-container">
    <button
      class="checkbox"
      class:checked={isChecked}
      class:indeterminate={isIndeterminate}
      on:click|stopPropagation={handleCheckboxChange}
      role="checkbox"
      aria-label="Select {item.name}"
      aria-checked={isIndeterminate ? 'mixed' : isChecked}
    ></button>

    <button class="row" on:click={handleRowClick} on:dblclick={openFile} on:mousedown={handleMouseDown}>
      {#if item.is_dir}
        <span class="icon folder-icon">{isExpanded ? '\u25BE' : '\u25B8'}</span>
      {/if}
      {#if isRenaming}
        <input
          class="rename-input"
          value={item.is_dir ? item.name : item.name.replace(/\.[^.]+$/, '')}
          on:keydown={handleRenameKeydown}
          on:blur={onRenameCancel}
          use:autofocus
        />
      {:else}
        <span class="name">{item.name}</span>
      {/if}
    </button>

    {#if hasTag}
      <div class="badge-wrapper">
        <button class="badge-cluster" on:click={toggleDropdown} aria-label="Edit game system tags">
          {#each visibleTags as tag}
            {@const c = colorFor(tag)}
            <span class="game-system-badge" style={c ? `--badge-color: ${c}` : ''}>{tag}</span>
          {/each}
          {#if hiddenTagCount > 0}
            <span class="game-system-badge overflow">+{hiddenTagCount}</span>
          {/if}
        </button>
      </div>
    {:else if isIndexed}
      <div class="badge-wrapper">
        <button class="add-tag-btn" on:click={toggleDropdown}>+ tag</button>
      </div>
    {/if}
  </div>

  {#if showDropdown}
    <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
    <div
      class="dropdown"
      style="left: {dropdownX}px; top: {dropdownY}px"
      on:click|stopPropagation
      on:mousedown|stopPropagation
    >
      {#each knownSystems as sys}
        <button class="dropdown-item" class:selected={tags.includes(sys.tag)} on:click={() => toggleSystem(sys.tag)}>
          <span class="dropdown-check">{tags.includes(sys.tag) ? '✓' : ''}</span>
          <span class="dropdown-tag">{sys.tag}</span>
        </button>
      {/each}
      {#if hasTag}
        <hr class="dropdown-divider" />
        <button class="dropdown-item dropdown-clear" on:click={clearSystem}>
          Clear tags
        </button>
      {/if}
    </div>
  {/if}

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
          {onSetGameSystems}
          {expandedPaths}
          {onToggleExpand}
          {focusedFilePath}
          {onFocusFile}
          {onContextMenu}
          {renamingFilePath}
          {onRenameSubmit}
          {onRenameCancel}
          {highlightPaths}
          {displayPaths}
          {hiddenPaths}
          {showHidden}
        />
      {/each}
    </div>
  {/if}
</div>
{/if}

<style>
  .item {
    -webkit-user-select: none;
    user-select: none;
  }
  .row-container {
    display: flex;
    align-items: center;
    padding: 0 0.4rem;
    border-radius: var(--radius-sm);
    transition: background var(--transition-fast);
  }
  .row-container:hover {
    background: var(--bg-focused);
  }
  .checkbox {
    width: 14px;
    height: 14px;
    margin-right: 0.5rem;
    margin-left: 0.2rem;
    padding: 0;
    cursor: pointer;
    border: 1.5px solid var(--text-tertiary);
    border-radius: var(--radius-sm);
    background: transparent;
    position: relative;
    flex-shrink: 0;
    transition: border-color var(--transition-fast), background var(--transition-fast);
  }
  .checkbox:hover {
    border-color: var(--text-accent);
  }
  .checkbox.checked {
    background: var(--text-accent);
    border-color: var(--text-accent);
  }
  .checkbox.checked::after {
    content: '';
    position: absolute;
    left: 3px;
    top: 0px;
    width: 5px;
    height: 9px;
    border: solid var(--bg-app);
    border-width: 0 2px 2px 0;
    transform: rotate(45deg);
  }
  .checkbox.indeterminate {
    background: var(--text-accent);
    border-color: var(--text-accent);
  }
  .checkbox.indeterminate::after {
    content: '';
    position: absolute;
    left: 2px;
    top: 5px;
    width: 8px;
    height: 2px;
    background: var(--bg-app);
    border-radius: 1px;
  }
  /* Hidden via the user's hide flag — only rendered when "Show hidden" is on.
     Italicized + dimmed so it reads as "explicitly suppressed". */
  .hidden-item {
    opacity: 0.55;
  }
  .hidden-item .name {
    font-style: italic;
  }
  .highlighted {
    background: rgba(182, 159, 129, 0.12);
    border-left: 3px solid var(--text-accent);
    margin-left: -3px;
  }
  .focused > .row-container {
    background: var(--bg-focused);
  }
  .row {
    display: flex;
    align-items: center;
    padding: 0.2rem 0.25rem;
    cursor: pointer;
    background: none;
    border: none;
    border-radius: var(--radius-sm);
    flex: 1;
    text-align: left;
    font-size: 0.95rem;
    font-family: var(--font-body);
    color: var(--text-primary);
    -webkit-user-select: none;
    user-select: none;
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
  .rename-input {
    background: var(--bg-container);
    color: var(--text-primary);
    border: 1px solid var(--text-accent);
    border-radius: var(--radius-sm);
    padding: 0.1rem 0.3rem;
    font-size: 0.95rem;
    font-family: var(--font-body);
    outline: none;
    width: 100%;
  }
  .badge-wrapper {
    position: relative;
    flex-shrink: 0;
  }
  .badge-cluster {
    display: inline-flex;
    align-items: center;
    gap: 0.2rem;
    margin-left: 0.5rem;
    padding: 0;
    background: none;
    border: none;
    cursor: pointer;
  }
  .game-system-badge {
    --badge-color: var(--text-accent);
    display: inline-block;
    padding: 0.1rem 0.4rem;
    border-radius: var(--radius-sm);
    font-size: 0.75rem;
    font-family: var(--font-body);
    background: color-mix(in srgb, var(--badge-color) 18%, transparent);
    color: var(--badge-color);
    white-space: nowrap;
    border: 1px solid transparent;
    transition: border-color var(--transition-fast);
  }
  .badge-cluster:hover .game-system-badge {
    border-color: var(--badge-color);
  }
  .game-system-badge.overflow {
    color: var(--text-secondary);
    background: rgba(182, 159, 129, 0.08);
  }
  .add-tag-btn {
    display: inline-block;
    padding: 0.1rem 0.55rem;
    margin-left: 0.5rem;
    border-radius: var(--radius-sm);
    font-size: 0.8rem;
    background: transparent;
    color: var(--text-secondary);
    border: 1px dashed var(--text-tertiary);
    cursor: pointer;
    line-height: 1.4;
    letter-spacing: 0.02em;
    transition: all var(--transition-fast);
  }
  .add-tag-btn:hover {
    background: rgba(182, 159, 129, 0.1);
    color: var(--text-accent);
    border-color: var(--text-accent);
    border-style: solid;
  }
  .dropdown {
    position: fixed;
    z-index: 200;
    background: var(--bg-focused);
    border: 1px solid var(--bg-category);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-dropdown);
    max-height: 320px;
    overflow-y: auto;
    width: 200px;
    padding: 0.15rem 0;
  }
  .dropdown-item {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    width: 100%;
    padding: 0.2rem 0.6rem;
    border: none;
    background: none;
    cursor: pointer;
    text-align: left;
    font-size: 0.8rem;
    line-height: 1.3;
    font-family: var(--font-body);
    color: var(--text-primary);
    transition: background var(--transition-fast);
  }
  .dropdown-item:hover {
    background: var(--bg-container);
  }
  .dropdown-item.selected {
    background: var(--bg-container);
  }
  .dropdown-check {
    width: 0.9rem;
    color: var(--text-accent);
    font-weight: 700;
    flex-shrink: 0;
  }
  .dropdown-tag {
    font-weight: 600;
    color: var(--text-accent);
    white-space: nowrap;
  }
  .dropdown-divider {
    margin: 0.15rem 0;
    border: none;
    border-top: 1px solid var(--bg-category);
  }
  .dropdown-clear {
    color: var(--text-danger);
  }
</style>
