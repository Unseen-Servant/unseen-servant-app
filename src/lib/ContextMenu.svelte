<script lang="ts">
  import { afterUpdate, onMount } from 'svelte';
  import type { FileItem, CollectionInfo, KnownGameSystem } from './types';
  import { chord, matchKey } from './keybindings';

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
  // Collection-axis S/M (folders and files) — replaces the old
  // "Search in this folder / file" scoping. Offered only when the row
  // has indexed material to act on, or is already engaged.
  export let canScope: boolean = false;
  export let isSoloed: boolean = false;
  export let isMuted: boolean = false;
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
  export let onToggleSolo: () => void = () => {};
  export let onToggleMute: () => void = () => {};
  export let onAddToCollection: (name: string) => void = () => {};
  export let onAddToNewCollection: () => void = () => {};
  export let onRemoveFromCollection: (name: string) => void = () => {};
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

    // Same idea horizontally: the static CSS opens at left: 100%, which
    // clips against the right window edge. Flip to the left side of the
    // menu when it has more room and the right side can't fit the submenu.
    const menuRect = menuEl.getBoundingClientRect();
    const spaceRight = window.innerWidth - menuRect.right - padding;
    const spaceLeft = menuRect.left - padding;
    if (submenu.offsetWidth > spaceRight && spaceLeft > spaceRight) {
      submenu.style.left = 'auto';
      submenu.style.right = '100%';
    } else {
      submenu.style.left = '100%';
      submenu.style.right = 'auto';
    }
  }

  onMount(() => {
    clampMenuToViewport();
    positioned = true;
    refreshItemsAndFocus({ initial: true });
  });
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

  // Position is bound on first render then measured-and-shifted in onMount
  // so the menu always fits within the viewport, regardless of how many
  // conditional sections (Game system, collection submenus, etc.) end up
  // rendered. Hidden for one tick during the measurement to avoid the
  // pre-clamp position flashing on screen.
  let clampedX = x;
  let clampedY = y;
  let positioned = false;

  function clampMenuToViewport() {
    if (!menuEl) return;
    const padding = 8;
    const h = menuEl.offsetHeight;
    const w = menuEl.offsetWidth;
    clampedX = Math.max(padding, Math.min(x, window.innerWidth - w - padding));
    clampedY = Math.max(padding, Math.min(y, window.innerHeight - h - padding));
  }

  $: addExcludeSet = new Set(excludeFromAdd);
  // Archived collections are shelved and inert — neither submenu offers them.
  $: addableCollections = Object.values(collections).filter(
    (c) => !c.archived && !addExcludeSet.has(c.name),
  );
  $: removableCollections = containingCollections.filter((n) => !collections[n]?.archived);
  // Remove-submenu rows only carry names — resolve their pigment here.
  $: collectionColorByName = new Map(Object.values(collections).map((c) => [c.name, c.color]));
  $: hasCollections = addableCollections.length > 0;
  $: hasContainingCollections = removableCollections.length > 0;

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

</script>

<svelte:window on:click={onClose} on:mousedown={handleOutsideMouseDown} on:keydown={handleKeydown} />

<!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
<div
  class="context-menu"
  role="menu"
  tabindex="-1"
  bind:this={menuEl}
  style="left: {clampedX}px; top: {clampedY}px; visibility: {positioned ? 'visible' : 'hidden'}"
  on:click|stopPropagation
  on:mousedown|stopPropagation
