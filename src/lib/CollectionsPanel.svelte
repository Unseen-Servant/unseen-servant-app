<script lang="ts">
  import type { CollectionInfo } from './types';
  import ActionButton from './ActionButton.svelte';

  export let collections: Record<string, CollectionInfo> = {};
  // Per-collection count of files currently hidden in the tree. Only
  // entries with count > 0 are shown alongside the file-count chip as a
  // muted reminder that the collection holds tucked-away items.
  export let hiddenCountByCollection: Record<string, number> = {};
  export let activeName: string | null = null;
  export let editingName: string | null = null;
  export let onSetActive: (name: string) => void = () => {};
  export let onClearActive: () => void = () => {};
  export let onEdit: (name: string) => void = () => {};
  export let onEditFiles: (name: string) => void = () => {};
  export let onDelete: (name: string) => void = () => {};
  export let onToggleArchived: (name: string, archived: boolean) => void = () => {};
  export let onCreate: (name: string) => void = () => {};

  type SortKey = 'last_used' | 'name' | 'size';
  const SORT_OPTIONS: { value: SortKey; label: string }[] = [
    { value: 'last_used', label: 'Last used' },
    { value: 'name', label: 'Name' },
    { value: 'size', label: 'Size' },
  ];
  let sortKey: SortKey = 'last_used';
  let showArchived = false;

  let creating = false;
  let newName = '';
  let newNameInput: HTMLInputElement;

  let sortMenuOpen = false;
  let sortBtn: HTMLButtonElement;

  $: if (creating && newNameInput) newNameInput.focus();

  $: rows = (() => {
    const list = Object.values(collections);
    const visible = showArchived ? list : list.filter(c => !c.archived);
    visible.sort((a, b) => {
      if (sortKey === 'name') return a.name.localeCompare(b.name);
      if (sortKey === 'size') return b.file_count - a.file_count;
      const ta = a.last_used_at ? Date.parse(a.last_used_at) : -Infinity;
      const tb = b.last_used_at ? Date.parse(b.last_used_at) : -Infinity;
      return tb - ta;
    });
    return visible;
  })();

  $: archivedCount = Object.values(collections).filter(c => c.archived).length;
  $: hasNone = Object.keys(collections).length === 0;

  function startCreate() {
    creating = true;
    newName = '';
  }

  function cancelCreate() {
    creating = false;
    newName = '';
  }

  function commitCreate() {
    const trimmed = newName.trim();
    if (!trimmed) return;
    onCreate(trimmed);
    creating = false;
    newName = '';
  }

  function handleNewKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter') {
      e.preventDefault();
      commitCreate();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      cancelCreate();
    }
  }

  function handleRowClick(name: string) {
    if (activeName === name) onClearActive();
    else onSetActive(name);
  }

  function toggleSortMenu() {
    sortMenuOpen = !sortMenuOpen;
  }

  function pickSort(value: SortKey) {
    sortKey = value;
    sortMenuOpen = false;
  }

  function handleWindowClick(event: MouseEvent) {
    if (!sortMenuOpen) return;
    const target = event.target as Node;
    if (sortBtn && (sortBtn === target || sortBtn.contains(target))) return;
    sortMenuOpen = false;
  }
</script>

<svelte:window on:click={handleWindowClick} />

