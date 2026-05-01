<script lang="ts">
  import type {
    CollectionInfo,
    LibraryHealthResult,
    OrphanFile,
    StaleCollection,
  } from './types';

  export let data: LibraryHealthResult;
  export let collections: Record<string, CollectionInfo> = {};
  export let onClose: () => void = () => {};
  export let onAddOrphanToCollection: (path: string, collectionName: string) => void = () => {};
  export let onArchiveStale: (name: string) => void = () => {};

  const STALE_THRESHOLDS = [30, 60, 90] as const;
  let staleThreshold: 30 | 60 | 90 = 60;
  let showNeverUsed = false;

  let openOrphanPicker: string | null = null;

  $: collectionList = Object.values(collections).filter(c => !c.archived);
  $: hasCollectionsToPick = collectionList.length > 0;

  $: staleEntries = (() => {
    if (!data?.stale) return { dated: [], neverUsed: [] };
    const cutoff = Date.now() - staleThreshold * 86400000;
    const dated: StaleCollection[] = [];
    const neverUsed: StaleCollection[] = [];
    for (const s of data.stale) {
      if (s.last_used_at === null) {
        neverUsed.push(s);
        continue;
      }
      if (Date.parse(s.last_used_at) < cutoff) {
        dated.push(s);
      }
    }
    return { dated, neverUsed };
  })();

  $: hasNoIssues =
    (data?.orphans?.length ?? 0) === 0 &&
    (data?.anchors?.length ?? 0) === 0 &&
    (data?.overlap?.length ?? 0) === 0 &&
    staleEntries.dated.length === 0 &&
    staleEntries.neverUsed.length === 0;

  function relativeTime(iso: string | null): string {
    if (!iso) return 'never used';
    const ms = Date.now() - Date.parse(iso);
    if (Number.isNaN(ms)) return 'never used';
    const sec = Math.floor(ms / 1000);
    if (sec < 60) return 'just now';
    const min = Math.floor(sec / 60);
    if (min < 60) return `${min}m ago`;
    const h = Math.floor(min / 60);
    if (h < 24) return `${h}h ago`;
    const d = Math.floor(h / 24);
    if (d === 1) return 'yesterday';
    if (d < 30) return `${d} days ago`;
    const mo = Math.floor(d / 30);
    if (mo < 12) return `${mo}mo ago`;
    return `${Math.floor(mo / 12)}y ago`;
  }

  function formatBytes(bytes: number): string {
    if (!bytes) return '';
    const mb = bytes / (1024 * 1024);
    if (mb < 1) return `${(bytes / 1024).toFixed(0)} KB`;
    return `${mb.toFixed(1)} MB`;
  }

  function handleKey(event: KeyboardEvent) {
    if (event.key === 'Escape') onClose();
  }

  function pickForOrphan(orphan: OrphanFile, collectionName: string) {
    onAddOrphanToCollection(orphan.path, collectionName);
    openOrphanPicker = null;
  }
</script>

<svelte:window on:keydown={handleKey} />

