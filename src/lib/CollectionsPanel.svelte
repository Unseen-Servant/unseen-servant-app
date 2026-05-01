<script lang="ts">
  import type { CollectionInfo } from './types';

  export let collections: Record<string, CollectionInfo> = {};
  export let activeName: string | null = null;
  export let onClose: () => void = () => {};
  export let onSetActive: (name: string) => void = () => {};
  export let onClearActive: () => void = () => {};
  export let onEdit: (name: string) => void = () => {};
  export let onDelete: (name: string) => void = () => {};
  export let onToggleArchived: (name: string, archived: boolean) => void = () => {};
  export let onStartCreate: () => void = () => {};

  type SortKey = 'name' | 'last_used' | 'size';
  let sortKey: SortKey = 'last_used';
  let showArchived = false;

  $: rows = (() => {
    const list = Object.values(collections);
    const visible = showArchived ? list : list.filter(c => !c.archived);
    visible.sort((a, b) => {
      if (sortKey === 'name') return a.name.localeCompare(b.name);
      if (sortKey === 'size') return b.file_count - a.file_count;
      // last_used (recent first; null at the end)
      const ta = a.last_used_at ? Date.parse(a.last_used_at) : -Infinity;
      const tb = b.last_used_at ? Date.parse(b.last_used_at) : -Infinity;
      return tb - ta;
    });
    return visible;
  })();

  $: archivedCount = Object.values(collections).filter(c => c.archived).length;
  $: hasNone = Object.keys(collections).length === 0;

  function relativeTime(iso: string | null): string {
    if (!iso) return 'never';
    const ms = Date.now() - Date.parse(iso);
    if (Number.isNaN(ms)) return 'never';
    const sec = Math.floor(ms / 1000);
    if (sec < 60) return 'just now';
    const min = Math.floor(sec / 60);
    if (min < 60) return `${min}m ago`;
    const h = Math.floor(min / 60);
    if (h < 24) return `${h}h ago`;
    const d = Math.floor(h / 24);
    if (d === 1) return 'yesterday';
    if (d < 30) return `${d}d ago`;
    const mo = Math.floor(d / 30);
    if (mo < 12) return `${mo}mo ago`;
    return `${Math.floor(mo / 12)}y ago`;
  }

  function handleKey(event: KeyboardEvent) {
    if (event.key === 'Escape') onClose();
  }

  function handleRowSetActive(name: string) {
    if (activeName === name) onClearActive();
    else onSetActive(name);
  }
</script>

<svelte:window on:keydown={handleKey} />