>
  {#if !item.is_dir}
    <button class="context-item" data-mi="item" role="menuitem" on:click={onOpen}>Open file</button>
  {/if}
  <button class="context-item" data-mi="item" role="menuitem" data-chord={matchKey('tree.openExternal')} on:click={onReveal}>
    Reveal in folder
    <span class="menu-chord">{chord('tree.openExternal')}</span>
  </button>
  {#if canScope}
    <hr class="context-divider" />
    <button class="context-item" data-mi="item" role="menuitem" data-chord={matchKey('tree.solo')} on:click={onToggleSolo}>
      {isSoloed ? 'Stop soloing' : 'Solo'} this {item.is_dir ? 'folder' : 'file'}
      <span class="menu-chord">{chord('tree.solo')}</span>
    </button>
    <button class="context-item" data-mi="item" role="menuitem" data-chord={matchKey('tree.mute')} on:click={onToggleMute}>
      {isMuted ? 'Unmute' : 'Mute'} this {item.is_dir ? 'folder' : 'file'}
      <span class="menu-chord">{chord('tree.mute')}</span>
    </button>
  {/if}
  {#if !item.is_dir && isIndexed}
    <hr class="context-divider" />
    <button class="context-item" data-mi="item" role="menuitem" on:click={onReindex}>Re-index file</button>
    <button class="context-item" data-mi="item" role="menuitem" data-chord={matchKey('info.show')} on:click={onShowStats}>
      Get info
      <span class="menu-chord">{chord('info.show')}</span>
    </button>
  {/if}

  {#if canTag}
    <hr class="context-divider" />
    <!-- svelte-ignore a11y-mouse-events-have-key-events -->
    <div
      class="context-item submenu-trigger"
      class:open={openSubmenu === 'tag'}
      data-mi="submenu-trigger"
      data-submenu="tag"
      role="menuitem"
      tabindex="-1"
      aria-haspopup="menu"
      aria-expanded={openSubmenu === 'tag'}
      on:mouseenter={() => { openSubmenu = 'tag'; }}
      on:mouseleave={() => { openSubmenu = null; }}
    >
      <span>Game system&hellip;</span>
      <span class="submenu-caret">&#9656;</span>
      {#if openSubmenu === 'tag'}
        <div class="submenu" role="menu">
          {#each knownSystems as sys}
            <button
              class="context-item"
              data-mi="item"
              role="menuitemcheckbox"
              aria-checked={currentTags.includes(sys.tag)}
              on:click={() => toggleGameSystem(sys.tag)}
            >
              <span class="menu-pip" class:on={currentTags.includes(sys.tag)} aria-hidden="true"></span>
              <!-- Font Awesome "dice-d6" — one fill for every system -->
              <svg class="submenu-icon" viewBox="0 0 640 640" fill="var(--text-secondary)" aria-hidden="true">
                <path d="M288.4 72.3C308 61.2 332 61.2 351.6 72.3L527.6 172C547.6 183.4 560 204.6 560 227.7L560 425.1C560 448.1 547.6 469.4 527.6 480.8L351.6 580.5C332 591.6 308 591.6 288.5 580.5L112.5 480.8C92.4 469.5 80 448.2 80 425.2L80 227.8C80 204.8 92.4 183.5 112.4 172.1L288.4 72.4zM166.6 219.6C157.8 216.5 147.8 219.9 142.8 228.2C137.8 236.5 139.6 246.9 146.4 253.2L149.6 255.6L299.8 345.8L299.8 494.5C299.8 505.5 308.8 514.5 319.8 514.5C330.8 514.5 339.8 505.5 339.8 494.5L339.8 345.8L490.1 255.6C499.6 249.9 502.7 237.6 497 228.2C491.3 218.8 479 215.7 469.6 221.3L319.9 311.1L170.2 221.3L166.5 219.6z"/>
              </svg>
              <span class="submenu-tag">{sys.tag}</span>
            </button>
          {/each}
          {#if currentTags.length > 0}
            <hr class="context-divider" />
            <button class="context-item danger" data-mi="item" role="menuitem" on:click={clearGameSystems}>
              Clear tags
            </button>
          {/if}
        </div>
      {/if}
    </div>
  {/if}

  {#if canAddToCollection}
    <hr class="context-divider" />
    <!-- svelte-ignore a11y-mouse-events-have-key-events -->
    <div
      class="context-item submenu-trigger"
      class:open={openSubmenu === 'add'}
      data-mi="submenu-trigger"
      data-submenu="add"
      data-chord={matchKey('tree.addToCollection')}
      role="menuitem"
      tabindex="-1"
      aria-haspopup="menu"
      aria-expanded={openSubmenu === 'add'}
      on:mouseenter={() => { openSubmenu = 'add'; }}
      on:mouseleave={() => { openSubmenu = null; }}
    >
      <span>Add to collection</span>
      <span class="menu-chord">{chord('tree.addToCollection')}</span>
      <span class="submenu-caret">&#9656;</span>
      {#if openSubmenu === 'add'}
        <div class="submenu" role="menu">
          {#each addableCollections as col}
            <button
              class="context-item"
              data-mi="item"
              role="menuitem"
              on:click={() => onAddToCollection(col.name)}
            >
              {#if col.color}
                <!-- Bookmark ribbon — the collection keeps its pigment -->
                <svg class="submenu-icon" viewBox="0 0 24 24" fill={col.color} aria-hidden="true">
                  <path d="M5 2h14v20l-7-5.2L5 22z"/>
                </svg>
              {:else}
                <!-- No pigment — outline ribbon, same grammar as the chips -->
                <svg class="submenu-icon" viewBox="0 0 24 24" fill="none" stroke="var(--text-tertiary)" stroke-width="2.2" stroke-linejoin="round" aria-hidden="true">
                  <path d="M6 3h12v18l-6-4.4L6 21z"/>
                </svg>
              {/if}
              <span>{col.name}</span>
            </button>
          {/each}
          {#if hasCollections}
            <hr class="context-divider" />
          {/if}
          <button class="context-item" data-mi="item" role="menuitem" on:click={onAddToNewCollection}>
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
        role="menuitem"
        tabindex="-1"
        aria-haspopup="menu"
        aria-expanded={openSubmenu === 'remove'}
        on:mouseenter={() => { openSubmenu = 'remove'; }}
        on:mouseleave={() => { openSubmenu = null; }}
      >
        <span>Remove from collection&hellip;</span>
        <span class="submenu-caret">&#9656;</span>
        {#if openSubmenu === 'remove'}
          <div class="submenu" role="menu">
            {#each removableCollections as name}
              <button
                class="context-item"
                data-mi="item"
                role="menuitem"
                on:click={() => onRemoveFromCollection(name)}
              >
                {#if collectionColorByName.get(name)}
                  <!-- Bookmark ribbon — the collection keeps its pigment -->
                  <svg class="submenu-icon" viewBox="0 0 24 24" fill={collectionColorByName.get(name)} aria-hidden="true">
                    <path d="M5 2h14v20l-7-5.2L5 22z"/>
                  </svg>
                {:else}
                  <svg class="submenu-icon" viewBox="0 0 24 24" fill="none" stroke="var(--text-tertiary)" stroke-width="2.2" stroke-linejoin="round" aria-hidden="true">
                    <path d="M6 3h12v18l-6-4.4L6 21z"/>
                  </svg>
                {/if}
                <span>{name}</span>
              </button>
            {/each}
          </div>
        {/if}
      </div>
    {/if}
  {/if}

  <!-- Hide is the visibility verb for what scope can't speak about:
       indexed files get M instead (hide is display-only and would
       leave them searchable but invisible). Unhide always stays
       available so nothing strands. -->
  {#if !inheritedHidden && (item.is_dir || directlyHidden || !isIndexed)}
    <hr class="context-divider" />
    <button class="context-item" data-mi="item" role="menuitem" data-chord={matchKey('tree.hide')} on:click={onToggleHidden}>
      {directlyHidden ? 'Unhide' : 'Hide'} {item.is_dir ? 'folder' : 'file'}
      <span class="menu-chord">{chord('tree.hide')}</span>
    </button>
  {/if}

  <hr class="context-divider" />
  <button class="context-item" data-mi="item" role="menuitem" data-chord={matchKey('tree.rename')} on:click={onRename}>
    Rename {item.is_dir ? 'folder' : 'file'}
    <span class="menu-chord">{chord('tree.rename')}</span>
  </button>
  <button class="context-item danger" data-mi="item" role="menuitem" on:click={onDelete}>Delete {item.is_dir ? 'folder' : 'file'}</button>
</div>

<style>
  .context-menu {
    position: fixed;
    z-index: 200;
    background: var(--bg-focused);
    border: 1px solid var(--bg-category);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-dropdown);
    min-width: 200px;
    padding: 0.15rem 0;
  }
  .context-item {
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
    margin-left: auto;
  }
  .submenu-icon {
    width: 11px;
    height: 11px;
    flex-shrink: 0;
  }
  .submenu-tag {
    font-weight: 600;
    color: var(--text-accent);
    white-space: nowrap;
  }
  .submenu {
    position: absolute;
    left: 100%;
    top: -0.15rem;
    background: var(--bg-focused);
    border: 1px solid var(--bg-category);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-dropdown);
    min-width: 180px;
    max-height: 320px;
    overflow-y: auto;
    padding: 0.15rem 0;
    z-index: 201;
  }
</style>
