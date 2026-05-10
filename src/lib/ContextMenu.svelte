<script lang="ts">
  import { afterUpdate, onMount } from 'svelte';
  import type { FileItem, CollectionInfo, KnownGameSystem } from './types';

  export let x: number;
  export let y: number;
  export let item: FileItem;
  export let isIndexed: boolean = false;
  export let collections: Record<string, CollectionInfo> = {};
  export let containingCollections: string[] = [];
  // Names to suppress from the Add-to-collection submenu — used to hide
  // collections that already fully contain the target so we don't offer
  // a no-op action. Folder partials (some files in, some not) stay visible.
  export let excludeFromAdd: string[] = [];
  export let canAddToCollection: boolean = true;
  export let canScopeSearch: boolean = false;
  // Hide/show state. `inheritedHidden` means an ancestor folder is hidden,
  // so the toggle is omitted (user must unhide the originally-hidden folder).
  export let directlyHidden: boolean = false;
  export let inheritedHidden: boolean = false;
  // Optional initial submenu to open on mount (used by the C tree-row chord
  // in PR 2 of chunk c — for now the prop just exists so callers can land
  // a row directly in the Add submenu without a follow-up keystroke).
  export let initialSubmenu: 'add' | 'remove' | 'tag' | null = null;
  // Game-system tagging — only relevant for indexed PDFs. Empty arrays
  // are valid (no tags / no known systems) and gate the trigger off.
  export let knownSystems: KnownGameSystem[] = [];
  export let currentTags: string[] = [];
  export let onSetGameSystems: (tags: string[]) => void = () => {};
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
  let openSubmenu: 'add' | 'remove' | 'tag' | null = initialSubmenu;
  // -1 means "no keyboard cursor yet" — stays that way for mouse users.
  // First ↑/↓ promotes to 0 (Math.max(0, -1 ± 1) clamps to 0). When the
  // menu opens directly into a submenu (C chord) the trigger's index is
  // resolved in refreshItemsAndFocus so ← from the submenu has somewhere
  // to land.
  let focusedIdx = -1;
  let focusedSubmenuIdx: number | null = openSubmenu ? 0 : null;
  let mainItems: HTMLElement[] = [];
  let submenuItems: HTMLElement[] = [];

  function handleOutsideMouseDown(event: MouseEvent) {
    if (event.button === 2 && menuEl && !menuEl.contains(event.target as Node)) {
      onClose();
    }
  }

  // Re-query items after every render so adding/removing conditional sections
  // doesn't desync the keyboard cursor. Apply the .kb-focused class
  // imperatively because the row markup is conditional, not #each-driven.
  //
  // ``initial`` only true on the onMount call — that's when we may need to
  // promote focusedIdx to the trigger of an initialSubmenu chord-open.
  // Doing it on every afterUpdate would also fire when a hover-open sets
  // openSubmenu, which would leave .kb-focused stuck on the trigger after
  // mouse-leave clears .open.
  function refreshItemsAndFocus(opts: { initial?: boolean } = {}) {
    if (!menuEl) return;
    mainItems = Array.from(menuEl.querySelectorAll(':scope > [data-mi]')) as HTMLElement[];
    if (openSubmenu) {
      const trigger = menuEl.querySelector(`[data-mi="submenu-trigger"][data-submenu="${openSubmenu}"]`);
      submenuItems = trigger
        ? Array.from(trigger.querySelectorAll('.submenu > [data-mi]')) as HTMLElement[]
        : [];
    } else {
      submenuItems = [];
    }
    // Clamp upper bound only — leave -1 alone so mouse users don't get
    // a false cursor highlight on the first row.
    if (focusedIdx >= mainItems.length) focusedIdx = mainItems.length - 1;
    if (focusedSubmenuIdx !== null && submenuItems.length > 0) {
      focusedSubmenuIdx = Math.max(0, Math.min(submenuItems.length - 1, focusedSubmenuIdx));
    }
    // When the menu opened directly into a submenu (C chord), resolve
    // the trigger's index so ← / Esc from the submenu has a row to fall
    // back to. Only on initial mount — afterUpdate runs would also trip
    // this branch on hover-opens and strand .kb-focused.
    if (opts.initial && openSubmenu && focusedIdx < 0) {
      const triggerIdx = mainItems.findIndex(
        (el) => el.dataset.mi === 'submenu-trigger' && el.dataset.submenu === openSubmenu,
      );
      if (triggerIdx >= 0) focusedIdx = triggerIdx;
    }
    const inSub = focusedSubmenuIdx !== null;
    mainItems.forEach((el, i) => el.classList.toggle('kb-focused', i === focusedIdx && !inSub));
    submenuItems.forEach((el, i) => el.classList.toggle('kb-focused', i === focusedSubmenuIdx));

    clampOpenSubmenuToViewport();
  }

  // The static .submenu CSS opens downward at top: -0.15rem and caps at
  // 320px, but a trigger near the bottom of the window leaves no room —
  // items become unreachable. Re-measure on every render: pick whichever
  // side (above or below the trigger) has more room, anchor the submenu
  // there, and shrink max-height to fit. Generic across Add/Remove/Tag.
  function clampOpenSubmenuToViewport() {
    if (!menuEl || !openSubmenu) return;
    const trigger = menuEl.querySelector(
      `[data-submenu="${openSubmenu}"]`,
    ) as HTMLElement | null;
    const submenu = trigger?.querySelector('.submenu') as HTMLElement | null;
    if (!trigger || !submenu) return;

    const padding = 8;
    const triggerRect = trigger.getBoundingClientRect();
    // If anchored at top: -0.15rem the submenu starts at trigger.top, so
    // the room below is the viewport from there. If anchored at bottom:
    // -0.15rem it ends at trigger.bottom, so the room above is the
    // viewport up to there.
    const spaceBelow = window.innerHeight - triggerRect.top - padding;
    const spaceAbove = triggerRect.bottom - padding;

    if (spaceAbove > spaceBelow) {
      submenu.style.top = 'auto';
      submenu.style.bottom = '-0.15rem';
      submenu.style.maxHeight = `${Math.max(120, Math.min(spaceAbove, 320))}px`;
    } else {
      submenu.style.top = '-0.15rem';
      submenu.style.bottom = 'auto';
      submenu.style.maxHeight = `${Math.max(120, Math.min(spaceBelow, 320))}px`;
    }
  }

  onMount(() => refreshItemsAndFocus({ initial: true }));
  afterUpdate(() => refreshItemsAndFocus());

  function handleKeydown(event: KeyboardEvent) {
    const meta = event.metaKey || event.ctrlKey;
    const lk = event.key.toLowerCase();
    const bareLetter = !meta && !event.shiftKey && !event.altKey;
    const inSub = focusedSubmenuIdx !== null;

    const isDown  = event.key === 'ArrowDown'  || (bareLetter && lk === 'j');
    const isUp    = event.key === 'ArrowUp'    || (bareLetter && lk === 'k');
    const isRight = event.key === 'ArrowRight' || (bareLetter && lk === 'l');
    const isLeft  = event.key === 'ArrowLeft'  || (bareLetter && lk === 'h');

    if (isDown) {
      event.preventDefault();
      if (inSub) focusedSubmenuIdx = Math.min(submenuItems.length - 1, (focusedSubmenuIdx ?? -1) + 1);
      else       focusedIdx = Math.min(mainItems.length - 1, focusedIdx + 1);
      refreshItemsAndFocus();
      return;
    }
    if (isUp) {
      event.preventDefault();
      if (inSub) focusedSubmenuIdx = Math.max(0, (focusedSubmenuIdx ?? 0) - 1);
      else       focusedIdx = Math.max(0, focusedIdx - 1);
      refreshItemsAndFocus();
      return;
    }
    if (isRight && !inSub) {
      const item = mainItems[focusedIdx];
      const which = item?.dataset.submenu as 'add' | 'remove' | 'tag' | undefined;
      if (item?.dataset.mi === 'submenu-trigger' && which) {
        event.preventDefault();
        openSubmenu = which;
        focusedSubmenuIdx = 0;
      }
      return;
    }
    if (isLeft && inSub) {
      event.preventDefault();
      openSubmenu = null;
      focusedSubmenuIdx = null;
      return;
    }
    if (event.key === 'Enter') {
      event.preventDefault();
      const target = inSub ? submenuItems[focusedSubmenuIdx!] : mainItems[focusedIdx];
      target?.click();
      return;
    }
    if (event.key === 'Escape') {
      event.preventDefault();
      if (inSub) {
        openSubmenu = null;
        focusedSubmenuIdx = null;
      } else {
        onClose();
      }
    }
  }

  $: addExcludeSet = new Set(excludeFromAdd);
  $: addableCollections = Object.values(collections).filter((c) => !addExcludeSet.has(c.name));
  $: hasCollections = addableCollections.length > 0;
  $: hasContainingCollections = containingCollections.length > 0;

  $: canTag = !item.is_dir && isIndexed && knownSystems.length > 0;

  function toggleGameSystem(tag: string) {
    const next = currentTags.includes(tag)
      ? currentTags.filter((t) => t !== tag)
      : [...currentTags, tag];
    onSetGameSystems(next);
  }

  function clearGameSystems() {
    onSetGameSystems([]);
  }

  // Clamp position so the menu stays within the viewport
  $: clampedX = Math.min(x, window.innerWidth - 200);
  $: clampedY = Math.min(y, window.innerHeight - 240);
