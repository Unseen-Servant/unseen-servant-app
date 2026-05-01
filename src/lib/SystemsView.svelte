<script lang="ts">
  import { openPath } from '@tauri-apps/plugin-opener';
  import type { FileItem, FileStatusEntry } from './types';

  // Indexed file entries from indexStatus (up_to_date + to_update). Unindexed
  // files don't appear here on purpose — only indexed PDFs carry a system tag,
  // and grouping unindexed files under "Untagged" with no path-context would
  // be misleading.
  export let entries: FileStatusEntry[] = [];

  // Same scope/filter narrowing as the tree view. null = no narrowing.
  export let displayPaths: Set<string> | null = null;

  export let focusedFilePath: string | null = null;
  export let onFocusFile: (path: string | null) => void = () => {};
  export let onContextMenu: (event: MouseEvent, item: FileItem) => void = () => {};

  // Section collapse state — transient (not persisted).
  let collapsed = new Set<string>();

  $: groups = (() => {
    const byTag = new Map<string, FileStatusEntry[]>();
    for (const e of entries) {
      if (displayPaths && !displayPaths.has(e.path)) continue;
      const tag = e.game_system && e.game_system !== 'unknown' ? e.game_system : 'Untagged';
      const list = byTag.get(tag) ?? [];
      list.push(e);
      byTag.set(tag, list);
    }
    for (const list of byTag.values()) {
      list.sort((a, b) => a.filename.localeCompare(b.filename));
    }
    const known = [...byTag.keys()].filter((k) => k !== 'Untagged').sort();
    const out: { tag: string; entries: FileStatusEntry[] }[] = [];
    for (const tag of known) out.push({ tag, entries: byTag.get(tag)! });
    if (byTag.has('Untagged')) out.push({ tag: 'Untagged', entries: byTag.get('Untagged')! });
    return out;
  })();

  function toggleSection(tag: string) {
    if (collapsed.has(tag)) collapsed.delete(tag);
    else collapsed.add(tag);
    collapsed = collapsed;
  }

  function entryToFileItem(entry: FileStatusEntry): FileItem {
    return { name: entry.filename, path: entry.path, is_dir: false, children: null };
  }

  function handleRowClick(entry: FileStatusEntry) {
    onFocusFile(entry.path);
  }

  async function handleDoubleClick(entry: FileStatusEntry) {
    try {
      await openPath(entry.path);
    } catch (e) {
      console.error('Failed to open file:', e);
    }
  }

  function handleMouseDown(event: MouseEvent, entry: FileStatusEntry) {
    if (event.button === 2) {
      event.preventDefault();
      event.stopPropagation();
      onContextMenu(event, entryToFileItem(entry));
    }
  }

  function parentDir(path: string): string {
    const i = path.lastIndexOf('/');
    return i >= 0 ? path.slice(0, i) : '';
  }
</script>

{#if groups.length === 0}
  <div class="empty">No indexed files match the current view.</div>
{:else}
  <div class="systems-view">
    {#each groups as group (group.tag)}
      <section class="group">
        <button class="group-head" on:click={() => toggleSection(group.tag)}>
          <span class="group-arrow" aria-hidden="true">{collapsed.has(group.tag) ? '▸' : '▾'}</span>
          <span class="group-name">{group.tag}</span>
          <span class="group-count">{group.entries.length}</span>
        </button>
        {#if !collapsed.has(group.tag)}
          <ul class="group-files">
            {#each group.entries as entry (entry.path)}
              <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-noninteractive-element-interactions -->
              <li
                class="file"
                class:focused={focusedFilePath === entry.path}
                on:click={() => handleRowClick(entry)}
                on:dblclick={() => handleDoubleClick(entry)}
                on:mousedown={(e) => handleMouseDown(e, entry)}
              >
                <span class="file-name">{entry.filename}</span>
                <span class="file-path" title={entry.path}>{parentDir(entry.path)}</span>
              </li>
            {/each}
          </ul>
        {/if}
      </section>
    {/each}
  </div>
{/if}

<style>
  .systems-view {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
    padding: 0.25rem 0 1rem;
  }

  .group {
    display: flex;
    flex-direction: column;
  }

  .group-head {
    display: flex;
    align-items: baseline;
    gap: 0.4rem;
    padding: 0.3rem 0.25rem;
    background: none;
    border: none;
    cursor: pointer;
    text-align: left;
    font-family: var(--font-heading, var(--font-body));
    color: var(--text-accent);
    border-bottom: 1px solid var(--border-subtle);
    transition: color var(--transition-fast);
  }
  .group-head:hover {
    color: var(--text-primary);
  }
  .group-arrow {
    width: 0.8rem;
    color: var(--text-secondary);
    font-size: 0.7rem;
    flex-shrink: 0;
  }
  .group-name {
    flex: 1;
    font-size: 0.85rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }
  .group-count {
    font-size: 0.7rem;
    color: var(--text-secondary);
    font-variant-numeric: tabular-nums;
  }

  .group-files {
    list-style: none;
    margin: 0;
    padding: 0;
  }

  .file {
    display: flex;
    flex-direction: column;
    gap: 0.05rem;
    padding: 0.25rem 0.5rem 0.25rem 1.5rem;
    cursor: pointer;
    transition: background var(--transition-fast);
    -webkit-user-select: none;
    user-select: none;
  }
  .file:hover {
    background: var(--bg-focused);
  }
  .file.focused {
    background: var(--bg-focused);
  }
  .file-name {
    font-size: 0.85rem;
    color: var(--text-primary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .file-path {
    font-size: 0.7rem;
    color: var(--text-secondary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    direction: rtl;
    text-align: left;
  }

  .empty {
    padding: 0.6rem 0.75rem;
    color: var(--text-secondary);
    font-family: var(--font-body);
    font-size: 0.85rem;
  }
</style>