<!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions a11y-no-noninteractive-element-interactions -->
<div class="backdrop" on:click={onClose}>
  <aside class="panel" on:click|stopPropagation>
    <header class="panel-header">
      <span class="panel-title">Collections</span>
      <button class="close-btn" on:click={onClose} title="Close">&times;</button>
    </header>

    <div class="toolbar">
      <button class="new-btn" on:click={onStartCreate}>+ New collection</button>
      <div class="spacer"></div>
      <label class="sort-label">
        Sort
        <select bind:value={sortKey} class="sort-select">
          <option value="last_used">Last used</option>
          <option value="name">Name</option>
          <option value="size">Size</option>
        </select>
      </label>
    </div>

    {#if archivedCount > 0}
      <label class="archived-toggle">
        <input type="checkbox" bind:checked={showArchived} />
        <span>Show archived ({archivedCount})</span>
      </label>
    {/if}

    {#if hasNone}
      <div class="empty">
        <div class="empty-title">No collections yet</div>
        <p class="empty-body">
          Collections group sourcebooks for fast access during prep and play.
          Try <strong>Create collection from folder</strong> by right-clicking
          any folder in your library.
        </p>
        <button class="btn primary" on:click={onStartCreate}>+ New collection</button>
      </div>
    {:else if rows.length === 0}
      <div class="empty">
        <p class="empty-body">All collections are archived. Toggle "Show archived" above to see them.</p>
      </div>
    {:else}
      <ul class="rows">
        {#each rows as col (col.name)}
          <li class="row" class:active={activeName === col.name} class:archived={col.archived}>
            <span
              class="row-color"
              style={col.color ? `background: ${col.color}` : ''}
              class:none={!col.color}
            ></span>
            <div class="row-main">
              <div class="row-name">
                {col.name}
                {#if activeName === col.name}
                  <span class="active-badge" title="Active context">&#9733;</span>
                {/if}
                {#if col.archived}
                  <span class="archived-badge">archived</span>
                {/if}
              </div>
              {#if col.description}
                <div class="row-desc">{col.description}</div>
              {/if}
              <div class="row-meta">
                {col.file_count} file{col.file_count === 1 ? '' : 's'}
                <span class="dot">&middot;</span>
                last used {relativeTime(col.last_used_at)}
              </div>
            </div>
            <div class="row-actions">
              <button
                class="row-btn"
                class:on={activeName === col.name}
                on:click={() => handleRowSetActive(col.name)}
                title={activeName === col.name ? 'Clear active context' : 'Set as active context'}
              >
                &#9733;
              </button>
              <button class="row-btn" on:click={() => onEdit(col.name)} title="Edit">
                <svg viewBox="0 0 640 640" fill="currentColor" class="icon">
                  <path d="M535.6 85.7C513.7 63.8 478.3 63.8 456.4 85.7L432 110.1L529.9 208L554.3 183.6C576.2 161.7 576.2 126.3 554.3 104.4L535.6 85.7zM236.4 305.7C230.3 311.8 225.6 319.3 222.9 327.6L193.3 416.4C190.4 425 192.7 434.5 199.1 441C205.5 447.5 215 449.7 223.7 446.8L312.5 417.2C320.7 414.5 328.2 409.8 334.4 403.7L496 241.9L398.1 144L236.4 305.7zM160 128C107 128 64 171 64 224L64 480C64 533 107 576 160 576L416 576C469 576 512 533 512 480L512 384C512 366.3 497.7 352 480 352C462.3 352 448 366.3 448 384L448 480C448 497.7 433.7 512 416 512L160 512C142.3 512 128 497.7 128 480L128 224C128 206.3 142.3 192 160 192L256 192C273.7 192 288 177.7 288 160C288 142.3 273.7 128 256 128L160 128z"/>
                </svg>
              </button>
              <button
                class="row-btn"
                on:click={() => onToggleArchived(col.name, !col.archived)}
                title={col.archived ? 'Unarchive' : 'Archive'}
              >
                {col.archived ? '↺' : '⇩'}
              </button>
              <button
                class="row-btn danger"
                on:click={() => onDelete(col.name)}
                title="Delete"
              >
                &times;
              </button>
            </div>
          </li>
        {/each}
      </ul>
    {/if}
  </aside>
</div>

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.4);
    display: flex;
    justify-content: flex-end;
    z-index: 280;
  }
  .panel {
    background: var(--bg-focused);
    border-left: 1px solid var(--bg-category);
    width: 420px;
    max-width: 90vw;
    height: 100%;
    display: flex;
    flex-direction: column;
    font-family: var(--font-body);
    overflow: hidden;
  }
  .panel-header {
    display: flex;
    align-items: center;
    padding: 0.75rem 1rem;
    border-bottom: 1px solid var(--bg-category);
  }
  .panel-title {
    font-family: var(--font-heading);
    font-size: 1rem;
    font-weight: 600;
    color: var(--text-accent);
    flex: 1;
  }
  .close-btn {
    background: none;
    border: none;
    color: var(--text-secondary);
    cursor: pointer;
    font-size: 1.1rem;
    padding: 0.2rem 0.5rem;
    border-radius: 4px;
  }
  .close-btn:hover {
    background: var(--bg-container);
    color: var(--text-primary);
  }
  .toolbar {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 1rem;
    border-bottom: 1px solid var(--bg-category);
  }
  .spacer {
    flex: 1;
  }
  .new-btn {
    padding: 0.3rem 0.7rem;
    background: var(--bg-active);
    color: var(--text-primary);
    border: 1px solid transparent;
    border-radius: 4px;
    font-size: 0.8rem;
    cursor: pointer;
  }
  .new-btn:hover {
    background: var(--bg-active-focused);
  }
  .sort-label {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    font-size: 0.8rem;
    color: var(--text-secondary);
  }
  .sort-select {
    padding: 0.2rem 0.4rem;
    background: var(--bg-container);
    color: var(--text-primary);
    border: 1px solid var(--bg-category);
    border-radius: 3px;
    font-size: 0.8rem;
  }
  .archived-toggle {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.4rem 1rem;
    font-size: 0.8rem;
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
    align-items: stretch;
    gap: 0.6rem;
    padding: 0.6rem 1rem;
    border-bottom: 1px solid var(--bg-container);
    transition: background var(--transition-fast);
  }
  .row:hover {
    background: var(--bg-container);
  }
  .row.active {
    background: rgba(182, 159, 129, 0.1);
  }
  .row.archived {
    opacity: 0.6;
  }
  .row-color {
    width: 4px;
    border-radius: 2px;
    flex-shrink: 0;
  }
  .row-color.none {
    background: var(--bg-category);
  }
  .row-main {
    flex: 1;
    min-width: 0;
  }
  .row-name {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    font-weight: 600;
    font-size: 0.9rem;
    color: var(--text-primary);
  }
  .active-badge {
    color: var(--text-accent);
    font-size: 0.8rem;
  }
  .archived-badge {
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-secondary);
    background: var(--bg-container);
    padding: 0.05rem 0.35rem;
    border-radius: 3px;
  }
  .row-desc {
    font-size: 0.8rem;
    color: var(--text-secondary);
    margin-top: 0.15rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .row-meta {
    font-size: 0.75rem;
    color: var(--text-secondary);
    margin-top: 0.2rem;
  }
  .dot {
    margin: 0 0.3rem;
    opacity: 0.6;
  }
  .row-actions {
    display: flex;
    align-items: flex-start;
    gap: 0.15rem;
  }
  .row-btn {
    background: none;
    border: none;
    color: var(--text-secondary);
    cursor: pointer;
    padding: 0.2rem 0.35rem;
    border-radius: 3px;
    font-size: 0.85rem;
    line-height: 1;
    opacity: 0.6;
    transition: all var(--transition-fast);
  }
  .row:hover .row-btn {
    opacity: 1;
  }
  .row-btn:hover {
    background: var(--bg-focused);
    color: var(--text-primary);
  }
  .row-btn.on {
    color: var(--text-accent);
    opacity: 1;
  }
  .row-btn.danger:hover {
    color: var(--text-danger);
  }
  .icon {
    width: 0.85rem;
    height: 0.85rem;
    display: block;
  }

  .empty {
    padding: 2rem 1.25rem;
    text-align: center;
    color: var(--text-secondary);
  }
  .empty-title {
    font-family: var(--font-heading);
    color: var(--text-accent);
    font-size: 1rem;
    margin-bottom: 0.5rem;
  }
  .empty-body {
    font-size: 0.85rem;
    line-height: 1.5;
    margin-bottom: 1rem;
  }
  .btn.primary {
    padding: 0.4rem 0.9rem;
    background: var(--bg-active);
    color: var(--text-primary);
    border: 1px solid transparent;
    border-radius: 4px;
    font-size: 0.85rem;
    cursor: pointer;
  }
  .btn.primary:hover {
    background: var(--bg-active-focused);
  }
</style>