</script>

<svelte:window on:click={onClose} on:mousedown={handleOutsideMouseDown} on:keydown={handleKeydown} />

<!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
<div
  class="context-menu"
  bind:this={menuEl}
  style="left: {clampedX}px; top: {clampedY}px"
  on:click|stopPropagation
  on:mousedown|stopPropagation
>
  {#if !item.is_dir}
    <button class="context-item" data-mi="item" on:click={onOpen}>Open file</button>
  {/if}
  <button class="context-item" data-mi="item" on:click={onReveal}>Reveal in folder</button>
  {#if canScopeSearch}
    <hr class="context-divider" />
    <button class="context-item" data-mi="item" on:click={onSearchInScope}>
      Search in this {item.is_dir ? 'folder' : 'file'}
    </button>
  {/if}
  {#if !item.is_dir && isIndexed}
    <hr class="context-divider" />
    <button class="context-item" data-mi="item" on:click={onReindex}>Re-index file</button>
    <button class="context-item" data-mi="item" on:click={onShowStats}>Get info</button>
  {/if}

  {#if canTag}
    <hr class="context-divider" />
    <!-- svelte-ignore a11y-mouse-events-have-key-events -->
    <div
      class="context-item submenu-trigger"
      class:open={openSubmenu === 'tag'}
      data-mi="submenu-trigger"
      data-submenu="tag"
      on:mouseenter={() => { openSubmenu = 'tag'; }}
      on:mouseleave={() => { openSubmenu = null; }}
    >
      <span>Game system&hellip;</span>
      <span class="submenu-caret">&#9656;</span>
      {#if openSubmenu === 'tag'}
        <div class="submenu">
          {#each knownSystems as sys}
            <button
              class="context-item"
              data-mi="item"
              on:click={() => toggleGameSystem(sys.tag)}
            >
              <span class="submenu-check">{currentTags.includes(sys.tag) ? '✓' : ''}</span>
              <span>{sys.tag}</span>
            </button>
          {/each}
          {#if currentTags.length > 0}
            <hr class="context-divider" />
            <button class="context-item" data-mi="item" on:click={clearGameSystems}>
              Clear tags
            </button>
          {/if}
        </div>
      {/if}
    </div>
  {/if}

  {#if canAddToCollection}
    <hr class="context-divider" />
    {#if item.is_dir}
      <button class="context-item" data-mi="item" on:click={onCreateCollectionFromFolder}>
        Create collection from folder
      </button>
    {/if}
    <!-- svelte-ignore a11y-mouse-events-have-key-events -->
    <div
      class="context-item submenu-trigger"
      class:open={openSubmenu === 'add'}
      data-mi="submenu-trigger"
      data-submenu="add"
      on:mouseenter={() => { openSubmenu = 'add'; }}
      on:mouseleave={() => { openSubmenu = null; }}
    >
      <span>Add to collection&hellip;</span>
      <span class="submenu-caret">&#9656;</span>
      {#if openSubmenu === 'add'}
        <div class="submenu">
          {#each addableCollections as col}
            <button
              class="context-item"
              data-mi="item"
              on:click={() => onAddToCollection(col.name)}
            >
              {col.name}
            </button>
          {/each}
          {#if hasCollections}
            <hr class="context-divider" />
          {/if}
          <button class="context-item" data-mi="item" on:click={onAddToNewCollection}>
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
        data-mi="submenu-trigger"
        data-submenu="remove"
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
                data-mi="item"
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
    <button class="context-item" data-mi="item" on:click={onToggleHidden}>
      {directlyHidden ? 'Unhide' : 'Hide'} {item.is_dir ? 'folder' : 'file'}
    </button>
  {/if}

  <hr class="context-divider" />
  <button class="context-item" data-mi="item" on:click={onRename}>Rename {item.is_dir ? 'folder' : 'file'}</button>
  <button class="context-item danger" data-mi="item" on:click={onDelete}>Delete {item.is_dir ? 'folder' : 'file'}</button>
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
  .context-item:hover,
  .context-item:global(.kb-focused) {
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
  .submenu-check {
    display: inline-block;
    width: 1rem;
    text-align: center;
    margin-right: 0.25rem;
    color: var(--text-accent);
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
