<script lang="ts">
  import { afterUpdate } from 'svelte';
  import { invoke } from '@tauri-apps/api/core';
  import { openPath } from '@tauri-apps/plugin-opener';
  import { slide } from 'svelte/transition';
  import type { FileItem, KnownGameSystem } from './types';
  import { areAllDescendantsSelected, isPathOrAncestorIn } from './selectionUtils';
  import { isRowOutOfScope, rowHasIndexedMaterial } from './treeNav';
  import SystemBadge from './SystemBadge.svelte';
  import SystemTagMenu from './SystemTagMenu.svelte';

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
  let tagMenu: SystemTagMenu | undefined;
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

  function toggleSystem(tag: string) {
    const next = tags.includes(tag)
      ? tags.filter((t) => t !== tag)
      : [...tags, tag];
    onSetGameSystems(item.path, item.name, next);
  }

  function clearSystem() {
    onSetGameSystems(item.path, item.name, []);
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

</script>

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
        <span class="icon arrow" aria-hidden="true">{isExpanded ? '\u25BE' : '\u25B8'}</span>
        <span class="icon type-icon folder-glyph" aria-hidden="true">
          <!-- Font Awesome "folder" \u2014 identity lives on the icon, the arrow
               carries expand state, mirroring the systems view's headers -->
          <svg viewBox="0 0 512 512" fill="currentColor">
            <path d="M64 480H448c35.3 0 64-28.7 64-64V160c0-35.3-28.7-64-64-64H288c-10.1 0-19.6-4.7-25.6-12.8L243.2 57.6C231.1 41.5 212.1 32 192 32H64C28.7 32 0 60.7 0 96V416c0 35.3 28.7 64 64 64z"/>
          </svg>
        </span>
      {:else}
        <!-- Phantom arrow slot so file and folder icons form one column -->
        <span class="icon gutter" aria-hidden="true"></span>
        <span class="icon type-icon file-glyph" aria-hidden="true">
          <!-- Font Awesome "book" \u2014 matches systems-view file rows -->
          <svg viewBox="0 0 640 640" fill="currentColor">
            <path d="M480 576L192 576C139 576 96 533 96 480L96 160C96 107 139 64 192 64L496 64C522.5 64 544 85.5 544 112L544 400C544 420.9 530.6 438.7 512 445.3L512 512C529.7 512 544 526.3 544 544C544 561.7 529.7 576 512 576L480 576zM192 448C174.3 448 160 462.3 160 480C160 497.7 174.3 512 192 512L448 512L448 448L192 448zM224 216C224 229.3 234.7 240 248 240L424 240C437.3 240 448 229.3 448 216C448 202.7 437.3 192 424 192L248 192C234.7 192 224 202.7 224 216zM248 288C234.7 288 224 298.7 224 312C224 325.3 234.7 336 248 336L424 336C437.3 336 448 325.3 448 312C448 298.7 437.3 288 424 288L248 288z"/>
          </svg>
        </span>
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
        <button class="badge-cluster" on:click={(e) => tagMenu?.toggle(e)} aria-label="Edit game system tags">
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
        <button class="add-tag-btn" on:click={(e) => tagMenu?.toggle(e)}>+ tag</button>
      </div>
    {/if}
  </div>

  <SystemTagMenu
    bind:this={tagMenu}
    {knownSystems}
    {tags}
    align="right"
    onToggleSystem={toggleSystem}
    onClear={clearSystem}
  />

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
    padding: 0.25rem;
    cursor: pointer;
    background: none;
    border: none;
    border-radius: var(--radius-sm);
    flex: 1;
    text-align: left;
    font-size: 0.9rem;
    /* Buttons don't inherit body line-height; set it so rows share the
       systems view's vertical rhythm. */
    line-height: 1.5;
    font-family: var(--font-body);
    color: var(--text-primary);
    -webkit-user-select: none;
    user-select: none;
  }
  .icon {
    margin-right: 0.3rem;
    flex-shrink: 0;
  }
  .arrow {
    color: var(--text-secondary);
    font-size: 0.7rem;
    width: 0.8rem;
    display: inline-block;
    text-align: center;
  }
  .gutter {
    width: 0.8rem;
    display: inline-block;
  }
  .type-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 14px;
  }
  .type-icon svg {
    display: block;
  }
  /* Parchment = content identity, same as the systems view's die icon. */
  .folder-glyph {
    color: var(--text-accent);
  }
  /* The 512-grid folder renders optically larger than 640-grid icons
     (those pad 64px per side), so it gets a smaller box. */
  .folder-glyph svg {
    width: 11px;
    height: 11px;
  }
  .file-glyph {
    color: var(--text-secondary);
  }
  .file-glyph svg {
    width: 13px;
    height: 13px;
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
    font-size: 0.9rem;
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
</style>
