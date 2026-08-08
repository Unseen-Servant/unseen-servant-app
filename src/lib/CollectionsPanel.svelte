<script lang="ts">
  import type { CollectionInfo } from './types';
  import ActionButton from './ActionButton.svelte';
  import SystemBadge from './SystemBadge.svelte';
  import { PIGMENTS } from './palette';
  import { tick } from 'svelte';

  export let collections: Record<string, CollectionInfo> = {};
  // Keyboard focus is lifted to +page.svelte so it can mutex against
  // focusedFilePath (only one region claims arrow keys at a time).
  export let focusedName: string | null = null;
  export let onFocusCollection: (name: string | null) => void = () => {};
  export let editingName: string | null = null;
  // Proposed name of an in-progress draft (new collection that hasn't been
  // saved yet). When set, the panel renders a synthetic top row carrying
  // the inline Save/Cancel controls just like an editing row.
  export let draftName: string | null = null;
  // Live count of paths currently selected in the in-progress edit/draft.
  // Shown on the row being edited.
  export let editFileCount: number = 0;
  // Collection transport — names currently playing (armed into the
  // search scope). Several can play at once; while any plays, the
  // stopped rows dim out of scope.
  export let playingNames: Set<string> = new Set();
  // File path → game-system tags, for the badge on expanded file rows.
  export let gameSystemMap: Map<string, string[]> = new Map();
  // Sort state is lifted to +page for per-vault persistence.
  export let sortKey: 'custom' | 'name' | 'size' | 'created' = 'custom';
  export let customOrder: string[] = [];
  export let onEditFiles: (name: string) => void = () => {};
  export let onDelete: (name: string) => void = () => {};
  export let onToggleArchived: (name: string, archived: boolean) => void = () => {};
  export let onCreate: () => void = () => {};
  export let onSaveFiles: () => void = () => {};
  export let onCancelFiles: () => void = () => {};
  export let onDraftRename: (name: string) => void = () => {};
  export let onRename: (name: string, newName: string) => void = () => {};
  export let onSetColor: (name: string, color: string | null) => void = () => {};
  export let onTogglePlay: (name: string) => void = () => {};
  export let onSetSortKey: (key: 'custom' | 'name' | 'size' | 'created') => void = () => {};
  export let onReorder: (order: string[]) => void = () => {};

  const SORT_OPTIONS: { value: typeof sortKey; label: string }[] = [
    { value: 'custom', label: 'Custom order' },
    { value: 'name', label: 'Name' },
    { value: 'size', label: 'File count' },
    { value: 'created', label: 'Recently added' },
  ];
  // Archive is shelving, not deleting: archived rows hide by default and
  // keep pigment, files, and their custom-order slot.
  let showArchived = false;

  let sortMenuOpen = false;
  let sortBtn: HTMLButtonElement;

  // Disclosure state — which collections show their file rows.
  let expandedNames = new Set<string>();

  function toggleExpand(name: string) {
    if (expandedNames.has(name)) expandedNames.delete(name);
    else expandedNames.add(name);
    expandedNames = expandedNames;
  }

  // ------------------------------------------------------------------
  // Inline rename — draft rows (unsaved) and existing rows (F2 or
  // double-click) share the input treatment; drafts rename locally,
  // existing rows commit through the backend via onRename.
  // ------------------------------------------------------------------
  let renamingDraft = false;
  let draftRenameValue = '';
  let renamingName: string | null = null;
  let renameValue = '';

  // Reset rename mode when the draft itself goes away.
  $: if (!draftName) renamingDraft = false;

  // Auto-enter rename mode when a fresh draft appears (matches Finder's
  // "new folder lands you in rename" convention). Tracks the last-seen
  // draft name so renames don't re-trigger this.
  let lastSeenDraft: string | null = null;
  $: {
    if (draftName && !lastSeenDraft) startDraftRename();
    lastSeenDraft = draftName;
  }

  function startDraftRename() {
    if (!draftName) return;
    draftRenameValue = draftName;
    renamingDraft = true;
  }

  function commitDraftRename() {
    const trimmed = draftRenameValue.trim();
    if (trimmed && trimmed !== draftName) onDraftRename(trimmed);
    renamingDraft = false;
  }

  function handleDraftRenameKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter') {
      e.preventDefault();
      commitDraftRename();
      // Plain Enter from the rename input commits AND saves (Finder
      // "type name + Enter creates the folder"). For Cmd/Ctrl+Enter we
      // skip saving here so the global handler in +page.svelte fires
      // exactly once instead of double-firing.
      if (!e.metaKey && !e.ctrlKey) onSaveFiles();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      renamingDraft = false;
    }
  }

  function startRename(name: string) {
    renamingName = name;
    renameValue = name;
  }

  function commitRename() {
    if (renamingName === null) return;
    const trimmed = renameValue.trim();
    if (trimmed && trimmed !== renamingName) onRename(renamingName, trimmed);
    renamingName = null;
  }

  function handleRenameKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter') {
      e.preventDefault();
      commitRename();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      e.stopPropagation();
      renamingName = null;
    }
  }

  function autofocusInput(node: HTMLInputElement) {
    node.focus();
    node.select();
  }

  // ------------------------------------------------------------------
  // Sorting + drag reorder
  // ------------------------------------------------------------------
  $: rows = (() => {
    const list = Object.values(collections);
    const visible = showArchived ? list : list.filter(c => !c.archived);
    if (sortKey === 'name') {
      visible.sort((a, b) => a.name.localeCompare(b.name));
    } else if (sortKey === 'size') {
      visible.sort((a, b) => b.file_count - a.file_count);
    } else if (sortKey === 'created') {
      visible.sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
    } else {
      // Custom order — persisted name array; names it doesn't know yet
      // (created since the last drag) sort after it, alphabetically.
      const idx = new Map(customOrder.map((n, i) => [n, i]));
      visible.sort((a, b) => {
        const ia = idx.has(a.name) ? idx.get(a.name)! : Infinity;
        const ib = idx.has(b.name) ? idx.get(b.name)! : Infinity;
        if (ia !== ib) return ia - ib;
        return a.name.localeCompare(b.name);
      });
    }
    return visible;
  })();

  $: archivedCount = Object.values(collections).filter(c => c.archived).length;
  $: hasNone = Object.keys(collections).length === 0;
  $: canDrag = sortKey === 'custom' && rows.length > 1 && !editingName && !draftName;
  $: anyPlaying = playingNames.size > 0;

  let draggingName: string | null = null;
  // Insertion index into `rows` while dragging (rows.length = after last).
  let dropInsertIndex: number | null = null;

  function handleDragStart(e: DragEvent, name: string) {
    if (!canDrag) {
      e.preventDefault();
      return;
    }
    draggingName = name;
    if (e.dataTransfer) {
      e.dataTransfer.effectAllowed = 'move';
      e.dataTransfer.setData('text/plain', name);
    }
  }

  function handleDragOver(e: DragEvent, index: number) {
    if (draggingName === null) return;
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
    const el = e.currentTarget as HTMLElement;
    const rect = el.getBoundingClientRect();
    dropInsertIndex = e.clientY < rect.top + rect.height / 2 ? index : index + 1;
  }

  function handleDrop(e: DragEvent) {
    e.preventDefault();
    if (draggingName === null || dropInsertIndex === null) return;
    const names = rows.map(r => r.name);
    const from = names.indexOf(draggingName);
    if (from >= 0) {
      const insertAt = dropInsertIndex > from ? dropInsertIndex - 1 : dropInsertIndex;
      names.splice(from, 1);
      names.splice(insertAt, 0, draggingName);
      // Persist the full order: the visible sequence first, then any
      // collections the current view hides (archived), so their slots
      // aren't forgotten.
      const inVisible = new Set(names);
      const rest = Object.values(collections).map(c => c.name).filter(n => !inVisible.has(n));
      onReorder([...names, ...rest]);
    }
    draggingName = null;
    dropInsertIndex = null;
  }

  function handleDragEnd() {
    draggingName = null;
    dropInsertIndex = null;
  }

  // ------------------------------------------------------------------
  // Context menu (right-click a collection row): Rename / Pigment ▸ /
  // Add files… / Archive / Delete. Same visual family as the file
  // tree's ContextMenu, scoped to what a collection can do.
  // ------------------------------------------------------------------
  let ctxMenu: { x: number; y: number; name: string } | null = null;
  let ctxPigmentOpen = false;

  const CTX_WIDTH = 190;
  const CTX_HEIGHT = 200;

  function openContextMenu(e: MouseEvent, name: string) {
    e.preventDefault();
    e.stopPropagation();
    onFocusCollection(name);
    ctxPigmentOpen = false;
    ctxMenu = {
      x: Math.min(e.clientX, window.innerWidth - CTX_WIDTH - 4),
      y: Math.min(e.clientY, window.innerHeight - CTX_HEIGHT - 4),
      name,
    };
  }

  function closeContextMenu() {
    ctxMenu = null;
    ctxPigmentOpen = false;
  }

  // Runs a menu action against the menu's collection, then closes the
  // menu. The action must run BEFORE closing: Svelte 5 re-evaluates the
  // template's `{@const col}` lazily at read time, so an action that
  // reads it after `ctxMenu` is nulled re-derives from the nulled menu
  // and throws (the Archive item read `col?.archived` exactly there).
  function ctxAction(fn: (name: string) => void) {
    if (!ctxMenu) return;
    const name = ctxMenu.name;
    fn(name);
    closeContextMenu();
  }

  // Scroll the focused row into view whenever focus changes.
  $: if (focusedName) scrollFocusedIntoView(focusedName);
  async function scrollFocusedIntoView(name: string) {
    await tick();
    const el = document.querySelector(`[data-cp-row="${CSS.escape(name)}"]`);
    el?.scrollIntoView({ block: 'nearest' });
  }

  function handleWindowKey(event: KeyboardEvent) {
    // The context menu claims Esc before anything else.
    if (ctxMenu && event.key === 'Escape') {
      event.preventDefault();
      closeContextMenu();
      return;
    }
    if (focusedName === null) return;
    // Yield to inline renames, the sort menu, the context menu, and any
    // other popover that may be claiming keys.
    if (renamingDraft || renamingName !== null || sortMenuOpen || ctxMenu) return;
    if (document.querySelector('.dropdown, .context-menu')) return;
    // Yield to any open <dialog> — the browser inerts the page but
    // window-level keydown still bubbles, so we'd otherwise navigate
    // collections behind the modal.
    if (document.querySelector('dialog[open]')) return;
    const target = event.target as HTMLElement | null;
    if (target?.matches('input, textarea, [contenteditable="true"]')) return;

    const meta = event.metaKey || event.ctrlKey;
    const lk = event.key.toLowerCase();
    const bareLetter = !meta && !event.shiftKey && !event.altKey;
    const isDown = event.key === 'ArrowDown' || (bareLetter && lk === 'j');
    const isUp   = event.key === 'ArrowUp'   || (bareLetter && lk === 'k');

    const idx = rows.findIndex((r) => r.name === focusedName);

    if (isDown) {
      event.preventDefault();
      const next = idx < 0 ? 0 : Math.min(rows.length - 1, idx + 1);
      if (rows[next]) onFocusCollection(rows[next].name);
      return;
    }
    if (isUp) {
      event.preventDefault();
      const prev = idx < 0 ? rows.length - 1 : Math.max(0, idx - 1);
      if (rows[prev]) onFocusCollection(rows[prev].name);
      return;
    }
    if (event.key === 'Home' && !meta && rows[0]) {
      event.preventDefault();
      onFocusCollection(rows[0].name);
      return;
    }
    if (event.key === 'End' && !meta && rows.length > 0) {
      event.preventDefault();
      onFocusCollection(rows[rows.length - 1].name);
      return;
    }

    // Esc/Enter on a focused draft / row-being-edited handled before the
    // idx-out-of-range early return: a fresh draft sits outside `rows`
    // (it's rendered separately above the list) so idx is -1 for it.
    const isOnDraft = draftName !== null && focusedName === draftName;
    const isOnEditing = editingName !== null && focusedName === editingName;

    if (event.key === 'Escape') {
      event.preventDefault();
      if (isOnDraft || isOnEditing) onCancelFiles();
      else onFocusCollection(null);
      return;
    }
    if (event.key === 'Enter' && (isOnDraft || isOnEditing)) {
      event.preventDefault();
      onSaveFiles();
      return;
    }

    if (idx < 0) return;
    const col = rows[idx];

    if (event.key === 'F2') {
      event.preventDefault();
      startRename(col.name);
      return;
    }
    if (bareLetter && (event.key === 'ArrowRight' || lk === 'l') && !expandedNames.has(col.name)) {
      event.preventDefault();
      toggleExpand(col.name);
      return;
    }
    if (bareLetter && (event.key === 'ArrowLeft' || lk === 'h') && expandedNames.has(col.name)) {
      event.preventDefault();
      toggleExpand(col.name);
      return;
    }
    if (bareLetter) {
      if (lk === 'f') { event.preventDefault(); onEditFiles(col.name); return; }
      // P or Space toggle the transport — Space is the DAW play/stop
      // convention, shared with file rows (where it opens). A shelved
      // track has no transport, so both are inert until unarchived
      // (Space still swallowed so the list doesn't scroll).
      if (lk === 'p' || lk === ' ') {
        event.preventDefault();
        if (!col.archived) onTogglePlay(col.name);
        return;
      }
      if (lk === 'a') { event.preventDefault(); onToggleArchived(col.name, !col.archived); return; }
    }
  }

  function toggleSortMenu() {
    sortMenuOpen = !sortMenuOpen;
  }

  function pickSort(value: typeof sortKey) {
    onSetSortKey(value);
    sortMenuOpen = false;
  }

  function handleWindowClick(event: MouseEvent) {
    if (ctxMenu) {
      closeContextMenu();
    }
    if (!sortMenuOpen) return;
    const target = event.target as Node;
    if (sortBtn && (sortBtn === target || sortBtn.contains(target))) return;
    sortMenuOpen = false;
  }

  // Click anywhere in the panel chrome (not on a specific row) claims the
  // collections region — so arrow keys move here next, even when the user
  // hasn't picked a row yet. Row clicks set their own focus and we let
  // those win by skipping when the target is inside a [data-cp-row].
  function handlePanelMousedown(event: MouseEvent) {
    if (focusedName !== null) return;
    const target = event.target as HTMLElement | null;
    if (target?.closest('[data-cp-row]')) return;
    if (rows.length > 0) onFocusCollection(rows[0].name);
  }

  // Exposed for the page-level Cmd+Alt+← jump. Restores `preferred` if
  // it's still in the visible list (matches user expectation: "take me
  // back to where I was"); otherwise falls back to the first row, or
  // the draft when one is being created.
  export function claim(preferred: string | null) {
    if (draftName !== null) {
      onFocusCollection(draftName);
      return;
    }
    if (preferred && rows.some((r) => r.name === preferred)) {
      onFocusCollection(preferred);
      return;
    }
    if (rows.length > 0) onFocusCollection(rows[0].name);
  }

  function basename(path: string): string {
    return path.split('/').pop() ?? path;
  }

  // Expanded file rows: name + first system badge, alphabetical.
  function childFiles(col: CollectionInfo): { path: string; base: string; tag: string | null }[] {
    return col.file_paths
      .map((p) => ({ path: p, base: basename(p), tag: gameSystemMap.get(p)?.[0] ?? null }))
      .sort((a, b) => a.base.localeCompare(b.base));
  }
