<script lang="ts">
  import { tick } from 'svelte';
  import { openPath } from '@tauri-apps/plugin-opener';
  import type { FileItem, FileStatusEntry } from './types';
  import { isPathOrAncestorIn } from './selectionUtils';
  import { UNTAGGED_KEY } from './searchScope';
  import { materializeKey } from './paneFocus';
  import { splitRibbons, EMPTY_RIBBONS, type Ribbon } from './collectionRibbons';
  import { groupMemberState, type MemberState } from './collectionMembership';
  import { writeTreePathsTransfer, clearTreePathsPayload, type TreePathsPayload } from './dragPayload';

  // File path → the collections holding it. Same strip as the file tree.
  export let ribbonIndex: Map<string, Ribbon[]> = new Map();

  // Same drag contract as the file tree: the page resolves the row to its
  // indexed paths and stashes the payload.
  export let onBeginDrag: (path: string, name: string, isDir: boolean) => TreePathsPayload | null =
    () => null;

  function handleDragStart(event: DragEvent, entry: FileStatusEntry) {
    const payload = onBeginDrag(entry.path, entry.filename, false);
    if (!payload || !event.dataTransfer) {
      event.preventDefault();
      return;
    }
    writeTreePathsTransfer(event.dataTransfer, payload);
  }

  // Indexed file entries from indexStatus (up_to_date + to_update). Unindexed
  // files don't appear here on purpose — only indexed PDFs carry a system tag,
  // and grouping unindexed files under "Untagged" with no path-context would
  // be misleading.
  export let entries: FileStatusEntry[] = [];

  // Same scope/filter narrowing as the tree view. null = no narrowing.
  export let displayPaths: Set<string> | null = null;

  // DAW-style channel state, shared with the filter menu. Muted (excluded)
  // groups stay visible but dim — hiding them would take the M button
  // with them. The opt-in focus lens is the exception: it drops dimmed
  // groups entirely; recovery lives in the filter console and the
  // scope-bar chips (console surfaces never hide).
  export let excludedSystems: Set<string> = new Set();
  export let soloedSystems: Set<string> = new Set();
  export let onToggleSystemFilter: (system: string) => void = () => {};
  export let onToggleSystemSolo: (system: string) => void = () => {};

  // Scope membership — see FileTree. null = no narrowing engaged.
  export let scopeBrightPaths: Set<string> | null = null;
  // Focus lens: dimmed groups drop from the render entirely.
  export let hideOutOfScope: boolean = false;

  // User-hidden paths (same set as the tree). Entries whose path is hidden
  // are dropped when `showHidden` is false; rendered with dimmed/italic
  // styling when `showHidden` is true.
  export let hiddenPaths: Set<string> = new Set();
  export let showHidden: boolean = false;

  // Library root path — used to render parent folders relative rather than
  // absolute. Empty string falls back to absolute paths.
  export let libraryRoot: string = '';

  export let focusedFilePath: string | null = null;
  // The file region owns the arrow keys. False while a dock pane holds them,
  // so ↓/↑ doesn't move the systems cursor too.
  export let active = false;
  // Where the caret lands when this pane is active but has none yet.
  export let lastFocusedPath: string | null = null;
  export let onFocusFile: (path: string | null) => void = () => {};
  export let onContextMenu: (event: MouseEvent, item: FileItem) => void = () => {};

  // Curation props. True while a collection is armed or a draft is being
  // shaped: rows render checkboxes and group headers carry a tri-state
  // "select all in group" toggle. All inert otherwise. The parent owns the
  // underlying Set and decides whether a change is staged or committed;
  // this view is purely additive/subtractive via these two callbacks.
  export let curating: boolean = false;
  export let collectionPaths: Set<string> = new Set();
  export let onCollectionAdd: (paths: string[]) => void = () => {};
  export let onCollectionRemove: (paths: string[]) => void = () => {};

  // Inline rename — mirrors FileTree's pattern. Set by the parent when
  // R is pressed on a focused row; the matching occurrence renders an
  // <input> in place of the filename. The input is gated to the focused
  // occurrence so a multi-tagged file doesn't grow editors in every
  // group it appears under.
  export let renamingFilePath: string | null = null;
  export let onRenameSubmit: (oldPath: string, newName: string, isDir: boolean) => void = () => {};
  export let onRenameCancel: () => void = () => {};

  // Whether the parent's context menu is open. Used to yield Esc handling
  // to ContextMenu's own keydown listener (so it can step submenu →
  // parent menu, then close), and to keep this view from clearing
  // focused-row state while the menu is open. State-based, not DOM-
  // queried, so the invariant doesn't depend on Svelte's DOM-update
  // timing.
  export let contextMenuOpen: boolean = false;

  // Anchor for shift-click range selection; bound to a group so a range
  // never crosses tag boundaries (would feel arbitrary in this view).
  let lastClickedPath: string | null = null;
  let lastClickedGroup: string | null = null;

  // Section collapse state — transient (not persisted).
  let collapsed = new Set<string>();

  $: groups = (() => {
    const byTag = new Map<string, FileStatusEntry[]>();
    for (const e of entries) {
      if (displayPaths && !displayPaths.has(e.path)) continue;
      if (!showHidden && isPathOrAncestorIn(e.path, hiddenPaths)) continue;
      const tags = e.game_systems && e.game_systems.length > 0
        ? e.game_systems
        : (e.game_system && e.game_system !== 'unknown' ? [e.game_system] : ['Untagged']);
      // A multi-tagged file appears under every group it belongs to.
      // Muted groups are kept (marked, dimmed below) — never hidden.
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
    const out: { tag: string; entries: FileStatusEntry[]; muted: boolean }[] = [];
    for (const tag of known) out.push({ tag, entries: byTag.get(tag)!, muted: excludedSystems.has(tag) });
    if (byTag.has('Untagged')) {
      out.push({ tag: 'Untagged', entries: byTag.get('Untagged')!, muted: excludedSystems.has(UNTAGGED_KEY) });
    }
    return out;
  })();

  function toggleSection(tag: string) {
    if (collapsed.has(tag)) collapsed.delete(tag);
    else collapsed.add(tag);
    collapsed = collapsed;
  }

  // One source of truth for the channel-dim rule — the template's
  // groupDimmed and the keyboard-nav model both call this; keep them
  // in sync through it, never by copy (same pattern as treeNav's
  // isRowOutOfScope).
  function isGroupDimmed(
    group: { muted: boolean; tag: string; entries: FileStatusEntry[] },
    soloed: Set<string>,
    bright: Set<string> | null
  ): boolean {
    return group.muted
      || (soloed.size > 0 && !soloed.has(group.tag))
      || (bright !== null && !group.entries.some((e) => bright.has(e.path)));
  }

  function entryToFileItem(entry: FileStatusEntry): FileItem {
    return { name: entry.filename, path: entry.path, is_dir: false, children: null };
  }

  function handleRowClick(
    event: MouseEvent,
    entry: FileStatusEntry,
    groupTag: string,
    groupEntries: FileStatusEntry[],
  ) {
    // In edit mode the row IS the checkbox — clicking anywhere on it
    // toggles inclusion (with shift-range support). Focus-on-click would
    // just be friction when curating a collection.
    if (curating) {
      handleCheckboxClick(event, entry, groupTag, groupEntries);
      return;
    }
    // Pin focusedIdx to the specific (path, tag) the user clicked so the
    // multi-occurrence case lands on the right row. The reactive sync
    // would otherwise pick the first match for an external focus change.
    const i = visibleEntries.findIndex((v) => v.path === entry.path && v.tag === groupTag);
    if (i >= 0) setFocusedIdx(i);
    else onFocusFile(entry.path);
  }

  async function openEntry(entry: FileStatusEntry) {
    try {
      await openPath(entry.path);
    } catch (e) {
      console.error('Failed to open file:', e);
    }
  }

  function handleDoubleClick(entry: FileStatusEntry) {
    // While curating the row's job is "tick to include", and a click has
    // already toggled it — opening on the second click would compete with
    // that. Space still opens, since it toggles nothing.
    if (curating) return;
    void openEntry(entry);
  }

  function handleMouseDown(event: MouseEvent, entry: FileStatusEntry) {
    if (event.button === 2) {
      event.preventDefault();
      event.stopPropagation();
      onContextMenu(event, entryToFileItem(entry));
    }
  }

  function handleCheckboxClick(
    event: MouseEvent,
    entry: FileStatusEntry,
    groupTag: string,
    groupEntries: FileStatusEntry[],
  ) {
    event.stopPropagation();
    const isCurrentlyIn = collectionPaths.has(entry.path);
    if (event.shiftKey && lastClickedPath && lastClickedGroup === groupTag) {
      const a = groupEntries.findIndex((e) => e.path === lastClickedPath);
      const b = groupEntries.findIndex((e) => e.path === entry.path);
      if (a !== -1 && b !== -1) {
        const lo = Math.min(a, b);
        const hi = Math.max(a, b);
        const range = groupEntries.slice(lo, hi + 1).map((e) => e.path);
        if (isCurrentlyIn) onCollectionRemove(range);
        else onCollectionAdd(range);
        lastClickedPath = entry.path;
        lastClickedGroup = groupTag;
        return;
      }
    }
    if (isCurrentlyIn) onCollectionRemove([entry.path]);
    else onCollectionAdd([entry.path]);
    lastClickedPath = entry.path;
    lastClickedGroup = groupTag;
  }

  // Per-system tri-state for the "select all" header.
  //
  // This has to be a reactive derivation, not a call in the template.
  // Svelte tracks the dependencies of the expression it sees, and a call
  // like groupSelectionState(group.entries) hides its read of
  // collectionPaths inside the function body — so the header latched at
  // whatever it showed when the group was last rebuilt, and unticking the
  // last file left the system still looking selected.
  const NO_GROUP_STATES = new Map<string, MemberState>();
  $: groupStates = curating
    ? new Map(groups.map((g) => [g.tag, groupMemberState(g.entries, collectionPaths)]))
    : NO_GROUP_STATES;

  function handleGroupCheckboxClick(event: MouseEvent, entries: FileStatusEntry[]) {
    event.stopPropagation();
    const paths = entries.map((e) => e.path);
    // Read membership now rather than trusting the rendered state.
    if (groupMemberState(entries, collectionPaths) === 'all') onCollectionRemove(paths);
    else onCollectionAdd(paths);
  }

  // Flat list of entries the user can keyboard-navigate to: every entry
  // from a non-collapsed group, in display order. A multi-tagged file
  // appears once per group it belongs to — same as the rendered list,
  // so ↓ walks visually adjacent rows. Mirrors the template's lens guard
  // via isGroupDimmed so nav and render never drift: a group the lens
  // drops is never focusable.
  $: visibleEntries = (() => {
    const out: { path: string; entry: FileStatusEntry; tag: string }[] = [];
    for (const g of groups) {
      if (collapsed.has(g.tag)) continue;
      if (hideOutOfScope && isGroupDimmed(g, soloedSystems, scopeBrightPaths)) continue;
      for (const e of g.entries) out.push({ path: e.path, entry: e, tag: g.tag });
    }
    return out;
  })();

  // focusedFilePath is shared with the tree view (one focus state for
  // global actions), but a multi-tagged file appears at multiple indices
  // here. Track the visible-entries index locally so ↓ from the second
  // occurrence steps to the next row, not back to "first occurrence + 1".
  let focusedIdx: number | null = null;

  // Reconcile focusedIdx when focusedFilePath changes externally (mouse
  // click that didn't go through us, page-level setter, etc.) or when
  // the visible list changes (group expand/collapse). For the multi-
  // occurrence case we land on the first match — moving down then walks
  // through subsequent occurrences naturally.
  $: {
    if (focusedFilePath === null) {
      focusedIdx = null;
    } else if (focusedIdx === null || visibleEntries[focusedIdx]?.path !== focusedFilePath) {
      const i = visibleEntries.findIndex((v) => v.path === focusedFilePath);
      focusedIdx = i >= 0 ? i : null;
    }
  }

  function isFocused(entry: FileStatusEntry, tag: string): boolean {
    if (focusedIdx === null) return false;
    const f = visibleEntries[focusedIdx];
    return f?.path === entry.path && f?.tag === tag;
  }

  function setFocusedIdx(i: number | null) {
    focusedIdx = i;
    onFocusFile(i === null ? null : visibleEntries[i]?.path ?? null);
  }

  $: if (focusedFilePath) scrollFocusedIntoView(focusedFilePath);
  async function scrollFocusedIntoView(path: string) {
    await tick();
    // When the same path appears multiple times, scroll the focused
    // index's row specifically rather than the first DOM match.
    const focused = focusedIdx !== null ? visibleEntries[focusedIdx] : null;
    if (focused) {
      const rows = document.querySelectorAll(`[data-sv-row="${CSS.escape(focused.path)}"]`);
      const target = rows[
        visibleEntries.slice(0, focusedIdx!).filter((v) => v.path === focused.path).length
      ];
      target?.scrollIntoView({ block: 'nearest' });
    } else {
      document.querySelector(`[data-sv-row="${CSS.escape(path)}"]`)?.scrollIntoView({ block: 'nearest' });
    }
  }

  function moveFocus(delta: number) {
    if (visibleEntries.length === 0) return;
    const cur = focusedIdx;
    // No caret yet — the region owns the arrows but nothing is ringed. Place
    // the caret rather than stepping, so the first press lands *on* the
    // restored entry instead of one past it.
    if (cur === null) {
      const entry = materializeKey(
        visibleEntries.map((v) => v.path),
        lastFocusedPath,
        delta > 0 ? 1 : -1,
      );
      const i = entry === null ? -1 : visibleEntries.findIndex((v) => v.path === entry);
      if (i >= 0) setFocusedIdx(i);
      return;
    }
    setFocusedIdx(Math.max(0, Math.min(visibleEntries.length - 1, cur + delta)));
  }

  function handleWindowKey(event: KeyboardEvent) {
    // Yield to the context menu via state — DOM checks for `.context-menu`
    // are racy because Svelte's reactive DOM updates flush in a microtask
    // after the synchronous handler chain. State is the source of truth.
    if (contextMenuOpen) return;
    // Yield to inputs, popovers, and any rename in flight elsewhere.
    if (document.querySelector('.filter-menu, .dropdown, .sort-menu')) return;
    // Yield to any open <dialog> — modal inerting doesn't suppress
    // window-level keydown listeners, so without this we'd nav behind it.
    if (document.querySelector('dialog[open]')) return;
    const target = event.target as HTMLElement | null;
    if (target?.matches('input, textarea, [contenteditable="true"]')) return;
    // Yield whenever a dock pane owns the arrows. Gating on the pane rather
    // than on a collection token also stops ↓ stealing the caret out of the
    // filter panel, which the old check never considered.
    if (!active) return;

    const meta = event.metaKey || event.ctrlKey;
    const lk = event.key.toLowerCase();
    const bareLetter = !meta && !event.shiftKey && !event.altKey;
    const isDown = event.key === 'ArrowDown' || (bareLetter && lk === 'j');
    const isUp   = event.key === 'ArrowUp'   || (bareLetter && lk === 'k');

    if (isDown) { event.preventDefault(); moveFocus(1);  return; }
    if (isUp)   { event.preventDefault(); moveFocus(-1); return; }

    if (event.key === 'Home' && !meta && visibleEntries[0]) {
      event.preventDefault();
      setFocusedIdx(0);
      return;
    }
    if (event.key === 'End' && !meta && visibleEntries.length > 0) {
      event.preventDefault();
      setFocusedIdx(visibleEntries.length - 1);
      return;
    }

    // Esc clears focus when a systems entry is focused. Skip otherwise so
    // we don't fight the page's Esc ladder (search, modals, etc.).
    if (event.key === 'Escape' && focusedIdx !== null) {
      event.preventDefault();
      setFocusedIdx(null);
      return;
    }

    if (focusedIdx === null) return;
    const focused = visibleEntries[focusedIdx];
    if (!focused) return;

    // S / M toggle solo / mute for the focused row's group — same
    // bare-letter guard as j/k. Untagged gets no solo (untagged files
    // never pass under solos) and mutes under the backend's key.
    if (bareLetter && lk === 's' && focused.tag !== 'Untagged') {
      event.preventDefault();
      onToggleSystemSolo(focused.tag);
      return;
    }
    if (bareLetter && lk === 'm') {
      event.preventDefault();
      onToggleSystemFilter(focused.tag === 'Untagged' ? UNTAGGED_KEY : focused.tag);
      return;
    }

    // Space is the row's primary action, same grammar as the tree and the
    // collection transport: open the PDF.
    if (event.key === ' ') {
      event.preventDefault();
      void openEntry(focused.entry);
      return;
    }

    // X ticks the row's checkbox — the tree spends the same key on its
    // indexing checkbox, so "X toggles the box you can see" holds in both
    // views. Left unhandled when there's no box to tick.
    if (bareLetter && lk === 'x' && curating) {
      event.preventDefault();
      handleCheckboxClick(
        { shiftKey: false, stopPropagation: () => {} } as MouseEvent,
        focused.entry,
        focused.tag,
        groups.find((g) => g.tag === focused.tag)?.entries ?? []
      );
      return;
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

  // Resolve the currently-focused entry as a FileItem so the parent's
  // shared action-key helper (R/F/./M/C/Cmd+O) can run against it
  // regardless of view mode. Returns null when nothing is focused or
  // the focused index is stale (mid-update). Indexed PDFs are always
  // leaves, so is_dir is hardcoded false.
  export function getFocusedItem(): FileItem | null {
    if (focusedIdx === null) return null;
    const v = visibleEntries[focusedIdx];
    return v ? entryToFileItem(v.entry) : null;
  }

  // Inline rename helpers. Enter commits with the extension preserved,
  // blur cancels. The page's global Escape ladder owns cancel (it nulls
  // renamingFilePath and returns before the focus-clear branch). On Esc
  // we additionally snap the scroll container back to its pre-unmount
  // scrollTop via a microtask — when Svelte unmounts the input, WebKit
  // reassigns DOM focus and resets the parent container's scrollTop,
  // bouncing the user back to the top.
  function handleRenameKeydown(event: KeyboardEvent, entry: FileStatusEntry) {
    if (event.key === 'Enter') {
      const input = event.currentTarget as HTMLInputElement;
      const ext = entry.filename.match(/\.[^.]+$/)?.[0] ?? '';
      onRenameSubmit(entry.path, input.value + ext, false);
    } else if (event.key === 'Escape') {
      // See FileTree.handleRenameKeydown for why two rAF rounds: WebKit
      // fires a delayed scroll reset ~2 frames after the input unmounts,
      // and a single rAF runs too early to overwrite it.
      const scroller = (event.currentTarget as HTMLElement).closest('.file-tree-area') as HTMLElement | null;
      if (scroller) {
        const saved = scroller.scrollTop;
        const restore = () => { scroller.scrollTop = saved; };
        requestAnimationFrame(restore);
        requestAnimationFrame(() => requestAnimationFrame(restore));
      }
    }
  }
  function autofocus(node: HTMLInputElement) {
    // preventScroll mirrors FileTree's autofocus — R is pressed on a
    // focused (visible) row, so focus()'s default scroll-into-view is
    // both unnecessary and the source of drift on Esc-cancel.
    node.focus({ preventScroll: true });
    node.select();
  }

  // The Cmd+Alt+→ jump: passing a path restores that entry when it's still
  // visible (multi-tagged files land on the first occurrence and ↓ walks the
  // rest), otherwise we fall back to the first visible entry. Chrome clicks
  // do NOT come through here — they only activate the pane, via the parent's
  // .file-tree-area mousedown, and leave the caret for the first arrow.
  export function claim(preferred: string | null = null) {
    if (focusedFilePath !== null) return;
    if (visibleEntries.length === 0) return;
    if (preferred) {
      const i = visibleEntries.findIndex((v) => v.path === preferred);
      if (i >= 0) { setFocusedIdx(i); return; }
    }
    setFocusedIdx(0);
  }
</script>

<svelte:window on:keydown={handleWindowKey} />

{#if groups.length === 0}
  <div class="empty">No indexed files match the current view.</div>
{:else}
  <div class="systems-view">
    {#each groups as group (group.tag)}
      {@const groupState = groupStates.get(group.tag) ?? 'none'}
      {@const smLabel = group.tag === 'Untagged' ? 'untagged files' : group.tag}
      {@const groupDimmed = isGroupDimmed(group, soloedSystems, scopeBrightPaths)}
      {#if !(hideOutOfScope && groupDimmed)}
      <section class="group">
        <div class="group-head-row" class:untagged={group.tag === 'Untagged'}>
          {#if curating}
            <button
              class="app-checkbox group-checkbox"
              on:click={(e) => handleGroupCheckboxClick(e, group.entries)}
              role="checkbox"
              aria-label="Select all in {group.tag}"
              aria-checked={groupState === 'some' ? 'mixed' : groupState === 'all'}
            ></button>
          {/if}
          <button
            class="group-head"
            on:click={() => toggleSection(group.tag)}
          >
            <span class="group-arrow" aria-hidden="true">{collapsed.has(group.tag) ? '▸' : '▾'}</span>
            {#if group.tag !== 'Untagged'}
              <span class="group-icon" aria-hidden="true">
                <!-- Font Awesome "dice-d6" -->
                <svg viewBox="0 0 640 640" fill="currentColor">
                  <path d="M288.4 72.3C308 61.2 332 61.2 351.6 72.3L527.6 172C547.6 183.4 560 204.6 560 227.7L560 425.1C560 448.1 547.6 469.4 527.6 480.8L351.6 580.5C332 591.6 308 591.6 288.5 580.5L112.5 480.8C92.4 469.5 80 448.2 80 425.2L80 227.8C80 204.8 92.4 183.5 112.4 172.1L288.4 72.4zM166.6 219.6C157.8 216.5 147.8 219.9 142.8 228.2C137.8 236.5 139.6 246.9 146.4 253.2L149.6 255.6L299.8 345.8L299.8 494.5C299.8 505.5 308.8 514.5 319.8 514.5C330.8 514.5 339.8 505.5 339.8 494.5L339.8 345.8L490.1 255.6C499.6 249.9 502.7 237.6 497 228.2C491.3 218.8 479 215.7 469.6 221.3L319.9 311.1L170.2 221.3L166.5 219.6z"/>
                </svg>
              </span>
            {:else}
              <span class="group-icon" aria-hidden="true">
                <!-- Outline die: the untagged bucket is a placeholder, not an identity -->
                <svg viewBox="0 0 640 640" fill="none" stroke="currentColor" stroke-width="40" stroke-linejoin="round" stroke-linecap="round">
                  <path d="M320 76 L548 206 L548 434 L320 564 L92 434 L92 206 Z"/>
                  <path d="M92 206 L320 336 L548 206"/>
                  <path d="M320 336 L320 564"/>
                </svg>
              </span>
            {/if}
            <span class="group-name ledger-label">{group.tag}</span>
          </button>
          <span class="sm" class:engaged={soloedSystems.has(group.tag) || group.muted}>
            {#if group.tag !== 'Untagged'}
              <button
                type="button"
                class="sm-btn"
                class:solo-on={soloedSystems.has(group.tag)}
                on:click|stopPropagation={() => onToggleSystemSolo(group.tag)}
                aria-pressed={soloedSystems.has(group.tag)}
                title={soloedSystems.has(group.tag) ? `Stop soloing ${group.tag} (S)` : `Solo ${group.tag} (S)`}
              >S</button>
            {/if}
            <button
              type="button"
              class="sm-btn"
              class:mute-on={group.muted}
              on:click|stopPropagation={() => onToggleSystemFilter(group.tag === 'Untagged' ? UNTAGGED_KEY : group.tag)}
              aria-pressed={group.muted}
              title={group.muted ? `Unmute ${smLabel} (M)` : `Mute ${smLabel} (M)`}
            >M</button>
          </span>
          <span class="group-count">{group.entries.length}</span>
        </div>
        {#if !collapsed.has(group.tag)}
          <ul class="group-files" class:dimmed={groupDimmed}>
            {#each group.entries as entry (entry.path)}
              {@const relParent = relativeParent(entry.path)}
              {@const isChecked = curating && collectionPaths.has(entry.path)}
              {@const ribbons = ribbonIndex.get(entry.path) ?? EMPTY_RIBBONS}
              {@const ribbonSplit = splitRibbons(ribbons)}
              <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-noninteractive-element-interactions -->
              <li
                class="file"
                class:focused={isFocused(entry, group.tag)}
                class:hidden-item={isPathOrAncestorIn(entry.path, hiddenPaths)}
                data-sv-row={entry.path}
                draggable={renamingFilePath !== entry.path}
                on:dragstart={(e) => handleDragStart(e, entry)}
                on:dragend={clearTreePathsPayload}
                on:click={(e) => handleRowClick(e, entry, group.tag, group.entries)}
                on:dblclick={() => handleDoubleClick(entry)}
                on:mousedown={(e) => handleMouseDown(e, entry)}
              >
                {#if curating}
                  <button
                    class="app-checkbox row-checkbox"
                    on:click={(e) => handleCheckboxClick(e, entry, group.tag, group.entries)}
                    on:mousedown|stopPropagation
                    on:dblclick|stopPropagation
                    role="checkbox"
                    aria-label="Add {entry.filename} to collection"
                    aria-checked={isChecked}
                  ></button>
                {/if}
                <span class="file-icon" aria-hidden="true">
                  <!-- Font Awesome "book" — matches collection rows -->
                  <svg viewBox="0 0 640 640" fill="currentColor">
                    <path d="M480 576L192 576C139 576 96 533 96 480L96 160C96 107 139 64 192 64L496 64C522.5 64 544 85.5 544 112L544 400C544 420.9 530.6 438.7 512 445.3L512 512C529.7 512 544 526.3 544 544C544 561.7 529.7 576 512 576L480 576zM192 448C174.3 448 160 462.3 160 480C160 497.7 174.3 512 192 512L448 512L448 448L192 448zM224 216C224 229.3 234.7 240 248 240L424 240C437.3 240 448 229.3 448 216C448 202.7 437.3 192 424 192L248 192C234.7 192 224 202.7 224 216zM248 288C234.7 288 224 298.7 224 312C224 325.3 234.7 336 248 336L424 336C437.3 336 448 325.3 448 312C448 298.7 437.3 288 424 288L248 288z"/>
                  </svg>
                </span>
                {#if renamingFilePath === entry.path && isFocused(entry, group.tag)}
                  <input
                    class="rename-input"
                    value={entry.filename.replace(/\.[^.]+$/, '')}
                    on:click|stopPropagation
                    on:mousedown|stopPropagation
                    on:keydown={(e) => handleRenameKeydown(e, entry)}
                    on:blur={onRenameCancel}
                    use:autofocus
                  />
                {:else}
                  <span class="file-name">{entry.filename}</span>
                {/if}
                {#if relParent}
                  <span class="file-sep" aria-hidden="true">·</span>
                  <span class="file-path" title={entry.path}>{relParent}</span>
                {/if}
                {#if ribbons.length > 0}
                  <span class="ribbons" title={ribbons.map((r) => r.name).join(', ')}>
                    {#each ribbonSplit.shown as r (r.name)}
                      <svg class="ribbon" style={`color: ${r.color}`} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                        <path d="M5 2h14v20l-7-5.2L5 22z"/>
                      </svg>
                    {/each}
                    {#if ribbonSplit.overflow > 0}
                      <span class="ribbon-overflow">+{ribbonSplit.overflow}</span>
                    {/if}
                  </span>
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
      {/if}
    {/each}
    {#if hideOutOfScope && groups.length > 0 && groups.every((g) => isGroupDimmed(g, soloedSystems, scopeBrightPaths))}
      <div class="empty">Everything is out of scope.</div>
    {/if}
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

  /* Headers are monochrome — parchment name + die sigil; color belongs
     to collections. */
  .group-head-row {
    --group-color: var(--text-accent);
    display: flex;
    align-items: center;
    gap: 0.4rem;
    border-bottom: 1px solid var(--border-subtle);
  }
  /* The untagged bucket is a bucket, not an identity: grey, never the
     parchment fallback that uncolored real systems get. */
  .group-head-row.untagged {
    --group-color: var(--text-tertiary);
  }
  .group-head {
    flex: 1;
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
  .group-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    color: var(--group-color);
    align-self: center;
  }
  .group-icon svg {
    width: 0.85rem;
    height: 0.85rem;
    display: block;
  }
  .group-name {
    flex: 1;
    color: inherit;
  }

  /* S/M cluster — hidden at rest, revealed on header hover or keyboard
     focus, always visible while engaged. Button anatomy is the shared
     .sm-btn in app.css. */
  .sm {
    display: inline-flex;
    gap: 0.25rem;
    align-self: center;
    opacity: 0;
    transition: opacity var(--transition-fast);
  }
  .group-head-row:hover .sm,
  .group-head-row:focus-within .sm,
  .sm.engaged {
    opacity: 1;
  }

  /* The count is the cluster's LED readout: same 18px height as the S/M
     buttons but inverted anatomy (filled, borderless) so it can't be
     mistaken for a third switch. */
  .group-count {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    align-self: center;
    height: 18px;
    min-width: 18px;
    padding: 0 0.3rem;
    margin-right: 0.25rem;
    border-radius: var(--radius-sm);
    background: color-mix(in srgb, var(--text-tertiary) 18%, transparent);
    color: var(--text-secondary);
    font-family: var(--font-body);
    font-size: 0.65rem;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    line-height: 1;
  }

  .group-files {
    list-style: none;
    margin: 0;
    padding: 0;
  }

  /* Muted groups (and non-soloed groups while a solo is active) dim but
     stay visible — a muted channel never disappears from the mixer.
     Hover restores legibility, mirroring the filter menu's row-dimmed. */
  .group-files.dimmed {
    opacity: var(--opacity-out-of-scope);
    transition: opacity var(--transition-fast);
  }
  .group-files.dimmed:hover {
    opacity: var(--opacity-out-of-scope-hover);
  }

  /* Edit-mode selection is a mode the user switched on, so these boxes take
     --text-active rather than the shared recipe's --text-accent. Anatomy and
     both knockout glyphs come from .app-checkbox. */
  .app-checkbox {
    align-self: center;
  }
  .app-checkbox:hover {
    border-color: var(--text-active);
  }
  .app-checkbox[aria-checked="true"],
  .app-checkbox[aria-checked="mixed"] {
    background-color: var(--text-active);
    border-color: var(--text-active);
  }
  .group-checkbox {
    margin-left: 0.25rem;
  }
  .row-checkbox {
    margin-right: 0.1rem;
  }

  .file {
    display: flex;
    align-items: baseline;
    gap: 0.4rem;
    padding: 0.25rem 0.75rem 0.25rem 1.5rem;
    margin: 0 0.25rem;
    border-radius: var(--radius-sm);
    cursor: pointer;
    transition: background var(--transition-fast);
    -webkit-user-select: none;
    user-select: none;
  }
  .file:hover {
    background: var(--bg-container);
  }
  .file.focused {
    box-shadow: var(--ring-focus);
  }
  /* Hidden via the user's hide flag — only rendered when "Show hidden" is on.
     Italic + dimmed so it reads as "explicitly suppressed", matching the
     tree-view treatment. */
  .file.hidden-item {
    opacity: 0.55;
  }
  .file.hidden-item .file-name {
    font-style: italic;
  }
  .file-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    color: var(--text-secondary);
    flex-shrink: 0;
    align-self: center;
  }
  .file-icon svg {
    width: 13px;
    height: 13px;
    display: block;
  }
  .file-name {
    font-size: 0.9rem;
    color: var(--text-primary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    flex-shrink: 1;
    min-width: 0;
  }
  .rename-input {
    flex: 1;
    min-width: 0;
    background: var(--bg-container);
    color: var(--text-primary);
    border: 1px solid var(--text-accent);
    border-radius: var(--radius-sm);
    padding: 0.1rem 0.3rem;
    font-size: 0.9rem;
    font-family: var(--font-body);
    outline: none;
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
  /* Sits just left of the indexed-at readout, which keeps the flush-right
     slot. Same strip, same recipe, as the file tree's. */
  .ribbons {
    display: inline-flex;
    align-items: center;
    gap: 0.15rem;
    margin-left: 0.5rem;
    flex-shrink: 0;
  }
  .ribbon {
    display: block;
    width: 10px;
    height: 10px;
  }
  .ribbon-overflow {
    display: inline-block;
    padding: 0.1rem 0.4rem;
    border-radius: var(--radius-sm);
    font-size: 0.75rem;
    font-family: var(--font-body);
    color: var(--text-secondary);
    background: color-mix(in srgb, var(--text-accent) 8%, transparent);
    white-space: nowrap;
  }

  .file-meta {
    flex-shrink: 0;
    font-family: var(--font-mono);
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
