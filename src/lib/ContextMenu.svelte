<script lang="ts">
  import type { FileItem, CollectionInfo } from './types';

  export let x: number;
  export let y: number;
  export let item: FileItem;
  export let isIndexed: boolean = false;
  export let collections: Record<string, CollectionInfo> = {};
  export let containingCollections: string[] = [];
  export let canAddToCollection: boolean = true;
  export let canScopeSearch: boolean = false;
  // Hide/show state. `inheritedHidden` means an ancestor folder is hidden,
  // so the toggle is omitted (user must unhide the originally-hidden folder).
  export let directlyHidden: boolean = false;
  export let inheritedHidden: boolean = false;
  export let onOpen: () => void = () => {};
  export let onReveal: () => void = () => {};
  export let onRename: () => void = () => {};
  export let onDelete: () => void = () => {};
  export let onReindex: () => void = () => {};
  export let onShowStats: () => void = () => {};
  export let onSearchInScope: () => void = () => {};
  export let onAddToCollection: (name: string) => void = () => {};
  export let onAddToNewCollection: () => void = () => {};
  export let onRemoveFromCollection: (name: string) => void = () => {};
  export let onCreateCollectionFromFolder: () => void = () => {};
  export let onToggleHidden: () => void = () => {};
  export let onClose: () => void = () => {};

  let menuEl: HTMLDivElement;
  let openSubmenu: 'add' | 'remove' | null = null;

  function handleOutsideMouseDown(event: MouseEvent) {
    if (event.button === 2 && menuEl && !menuEl.contains(event.target as Node)) {
      onClose();
    }
  }

  $: collectionList = Object.values(collections);
  $: hasCollections = collectionList.length > 0;
  $: hasContainingCollections = containingCollections.length > 0;

  // Clamp position so the menu stays within the viewport
  $: clampedX = Math.min(x, window.innerWidth - 200);
  $: clampedY = Math.min(y, window.innerHeight - 240);
</script>

<svelte:window on:click={onClose} on:mousedown={handleOutsideMouseDown} />

<!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
<div
  class="context-menu"
  bind:this={menuEl}
  style="left: {clampedX}px; top: {clampedY}px"
  on:click|stopPropagation
  on:mousedown|stopPropagation
>
  {#if !item.is_dir}
    <button class="context-item" on:click={onOpen}>Open file</button>
  {/if}
  <button class="context-item" on:click={onReveal}>Reveal in folder</button>
  {#if canScopeSearch}
    <hr class="context-divider" />
    <button class="context-item" on:click={onSearchInScope}>
      Search in this {item.is_dir ? 'folder' : 'file'}
    </button>
  {/if}
  {#if !item.is_dir && isIndexed}
    <hr class="context-divider" />
    <button class="context-item" on:click={onReindex}>Re-index file</button>
    <button class="context-item" on:click={onShowStats}>Get info</button>
  {/if}

  {#if canAddToCollection}
    <hr class="context-divider" />
    {#if item.is_dir}
      <button class="context-item" on:click={onCreateCollectionFromFolder}>
        Create collection from folder
      </button>
    {/if}
    <!-- svelte-ignore a11y-mouse-events-have-key-events -->
    <div
      class="context-item submenu-trigger"
      class:open={openSubmenu === 'add'}
      on:mouseenter={() => { openSubmenu = 'add'; }}
      on:mouseleave={() => { openSubmenu = null; }}
    >
      <span>Add to collection&hellip;</span>
      <span class="submenu-caret">&#9656;</span>
      {#if openSubmenu === 'add'}
        <div class="submenu">
          {#each collectionList as col}
            <button
              class="context-item"
              on:click={() => onAddToCollection(col.name)}
            >
              {col.name}
            </button>
          {/each}
          {#if hasCollections}
            <hr class="context-divider" />
          {/if}
          <button class="context-item" on:click={onAddToNewCollection}>
            + New collection&hellip;
          </button>
        </div>
      {/if}
    </div>

    {#if hasContainingCollections}
      <!-- svelte-ignore a11y-mouse-events-have-key-events -->
      <div
        class="context-item submenu-trigger"
        class:open={openSubmenu === 'remove'}
        on:mouseenter={() => { openSubmenu = 'remove'; }}
        on:mouseleave={() => { openSubmenu = null; }}
      >
        <span>Remove from collection&hellip;</span>
        <span class="submenu-caret">&#9656;</span>
        {#if openSubmenu === 'remove'}
          <div class="submenu">
            {#each containingCollections as name}
              <button
                class="context-item"
                on:click={() => onRemoveFromCollection(name)}
              >
                {name}
              </button>
            {/each}
          </div>
        {/if}
      </div>
    {/if}
  {/if}

  {#if !inheritedHidden}
    <hr class="context-divider" />
    <button class="context-item" on:click={onToggleHidden}>
      {directlyHidden ? 'Unhide' : 'Hide'} {item.is_dir ? 'folder' : 'file'}
    </button>
  {/if}

  <hr class="context-divider" />
  <button class="context-item" on:click={onRename}>Rename {item.is_dir ? 'folder' : 'file'}</button>
  <button class="context-item danger" on:click={onDelete}>Delete {item.is_dir ? 'folder' : 'file'}</button>
</div>

<style>
  .context-menu {
    position: fixed;
    z-index: 200;
    background: var(--bg-focused);
    border: 1px solid var(--bg-category);
    border-radius: 4px;
    box-shadow: var(--shadow-dropdown);
    min-width: 200px;
    padding: 0.15rem 0;
  }
  .context-item {
    display: block;
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
  .context-item:hover {
    background: var(--bg-container);
  }
  .context-item.danger {
    color: var(--text-danger);
  }
  .context-divider {
    margin: 0.15rem 0;
    border: none;
    border-top: 1px solid var(--bg-category);
  }
  .submenu-trigger {
    position: relative;
    display: flex;
    justify-content: space-between;
    align-items: center;
    user-select: none;
  }
  .submenu-trigger:hover,
  .submenu-trigger.open {
    background: var(--bg-container);
  }
  .submenu-caret {
    font-size: 0.7rem;
    opacity: 0.6;
    margin-left: 0.5rem;
  }
  .submenu {
    position: absolute;
    left: 100%;
    top: -0.15rem;
    background: var(--bg-focused);
    border: 1px solid var(--bg-category);
    border-radius: 4px;
    box-shadow: var(--shadow-dropdown);
    min-width: 180px;
    max-height: 320px;
    overflow-y: auto;
    padding: 0.15rem 0;
    z-index: 201;
  }
</style>
