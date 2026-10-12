<script lang="ts">
  import { afterUpdate, onMount } from 'svelte';
  import type { FileItem, CollectionInfo, KnownGameSystem } from './types';
  import { menuMemberState, type MemberState } from './collectionMembership';
  import { chord, matchKey, eventMatchKey, isBareKeyChord, keyShortcut } from '../shell/keybindings';
  import { claimMenuSlot, releaseMenuSlot } from '../shell/menuSlot';
  import { clampToViewport } from '../ui/menuGeometry';
  import { CARET_RIGHT, GEM } from '../ui/iconPaths';
  import { hoverLive } from '../ui/inputModality';
  import SystemTagRows from './SystemTagRows.svelte';
  import type { SendTargets } from './sendToCommand';

  type Submenu = 'collection' | 'tag' | 'command';

  export let x: number;
  export let y: number;
  export let item: FileItem;
  export let isIndexed: boolean = false;
  export let collections: Record<string, CollectionInfo> = {};
  // The two halves of the Collection submenu's tri-state: "holds any of the
  // target's files" and "holds all of them". They agree on a file and can
  // disagree on a folder, which is what makes a row read half-lit.
  export let containingCollections: string[] = [];
  export let fullyContainingCollections: string[] = [];
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
  // Rename renders an inline input on a browse-view row; opened from a
  // search result no row can host it, so the item is withheld rather
  // than left to silently no-op.
  export let canRename: boolean = true;
  // Optional initial submenu to open on mount (used by the C tree-row chord
  // in PR 2 of chunk c — for now the prop just exists so callers can land
  // a row directly in the Collection submenu without a follow-up keystroke).
  export let initialSubmenu: 'collection' | 'tag' | null = null;
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
  // A search hit rather than a file row: where Command can keep it (the
  // campaign open there and its tracks), 'loading' while Rust is asked.
  // Null on a file row, which has no Send to Command.
  export let sendTargets: SendTargets | 'loading' | null = null;
  // null: onto the campaign's shelf (Command design §3.6).
  export let onSendToCommand: (track: string | null) => void = () => {};
  export let onClose: () => void = () => {};

  let menuEl: HTMLDivElement;
  let openSubmenu: Submenu | null = initialSubmenu;
  // -1 means "no cursor yet" — stays that way until the pointer lands on a
  // row or the keyboard moves.
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
  // there, and shrink max-height to fit. Generic across Collection/Tag.
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

    // --submenu-room reports the space on the chosen side; the stylesheet
    // takes the smaller of it and --menu-max-height, so the scroll ceiling
    // stays declared in one place.
    if (spaceAbove > spaceBelow) {
      submenu.style.top = 'auto';
      submenu.style.bottom = '-0.15rem';
      submenu.style.setProperty('--submenu-room', `${Math.max(120, spaceAbove)}px`);
    } else {
      submenu.style.top = '-0.15rem';
      submenu.style.bottom = 'auto';
      submenu.style.setProperty('--submenu-room', `${Math.max(120, spaceBelow)}px`);
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

  // The page mounts this component to open the menu and unmounts it to close,
  // so holding the one-menu-at-a-time slot is a lifetime affair. Wrapped
  // rather than passing `onClose` itself so the slot keeps one stable
  // reference even if the prop is reassigned.
  const closeSelf = () => onClose();

  onMount(() => {
    clampMenuToViewport();
    positioned = true;
    refreshItemsAndFocus({ initial: true });
    claimMenuSlot(closeSelf);
    return () => releaseMenuSlot(closeSelf);
  });
  afterUpdate(() => refreshItemsAndFocus());

  // One cursor, two hands, as in a native menu. Hover and .kb-focused share
  // a fill here, so a hover that kept its own row read as a second
  // selection. A real move over a row puts the cursor there and opens or
  // closes submenus as it goes; $hoverLive filters out the moves WebKit
  // fakes when → opens a submenu under a resting pointer. Off a row (a
  // divider, the padding, outside the menu) the cursor stays put.
  function handlePointerMove(event: PointerEvent) {
    if (!$hoverLive) return;
    const row = (event.target as Element).closest('[data-mi]') as HTMLElement | null;
    if (!row) return;
    const subIdx = submenuItems.indexOf(row);
    if (subIdx >= 0) {
      focusedSubmenuIdx = subIdx;
    } else {
      const idx = mainItems.indexOf(row);
      if (idx < 0) return;
      focusedIdx = idx;
      focusedSubmenuIdx = null;
      openSubmenu = row.dataset.mi === 'submenu-trigger'
        ? (row.dataset.submenu as Submenu)
        : null;
    }
    refreshItemsAndFocus();
  }

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
      else       { focusedIdx = Math.min(mainItems.length - 1, focusedIdx + 1); openSubmenu = null; }
      refreshItemsAndFocus();
      return;
    }
    if (isUp) {
      event.preventDefault();
      if (inSub) focusedSubmenuIdx = Math.max(0, (focusedSubmenuIdx ?? 0) - 1);
      else       { focusedIdx = Math.max(0, focusedIdx - 1); openSubmenu = null; }
      refreshItemsAndFocus();
      return;
    }
    if (isRight && !inSub) {
      const item = mainItems[focusedIdx];
      const which = item?.dataset.submenu as Submenu | undefined;
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
    // Accelerators: the same chords that work on a focused tree row, live
    // inside the menu. The page's fileActionGate switches them off while a
    // context menu is open (+page.svelte), so nothing else claims them here.
    // Resolved against the rendered rows rather than a second dispatch table,
    // so a chord can only fire when its row actually exists — Solo/Mute only
    // render under canScope, Hide under its own condition.
    if (!inSub && !event.isComposing) {
      const mk = eventMatchKey(event);
      const hit = mk ? mainItems.find((el) => el.dataset.chord === mk) : undefined;
      if (hit) {
        event.preventDefault();
        const sub = hit.dataset.submenu as Submenu | undefined;
        if (hit.dataset.mi === 'submenu-trigger' && sub) {
          // The ArrowRight path gets this for free — the user had already
          // navigated onto the row. A chord jumps straight here, so resolve
          // the cursor too, or ← / Esc lands on no row at all.
          focusedIdx = mainItems.indexOf(hit);
          openSubmenu = sub;
          focusedSubmenuIdx = 0;
        } else {
          hit.click();
        }
        return;
      }
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
    ({ x: clampedX, y: clampedY } = clampToViewport(
      { x, y },
      { width: menuEl.offsetWidth, height: menuEl.offsetHeight },
      { width: window.innerWidth, height: window.innerHeight },
    ));
  }

  // Archived collections are shelved and inert — the submenu never offers them.
  // Row order is the IPC's, alphabetical by name since CollectionsResult became
  // a BTreeMap. Deliberately NOT the panel's collectionsSortKey: a menu you
  // scan for one name wants A–Z, whatever order the panel is dragged into.
  $: activeCollections = Object.values(collections).filter((c) => !c.archived);
  $: containingSet = new Set(containingCollections);
  $: fullyContainingSet = new Set(fullyContainingCollections);
  $: hasCollections = activeCollections.length > 0;

  // Known systems are the reason to open the submenu; existing tags are a
  // reason of their own. A file tagged with a system since disabled in
  // Settings has no rows to toggle and still needs "Clear tags" — without the
  // second clause the submenu hides on exactly the file that needs it, while
  // the tree row's own badge keeps offering it.
  $: canTag = !item.is_dir && isIndexed && (knownSystems.length > 0 || currentTags.length > 0);

  // One row, both verbs. Only a collection that already holds everything has
  // nothing left to add, so that's the only state that removes; a half-lit
  // folder tops up instead, which is what the old Add submenu offered it.
  function toggleCollection(name: string, state: MemberState) {
    if (state === 'all') onRemoveFromCollection(name);
    else onAddToCollection(name);
  }

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
  class:hover-dark={!$hoverLive}
  bind:this={menuEl}
  style="left: {clampedX}px; top: {clampedY}px; visibility: {positioned ? 'visible' : 'hidden'}"
  on:pointermove={handlePointerMove}
  on:click|stopPropagation
  on:mousedown|stopPropagation
>
  {#if !item.is_dir}
    <button class="menu-row" data-mi="item" role="menuitem" data-chord={matchKey('tree.open')} aria-keyshortcuts={keyShortcut('tree.open')} on:click={onOpen}>
      Open file
      <span class="menu-chord" class:bare={isBareKeyChord('tree.open')} aria-hidden="true">{chord('tree.open')}</span>
    </button>
  {/if}
  <!-- Reveal shows its chord but does not claim it: ⌥⌘R carries a modifier
       eventMatchKey deliberately rejects, so it isn't dispatchable from an open
       menu. Display-only, like the Collections rows — no data-chord, and no
       aria-keyshortcuts promising something this row won't honour. -->
  <button class="menu-row" data-mi="item" role="menuitem" on:click={onReveal}>
    Reveal in folder
    <span class="menu-chord" class:bare={isBareKeyChord('tree.openExternal')} aria-hidden="true">{chord('tree.openExternal')}</span>
  </button>
  <!-- Get info rides with the other two ways of looking at the file; its
       sibling Re-index is an action and sits down with Rename. -->
  {#if !item.is_dir && isIndexed}
    <button class="menu-row" data-mi="item" role="menuitem" data-chord={matchKey('info.show')} aria-keyshortcuts={keyShortcut('info.show')} on:click={onShowStats}>
      Get info
      <span class="menu-chord" class:bare={isBareKeyChord('info.show')} aria-hidden="true">{chord('info.show')}</span>
    </button>
  {/if}
  <!-- The hit, kept in Command: a crossing to the other tool, so it sits
       apart from what this menu does to the file. -->
  {#if sendTargets !== null}
    <hr class="menu-divider" />
    <div
      class="menu-row submenu-trigger"
      class:open={openSubmenu === 'command'}
      data-mi="submenu-trigger"
      data-submenu="command"
      role="menuitem"
      tabindex="-1"
      aria-haspopup="menu"
      aria-expanded={openSubmenu === 'command'}
    >
      <span>Send to Command</span>
      <svg class="caret submenu-caret" viewBox="96 64 512 512" fill="currentColor" aria-hidden="true"><path d={CARET_RIGHT}/></svg>
      {#if openSubmenu === 'command'}
        <div class="submenu" role="menu">
          {#if sendTargets === 'loading'}
            <span class="submenu-note">…</span>
          {:else if !sendTargets.campaign}
            <span class="submenu-note">Open a campaign in Command first</span>
          {:else}
            <span class="submenu-note micro-label" title={sendTargets.campaign}>{sendTargets.campaign}</span>
            <!-- The shelf first: where a clipping goes until it has a track. -->
            <button class="menu-row" data-mi="item" role="menuitem" on:click={() => onSendToCommand(null)}>
              <span class="submenu-name">Shelf</span>
            </button>
            {#if sendTargets.tracks.length}<hr class="menu-divider" />{/if}
            {#each sendTargets.tracks as track (track)}
              <button class="menu-row" data-mi="item" role="menuitem" on:click={() => onSendToCommand(track)}>
                <span class="submenu-name" title={track}>{track}</span>
              </button>
            {/each}
          {/if}
        </div>
      {/if}
    </div>
  {/if}
  {#if canScope}
    <hr class="menu-divider" />
    <button class="menu-row" data-mi="item" role="menuitem" data-chord={matchKey('tree.solo')} aria-keyshortcuts={keyShortcut('tree.solo')} on:click={onToggleSolo}>
      {isSoloed ? 'Stop soloing' : 'Solo'} {item.is_dir ? 'folder' : 'file'}
      <span class="menu-chord" class:bare={isBareKeyChord('tree.solo')} aria-hidden="true">{chord('tree.solo')}</span>
    </button>
    <button class="menu-row" data-mi="item" role="menuitem" data-chord={matchKey('tree.mute')} aria-keyshortcuts={keyShortcut('tree.mute')} on:click={onToggleMute}>
      {isMuted ? 'Unmute' : 'Mute'} {item.is_dir ? 'folder' : 'file'}
      <span class="menu-chord" class:bare={isBareKeyChord('tree.mute')} aria-hidden="true">{chord('tree.mute')}</span>
    </button>
  {/if}

  <!-- The two filing axes share a section: a collection is curation, a game
       system is what the book is. Both are submenus of togglable rows. -->
  {#if canAddToCollection || canTag}
    <hr class="menu-divider" />
  {/if}
  {#if canAddToCollection}
    <div
      class="menu-row submenu-trigger"
      class:open={openSubmenu === 'collection'}
      data-mi="submenu-trigger"
      data-submenu="collection"
      data-chord={matchKey('tree.addToCollection')} aria-keyshortcuts={keyShortcut('tree.addToCollection')}
      role="menuitem"
      tabindex="-1"
      aria-haspopup="menu"
      aria-expanded={openSubmenu === 'collection'}
    >
      <span>Collection</span>
      <span class="menu-chord" class:bare={isBareKeyChord('tree.addToCollection')} aria-hidden="true">{chord('tree.addToCollection')}</span>
      <svg class="caret submenu-caret" viewBox="96 64 512 512" fill="currentColor" aria-hidden="true"><path d={CARET_RIGHT}/></svg>
      {#if openSubmenu === 'collection'}
        <div class="submenu" role="menu">
          {#each activeCollections as col}
            {@const state = menuMemberState(col.name, containingSet, fullyContainingSet)}
            <button
              class="menu-row"
              data-mi="item"
              role="menuitemcheckbox"
              aria-checked={state === 'some' ? 'mixed' : state === 'all'}
              on:click={() => toggleCollection(col.name, state)}
            >
              <span class="menu-pip" class:on={state === 'all'} class:partial={state === 'some'} aria-hidden="true"></span>
              {#if col.color}
                <!-- Gem — the collection keeps its pigment -->
                <svg class="submenu-icon" viewBox="0 0 24 24" fill="none" stroke={col.color} stroke-width="2.2" stroke-linejoin="round" aria-hidden="true">
                  <path d={GEM}/>
                </svg>
              {:else}
                <!-- No pigment — outline gem, same grammar as the chips -->
                <svg class="submenu-icon" viewBox="0 0 24 24" fill="none" stroke="var(--text-tertiary)" stroke-width="2.2" stroke-linejoin="round" aria-hidden="true">
                  <path d={GEM}/>
                </svg>
              {/if}
              <span class="submenu-name" title={col.name}>{col.name}</span>
            </button>
          {/each}
          {#if hasCollections}
            <hr class="menu-divider" />
          {/if}
          <button class="menu-row" data-mi="item" role="menuitem" on:click={onAddToNewCollection}>
            + New collection
          </button>
        </div>
      {/if}
    </div>
  {/if}
  {#if canTag}
    <div
      class="menu-row submenu-trigger"
      class:open={openSubmenu === 'tag'}
      data-mi="submenu-trigger"
      data-submenu="tag"
      role="menuitem"
      tabindex="-1"
      aria-haspopup="menu"
      aria-expanded={openSubmenu === 'tag'}
    >
      <span>Game system</span>
      <svg class="caret submenu-caret" viewBox="96 64 512 512" fill="currentColor" aria-hidden="true"><path d={CARET_RIGHT}/></svg>
      {#if openSubmenu === 'tag'}
        <div class="submenu" role="menu">
          <SystemTagRows
            {knownSystems}
            tags={currentTags}
            onToggle={toggleGameSystem}
            onClear={clearGameSystems}
          />
        </div>
      {/if}
    </div>
  {/if}

  <!-- Hide is the visibility verb for what scope can't speak about:
       indexed files get M instead (hide is display-only and would
       leave them searchable but invisible). Unhide always stays
       available so nothing strands. -->
  {#if !inheritedHidden && (item.is_dir || directlyHidden || !isIndexed)}
    <hr class="menu-divider" />
    <button class="menu-row" data-mi="item" role="menuitem" data-chord={matchKey('tree.hide')} aria-keyshortcuts={keyShortcut('tree.hide')} on:click={onToggleHidden}>
      {directlyHidden ? 'Unhide' : 'Hide'} {item.is_dir ? 'folder' : 'file'}
      <span class="menu-chord" class:bare={isBareKeyChord('tree.hide')} aria-hidden="true">{chord('tree.hide')}</span>
    </button>
  {/if}

  {#if canRename || (!item.is_dir && isIndexed)}
    <hr class="menu-divider" />
  {/if}
  {#if canRename}
    <button class="menu-row" data-mi="item" role="menuitem" data-chord={matchKey('tree.rename')} aria-keyshortcuts={keyShortcut('tree.rename')} on:click={onRename}>
      Rename {item.is_dir ? 'folder' : 'file'}
      <span class="menu-chord" class:bare={isBareKeyChord('tree.rename')} aria-hidden="true">{chord('tree.rename')}</span>
    </button>
  {/if}
  {#if !item.is_dir && isIndexed}
    <button class="menu-row" data-mi="item" role="menuitem" on:click={onReindex}>Re-index file</button>
  {/if}

  <!-- Delete stands alone: a divider between it and the other write actions
       is the only thing between a misaimed click and the wrong row. -->
  <hr class="menu-divider" />
  <!-- Display-only, like Reveal above: ⌘⌫ is a named key eventMatchKey can't
       resolve, so the row hints the chord without claiming it. -->
  <button class="menu-row danger" data-mi="item" role="menuitem" on:click={onDelete}>
    Delete {item.is_dir ? 'folder' : 'file'}
    <span class="menu-chord" class:bare={isBareKeyChord('tree.delete')} aria-hidden="true">{chord('tree.delete')}</span>
  </button>
</div>

<style>
  .context-menu {
    position: fixed;
    z-index: 200;
    background: var(--bg-container);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-dropdown);
    min-width: var(--menu-width);
    max-width: var(--menu-max-width);
    padding: 0.15rem 0;
  }
  /* Rows and dividers are .menu-row / .menu-divider in app.css — shared
     anatomy, so the tag rows this menu now delegates to SystemTagRows land
     under the same rule as the ones it renders itself. */
  .submenu-trigger {
    position: relative;
    display: flex;
    align-items: center;
    user-select: none;
  }
  .context-menu:not(.hover-dark) .submenu-trigger:hover,
  .submenu-trigger.open {
    background: var(--bg-focused);
  }
  .submenu-caret {
    font-size: 0.7rem;
    opacity: 0.6;
    margin-left: auto;
  }
  /* The chord already claims the row's free space; a second auto margin
     would split it and strand the chord mid-row. */
  .menu-chord + .submenu-caret {
    margin-left: 0;
  }
  .submenu-icon {
    width: 11px;
    height: 11px;
    flex-shrink: 0;
  }
  /* Collection names are user-written and uncapped — they ellipsize against
     --menu-max-width rather than stretching the menu, and carry a title so
     the full name stays recoverable. */
  /* A line in a submenu that isn't a choice: the campaign the tracks
     belong to, or why there are none. */
  .submenu-note {
    display: block;
    padding: 0.2rem 0.6rem;
    font-size: 0.75rem;
    color: var(--text-tertiary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .submenu-name {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .submenu {
    position: absolute;
    left: 100%;
    top: -0.15rem;
    background: var(--bg-container);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-dropdown);
    min-width: var(--submenu-width);
    max-width: var(--menu-max-width);
    /* --submenu-room is measured per open (clampOpenSubmenuToViewport);
       whichever is smaller wins, so the ceiling lives in the token. */
    max-height: min(var(--menu-max-height), var(--submenu-room, 100vh));
    overflow-y: auto;
    padding: 0.15rem 0;
    z-index: 201;
  }
</style>
