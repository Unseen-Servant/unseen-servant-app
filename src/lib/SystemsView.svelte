<script lang="ts">
  import { openPath } from '@tauri-apps/plugin-opener';
  import type { FileItem, FileStatusEntry, KnownGameSystem } from './types';

  // Indexed file entries from indexStatus (up_to_date + to_update). Unindexed
  // files don't appear here on purpose — only indexed PDFs carry a system tag,
  // and grouping unindexed files under "Untagged" with no path-context would
  // be misleading.
  export let entries: FileStatusEntry[] = [];

  // Same scope/filter narrowing as the tree view. null = no narrowing.
  export let displayPaths: Set<string> | null = null;

  // Library root path — used to render parent folders relative rather than
  // absolute. Empty string falls back to absolute paths.
  export let libraryRoot: string = '';

  // Known systems — used to look up each tag's accent color for group headers.
  export let knownSystems: KnownGameSystem[] = [];

  export let focusedFilePath: string | null = null;
  export let onFocusFile: (path: string | null) => void = () => {};
  export let onContextMenu: (event: MouseEvent, item: FileItem) => void = () => {};

  $: tagColors = (() => {
    const m = new Map<string, string>();
    for (const sys of knownSystems) {
      if (sys.color) m.set(sys.tag, sys.color);
    }
    return m;
  })();
  function colorFor(tag: string): string | null {
    return tagColors.get(tag) ?? null;
  }

  // Section collapse state — transient (not persisted).
  let collapsed = new Set<string>();

  $: groups = (() => {
    const byTag = new Map<string, FileStatusEntry[]>();
    for (const e of entries) {
      if (displayPaths && !displayPaths.has(e.path)) continue;
      const tags = e.game_systems && e.game_systems.length > 0
        ? e.game_systems
        : (e.game_system && e.game_system !== 'unknown' ? [e.game_system] : ['Untagged']);
      // A multi-tagged file appears under every group it belongs to.
      for (const tag of tags) {
        const list = byTag.get(tag) ?? [];
        list.push(e);
        byTag.set(tag, list);
      }
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

  function relativeParent(absPath: string): string {
    const i = absPath.lastIndexOf('/');
    if (i < 0) return '';
    const parent = absPath.slice(0, i);
    if (libraryRoot && parent.startsWith(libraryRoot + '/')) {
      return parent.slice(libraryRoot.length + 1) + '/';
    }
    if (libraryRoot && parent === libraryRoot) {
      return '/';
    }
    return parent;
  }

  // Compact "how long ago" formatter for the catalog metadata slot.
  // Drops the trailing "ago" since the column header carries that context.
  function formatRelativeShort(iso: string | undefined): string {
    if (!iso) return '';
    const seconds = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
    if (seconds < 60) return 'now';
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h`;
    const days = Math.floor(hours / 24);
    if (days < 30) return `${days}d`;
    const months = Math.floor(days / 30);
    if (months < 12) return `${months}mo`;
    const years = Math.floor(days / 365);
    return `${years}y`;
  }
</script>

{#if groups.length === 0}
  <div class="empty">No indexed files match the current view.</div>
{:else}
  <div class="systems-view">
    {#each groups as group (group.tag)}
      {@const groupColor = colorFor(group.tag)}
      <section class="group">
        <button
          class="group-head"
          style={groupColor ? `--group-color: ${groupColor}` : ''}
          on:click={() => toggleSection(group.tag)}
        >
          <span class="group-arrow" aria-hidden="true">{collapsed.has(group.tag) ? '▸' : '▾'}</span>
          {#if groupColor}
            <span class="group-dot" aria-hidden="true"></span>
          {/if}
          <span class="group-name">{group.tag}</span>
          <span class="group-count">{group.entries.length}</span>
        </button>
        {#if !collapsed.has(group.tag)}
          <ul class="group-files">
            {#each group.entries as entry (entry.path)}
              {@const relParent = relativeParent(entry.path)}
              <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-noninteractive-element-interactions -->
              <li
                class="file"
                class:focused={focusedFilePath === entry.path}
                on:click={() => handleRowClick(entry)}
                on:dblclick={() => handleDoubleClick(entry)}
                on:mousedown={(e) => handleMouseDown(e, entry)}
              >
                <span class="file-icon" aria-hidden="true">
                  <!-- Font Awesome "book" — matches collection rows -->
                  <svg viewBox="0 0 640 640" fill="currentColor">
                    <path d="M480 576L192 576C139 576 96 533 96 480L96 160C96 107 139 64 192 64L496 64C522.5 64 544 85.5 544 112L544 400C544 420.9 530.6 438.7 512 445.3L512 512C529.7 512 544 526.3 544 544C544 561.7 529.7 576 512 576L480 576zM192 448C174.3 448 160 462.3 160 480C160 497.7 174.3 512 192 512L448 512L448 448L192 448zM224 216C224 229.3 234.7 240 248 240L424 240C437.3 240 448 229.3 448 216C448 202.7 437.3 192 424 192L248 192C234.7 192 224 202.7 224 216zM248 288C234.7 288 224 298.7 224 312C224 325.3 234.7 336 248 336L424 336C437.3 336 448 325.3 448 312C448 298.7 437.3 288 424 288L248 288z"/>
                  </svg>
                </span>
                <span class="file-name">{entry.filename}</span>
                {#if relParent}
                  <span class="file-sep" aria-hidden="true">·</span>
                  <span class="file-path" title={entry.path}>{relParent}</span>
                {/if}
                {#if entry.indexed_at}
                  <span
                    class="file-meta"
                    title={`Indexed ${new Date(entry.indexed_at).toLocaleString()}`}
                  >
                    {formatRelativeShort(entry.indexed_at)}
                  </span>
                {/if}
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
    --group-color: var(--text-accent);
    display: flex;
    align-items: baseline;
    gap: 0.4rem;
    padding: 0.3rem 0.25rem;
    background: none;
    border: none;
    cursor: pointer;
    text-align: left;
    font-family: var(--font-heading, var(--font-body));
    color: var(--group-color);
    border-bottom: 1px solid color-mix(in srgb, var(--group-color) 35%, var(--border-subtle));
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
  .group-dot {
    width: 0.55rem;
    height: 0.55rem;
    border-radius: 50%;
    background: var(--group-color);
    flex-shrink: 0;
    align-self: center;
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
    align-items: baseline;
    gap: 0.4rem;
    padding: 0.25rem 0.75rem 0.25rem 1.5rem;
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
  .file-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    color: var(--text-accent);
    flex-shrink: 0;
    align-self: center;
  }
  .file-icon svg {
    width: 13px;
    height: 13px;
    display: block;
  }
  .file-name {
    font-size: 0.85rem;
    color: var(--text-primary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    flex-shrink: 1;
    min-width: 0;
  }
  .file-sep {
    color: var(--text-tertiary);
    font-size: 0.75rem;
    flex-shrink: 0;
  }
  .file-path {
    font-size: 0.75rem;
    color: var(--text-tertiary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    flex: 1;
    min-width: 0;
  }
  .file-meta {
    flex-shrink: 0;
    font-family: var(--font-mono, ui-monospace, monospace);
    font-size: 0.7rem;
    color: var(--text-secondary);
    font-variant-numeric: tabular-nums;
    margin-left: auto;
  }

  .empty {
    padding: 0.6rem 0.75rem;
    color: var(--text-secondary);
    font-family: var(--font-body);
    font-size: 0.85rem;
  }
</style>