<aside class="panel">
  <header class="panel-header">
    <span class="panel-title">Collections</span>
    <div class="header-actions">
      <button class="header-btn" on:click={startCreate} title="New collection" aria-label="New collection">
        <!-- Font Awesome "plus" (static/icons/plus-solid-full.svg) -->
        <svg viewBox="0 0 640 640" fill="currentColor" class="icon">
          <path d="M352 128C352 110.3 337.7 96 320 96C302.3 96 288 110.3 288 128L288 288L128 288C110.3 288 96 302.3 96 320C96 337.7 110.3 352 128 352L288 352L288 512C288 529.7 302.3 544 320 544C337.7 544 352 529.7 352 512L352 352L512 352C529.7 352 544 337.7 544 320C544 302.3 529.7 288 512 288L352 288L352 128z"/>
        </svg>
      </button>
      <div class="sort-wrapper">
        <button
          class="header-btn"
          class:on={sortMenuOpen}
          on:click|stopPropagation={toggleSortMenu}
          bind:this={sortBtn}
          title="Sort"
          aria-label="Sort collections"
          aria-haspopup="menu"
          aria-expanded={sortMenuOpen}
        >
          <!-- Font Awesome "sort" (static/icons/sort-solid-full.svg) -->
          <svg viewBox="0 0 640 640" fill="currentColor" class="icon">
            <path d="M130.4 268.2C135.4 280.2 147 288 160 288L480 288C492.9 288 504.6 280.2 509.6 268.2C514.6 256.2 511.8 242.5 502.7 233.3L342.7 73.3C330.2 60.8 309.9 60.8 297.4 73.3L137.4 233.3C128.2 242.5 125.5 256.2 130.5 268.2zM130.4 371.7C125.4 383.7 128.2 397.4 137.3 406.6L297.3 566.6C309.8 579.1 330.1 579.1 342.6 566.6L502.6 406.6C511.8 397.4 514.5 383.7 509.5 371.7C504.5 359.7 492.9 352 480 352L160 352C147.1 352 135.4 359.8 130.4 371.8z"/>
          </svg>
        </button>
        {#if sortMenuOpen}
          <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
          <div class="sort-menu" on:click|stopPropagation>
            <div class="sort-section-label">Sort by</div>
            {#each SORT_OPTIONS as opt}
              <button
                class="sort-item"
                class:selected={sortKey === opt.value}
                on:click={() => pickSort(opt.value)}
              >{opt.label}</button>
            {/each}
            {#if archivedCount > 0}
              <hr class="sort-divider" />
              <label class="sort-toggle">
                <span>Show archived</span>
                <input class="app-checkbox" type="checkbox" bind:checked={showArchived} />
              </label>
            {/if}
          </div>
        {/if}
      </div>
    </div>
  </header>

  {#if creating}
    <div class="create-row">
      <input
        bind:this={newNameInput}
        bind:value={newName}
        class="new-input"
        type="text"
        placeholder="Collection name"
        on:keydown={handleNewKeydown}
      />
      <ActionButton kind="confirm" compact title="Create" onClick={commitCreate} disabled={!newName.trim()} />
      <ActionButton kind="discard" compact title="Cancel" onClick={cancelCreate} />
    </div>
  {/if}

  {#if hasNone}
    <div class="empty">
      <span class="empty-label">No collections yet</span>
    </div>
  {:else if rows.length === 0}
    <div class="empty">
      <span class="empty-label">All archived</span>
    </div>
  {:else}
    <ul class="rows">
      {#each rows as col (col.name)}
        <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-noninteractive-element-interactions -->
        <li
          class="row"
          class:active={activeName === col.name}
          class:editing={editingName === col.name}
          class:archived={col.archived}
          title={col.description || col.name}
          on:click={() => handleRowClick(col.name)}
        >
          <span
            class="row-icon"
            class:none={!col.color}
            style={col.color ? `color: ${col.color}` : ''}
            aria-hidden="true"
          >
            <!-- "books" — three rounded spines, collection of books -->
            <svg viewBox="0 0 640 640" fill="currentColor" class="icon">
              <path d="M96 96 C96 78.3 110.3 64 128 64L192 64 C209.7 64 224 78.3 224 96L224 544 C224 561.7 209.7 576 192 576L128 576 C110.3 576 96 561.7 96 544L96 96zM256 96 C256 78.3 270.3 64 288 64L352 64 C369.7 64 384 78.3 384 96L384 544 C384 561.7 369.7 576 352 576L288 576 C270.3 576 256 561.7 256 544L256 96zM416 96 C416 78.3 430.3 64 448 64L512 64 C529.7 64 544 78.3 544 96L544 544 C544 561.7 529.7 576 512 576L448 576 C430.3 576 416 561.7 416 544L416 96z"/>
            </svg>
          </span>
          <span class="row-name">{col.name}</span>
          {#if activeName === col.name}
            <span class="row-marker" title="Active">&#9733;</span>
          {/if}
          <span class="row-count">{col.file_count}</span>
          {#if hiddenCountByCollection[col.name]}
            <span
              class="row-hidden-count"
              title={`${hiddenCountByCollection[col.name]} file${hiddenCountByCollection[col.name] === 1 ? '' : 's'} hidden in the tree`}
            >({hiddenCountByCollection[col.name]} hidden)</span>
          {/if}
          <div class="row-actions">
            <button
              class="row-btn"
              on:click|stopPropagation={() => onEditFiles(col.name)}
              title="Edit files"
              aria-label="Edit files"
            >
              <!-- Font Awesome "file-circle-check" (static/icons/file-circle-check-solid-full.svg) -->
              <svg viewBox="0 0 640 640" fill="currentColor" class="icon">
                <path d="M128 64C92.7 64 64 92.7 64 128L64 512C64 547.3 92.7 576 128 576L308 576C285.3 544.5 272 505.8 272 464C272 363.4 349.4 280.8 448 272.7L448 234.6C448 217.6 441.3 201.3 429.3 189.3L322.7 82.7C310.7 70.7 294.5 64 277.5 64L128 64zM389.5 240L296 240C282.7 240 272 229.3 272 216L272 122.5L389.5 240zM608 464C608 384.5 543.5 320 464 320C384.5 320 320 384.5 320 464C320 543.5 384.5 608 464 608C543.5 608 608 543.5 608 464zM521.4 403.1C528.5 408.3 530.1 418.3 524.9 425.4L460.9 513.4C458.1 517.2 453.9 519.6 449.2 519.9C444.5 520.2 439.9 518.6 436.6 515.3L396.6 475.3C390.4 469.1 390.4 458.9 396.6 452.7C402.8 446.5 413 446.5 419.2 452.7L446 479.5L499 406.6C504.2 399.5 514.2 397.9 521.4 403.1z"/>
              </svg>
            </button>
            <button
              class="row-btn"
              on:click|stopPropagation={() => onEdit(col.name)}
              title="Edit info"
              aria-label="Edit info"
            >
              <!-- Font Awesome "pen-to-square" -->
              <svg viewBox="0 0 640 640" fill="currentColor" class="icon">
                <path d="M535.6 85.7C513.7 63.8 478.3 63.8 456.4 85.7L432 110.1L529.9 208L554.3 183.6C576.2 161.7 576.2 126.3 554.3 104.4L535.6 85.7zM236.4 305.7C230.3 311.8 225.6 319.3 222.9 327.6L193.3 416.4C190.4 425 192.7 434.5 199.1 441C205.5 447.5 215 449.7 223.7 446.8L312.5 417.2C320.7 414.5 328.2 409.8 334.4 403.7L496 241.9L398.1 144L236.4 305.7zM160 128C107 128 64 171 64 224L64 480C64 533 107 576 160 576L416 576C469 576 512 533 512 480L512 384C512 366.3 497.7 352 480 352C462.3 352 448 366.3 448 384L448 480C448 497.7 433.7 512 416 512L160 512C142.3 512 128 497.7 128 480L128 224C128 206.3 142.3 192 160 192L256 192C273.7 192 288 177.7 288 160C288 142.3 273.7 128 256 128L160 128z"/>
              </svg>
            </button>
            <button
              class="row-btn"
              on:click|stopPropagation={() => onToggleArchived(col.name, !col.archived)}
              title={col.archived ? 'Unarchive' : 'Archive'}
              aria-label={col.archived ? 'Unarchive' : 'Archive'}
            >
              <!-- Font Awesome "box-archive" (static/icons/box-archive-solid-full.svg) -->
              <svg viewBox="0 0 640 640" fill="currentColor" class="icon">
                <path d="M64 128C64 110.3 78.3 96 96 96L544 96C561.7 96 576 110.3 576 128L576 160C576 177.7 561.7 192 544 192L96 192C78.3 192 64 177.7 64 160L64 128zM96 240L544 240L544 480C544 515.3 515.3 544 480 544L160 544C124.7 544 96 515.3 96 480L96 240zM248 304C234.7 304 224 314.7 224 328C224 341.3 234.7 352 248 352L392 352C405.3 352 416 341.3 416 328C416 314.7 405.3 304 392 304L248 304z"/>
              </svg>
            </button>
            <button
              class="row-btn danger"
              on:click|stopPropagation={() => onDelete(col.name)}
              title="Delete"
              aria-label="Delete"
            >
              <!-- Font Awesome "trash" (static/icons/trash-solid-full.svg) -->
              <svg viewBox="0 0 640 640" fill="currentColor" class="icon">
                <path d="M232.7 69.9L224 96L128 96C110.3 96 96 110.3 96 128C96 145.7 110.3 160 128 160L512 160C529.7 160 544 145.7 544 128C544 110.3 529.7 96 512 96L416 96L407.3 69.9C402.9 56.8 390.7 48 376.9 48L263.1 48C249.3 48 237.1 56.8 232.7 69.9zM512 208L128 208L149.1 531.1C150.7 556.4 171.7 576 197 576L443 576C468.3 576 489.3 556.4 490.9 531.1L512 208z"/>
              </svg>
            </button>
          </div>
        </li>
      {/each}
    </ul>
  {/if}
</aside>

<style>
  .panel {
    width: 240px;
    flex-shrink: 0;
    background: var(--bg-container);
    border-right: 1px solid var(--bg-category);
    display: flex;
    flex-direction: column;
    font-family: var(--font-body);
    overflow: hidden;
  }
  .panel-header {
    display: flex;
    align-items: center;
    padding: 0.5rem 0.75rem;
    border-bottom: 1px solid var(--bg-category);
    gap: 0.4rem;
  }
  .panel-title {
    font-family: var(--font-heading);
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--text-accent);
    flex: 1;
  }
  .header-actions {
    display: flex;
    align-items: center;
    gap: 0.15rem;
  }
  .header-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 22px;
    height: 22px;
    padding: 0;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 3px;
    color: var(--text-secondary);
    cursor: pointer;
    transition: all var(--transition-fast);
  }
  .header-btn:hover {
    color: var(--text-primary);
  }
  .header-btn.on {
    color: var(--text-accent);
  }

  .sort-wrapper {
    position: relative;
  }
  .sort-menu {
    position: absolute;
    right: 0;
    top: calc(100% + 4px);
    background: var(--bg-focused);
    border: 1px solid var(--bg-category);
    border-radius: 4px;
    box-shadow: var(--shadow-dropdown);
    padding: 0.15rem 0;
    min-width: 130px;
    z-index: 50;
  }
  .sort-item {
    display: block;
    width: 100%;
    padding: 0.3rem 0.6rem;
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
  .sort-item.selected {
    color: var(--text-accent);
    font-weight: 600;
  }
  .sort-section-label {
    font-family: var(--font-heading, var(--font-body));
    font-size: 0.65rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--text-secondary);
    padding: 0.3rem 0.6rem 0.15rem;
  }
  .sort-divider {
    margin: 0.25rem 0;
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

  .create-row {
    display: flex;
    align-items: center;
    gap: 0.3rem;
    padding: 0.4rem 0.75rem;
    border-bottom: 1px solid var(--bg-category);
  }
  .new-input {
    flex: 1;
    min-width: 0;
    padding: 0.2rem 0.4rem;
    background: var(--bg-app);
    color: var(--text-primary);
    border: 1px solid var(--text-accent);
    border-radius: 3px;
    font-size: 0.8rem;
    outline: none;
  }
  .rows {
    list-style: none;
    margin: 0;
    padding: 0;
    overflow-y: auto;
    flex: 1;
  }
  .row {
    display: flex;
    align-items: center;
    gap: 0.55rem;
    padding: 0.3rem 0.75rem;
    border-bottom: 1px solid var(--bg-container);
    cursor: pointer;
    transition: background var(--transition-fast);
    min-height: 28px;
  }
  .row:hover { background: var(--bg-focused); }
  .row.active { background: rgba(182, 159, 129, 0.15); }
  .row.editing { background: rgba(182, 159, 129, 0.25); }
  .row.archived { opacity: 0.55; }
  .row-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    color: var(--text-accent);
    margin-right: 0.15rem;
  }
  .row-icon.none {
    color: var(--text-tertiary);
  }
  .row-icon .icon {
    width: 13px;
    height: 13px;
  }
  .row-name {
    flex: 1;
    font-size: 0.82rem;
    color: var(--text-primary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .row.active .row-name { color: var(--text-accent); font-weight: 600; }
  .row-marker {
    color: var(--text-accent);
    font-size: 0.75rem;
    flex-shrink: 0;
  }
  .row-count {
    font-size: 0.7rem;
    color: var(--text-secondary);
    margin-right: 0.25rem;
    flex-shrink: 0;
  }
  .row-hidden-count {
    font-size: 0.65rem;
    font-style: italic;
    color: var(--text-tertiary);
    margin-right: 0.25rem;
    flex-shrink: 0;
  }
  /* Hide on hover so the action buttons have room to surface. */
  .row:hover .row-hidden-count,
  .row.editing .row-hidden-count {
    display: none;
  }
  .row-actions {
    display: none;
    align-items: center;
    gap: 0.05rem;
    flex-shrink: 0;
  }
  .row:hover .row-actions { display: flex; }
  .row.editing .row-actions { display: flex; }
  .row-btn {
    background: none;
    border: none;
    color: var(--text-secondary);
    cursor: pointer;
    padding: 0.15rem 0.3rem;
    border-radius: 3px;
    line-height: 1;
    transition: all var(--transition-fast);
  }
  .row-btn:hover {
    color: var(--text-primary);
  }
  .row-btn.danger:hover { color: var(--text-danger); }
  .icon {
    width: 11px;
    height: 11px;
    display: block;
  }

  .empty {
    padding: 0.6rem 0.75rem;
  }
  .empty-label {
    font-family: var(--font-heading, var(--font-body));
    font-size: 0.7rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--text-tertiary);
  }
</style>
