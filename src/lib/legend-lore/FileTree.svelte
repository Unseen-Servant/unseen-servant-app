<script lang="ts">
  import { afterUpdate } from 'svelte';
  import { invoke } from '@tauri-apps/api/core';
  import { openPath } from '@tauri-apps/plugin-opener';
  import { slide } from 'svelte/transition';
  import type { FileItem, KnownGameSystem } from './types';
  import { checkboxState, isPathOrAncestorIn } from './selectionUtils';
  import { isRowOutOfScope, rowHasIndexedMaterial, rowHasLibraryMaterial } from './treeNav';
  import { splitRibbons, EMPTY_RIBBONS, type Ribbon } from './collectionRibbons';
  import { memberStateFor, type ArmState } from './collectionMembership';
  import { writeTreePathsTransfer, clearTreePathsPayload, type TreePathsPayload } from './dragPayload';
  import { BOOK, CARET_RIGHT, RIBBON_OUTLINE } from '../ui/iconPaths';
  import { hoverLive } from '../ui/inputModality';
  import { markName } from './nameFilter';
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
  export let onSetGameSystems: (path: string, tags: string[]) => void = () => {};

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
  // The bar's / filter, as words (empty = off). Only marks what matched —
  // displayPaths already carries which rows the filter keeps.
  export let filterWords: string[] = [];

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

  // Scope membership. null = no narrowing engaged, nothing dims.
  // Contains every in-scope indexed file plus its ancestor folders, so
  // the path to in-scope material stays bright.
  export let scopeBrightPaths: Set<string> | null = null;
  // Folders that contain at least one indexed file — a folder with no
  // indexed descendants has nothing to say about scope and never dims.
  export let indexedFolderPaths: Set<string> = new Set();
  // Focus lens: hide (don't render) out-of-scope rows instead of
  // dimming them. Browsing surfaces only — console surfaces never hide.
  export let hideOutOfScope: boolean = false;
  // File path → the collections holding it, colored ones first. Drawn as
  // a ribbon strip so curation is visible while browsing; folders carry
  // no membership of their own and get nothing.
  export let ribbonIndex: Map<string, Ribbon[]> = new Map();

  // The armed collection, or null. While armed the row's checkbox stops
  // meaning "index this" and starts meaning "file this", and clicking the
  // row itself does the same.
  export let arm: ArmState | null = null;
  export let onToggleMembership: (item: FileItem, shiftKey?: boolean) => void = () => {};

  // Resolving a row to its indexed PDFs needs the page's indexedPaths, so
  // the page does it at dragstart and stashes the payload; null means the
  // row has nothing to give and the drag is refused.
  export let onBeginDrag: (path: string, name: string, isDir: boolean) => TreePathsPayload | null =
    () => null;

  // "Hide unindexed items": drop rows the library knows nothing about —
  // neither in the index nor selected for it. Tree only; SystemsView
  // renders indexStatus entries and holds nothing unindexed to hide.
  export let hideUnindexed: boolean = false;

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

  // Rows the library knows nothing about. Unlike out-of-scope, this has
  // no dim tier — the switch off reproduces today's tree exactly.
  $: outsideLibrary = hideUnindexed && !rowHasLibraryMaterial(item.path, item.is_dir, {
    indexedPaths, indexedFolderPaths, selectedPaths, foldersWithSelections, hideUnindexed,
  });

  $: isHiddenItem = isPathOrAncestorIn(item.path, hiddenPaths);
  $: hidden = (displayPaths !== null && !displayPaths.has(item.path)) ||
              (isHiddenItem && !showHidden) ||
              (outOfScope && hideOutOfScope) ||
              outsideLibrary;

  $: isExpanded = item.is_dir && expandedPaths.has(item.path);
  let tagMenu: SystemTagMenu | undefined;
  let childrenLoading = false;
  // Hover latched on real pointerenter, not CSS :hover — closing a menu
  // or ending a drag re-hit-tests whatever lands under a pointer that
  // never moved, and :hover lights it with no leave ever queued. Same
  // fix the collections panel carries. Per-instance state: this
  // component IS one row. Painted only while $hoverLive, so an arrow
  // scrolling rows under a resting pointer doesn't light a second row.
  let hovered = false;
  // Auto-fetch children when a folder is expanded but tree data was reloaded
  afterUpdate(() => {
    if (!hidden && isExpanded && item.children === null && !childrenLoading) {
      childrenLoading = true;
      invoke<FileItem[]>('list_files', { folderPath: item.path })
        .then(children => { item = { ...item, children }; childrenLoading = false; })
        .catch(() => { item = { ...item, children: [] }; childrenLoading = false; });
    }
  });

  $: ({ isChecked, isIndeterminate } = checkboxState(item, selectedPaths, foldersWithSelections));

  $: isFocused = item.path === focusedFilePath;
  $: isRenaming = item.path === renamingFilePath;

  $: tags = (!item.is_dir && gameSystemMap.get(item.path)) || [];
  $: hasTag = tags.length > 0;
  $: visibleTags = tags.slice(0, 2);
  $: hiddenTagCount = Math.max(0, tags.length - visibleTags.length);
  $: isIndexed = !item.is_dir && indexedPaths.has(item.path);
  // Same gate the context menu puts on its "Game system" submenu: with no
  // systems known the menu has nothing to offer, and no menu in the app
  // carries empty-state copy. The badge cluster above stays ungated — on a
  // tagged file the menu still holds "Clear tags".
  $: canTag = isIndexed && knownSystems.length > 0;

  // The armed collection lives in the arm slot; showing it in the strip
  // as well would say the same thing twice on one row.
  // Every collection holding this file, armed one included. The strip is a
  // readout and the checkbox is a control; they can agree. (The armed
  // collection used to be filtered out because the old arm slot drew its
  // ribbon — with that gone, hiding it just cost the row its pigment.)
  $: ribbons = item.is_dir ? EMPTY_RIBBONS : (ribbonIndex.get(item.path) ?? EMPTY_RIBBONS);
  $: ribbonSplit = splitRibbons(ribbons);
  $: ribbonTitle = ribbons.length === 0 ? '' : ribbons.map((r) => r.name).join(', ');

  // Same predicate that gates S/M: a row with nothing indexed under it has
  // nothing a collection could hold — the sidecar drops unindexed paths at
  // read time — so its slot stays empty rather than offering a dead click.
  $: hasIndexedMaterial = rowHasIndexedMaterial(item.path, item.is_dir, indexedPaths, indexedFolderPaths);
  // Armed, a row with nothing indexed under it has nothing a collection can
  // take — the sidecar drops unindexed paths at read time — so its box is
  // shown disabled rather than removed, which would leave the column ragged.
  $: canArm = arm !== null && hasIndexedMaterial;
  $: memberState = arm === null ? 'none' : memberStateFor(item.path, item.is_dir, arm.paths, arm.folders);
  $: boxOn = arm ? memberState === 'all' : isChecked;
  $: boxMixed = arm ? memberState === 'some' : isIndeterminate;

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

  // One checkbox, two meanings. Unarmed it marks the row for indexing;
  // armed it files the row into the collection being curated. The colour
  // carries the difference — parchment for data, purple for a mode.
  function handleCheckboxChange(event: MouseEvent | KeyboardEvent) {
    if (arm) onToggleMembership(item, event.shiftKey);
    else onToggle(item.path, item.is_dir, item, event.shiftKey);
  }

  function toggleSystem(tag: string) {
    const next = tags.includes(tag)
      ? tags.filter((t) => t !== tag)
      : [...tags, tag];
    onSetGameSystems(item.path, next);
  }

  function clearSystem() {
    onSetGameSystems(item.path, []);
  }

  function handleDragStart(event: DragEvent) {
    const payload = onBeginDrag(item.path, item.name, item.is_dir);
    if (!payload || !event.dataTransfer) {
      event.preventDefault();
      return;
    }
    writeTreePathsTransfer(event.dataTransfer, payload);
  }

  function handleRowClick() {
    onFocusFile(item.path);
    // While armed, a file row's primary action is filing it — the same
    // rewrite the systems view already does when curating. Folders keep
    // expanding: you have to be able to navigate while you curate, so
    // enrolling a whole folder goes through its checkbox instead.
    if (item.is_dir) toggleExpand();
    else if (canArm) onToggleMembership(item);
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
  <!-- svelte-ignore a11y-no-static-element-interactions -->
  <div
    class="row-container"
    class:hovered={hovered && $hoverLive}
    on:pointerenter={() => (hovered = true)}
    on:pointerleave={() => (hovered = false)}
  >
    <!-- Arrow leads the row so the checkbox sits flush against the type
         icon; files keep a phantom slot so every checkbox forms one column. -->
    {#if item.is_dir}
      <!-- svelte-ignore a11y-click-events-have-key-events -->
      <svg on:click={handleRowClick} class="caret icon arrow" class:open={isExpanded} viewBox="96 64 512 512" fill="currentColor" aria-hidden="true"><path d={CARET_RIGHT}/></svg>
    {:else}
      <span class="icon gutter" aria-hidden="true"></span>
    {/if}
    <button
      class="app-checkbox row-checkbox"
      class:collecting={arm !== null}
      disabled={arm !== null && !canArm}
      on:click|stopPropagation={handleCheckboxChange}
      role="checkbox"
      aria-label={arm ? `Add ${item.name} to ${arm.name}` : `Select ${item.name} for indexing`}
      aria-checked={boxMixed ? 'mixed' : boxOn}
    ></button>

    <!-- Draggable on .row, not .row-container: the checkbox and the S/M
         buttons are siblings, so no drag can start from them. Never while
         renaming — a draggable ancestor kills text selection inside a
         descendant input in WebKit. -->
    <button
      class="row"
      draggable={hasIndexedMaterial && !isRenaming}
      on:dragstart={handleDragStart}
      on:dragend={() => { clearTreePathsPayload(); hovered = false; }}
      on:click={handleRowClick}
      on:dblclick={openFile}
      on:mousedown={handleMouseDown}
    >
      {#if item.is_dir}
        <span class="icon type-icon folder-glyph" aria-hidden="true">
          <!-- Font Awesome "folder" \u2014 identity lives on the icon, the arrow
               carries expand state, mirroring the systems view's headers -->
          <svg viewBox="0 0 512 512" fill="currentColor">
            <path d="M64 480H448c35.3 0 64-28.7 64-64V160c0-35.3-28.7-64-64-64H288c-10.1 0-19.6-4.7-25.6-12.8L243.2 57.6C231.1 41.5 212.1 32 192 32H64C28.7 32 0 60.7 0 96V416c0 35.3 28.7 64 64 64z"/>
          </svg>
        </span>
      {:else}
        <span class="icon type-icon file-glyph" aria-hidden="true">
          <!-- Font Awesome "book" \u2014 matches systems-view file rows -->
          <svg viewBox="0 0 640 640" fill="currentColor">
            <path d={BOOK}/>
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
        <span class="name">{#each markName(item.name, filterWords) as part, i (i)}{#if part.hit}<span class="hit">{part.text}</span>{:else}{part.text}{/if}{/each}</span>
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
    {:else if canTag}
      <div class="badge-wrapper">
        <button class="add-tag-btn" on:click={(e) => tagMenu?.toggle(e)}>+ tag</button>
      </div>
    {/if}

    {#if ribbons.length > 0}
      <!-- Which collections hold this book. Same ribbon the panel rows,
           scope chips and search results use, so the pigment↔collection
           mapping only has to be learned once. -->
      <span class="ribbons" title={ribbonTitle}>
        {#each ribbonSplit.shown as r (r.name)}
          <svg class="ribbon" style={`color: ${r.color}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round" aria-hidden="true">
            <path d={RIBBON_OUTLINE}/>
          </svg>
        {/each}
        {#if ribbonSplit.overflow > 0}
          <span class="ribbon-overflow">+{ribbonSplit.overflow}</span>
        {/if}
      </span>
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
          {filterWords}
          {hiddenPaths}
          {showHidden}
          {soloedScopePaths}
          {mutedScopePaths}
          {onToggleScopeSolo}
          {onToggleScopeMute}
          {scopeBrightPaths}
          {indexedFolderPaths}
          {hideOutOfScope}
          {hideUnindexed}
          {ribbonIndex}
          {arm}
          {onToggleMembership}
          {onBeginDrag}
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
  .row-container.hovered {
    background: var(--bg-container);
  }
  .row-checkbox {
    margin-right: 0.5rem;
    margin-left: 0.2rem;
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
  .out-of-scope > .row-container.hovered > :not(.sm) {
    opacity: var(--opacity-out-of-scope-hover);
  }
  /* S/M cluster on folder rows — hidden at rest, revealed on row hover
     or keyboard focus, always visible while engaged. Button anatomy is
     the shared .sm-btn in app.css. Hover is the latched .hovered class,
     not :hover — see the note at its declaration. */
  .sm {
    display: inline-flex;
    gap: 0.25rem;
    margin-left: auto;
    opacity: 0;
    transition: opacity var(--transition-fast);
  }
  .row-container.hovered .sm,
  .row-container:focus-within .sm,
  .focused > .row-container .sm,
  .sm.engaged {
    opacity: 1;
  }
  .focused > .row-container {
    box-shadow: var(--ring-focus);
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
    cursor: pointer;
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
  /* Parchment = content identity, same as the systems view's shield icon. */
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
  /* What the / filter matched — the same mark the search rows use. */
  .hit {
    color: var(--text-accent);
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
  .ribbons {
    display: inline-flex;
    align-items: center;
    gap: 0.15rem;
    margin-left: 0.5rem;
    flex-shrink: 0;
  }
  /* Without an explicit size an inline SVG falls back to its intrinsic
     dimensions, which is how this strip disappeared once. */
  .ribbon {
    display: block;
    width: 10px;
    height: 10px;
  }
  /* Base pill styles live in SystemBadge.svelte; the +N overflow pills have
     no shield and stay grey, so they keep their own copy here. One recipe for
     both clusters so tags and collections read as the same family. */
  .game-system-badge.overflow,
  .ribbon-overflow {
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
