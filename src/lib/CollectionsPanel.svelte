<script lang="ts">
  import type { CollectionInfo } from './types';

  export let collections: Record<string, CollectionInfo> = {};
  export let activeName: string | null = null;
  export let editingName: string | null = null;
  export let onSetActive: (name: string) => void = () => {};
  export let onClearActive: () => void = () => {};
  export let onEdit: (name: string) => void = () => {};
  export let onEditFiles: (name: string) => void = () => {};
  export let onDelete: (name: string) => void = () => {};
  export let onToggleArchived: (name: string, archived: boolean) => void = () => {};
  export let onCreate: (name: string) => void = () => {};

  type SortKey = 'name' | 'last_used' | 'size';
  let sortKey: SortKey = 'last_used';
  let showArchived = false;

  let creating = false;
  let newName = '';
  let newNameInput: HTMLInputElement;

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
</script>

<aside class="panel">
  <header class="panel-header">
    <span class="panel-title">Collections</span>
  </header>

  <div class="toolbar">
    {#if !creating}
      <button class="new-btn" on:click={startCreate}>+ New</button>
      <div class="spacer"></div>
      <select bind:value={sortKey} class="sort-select" title="Sort">
        <option value="last_used">Last used</option>
        <option value="name">Name</option>
        <option value="size">Size</option>
      </select>
    {:else}
      <input
        bind:this={newNameInput}
        bind:value={newName}
        class="new-input"
        type="text"
        placeholder="Collection name"
        on:keydown={handleNewKeydown}
      />
      <button
        class="new-confirm"
        on:click={commitCreate}
        disabled={!newName.trim()}
        title="Create"
      >&#10003;</button>
      <button class="new-cancel" on:click={cancelCreate} title="Cancel">&times;</button>
    {/if}
  </div>

  {#if archivedCount > 0}
    <label class="archived-toggle">
      <input type="checkbox" bind:checked={showArchived} />
      <span>Show archived ({archivedCount})</span>
    </label>
  {/if}

  {#if hasNone}
    <div class="empty">
      <p class="empty-body">
        Collections group sourcebooks for fast access. Try
        <strong>Create collection from folder</strong> from a folder's right-click menu, or use <strong>+ New</strong> above.
      </p>
    </div>
  {:else if rows.length === 0}
    <div class="empty">
      <p class="empty-body">All collections are archived.</p>
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
            class="row-color"
            class:none={!col.color}
            style={col.color ? `background: ${col.color}` : ''}
          ></span>
          <span class="row-name">{col.name}</span>
          {#if activeName === col.name}
            <span class="row-marker" title="Active">&#9733;</span>
          {/if}
          <span class="row-count">{col.file_count}</span>
          <div class="row-actions">
            <button
              class="row-btn"
              on:click|stopPropagation={() => onEditFiles(col.name)}
              title="Edit files"
              aria-label="Edit files"
            >
              <svg viewBox="0 0 640 640" fill="currentColor" class="icon">
                <path d="M88 152C88 138.7 98.7 128 112 128L528 128C541.3 128 552 138.7 552 152C552 165.3 541.3 176 528 176L112 176C98.7 176 88 165.3 88 152zM88 320C88 306.7 98.7 296 112 296L528 296C541.3 296 552 306.7 552 320C552 333.3 541.3 344 528 344L112 344C98.7 344 88 333.3 88 320zM88 488C88 474.7 98.7 464 112 464L528 464C541.3 464 552 474.7 552 488C552 501.3 541.3 512 528 512L112 512C98.7 512 88 501.3 88 488z"/>
              </svg>
            </button>
            <button
              class="row-btn"
              on:click|stopPropagation={() => onEdit(col.name)}
              title="Edit metadata"
              aria-label="Edit metadata"
            >
              <svg viewBox="0 0 640 640" fill="currentColor" class="icon">
                <path d="M535.6 85.7C513.7 63.8 478.3 63.8 456.4 85.7L432 110.1L529.9 208L554.3 183.6C576.2 161.7 576.2 126.3 554.3 104.4L535.6 85.7zM236.4 305.7C230.3 311.8 225.6 319.3 222.9 327.6L193.3 416.4C190.4 425 192.7 434.5 199.1 441C205.5 447.5 215 449.7 223.7 446.8L312.5 417.2C320.7 414.5 328.2 409.8 334.4 403.7L496 241.9L398.1 144L236.4 305.7zM160 128C107 128 64 171 64 224L64 480C64 533 107 576 160 576L416 576C469 576 512 533 512 480L512 384C512 366.3 497.7 352 480 352C462.3 352 448 366.3 448 384L448 480C448 497.7 433.7 512 416 512L160 512C142.3 512 128 497.7 128 480L128 224C128 206.3 142.3 192 160 192L256 192C273.7 192 288 177.7 288 160C288 142.3 273.7 128 256 128L160 128z"/>
              </svg>
            </button>
            <button
              class="row-btn"
              on:click|stopPropagation={() => onToggleArchived(col.name, !col.archived)}
              title={col.archived ? 'Unarchive' : 'Archive'}
              aria-label={col.archived ? 'Unarchive' : 'Archive'}
            >{col.archived ? '↺' : '⇩'}</button>
            <button
              class="row-btn danger"
              on:click|stopPropagation={() => onDelete(col.name)}
              title="Delete"
              aria-label="Delete"
            >&times;</button>
          </div>
        </li>
      {/each}
    </ul>
  {/if}
</aside>

<style>
  .panel {
    width: 280px;
    flex-shrink: 0;
    background: var(--bg-focused);
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
  }
  .panel-title {
    font-family: var(--font-heading);
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--text-accent);
    flex: 1;
  }
  .toolbar {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.4rem 0.75rem;
    border-bottom: 1px solid var(--bg-category);
  }
  .spacer { flex: 1; }
  .new-btn {
    padding: 0.25rem 0.55rem;
    background: var(--bg-active);
    color: var(--text-primary);
    border: 1px solid transparent;
    border-radius: 3px;
    font-size: 0.75rem;
    cursor: pointer;
  }
  .new-btn:hover { background: var(--bg-active-focused); }
  .sort-select {
    padding: 0.15rem 0.3rem;
    background: var(--bg-container);
    color: var(--text-primary);
    border: 1px solid var(--bg-category);
    border-radius: 3px;
    font-size: 0.75rem;
  }
  .new-input {
    flex: 1;
    min-width: 0;
    padding: 0.2rem 0.4rem;
    background: var(--bg-container);
    color: var(--text-primary);
    border: 1px solid var(--text-accent);
    border-radius: 3px;
    font-size: 0.8rem;
    outline: none;
  }
  .new-confirm,
  .new-cancel {
    padding: 0.2rem 0.4rem;
    border: 1px solid var(--bg-category);
    background: var(--bg-container);
    color: var(--text-secondary);
    border-radius: 3px;
    cursor: pointer;
    font-size: 0.8rem;
    line-height: 1;
  }
  .new-confirm:hover:not(:disabled) {
    background: var(--bg-active);
    color: var(--text-primary);
    border-color: transparent;
  }
  .new-confirm:disabled { opacity: 0.4; cursor: default; }
  .new-cancel:hover { color: var(--text-primary); }

  .archived-toggle {
    display: flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.3rem 0.75rem;
    font-size: 0.75rem;
    color: var(--text-secondary);
    border-bottom: 1px solid var(--bg-category);
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
    gap: 0.4rem;
    padding: 0.3rem 0.6rem;
    border-bottom: 1px solid var(--bg-container);
    cursor: pointer;
    transition: background var(--transition-fast);
    min-height: 28px;
  }
  .row:hover { background: var(--bg-container); }
  .row.active { background: rgba(182, 159, 129, 0.15); }
  .row.editing { background: rgba(182, 159, 129, 0.25); }
  .row.archived { opacity: 0.55; }
  .row-color {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .row-color.none {
    background: var(--bg-category);
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
    flex-shrink: 0;
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
    font-size: 0.75rem;
    line-height: 1;
    transition: all var(--transition-fast);
  }
  .row-btn:hover {
    background: var(--bg-focused);
    color: var(--text-primary);
  }
  .row-btn.danger:hover { color: var(--text-danger); }
  .icon {
    width: 11px;
    height: 11px;
    display: block;
  }

  .empty {
    padding: 1rem 0.75rem;
    color: var(--text-secondary);
    text-align: center;
  }
  .empty-body {
    font-size: 0.8rem;
    line-height: 1.4;
  }
</style>
