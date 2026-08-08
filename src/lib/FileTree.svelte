<script lang="ts">
  import { afterUpdate } from 'svelte';
  import { invoke } from '@tauri-apps/api/core';
  import { openPath } from '@tauri-apps/plugin-opener';
  import { slide } from 'svelte/transition';
  import type { FileItem, KnownGameSystem } from './types';
  import { areAllDescendantsSelected, isPathOrAncestorIn } from './selectionUtils';
  import { isRowOutOfScope, rowHasIndexedMaterial } from './treeNav';
  import SystemBadge from './SystemBadge.svelte';

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

  // Active-context filter — when set, only paths in this Set render.
  // Includes ancestor folders of every shown file so the tree structure
  // remains intact.
  export let displayPaths: Set<string> | null = null;

  // User-hidden files/folders. Stores explicit hides; descendants of a
  // hidden folder are hidden via prefix match. When `showHidden` is true,
  // hidden rows still render but with a dimmed style.
  export let hiddenPaths: Set<string> = new Set();
  export let showHidden: boolean = false;

  // Collection-axis S/M lit states for the tree-row buttons. The dim
  // itself no longer derives from these: out-of-scope rows dim through
  // scopeBrightPaths, which already accounts for mutes.
  export let soloedScopePaths: Set<string> = new Set();
  export let mutedScopePaths: Set<string> = new Set();
  export let onToggleScopeSolo: (item: FileItem) => void = () => {};
  export let onToggleScopeMute: (item: FileItem) => void = () => {};

  // Scope membership (spec: docs/specs/scope/2026-08-08-solo-mute-play-
  // doctrine-design.md). null = no narrowing engaged, nothing dims.
  // Contains every in-scope indexed file plus its ancestor folders, so
  // the path to in-scope material stays bright.
  export let scopeBrightPaths: Set<string> | null = null;
  // Folders that contain at least one indexed file — a folder with no
  // indexed descendants has nothing to say about scope and never dims.
  export let indexedFolderPaths: Set<string> = new Set();
  // Focus lens: hide (don't render) out-of-scope rows instead of
  // dimming them. Browsing surfaces only — console surfaces never hide.
  export let hideOutOfScope: boolean = false;

  $: isSoloedScope = soloedScopePaths.has(item.path);
  $: isMutedHere = mutedScopePaths.has(item.path);
  // S/M renders wherever the row has indexed material to act on — or
  // is already engaged, so a stale solo/mute stays reachable in place.
  $: canScope = isSoloedScope || isMutedHere ||
    rowHasIndexedMaterial(item.path, item.is_dir, indexedPaths, indexedFolderPaths);
  // Out-of-scope: dimming only speaks about searchability of indexed
  // material — unindexed files keep their existing treatments. Shared
  // with keyboard nav's row model via treeNav.ts so the two never drift.
  $: outOfScope = isRowOutOfScope(item.path, item.is_dir, { scopeBrightPaths, indexedFolderPaths, indexedPaths, hideOutOfScope });

  $: isHiddenItem = isPathOrAncestorIn(item.path, hiddenPaths);
  $: hidden = (displayPaths !== null && !displayPaths.has(item.path)) ||
              (isHiddenItem && !showHidden) ||
              (outOfScope && hideOutOfScope);

  $: isExpanded = item.is_dir && expandedPaths.has(item.path);
  let showDropdown: boolean = false;
  let dropdownX: number = 0;
  let dropdownY: number = 0;
  const DROPDOWN_WIDTH = 200;
  const DROPDOWN_MAX_HEIGHT = 320;
  let childrenLoading = false;
  // Auto-fetch children when a folder is expanded but tree data was reloaded
  afterUpdate(() => {
    if (!hidden && isExpanded && item.children === null && !childrenLoading) {
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

  $: isFocused = item.path === focusedFilePath;
  $: isRenaming = item.path === renamingFilePath;

  $: tags = (!item.is_dir && gameSystemMap.get(item.path)) || [];
  $: hasTag = tags.length > 0;
  $: visibleTags = tags.slice(0, 2);
  $: hiddenTagCount = Math.max(0, tags.length - visibleTags.length);
  $: isIndexed = !item.is_dir && indexedPaths.has(item.path);

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
<div class="item" class:focused={isFocused} class:hidden-item={isHiddenItem} class:out-of-scope={outOfScope && !isHiddenItem} style="padding-left: {level * 1.5}rem;" data-tree-row={item.path}>
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

    {#if canScope}
      <span class="sm" class:engaged={isSoloedScope || isMutedHere}>
        <button
          type="button"
          class="sm-btn"
          class:solo-on={isSoloedScope}
          on:click|stopPropagation={() => onToggleScopeSolo(item)}
          aria-pressed={isSoloedScope}
          title={isSoloedScope ? `Stop soloing ${item.name} (S)` : `Solo ${item.name} (S)`}
        >S</button>
        <button
          type="button"
          class="sm-btn"
          class:mute-on={isMutedHere}
          on:click|stopPropagation={() => onToggleScopeMute(item)}
          aria-pressed={isMutedHere}
          title={isMutedHere ? `Unmute ${item.name} (M)` : `Mute ${item.name} (M)`}
        >M</button>
      </span>
    {/if}

    {#if hasTag}
      <div class="badge-wrapper">
        <button class="badge-cluster" on:click={toggleDropdown} aria-label="Edit game system tags">
          {#each visibleTags as tag}
            <SystemBadge {tag} />
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
          <!-- Font Awesome "dice-d6" — one fill for every system -->
          <svg class="dd-die" viewBox="0 0 640 640" fill="var(--text-secondary)" aria-hidden="true">
            <path d="M288.4 72.3C308 61.2 332 61.2 351.6 72.3L527.6 172C547.6 183.4 560 204.6 560 227.7L560 425.1C560 448.1 547.6 469.4 527.6 480.8L351.6 580.5C332 591.6 308 591.6 288.5 580.5L112.5 480.8C92.4 469.5 80 448.2 80 425.2L80 227.8C80 204.8 92.4 183.5 112.4 172.1L288.4 72.4zM166.6 219.6C157.8 216.5 147.8 219.9 142.8 228.2C137.8 236.5 139.6 246.9 146.4 253.2L149.6 255.6L299.8 345.8L299.8 494.5C299.8 505.5 308.8 514.5 319.8 514.5C330.8 514.5 339.8 505.5 339.8 494.5L339.8 345.8L490.1 255.6C499.6 249.9 502.7 237.6 497 228.2C491.3 218.8 479 215.7 469.6 221.3L319.9 311.1L170.2 221.3L166.5 219.6z"/>
          </svg>
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
          {displayPaths}
          {hiddenPaths}
          {showHidden}
          {soloedScopePaths}
          {mutedScopePaths}
          {onToggleScopeSolo}
          {onToggleScopeMute}
          {scopeBrightPaths}
          {indexedFolderPaths}
          {hideOutOfScope}
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
  /* Out of the resolved scope — dimmed, never hidden (unless the focus
     lens is on, which drops the row from the render instead). Only the
     row itself dims (each descendant row evaluates its own membership),
     so nesting doesn't compound the opacity. Hover restores
     legibility, mirroring the systems view's dimmed groups. The S/M
     cluster stays full-strength — it's the way back in, mirroring the
     collections panel's transport. */
  .out-of-scope > .row-container > :not(.sm) {
    opacity: var(--opacity-out-of-scope);
  }
  .out-of-scope > .row-container:hover > :not(.sm) {
    opacity: var(--opacity-out-of-scope-hover);
  }
  /* S/M cluster on folder rows — hidden at rest, revealed on row hover
     or keyboard focus, always visible while engaged. Button anatomy is
     the shared .sm-btn in app.css. */
  .sm {
    display: inline-flex;
    gap: 0.25rem;
    margin-left: auto;
    opacity: 0;
    transition: opacity var(--transition-fast);
  }
  .row-container:hover .sm,
  .row-container:focus-within .sm,
  .focused > .row-container .sm,
  .sm.engaged {
    opacity: 1;
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
  /* Base pill styles live in SystemBadge.svelte; the +N overflow pill has
     no die and stays grey, so it keeps its own copy here. */
  .game-system-badge.overflow {
    display: inline-block;
    padding: 0.1rem 0.4rem;
    border-radius: var(--radius-sm);
    font-size: 0.75rem;
    font-family: var(--font-body);
    color: var(--text-secondary);
    background: color-mix(in srgb, var(--text-accent) 8%, transparent);
    white-space: nowrap;
    border: 1px solid transparent;
    transition: border-color var(--transition-fast);
  }
  .badge-cluster:hover :global(.game-system-badge) {
    border-color: var(--text-accent);
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
    background: color-mix(in srgb, var(--text-accent) 10%, transparent);
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
  .dd-die {
    width: 11px;
    height: 11px;
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