<!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
<div class="backdrop" on:click={onClose}>
  <div class="dialog" on:click|stopPropagation>
    <header class="dialog-header">
      <span class="title">Library Health</span>
      <button class="close-btn" on:click={onClose} title="Close" aria-label="Close">&times;</button>
    </header>

    <div class="dialog-body">
      {#if hasNoIssues}
        <div class="all-clear">
          <strong>Your library is clean.</strong>
          <p>No orphans, no overlap, no stale collections at the {staleThreshold}-day threshold.</p>
        </div>
      {/if}

      <!-- Orphans -->
      <section>
        <header class="section-header">
          <span class="section-title">Orphans</span>
          <span class="badge">{data.orphans.length}</span>
        </header>
        {#if data.orphans.length === 0}
          <p class="empty">Every indexed file belongs to at least one collection.</p>
        {:else}
          <ul class="list">
            {#each data.orphans as o (o.path)}
              <li class="row">
                <div class="row-main">
                  <span class="row-name">{o.filename}</span>
                  <span class="row-meta">
                    {#if o.game_system && o.game_system !== 'unknown'}{o.game_system}{:else}untagged{/if}
                    {#if o.size_bytes}<span class="dot">·</span>{formatBytes(o.size_bytes)}{/if}
                  </span>
                </div>
                <div class="row-actions">
                  <button
                    class="action-btn"
                    on:click={() => { openOrphanPicker = openOrphanPicker === o.path ? null : o.path; }}
                    disabled={!hasCollectionsToPick}
                    title={hasCollectionsToPick ? 'Add to collection…' : 'Create a collection first'}
                  >
                    + Add to…
                  </button>
                  {#if openOrphanPicker === o.path}
                    <div class="picker">
                      {#each collectionList as col}
                        <button
                          class="picker-item"
                          on:click={() => pickForOrphan(o, col.name)}
                        >{col.name}</button>
                      {/each}
                    </div>
                  {/if}
                </div>
              </li>
            {/each}
          </ul>
        {/if}
      </section>

      <!-- Anchors -->
      <section>
        <header class="section-header">
          <span class="section-title">Anchors</span>
          <span class="badge">{data.anchors.length}</span>
        </header>
        {#if data.anchors.length === 0}
          <p class="empty">No file appears in three or more collections.</p>
        {:else}
          <ul class="list">
            {#each data.anchors as a (a.path)}
              <li class="row">
                <div class="row-main">
                  <span class="row-name">{a.filename}</span>
                  <span class="row-meta" title={a.collections.join(', ')}>
                    in {a.count} collections — {a.collections.slice(0, 3).join(', ')}{a.collections.length > 3 ? `, +${a.collections.length - 3} more` : ''}
                  </span>
                </div>
                <span class="count-badge">{a.count}</span>
              </li>
            {/each}
          </ul>
        {/if}
      </section>

      <!-- Overlap -->
      <section>
        <header class="section-header">
          <span class="section-title">Overlap</span>
          <span class="badge">{data.overlap.length}</span>
        </header>
        {#if data.overlap.length === 0}
          <p class="empty">Collections don't share files yet.</p>
        {:else}
          <ul class="list">
            {#each data.overlap as p}
              <li class="row">
                <div class="row-main">
                  <span class="row-name">{p.a} ∩ {p.b}</span>
                  <span class="row-meta">{p.count} shared file{p.count === 1 ? '' : 's'}</span>
                </div>
                <span class="count-badge">{p.count}</span>
              </li>
            {/each}
          </ul>
        {/if}
      </section>

      <!-- Stale -->
      <section>
        <header class="section-header">
          <span class="section-title">Stale</span>
          <span class="badge">{staleEntries.dated.length}</span>
          <div class="threshold-pills">
            {#each STALE_THRESHOLDS as t}
              <button
                class="pill"
                class:on={staleThreshold === t}
                on:click={() => { staleThreshold = t; }}
              >{t}d</button>
            {/each}
          </div>
        </header>
        {#if staleEntries.dated.length === 0}
          <p class="empty">No collections older than {staleThreshold} days.</p>
        {:else}
          <ul class="list">
            {#each staleEntries.dated as s (s.name)}
              <li class="row">
                <div class="row-main">
                  <span class="row-name">{s.name}</span>
                  <span class="row-meta">
                    {relativeTime(s.last_used_at)}
                    <span class="dot">·</span>
                    {s.file_count} file{s.file_count === 1 ? '' : 's'}
                  </span>
                </div>
                <button
                  class="action-btn"
                  on:click={() => onArchiveStale(s.name)}
                  title="Archive"
                >Archive</button>
              </li>
            {/each}
          </ul>
        {/if}

        {#if staleEntries.neverUsed.length > 0}
          <button
            class="never-used-toggle"
            on:click={() => { showNeverUsed = !showNeverUsed; }}
          >
            {showNeverUsed ? '▾' : '▸'} Show never-used ({staleEntries.neverUsed.length})
          </button>
          {#if showNeverUsed}
            <ul class="list never-used-list">
              {#each staleEntries.neverUsed as s (s.name)}
                <li class="row">
                  <div class="row-main">
                    <span class="row-name">{s.name}</span>
                    <span class="row-meta">never used &middot; {s.file_count} file{s.file_count === 1 ? '' : 's'}</span>
                  </div>
                  <button
                    class="action-btn"
                    on:click={() => onArchiveStale(s.name)}
                    title="Archive"
                  >Archive</button>
                </li>
              {/each}
            </ul>
          {/if}
        {/if}
      </section>
    </div>
  </div>
</div>

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 320;
  }
  .dialog {
    background: var(--bg-focused);
    border: 1px solid var(--bg-category);
    border-radius: 6px;
    box-shadow: var(--shadow-dropdown);
    width: 560px;
    max-width: 90vw;
    max-height: 80vh;
    display: flex;
    flex-direction: column;
    font-family: var(--font-body);
  }
  .dialog-header {
    display: flex;
    align-items: center;
    padding: 0.6rem 0.9rem;
    border-bottom: 1px solid var(--bg-category);
  }
  .title {
    flex: 1;
    font-family: var(--font-heading);
    font-size: 0.95rem;
    font-weight: 600;
    color: var(--text-accent);
  }
  .close-btn {
    background: none;
    border: none;
    color: var(--text-secondary);
    cursor: pointer;
    font-size: 1rem;
    padding: 0.2rem 0.4rem;
    line-height: 1;
  }
  .close-btn:hover { color: var(--text-primary); }

  .dialog-body {
    overflow-y: auto;
    padding: 0.5rem 0;
  }

  section {
    padding: 0.5rem 0.9rem 0.75rem;
    border-bottom: 1px solid var(--bg-container);
  }
  section:last-child { border-bottom: none; }

  .section-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.3rem;
  }
  .section-title {
    font-family: var(--font-heading);
    color: var(--text-primary);
    font-size: 0.85rem;
    font-weight: 600;
  }
  .badge {
    font-size: 0.7rem;
    padding: 0.05rem 0.35rem;
    border-radius: 8px;
    background: var(--bg-container);
    color: var(--text-secondary);
  }

  .threshold-pills {
    display: flex;
    gap: 0.2rem;
    margin-left: auto;
  }
  .pill {
    padding: 0.1rem 0.45rem;
    background: transparent;
    border: 1px solid var(--bg-category);
    border-radius: 3px;
    color: var(--text-secondary);
    font-size: 0.7rem;
    cursor: pointer;
    font-family: var(--font-body);
  }
  .pill:hover { color: var(--text-primary); }
  .pill.on {
    color: var(--text-accent);
    border-color: var(--text-accent);
  }

  .list {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  .row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.3rem 0.1rem;
    font-size: 0.82rem;
    position: relative;
  }
  .row + .row { border-top: 1px solid var(--bg-container); }
  .row-main {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 0.05rem;
  }
  .row-name {
    color: var(--text-primary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .row-meta {
    color: var(--text-secondary);
    font-size: 0.72rem;
  }
  .dot {
    margin: 0 0.25rem;
    opacity: 0.6;
  }
  .count-badge {
    background: var(--bg-container);
    color: var(--text-accent);
    font-weight: 600;
    font-size: 0.75rem;
    padding: 0.1rem 0.45rem;
    border-radius: 8px;
  }

  .row-actions {
    position: relative;
  }
  .action-btn {
    padding: 0.2rem 0.55rem;
    background: transparent;
    border: 1px solid var(--bg-category);
    border-radius: 3px;
    color: var(--text-secondary);
    font-size: 0.75rem;
    cursor: pointer;
    font-family: var(--font-body);
  }
  .action-btn:hover:not(:disabled) {
    color: var(--text-accent);
    border-color: var(--text-accent);
  }
  .action-btn:disabled {
    opacity: 0.4;
    cursor: default;
  }

  .picker {
    position: absolute;
    right: 0;
    top: calc(100% + 4px);
    background: var(--bg-focused);
    border: 1px solid var(--bg-category);
    border-radius: 4px;
    box-shadow: var(--shadow-dropdown);
    max-height: 240px;
    overflow-y: auto;
    min-width: 160px;
    z-index: 5;
    padding: 0.15rem 0;
  }
  .picker-item {
    display: block;
    width: 100%;
    background: none;
    border: none;
    padding: 0.3rem 0.6rem;
    text-align: left;
    color: var(--text-primary);
    font-size: 0.8rem;
    font-family: var(--font-body);
    cursor: pointer;
  }
  .picker-item:hover {
    background: var(--bg-category);
  }

  .empty {
    margin: 0;
    color: var(--text-secondary);
    font-size: 0.78rem;
    font-style: italic;
  }

  .all-clear {
    padding: 0.7rem 0.9rem;
    margin: 0 0.9rem 0.5rem;
    border-radius: 4px;
    background: rgba(95, 176, 104, 0.12);
    border: 1px solid rgba(95, 176, 104, 0.4);
    color: var(--text-primary);
  }
  .all-clear strong { color: var(--text-accent); }
  .all-clear p {
    margin: 0.25rem 0 0;
    font-size: 0.78rem;
    color: var(--text-secondary);
  }

  .never-used-toggle {
    margin-top: 0.4rem;
    background: none;
    border: none;
    color: var(--text-secondary);
    font-size: 0.75rem;
    cursor: pointer;
    padding: 0.2rem 0;
    font-family: var(--font-body);
  }
  .never-used-toggle:hover { color: var(--text-primary); }
  .never-used-list {
    margin-top: 0.2rem;
  }
</style>