</script>

<svelte:window on:click={handleWindowClick} on:keydown={handleWindowKey} />

<!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
<aside class="panel" on:mousedown={handlePanelMousedown}>
  <header class="panel-head">
    <span class="panel-title">Collections</span>
    <div class="sort-wrapper">
      <button
        class="sort-btn"
        class:on={sortMenuOpen}
        on:click|stopPropagation={toggleSortMenu}
        bind:this={sortBtn}
        title="Sort collections"
        aria-label="Sort collections"
        aria-haspopup="menu"
        aria-expanded={sortMenuOpen}
      >
        <!-- Arrow + shrinking lines — sort -->
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon">
          <path d="M11 5h10M11 9h7M11 13h4"/>
          <path d="M5 5v14M5 19l-2.5-3M5 19l2.5-3"/>
        </svg>
      </button>
      {#if sortMenuOpen}
        <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
        <div class="sort-menu" on:click|stopPropagation>
          {#each SORT_OPTIONS as opt}
            <button
              class="sort-item"
              on:click={() => pickSort(opt.value)}
            >
              <span class="check">{sortKey === opt.value ? '✓' : ''}</span>
              <span>{opt.label}</span>
            </button>
          {/each}
          {#if archivedCount > 0}
            <hr class="menu-divider" />
            <label class="sort-toggle">
              <span>Show archived</span>
              <input class="app-checkbox" type="checkbox" bind:checked={showArchived} />
            </label>
          {/if}
        </div>
      {/if}
    </div>
  </header>

  {#if hasNone && !draftName}
    <div class="empty">
      <span class="empty-label">No collections yet</span>
    </div>
  {:else if rows.length === 0 && !draftName}
    <div class="empty">
      <span class="empty-label">All archived</span>
    </div>
  {/if}

  <ul class="rows">
    {#if draftName}
      <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-noninteractive-element-interactions -->
      <li
        class="row-container editing draft"
        class:kb-focused={focusedName === draftName}
        title="New collection (unsaved) — click name to rename"
        data-cp-row={draftName}
      >
        <span class="arrow-spacer" aria-hidden="true"></span>
        <!-- Outline bookmark — no pigment chosen yet -->
        <svg class="bkm" style="color: var(--text-tertiary)" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round" aria-hidden="true">
          <path d="M6 3h12v18l-6-4.4L6 21z"/>
        </svg>
        {#if renamingDraft}
          <input
            class="rename-input"
            bind:value={draftRenameValue}
            on:keydown={handleDraftRenameKeydown}
            on:blur={commitDraftRename}
            use:autofocusInput
          />
        {:else}
          <button class="row-name draft-name" on:click={startDraftRename} title="Rename">{draftName}</button>
        {/if}
        <span class="editing-count" title="{editFileCount} file{editFileCount === 1 ? '' : 's'}">{editFileCount}</span>
        <div class="row-actions">
          <ActionButton kind="discard" compact title="Discard draft" onClick={onCancelFiles} />
          <ActionButton kind="confirm" compact title="Save" onClick={onSaveFiles} />
        </div>
      </li>
    {/if}
    {#each rows as col, i (col.name)}
      {@const isEditing = editingName === col.name}
      {@const isExpanded = expandedNames.has(col.name)}
      {@const playing = playingNames.has(col.name)}
      {@const isRenamingRow = renamingName === col.name}
      <li class="item">
        <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-noninteractive-element-interactions a11y-no-static-element-interactions -->
        <div
          class="row-container"
          class:editing={isEditing}
          class:archived={col.archived}
          class:kb-focused={focusedName === col.name}
          class:playing
          class:dimmed={anyPlaying && !playing && !col.archived}
          class:dragging={draggingName === col.name}
          class:drop-before={dropInsertIndex === i}
          class:drop-after={dropInsertIndex === i + 1 && i === rows.length - 1}
          title={col.description || col.name}
          data-cp-row={col.name}
          draggable={canDrag && !isRenamingRow}
          on:dragstart={(e) => handleDragStart(e, col.name)}
          on:dragover={(e) => handleDragOver(e, i)}
          on:drop={handleDrop}
          on:dragend={handleDragEnd}
          on:click={() => { if (!isEditing && !isRenamingRow) onFocusCollection(col.name); }}
          on:dblclick={() => { if (!isEditing && !isRenamingRow) startRename(col.name); }}
          on:contextmenu={(e) => { if (!isEditing) openContextMenu(e, col.name); }}
        >
          {#if sortKey === 'custom'}
            <span class="grip" title="Drag to reorder" aria-hidden="true">⠿</span>
          {/if}
          <button
            class="arrow"
            on:click|stopPropagation={() => toggleExpand(col.name)}
            aria-label={isExpanded ? 'Collapse' : 'Expand'}
            aria-expanded={isExpanded}
          >{isExpanded ? '▼' : '▶'}</button>
          {#if col.color}
            <!-- Pigment bookmark — this is where the color↔collection
                 mapping is taught; the same ribbon reappears in scope
                 chips and search-result index cells. -->
            <svg class="bkm" style={`color: ${col.color}`} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <path d="M5 2h14v20l-7-5.2L5 22z"/>
            </svg>
          {:else}
            <!-- Outline ribbon — uncolored, same grammar as the untagged die -->
            <svg class="bkm" style="color: var(--text-tertiary)" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round" aria-hidden="true">
              <path d="M6 3h12v18l-6-4.4L6 21z"/>
            </svg>
          {/if}
          {#if isRenamingRow}
            <input
              class="rename-input"
              bind:value={renameValue}
              on:keydown={handleRenameKeydown}
              on:blur={commitRename}
              on:click|stopPropagation
              use:autofocusInput
            />
          {:else}
            <span class="row-name">{col.name}</span>
          {/if}
          {#if isEditing}
            <span class="editing-count" title="{editFileCount} file{editFileCount === 1 ? '' : 's'}">{editFileCount}</span>
            <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
            <div class="row-actions" on:click|stopPropagation>
              <ActionButton kind="discard" compact title="Cancel" onClick={onCancelFiles} />
              <ActionButton kind="confirm" compact title="Save" onClick={onSaveFiles} />
            </div>
          {:else if !isRenamingRow && !col.archived}
            <!-- Archived rows carry no transport — unarchive to play. -->
            <span class="tr" class:engaged={playing}>
              <button
                type="button"
                class="tr-btn"
                class:playing
                on:click|stopPropagation={() => onTogglePlay(col.name)}
                aria-pressed={playing}
                title={playing ? `Stop ${col.name} (P)` : `Play ${col.name} (P)`}
              >
                {#if playing}
                  <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M5 5h14v14H5z"/></svg>
                {:else}
                  <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M6 4.2v15.6L20 12z"/></svg>
                {/if}
              </button>
            </span>
          {/if}
        </div>
        {#if isExpanded}
          {#each childFiles(col) as f (f.path)}
            <div class="child-row" class:washed={playing} class:dimmed={anyPlaying && !playing} title={f.path}>
              <span class="indent" aria-hidden="true"></span>
              <span class="child-name">{f.base}</span>
              {#if f.tag}
                <SystemBadge tag={f.tag} />
              {/if}
            </div>
          {/each}
          {#if col.file_paths.length === 0}
            <div class="child-row child-empty" class:washed={playing}>
              <span class="indent" aria-hidden="true"></span>
              <span class="child-name">No files yet</span>
            </div>
          {/if}
        {/if}
      </li>
    {/each}
  </ul>
  {#if !draftName}
    <!-- Outside the scroll container: trails the last row while the
         list is short, stays visible once the list overflows. -->
    <button class="add-coll" on:click={onCreate}>+ collection</button>
  {/if}
</aside>

{#if ctxMenu}
  {@const col = collections[ctxMenu.name]}
  <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
  <div
    class="context-menu"
    style={`left: ${ctxMenu.x}px; top: ${ctxMenu.y}px`}
    on:click|stopPropagation
    on:contextmenu|preventDefault|stopPropagation
  >
    <button class="context-item" on:click={() => ctxAction(startRename)}>Rename</button>
    <div
      class="context-item has-submenu"
      class:open={ctxPigmentOpen}
      on:mouseenter={() => { ctxPigmentOpen = true; }}
      on:click={() => { ctxPigmentOpen = !ctxPigmentOpen; }}
      role="menuitem"
      tabindex="-1"
      aria-haspopup="menu"
      aria-expanded={ctxPigmentOpen}
    >
      <span>Pigment&hellip;</span>
      <span class="submenu-caret" aria-hidden="true">&#9656;</span>
      {#if ctxPigmentOpen}
        <div class="submenu">
          {#each PIGMENTS as pig (pig.hex)}
            <button
              class="context-item"
              on:click|stopPropagation={() => ctxAction((name) => onSetColor(name, pig.hex))}
            >
              <span class="pig-check">{col?.color === pig.hex ? '✓' : ''}</span>
              <svg class="bkm" style={`color: ${pig.hex}`} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <path d="M5 2h14v20l-7-5.2L5 22z"/>
              </svg>
              <span>{pig.name}</span>
            </button>
          {/each}
          <hr class="menu-divider" />
          <button
            class="context-item"
            on:click|stopPropagation={() => ctxAction((name) => onSetColor(name, null))}
          >
            <span class="pig-check">{!col?.color ? '✓' : ''}</span>
            <svg class="bkm" style="color: var(--text-tertiary)" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round" aria-hidden="true">
              <path d="M6 3h12v18l-6-4.4L6 21z"/>
            </svg>
            <span>None</span>
          </button>
        </div>
      {/if}
    </div>
    <hr class="menu-divider" />
    <button class="context-item" on:click={() => ctxAction(onEditFiles)}>Add files&hellip;</button>
    <button class="context-item" on:click={() => ctxAction((name) => onToggleArchived(name, !col?.archived))}>
      {col?.archived ? 'Unarchive' : 'Archive'}
    </button>
    <hr class="menu-divider" />
    <button class="context-item danger" on:click={() => ctxAction(onDelete)}>Delete collection</button>
  </div>
{/if}

<style>
  .panel {
    display: flex;
    flex-direction: column;
    min-height: 0;
    background: var(--bg-app);
    font-family: var(--font-body);
    overflow: hidden;
  }
  .panel-head {
    display: flex;
    align-items: baseline;
    gap: 0.5rem;
    padding: 0.6rem 0.75rem 0.4rem;
    flex-shrink: 0;
  }
  .panel-title {
    font-family: var(--font-display);
    font-size: 0.8rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--text-accent);
    flex: 1;
  }

  .sort-wrapper {
    position: relative;
    align-self: center;
  }
  .sort-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 22px;
    height: 22px;
    padding: 0;
    background: none;
    border: none;
    border-radius: var(--radius-sm);
    color: var(--text-secondary);
    cursor: pointer;
    transition: all var(--transition-fast);
  }
  .sort-btn:hover {
    color: var(--text-primary);
    background: var(--bg-container);
  }
  .sort-btn.on {
    color: var(--text-accent);
  }
  .sort-btn .icon {
    width: 13px;
    height: 13px;
    display: block;
  }
  .sort-menu {
    position: absolute;
    right: 0;
    top: calc(100% + 4px);
    background: var(--bg-focused);
    border: 1px solid var(--bg-category);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-dropdown);
    padding: 0.15rem 0;
    min-width: 150px;
    z-index: 50;
  }
  .sort-item {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    width: 100%;
    padding: 0.25rem 0.6rem;
    background: none;
    border: none;
    text-align: left;
    font-family: var(--font-body);
    font-size: 0.8rem;
    color: var(--text-primary);
    cursor: pointer;
    transition: background var(--transition-fast);
  }
  .sort-item:hover {
    background: var(--bg-category);
  }
  .check,
  .pig-check {
    width: 0.9rem;
    color: var(--text-accent);
    font-weight: 700;
    flex-shrink: 0;
  }
  .menu-divider {
    margin: 0.15rem 0;
    border: none;
    border-top: 1px solid var(--bg-category);
  }
  .sort-toggle {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.6rem;
    padding: 0.35rem 0.6rem;
    font-size: 0.8rem;
    color: var(--text-primary);
    cursor: pointer;
    transition: background var(--transition-fast);
  }
  .sort-toggle:hover {
    background: var(--bg-category);
  }
  .sort-toggle input {
    cursor: pointer;
    margin: 0;
  }

  .rows {
    list-style: none;
    margin: 0;
    padding: 0;
    overflow-y: auto;
    /* Content-sized, shrinkable: the list only scrolls once it runs out
       of room, and the "+ collection" row below it never leaves view. */
    flex: 0 1 auto;
    min-height: 0;
  }
  .item {
    -webkit-user-select: none;
    user-select: none;
  }

  .row-container {
    display: flex;
    align-items: center;
    gap: 0.3rem;
    padding: 0.22rem 0.4rem 0.22rem 0.75rem;
    /* Reserved for the solo rule so engaging S doesn't shift layout. */
    border-left: 3px solid transparent;
    cursor: pointer;
    transition: background var(--transition-fast);
    min-height: 28px;
  }
  .row-container:hover,
  .row-container.kb-focused {
    background: var(--bg-focused);
  }
  /* Playing — armed into the search scope: parchment wash + purple rule,
     the same "this track is in the mix" grammar as the tree's solo. */
  .row-container.playing {
    background: color-mix(in srgb, var(--text-accent) 8%, transparent);
    border-left-color: var(--text-active);
  }
  /* While any collection plays, stopped rows dim to 45% (out of scope),
     never hidden. Hover restores legibility, mirroring the tree's muted
     rows. The transport stays full-strength — it's the way back in. */
  .row-container.dimmed > :not(.tr) {
    opacity: 0.45;
  }
  .row-container.dimmed:hover > :not(.tr) {
    opacity: 0.7;
  }
  /* Shelved — quieter than the playing-dim and italic, a track set
     aside rather than one merely out of the current scope. */
  .row-container.archived {
    opacity: 0.55;
  }
  .row-container.archived .row-name {
    font-style: italic;
  }
  .row-container.dragging {
    opacity: 0.4;
  }
  .row-container.drop-before {
    box-shadow: inset 0 2px 0 var(--text-accent);
  }
  .row-container.drop-after {
    box-shadow: inset 0 -2px 0 var(--text-accent);
  }

  /* Armed-for-edit state: warmer background + purple stripe on the
     leading edge — DAW-style "this track is record-armed" affordance. */
  .row-container.editing {
    background: color-mix(in srgb, var(--text-accent) 25%, transparent);
    border-left-color: var(--text-active);
    cursor: default;
  }
  .row-container.draft .row-name {
    font-style: italic;
  }

  /* Drag grip — fades in at the row's left edge on hover, custom order
     only (the markup omits it under other sorts). */
  .grip {
    width: 0.55rem;
    flex-shrink: 0;
    color: var(--text-tertiary);
    font-size: 0.7rem;
    letter-spacing: -0.05em;
    opacity: 0;
    transition: opacity var(--transition-fast);
    cursor: grab;
  }
  .row-container:hover .grip {
    opacity: 1;
  }

  .arrow {
    width: 0.8rem;
    flex-shrink: 0;
    background: none;
    border: none;
    padding: 0;
    color: var(--text-secondary);
    font-size: 0.7rem;
    cursor: pointer;
    text-align: center;
  }
  .arrow-spacer {
    width: 0.8rem;
    flex-shrink: 0;
  }

  .bkm {
    width: 12px;
    height: 12px;
    flex-shrink: 0;
  }

  .row-name {
    flex: 1;
    min-width: 0;
    font-size: 0.9rem;
    color: var(--text-primary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  /* The name doubles as a click-to-rename button on the draft row. */
  .draft-name {
    background: none;
    border: 1px solid transparent;
    border-radius: var(--radius-sm);
    padding: 0.05rem 0.3rem;
    margin: 0 -0.3rem;
    text-align: left;
    cursor: text;
    transition: border-color var(--transition-fast);
  }
  .draft-name:hover {
    border-color: var(--bg-category);
  }

  .rename-input {
    flex: 1;
    min-width: 0;
    -webkit-user-select: text;
    user-select: text;
    background: var(--bg-container);
    border: 1px solid var(--text-accent);
    border-radius: var(--radius-sm);
    color: var(--text-primary);
    font-family: var(--font-body);
    font-size: 0.9rem;
    padding: 0.05rem 0.3rem;
    outline: none;
  }

  .editing-count {
    font-size: 0.7rem;
    color: var(--text-active);
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    flex-shrink: 0;
  }
  .row-actions {
    display: flex;
    align-items: center;
    gap: 0.05rem;
    flex-shrink: 0;
  }

  /* Transport — hidden at rest, revealed on row hover or keyboard
     focus, always visible while playing. One button per track: ▶ arms
     the collection into the search scope, the lit ■ stops it. */
  .tr {
    display: inline-flex;
    margin-left: auto;
    flex-shrink: 0;
    opacity: 0;
    transition: opacity var(--transition-fast);
  }
  .row-container:hover .tr,
  .row-container.kb-focused .tr,
  .tr.engaged {
    opacity: 1;
  }
  .tr-btn {
    flex-shrink: 0;
    width: 18px;
    height: 18px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0;
    background: transparent;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    color: var(--text-tertiary);
    cursor: pointer;
    transition: all var(--transition-fast);
  }
  .tr-btn svg {
    width: 9px;
    height: 9px;
    display: block;
  }
  .tr-btn:hover {
    color: var(--text-secondary);
    border-color: var(--text-secondary);
  }
  .tr-btn:active {
    transform: scale(0.97);
  }
  .tr-btn.playing {
    color: var(--text-active);
    border-color: var(--text-active);
    background: color-mix(in srgb, var(--text-active) 15%, transparent);
    filter: var(--glow-active);
  }

  /* Expanded file rows — the collection's contents, indented under the
     folder row. A playing collection's files take the wash too. */
  .child-row {
    display: flex;
    align-items: center;
    gap: 0.3rem;
    padding: 0.18rem 0.4rem 0.18rem 0.75rem;
    border-left: 3px solid transparent;
    font-size: 0.85rem;
    color: var(--text-primary);
  }
  .child-row.washed {
    background: color-mix(in srgb, var(--text-accent) 8%, transparent);
  }
  .child-row.dimmed {
    opacity: 0.45;
  }
  .child-empty .child-name {
    color: var(--text-tertiary);
    font-style: italic;
  }
  .indent {
    width: 1.1rem;
    flex-shrink: 0;
  }
  .child-name {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  /* Dashed create affordance — same family as the tree's "+ tag". */
  .add-coll {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    gap: 0.35rem;
    margin: 0.35rem 0.75rem;
    padding: 0.18rem 0.55rem;
    width: calc(100% - 1.5rem);
    background: transparent;
    color: var(--text-secondary);
    border: 1px dashed var(--text-tertiary);
    border-radius: var(--radius-sm);
    font-family: var(--font-body);
    font-size: 0.8rem;
    letter-spacing: 0.02em;
    cursor: pointer;
    transition: all var(--transition-fast);
  }
  .add-coll:hover {
    background: color-mix(in srgb, var(--text-accent) 10%, transparent);
    color: var(--text-accent);
    border-color: var(--text-accent);
    border-style: solid;
  }

  /* Context menu — same visual family as the file tree's ContextMenu. */
  .context-menu {
    position: fixed;
    background: var(--bg-focused);
    border: 1px solid var(--bg-category);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-dropdown);
    min-width: 180px;
    padding: 0.15rem 0;
    z-index: 100;
    font-family: var(--font-body);
    font-size: 0.8rem;
  }
  .context-item {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    width: 100%;
    padding: 0.25rem 0.6rem;
    border: none;
    background: none;
    cursor: pointer;
    text-align: left;
    line-height: 1.3;
    font-family: var(--font-body);
    font-size: 0.8rem;
    color: var(--text-primary);
    transition: background var(--transition-fast);
  }
  .context-item:hover,
  .context-item.open {
    background: var(--bg-container);
  }
  .context-item.danger {
    color: var(--text-danger);
  }
  .has-submenu {
    position: relative;
  }
  .submenu-caret {
    margin-left: auto;
    font-size: 0.7rem;
    opacity: 0.6;
  }
  .submenu {
    position: absolute;
    left: 100%;
    top: -0.15rem;
    background: var(--bg-focused);
    border: 1px solid var(--bg-category);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-dropdown);
    padding: 0.15rem 0;
    min-width: 130px;
    z-index: 2;
  }

  .empty {
    padding: 0.3rem 0.75rem 0.5rem;
  }
  .empty-label {
    font-family: var(--font-heading);
    font-size: 0.7rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--text-tertiary);
  }
</style>
