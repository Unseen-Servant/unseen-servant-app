<script lang="ts">
  import type { CollectionInfo } from './types';
  import { CARET_RIGHT, CIRCLE, CIRCLE_RING, GEM } from '../ui/iconPaths';
  import { hoverLive } from '../ui/inputModality';
  import SystemBadge from './SystemBadge.svelte';
  import { PIGMENTS } from './palette';
  import { flushSync, onDestroy, tick } from 'svelte';
  import { chord, chordHint, isBareKeyChord, isDeleteChord, jumpEdge, keyShortcut, slotChord } from '../shell/keybindings';
  import { materializeKey } from '../shell/paneFocus';
  import { holdLatch } from '../ui/holdLatch';
  import { childNavKey, computeCollectionNav, parseNavKey, stepNavKey } from './collectionsNav';
  import { claimMenuSlot, menuSlotHeld, releaseMenuSlot } from '../shell/menuSlot';
  import { isTreePathsDrag, getTreePathsPayload, clearTreePathsPayload } from './dragPayload';
  import { clampToViewport } from '../ui/menuGeometry';
  import { orderCollections, transportNames } from './collectionOrder';

  export let collections: Record<string, CollectionInfo> = {};
  // Keyboard focus is lifted to +page.svelte so it can mutex against
  // focusedFilePath (only one region claims arrow keys at a time).
  export let focusedName: string | null = null;
  // This panel owns the arrow keys. Independent of focusedName: a click on
  // the panel's chrome activates it without ringing a row, and the first
  // arrow then materializes the caret.
  export let active = false;
  export let onActivate: () => void = () => {};
  // Where that first arrow lands — the page remembers the last row this pane
  // held, so pointing at the panel doesn't throw away the user's position.
  export let lastFocusedName: string | null = null;
  export let onFocusCollection: (name: string | null) => void = () => {};
  // Non-null while a new collection is being named. The ghost track at the
  // list's end turns into the name field; nothing exists until it's
  // committed, so backing out leaves nothing behind. Carries the suggested
  // name — a folder's, when the creation was seeded from one.
  export let creating: { name: string } | null = null;
  export let onCommitCreate: (name: string) => void = () => {};
  export let onCancelCreate: () => void = () => {};
  // Collection transport — names currently playing (armed into the
  // search scope). Several can play at once; while any plays, the
  // stopped rows dim out of scope.
  export let playingNames: Set<string> = new Set();
  // Collection mutes — names carved out of the mix (or the library,
  // when the transport is idle). Mute wins over play while lit; a
  // muted, playing row keeps its armed transport and contributes
  // nothing until unmuted. Archived rows keep M (no transport).
  export let mutedNames: Set<string> = new Set();
  export let onToggleMute: (name: string) => void = () => {};
  // The armed track — the one the file tree is currently curating into.
  // At most one, and never persisted across launches.
  export let armedName: string | null = null;
  export let onArm: (name: string) => void = () => {};
  // Rows dragged in from the file tree / systems view.
  export let onDropPaths: (name: string, paths: string[]) => void = () => {};
  export let onDropNewCollection: (paths: string[], label: string) => void = () => {};
  export let onRemoveFile: (name: string, path: string) => void = () => {};
  // ⌘O on a focused child row — the page owns the opener plugin.
  export let onOpenFile: (path: string) => void = () => {};
  // File path → game-system tags, for the badge on expanded file rows.
  export let gameSystemMap: Map<string, string[]> = new Map();
  // Sort state is lifted to +page for per-vault persistence.
  export let sortKey: 'custom' | 'name' | 'size' | 'created' = 'custom';
  export let customOrder: string[] = [];
  export let onDelete: (name: string) => void = () => {};
  export let onToggleArchived: (name: string, archived: boolean) => void = () => {};
  export let onCreate: () => void = () => {};
  export let onRename: (name: string, newName: string) => void = () => {};
  export let onSetColor: (name: string, color: string | null) => void = () => {};
  export let onTogglePlay: (name: string) => void = () => {};
  export let onSetSortKey: (key: 'custom' | 'name' | 'size' | 'created') => void = () => {};
  export let onReorder: (order: string[]) => void = () => {};
  // The search bar's @-pick, played out on these rows: the @-word's text
  // (null while there is none), the names it matches, and the one ↵ will
  // play. While it runs the panel shows the pick, not the mix — only
  // non-matches fade, and the badges turn into their ⌘N.
  export let pickQuery: string | null = null;
  export let pickMatches: string[] = [];
  export let pickCursor: string | null = null;

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

  // Which rows reveal their hover-summoned controls: a collection's
  // transport, and an expanded file row's remove mark. Deliberately not CSS
  // :hover — closing a context menu or ending a drag tears an element out
  // from under the pointer, and the browser then re-hit-tests and hovers
  // whatever is underneath without ever queueing the matching leave. The
  // row lit up and stayed lit, because no event was coming to clear it.
  // Latching on a real pointerenter can't go stale that way: if the enter
  // never fires the control simply stays hidden, and if it does fire the
  // pointer has somewhere to leave from. Painted only while $hoverLive, so
  // an arrow scrolling rows under a resting pointer doesn't light a second
  // row.
  let hoveredRowName: string | null = null;
  let hoveredChildPath: string | null = null;

  function clearHover() {
    hoveredRowName = null;
    hoveredChildPath = null;
  }

  function leaveRow(name: string) {
    if (hoveredRowName === name) hoveredRowName = null;
  }

  function leaveChild(path: string) {
    if (hoveredChildPath === path) hoveredChildPath = null;
  }

  // ------------------------------------------------------------------
  // Inline rename — R or double-click on a settled row. Naming a new
  // collection is a separate affordance (see the create box below), so
  // this only ever renames something that already exists.
  // ------------------------------------------------------------------
  let renamingName: string | null = null;
  let renameValue = '';

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

  // ------------------------------------------------------------------
  // Naming a new collection, in the box that offers it. Committing
  // promotes it to a real row in the list above; backing out creates
  // nothing, so a stray ⌘N costs nothing to undo.
  // ------------------------------------------------------------------
  let newValue = '';
  // Keyed on the seed object, not its name: asking to create again while
  // the box is open must reload the field, and two requests can carry the
  // same suggested name.
  let lastSeed: { name: string } | null = null;
  $: if (creating && creating !== lastSeed) {
    lastSeed = creating;
    newValue = creating.name;
  }

  function commitCreate() {
    if (creating === null) return;
    const trimmed = newValue.trim();
    // Blurring an untouched field is a way out, not a request for an
    // "Untitled". Committing one deliberately (Enter) still gets a name.
    if (trimmed) onCommitCreate(trimmed);
    else onCancelCreate();
  }

  function handleCreateKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter') {
      e.preventDefault();
      onCommitCreate(newValue.trim() || 'Untitled');
    } else if (e.key === 'Escape') {
      e.preventDefault();
      e.stopPropagation();
      onCancelCreate();
    }
  }

  function autofocusInput(node: HTMLInputElement) {
    node.focus();
    node.select();
  }

  // ------------------------------------------------------------------
  // Sorting + drag reorder
  // ------------------------------------------------------------------
  $: rows = orderCollections(
    showArchived ? Object.values(collections) : Object.values(collections).filter(c => !c.archived),
    sortKey,
    customOrder,
  );

  // Track-select slot per name (⌘1–9), for the play button's tooltip.
  $: slotOf = new Map(transportNames(Object.values(collections), sortKey, customOrder).slice(0, 9).map((n, i) => [n, i + 1]));

  $: picking = pickQuery !== null;
  $: pickSet = new Set(pickMatches);
  $: if (pickCursor) void scrollFocusedIntoView(pickCursor);

  $: archivedCount = Object.values(collections).filter(c => c.archived).length;
  $: hasNone = Object.keys(collections).length === 0;
  $: canDrag = sortKey === 'custom' && rows.length > 1;
  $: anyPlaying = playingNames.size > 0;

  // What the keyboard can land on: head rows, plus expanded children in
  // render order (collectionsNav mirrors the template the way filterRows
  // mirrors the filter panel's). The focus token stays one string —
  // child keys parse back with parseNavKey — so the page's pane mutex
  // carries it unchanged.
  $: navEntries = computeCollectionNav(
    rows.map((r) => r.name),
    expandedNames,
    (name) => (collections[name] ? childFiles(collections[name]).map((f) => f.path) : []),
  );

  // ⌘⌫ on a child row: point the caret at the next sibling (or the head
  // when the last file goes) before removing, so the keyboard never
  // strands on a key that no longer renders.
  function removeChildRow(name: string, path: string) {
    const siblings = navEntries.filter((e) => e.name === name && e.path !== null);
    const i = siblings.findIndex((e) => e.path === path);
    const next = siblings[i + 1] ?? siblings[i - 1];
    onFocusCollection(next ? next.key : name);
    onRemoveFile(name, path);
  }

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
    // A reorder drag starts on a row the pointer is already latched to, and
    // delivers no pointerleave while it runs — so by the time it ends the
    // list has resequenced under a pointer that never moved. Unlatch and
    // let the next real pointerenter decide.
    clearHover();
  }

  // ------------------------------------------------------------------
  // Dropping tree rows onto a collection.
  //
  // Two drags reach this panel: its own row reorder, and paths dragged in
  // from a browsing surface. They're told apart by the private MIME —
  // during dragover the browser blanks getData(), so `.types` is the only
  // thing readable. Reorder keeps its handlers on .row-container; path
  // drops sit on the wrapping <li>, which also makes the expanded child
  // list a target at no extra cost.
  // ------------------------------------------------------------------
  // Which target is lit: a collection name, or the ghost track.
  let dropIntoName: string | null = null;
  let dropIntoNew = false;
  // What a drop on the ghost track would make, read from the drag's payload
  // (set at dragstart, so it is readable mid-drag where getData() is not).
  let newDropPreview: { label: string; count: number } | null = null;

  function acceptPathDrag(e: DragEvent): boolean {
    if (!isTreePathsDrag(e.dataTransfer?.types)) return false;
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy';
    return true;
  }

  function handlePathDragOver(e: DragEvent, name: string | null) {
    if (!acceptPathDrag(e)) return;
    dropIntoName = name;
    dropIntoNew = false;
  }

  function handleNewDragOver(e: DragEvent) {
    if (!acceptPathDrag(e)) return;
    dropIntoNew = true;
    dropIntoName = null;
    const payload = getTreePathsPayload();
    newDropPreview = payload ? { label: payload.label, count: payload.paths.length } : null;
  }

  // dragover fires continuously over descendants, so only clear when the
  // pointer has genuinely left the target's subtree.
  function handlePathDragLeave(e: DragEvent) {
    const el = e.currentTarget as HTMLElement;
    if (el.contains(e.relatedTarget as Node | null)) return;
    dropIntoName = null;
    dropIntoNew = false;
  }

  function takePathDrop(e: DragEvent): string[] | null {
    if (!isTreePathsDrag(e.dataTransfer?.types)) return null;
    e.preventDefault();
    e.stopPropagation();
    dropIntoName = null;
    dropIntoNew = false;
    // A drag delivers no pointerleave, and the rows it just added shift the
    // list under a pointer that hasn't moved. Drop the latch and let the
    // next real pointerenter decide.
    clearHover();
    const payload = getTreePathsPayload();
    clearTreePathsPayload();
    return payload?.paths ?? null;
  }

  function handlePathDrop(e: DragEvent, name: string) {
    const paths = takePathDrop(e);
    if (paths) onDropPaths(name, paths);
  }

  function handleNewDrop(e: DragEvent) {
    if (!isTreePathsDrag(e.dataTransfer?.types)) return;
    e.preventDefault();
    e.stopPropagation();
    dropIntoNew = false;
    const payload = getTreePathsPayload();
    clearTreePathsPayload();
    if (payload) onDropNewCollection(payload.paths, payload.label);
  }

  // ------------------------------------------------------------------
  // Context menu (right-click a collection row): the transport first
  // (Arm / Play / Mute), then the track's properties (Gem ▸ / Rename /
  // Archive), then Delete. Same visual family as the file tree's
  // ContextMenu, scoped to what a collection can do.
  // ------------------------------------------------------------------
  let ctxMenu: { x: number; y: number; name: string } | null = null;
  let ctxPigmentOpen = false;
  let ctxPositioned = false;

  function openContextMenu(e: MouseEvent, name: string) {
    e.preventDefault();
    e.stopPropagation();
    // A second right-click has to mount a new menu: placeContextMenu runs
    // only as the menu mounts, so a reused one stayed hidden while still
    // holding the menu slot, and the arrow keys went nowhere.
    if (ctxMenu) {
      closeContextMenu();
      flushSync();
    }
    onFocusCollection(name);
    ctxPigmentOpen = false;
    ctxPositioned = false;
    ctxMenu = { x: e.clientX, y: e.clientY, name };
    claimMenuSlot(closeContextMenu);
  }

  // Runs as the menu mounts, while it is still hidden: the pointer says where
  // it wants to go, the measured box says where it can. Clamping against
  // declared sizes instead used to float the menu off the pointer.
  function placeContextMenu(node: HTMLElement) {
    if (!ctxMenu) return;
    const { x, y } = clampToViewport(
      { x: ctxMenu.x, y: ctxMenu.y },
      { width: node.offsetWidth, height: node.offsetHeight },
      { width: window.innerWidth, height: window.innerHeight },
    );
    ctxMenu = { ...ctxMenu, x, y };
    ctxPositioned = true;
  }

  function closeContextMenu() {
    ctxMenu = null;
    ctxPigmentOpen = false;
    releaseMenuSlot(closeContextMenu);
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

  // Enter as a row verb — unmodified, and not on a focused button, which
  // keeps its own activation (the row's P/M/E squares).
  function isPlainEnter(event: KeyboardEvent): boolean {
    if (event.key !== 'Enter' || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return false;
    return !(event.target as HTMLElement | null)?.closest('button, a[href], [role="button"]');
  }

  function handleWindowKey(event: KeyboardEvent) {
    // The context menu claims Esc before anything else.
    if (ctxMenu && event.key === 'Escape') {
      event.preventDefault();
      closeContextMenu();
      return;
    }
    if (sortMenuOpen && event.key === 'Escape') {
      event.preventDefault();
      closeSortMenu();
      return;
    }
    if (!active) return;
    // Yield to inline renames, the sort menu, the context menu, and any
    // other popover that may be claiming keys.
    if (renamingName !== null || creating !== null || sortMenuOpen || ctxMenu) return;
    if (menuSlotHeld()) return;
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

    const edge = jumpEdge(event);
    if (edge && navEntries.length > 0) {
      event.preventDefault();
      onFocusCollection(navEntries[edge === 'first' ? 0 : navEntries.length - 1].key);
      return;
    }

    // Active with no caret (the pane was claimed by a chrome click): the
    // first arrow places the caret rather than stepping, so it lands *on*
    // the restored row instead of one past it.
    if (focusedName === null && (isDown || isUp)) {
      event.preventDefault();
      const entry = materializeKey(navEntries.map((e) => e.key), lastFocusedName, isDown ? 1 : -1);
      if (entry) onFocusCollection(entry);
      return;
    }

    if (isDown) {
      event.preventDefault();
      const next = stepNavKey(navEntries, focusedName, 1);
      if (next) onFocusCollection(next);
      return;
    }
    if (isUp) {
      event.preventDefault();
      const prev = stepNavKey(navEntries, focusedName, -1);
      if (prev) onFocusCollection(prev);
      return;
    }

    // Handled before the idx-out-of-range early return so Esc still works
    // with the caret nowhere in particular.
    if (event.key === 'Escape') {
      event.preventDefault();
      // Leaving the arm comes before releasing focus: the mode has
      // rewired what a click in the tree does, so it's the louder thing
      // Esc should undo.
      if (armedName !== null) onArm(armedName);
      else onFocusCollection(null);
      return;
    }

    const parsed = focusedName === null ? null : parseNavKey(focusedName);
    if (parsed === null) return;

    // A child row answers with the file verbs; the collection verbs stay
    // on its head row. ⌘⌫ mirrors the hover × (membership only — the
    // file itself is untouched), and ← hops to the head the way the
    // tree's ← climbs to the parent.
    if (parsed.path !== null) {
      if (isDeleteChord(event)) {
        event.preventDefault();
        removeChildRow(parsed.name, parsed.path);
        return;
      }
      if ((meta && !event.shiftKey && !event.altKey && lk === 'o') || isPlainEnter(event)) {
        event.preventDefault();
        onOpenFile(parsed.path);
        return;
      }
      if (bareLetter && (event.key === 'ArrowLeft' || lk === 'h')) {
        event.preventDefault();
        onFocusCollection(parsed.name);
        return;
      }
      return;
    }

    const col = rows.find((r) => r.name === parsed.name);
    if (!col) return;

    // ⌘⌫ / Del — the same chord the file tree spends on deleting a row.
    // Raises the confirm dialog; nothing goes until it's answered.
    if (isDeleteChord(event)) {
      event.preventDefault();
      onDelete(col.name);
      return;
    }

    // Enter folds the head row either way, as it does a tree folder.
    if (isPlainEnter(event)) {
      event.preventDefault();
      toggleExpand(col.name);
      return;
    }
    if (bareLetter && (event.key === 'ArrowRight' || lk === 'l')) {
      event.preventDefault();
      if (!expandedNames.has(col.name)) {
        toggleExpand(col.name);
      } else {
        // Already open: → walks into the first file — the tree's
        // "expand folder / first child" grammar.
        const firstChild = navEntries.find((e) => e.name === col.name && e.path !== null);
        if (firstChild) onFocusCollection(firstChild.key);
      }
      return;
    }
    if (bareLetter && (event.key === 'ArrowLeft' || lk === 'h') && expandedNames.has(col.name)) {
      event.preventDefault();
      toggleExpand(col.name);
      return;
    }
    if (bareLetter) {
      // E for edit, not F: F reads as find/filter everywhere, and this app
      // already spends ⌘F on the Filters panel — one modifier apart from an
      // unrelated meaning is worse than no mnemonic at all. Not R either: R is
      // rename one pane over.
      if (lk === 'r') { event.preventDefault(); startRename(col.name); return; }
      // Arm is inert on a shelved track, same as play: neither the row's
      // button strip nor the context menu offers it there.
      if (lk === 'e') {
        event.preventDefault();
        if (!col.archived) onArm(col.name);
        return;
      }
      // P or Space toggle the transport — Space is the DAW play/stop
      // convention. A shelved track has no transport, so both are inert
      // until unarchived (Space still swallowed so the list doesn't scroll).
      if (lk === 'p' || lk === ' ') {
        event.preventDefault();
        if (event.repeat) return;
        // Keyed on lk, not 'p': Space is the other way to fire this, and
        // the release has to match whichever one is physically held.
        if (!col.archived) holdLatch.press(lk, () => onTogglePlay(col.name));
        return;
      }
      if (lk === 'm') {
        event.preventDefault();
        if (event.repeat) return;
        holdLatch.press('m', () => onToggleMute(col.name));
        return;
      }
      if (lk === 'a') { event.preventDefault(); onToggleArchived(col.name, !col.archived); return; }
    }
  }

  function toggleSortMenu() {
    if (sortMenuOpen) {
      closeSortMenu();
      return;
    }
    sortMenuOpen = true;
    claimMenuSlot(closeSortMenu);
  }

  function closeSortMenu() {
    sortMenuOpen = false;
    releaseMenuSlot(closeSortMenu);
  }

  function pickSort(value: typeof sortKey) {
    onSetSortKey(value);
    closeSortMenu();
  }

  // The dock can be closed with either menu still open — don't leave a menu
  // that no longer exists holding the slot.
  onDestroy(() => {
    releaseMenuSlot(closeSortMenu);
    releaseMenuSlot(closeContextMenu);
  });

  function handleWindowClick(event: MouseEvent) {
    if (ctxMenu) {
      closeContextMenu();
    }
    if (!sortMenuOpen) return;
    const target = event.target as Node;
    if (sortBtn && (sortBtn === target || sortBtn.contains(target))) return;
    closeSortMenu();
  }

  // A mousedown on the panel's empty or non-selectable space — the masthead,
  // the sort button, "+ collection", the gap below the last row — points at
  // the pane and deselects. Rows are skipped so their own click owns the
  // caret, and so starting a drag doesn't clear it. Guarded on there being
  // somewhere for the caret to go, so an empty panel doesn't silently swallow
  // the arrows.
  function handlePanelMousedown(event: MouseEvent) {
    if (rows.length === 0) return;
    const target = event.target as HTMLElement | null;
    if (target?.closest('[data-cp-row]')) return;
    onActivate();
  }

  // Exposed for the page-level Cmd+Alt+← jump. Restores `preferred` if
  // it's still in the navigable list — child keys included (matches user
  // expectation: "take me back to where I was"); otherwise falls back to
  // the first row.
  export function claim(preferred: string | null) {
    if (preferred && navEntries.some((e) => e.key === preferred)) {
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
<aside
  class="panel"
  on:mousedown={handlePanelMousedown}
  on:pointerleave={clearHover}
>
  <header class="panel-head nameplate">
    <span class="panel-name ledger-label">Collections</span>
    {#if picking}
      <!-- Echo of the bar's @-word: the panel is what it's searching. -->
      <span class="pick-echo" aria-hidden="true">@{pickQuery}</span>
    {:else}
    <div class="sort-wrapper">
      <button
        class="plate-btn"
        on:click|stopPropagation={toggleSortMenu}
        bind:this={sortBtn}
        title="Sort collections"
        aria-label="Sort collections"
        aria-haspopup="menu"
        aria-expanded={sortMenuOpen}
      >sort</button>
      {#if sortMenuOpen}
        <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
        <div class="sort-menu" role="menu" tabindex="-1" on:click|stopPropagation>
          {#each SORT_OPTIONS as opt}
            <button
              class="sort-item"
              role="menuitemradio"
              aria-checked={sortKey === opt.value}
              on:click={() => pickSort(opt.value)}
            >
              <span class="menu-pip" class:on={sortKey === opt.value} aria-hidden="true"></span>
              <span>{opt.label}</span>
            </button>
          {/each}
          {#if archivedCount > 0}
            <hr class="menu-divider" />
            <label class="sort-toggle" role="none">
              <span>Show archived</span>
              <input
                class="app-checkbox"
                type="checkbox"
                role="menuitemcheckbox"
                aria-checked={showArchived}
                bind:checked={showArchived}
              />
            </label>
          {/if}
        </div>
      {/if}
    </div>
    {/if}
  </header>

  <!-- No collections at all needs no message of its own: the ghost track
       below is the invitation. -->
  {#if !hasNone && rows.length === 0 && creating === null}
    <div class="empty">
      <span class="ledger-label">All archived</span>
    </div>
  {/if}

  <ul class="rows">
    {#each rows as col, i (col.name)}
      {@const isExpanded = expandedNames.has(col.name)}
      {@const playing = playingNames.has(col.name)}
      {@const muted = mutedNames.has(col.name)}
      {@const isRenamingRow = renamingName === col.name}
      {@const armed = armedName === col.name}
      <!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
      <li
        class="item"
        class:drop-into={dropIntoName === col.name}
        on:dragover={(e) => handlePathDragOver(e, col.name)}
        on:dragleave={handlePathDragLeave}
        on:drop={(e) => handlePathDrop(e, col.name)}
      >
        <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-noninteractive-element-interactions a11y-no-static-element-interactions -->
        <div
          class="row-container"
          class:hovered={$hoverLive && hoveredRowName === col.name}
          class:armed
          class:archived={col.archived}
          class:kb-focused={picking ? pickCursor === col.name : focusedName === col.name}
          class:playing
          class:dimmed={picking ? !pickSet.has(col.name) : !col.archived && (muted || (anyPlaying && !playing))}
          class:dragging={draggingName === col.name}
          class:drop-before={dropInsertIndex === i}
          class:drop-after={dropInsertIndex === i + 1 && i === rows.length - 1}
          title={col.description || col.name}
          data-cp-row={col.name}
          draggable={canDrag && !isRenamingRow}
          on:pointerenter={() => (hoveredRowName = col.name)}
          on:pointerleave={() => leaveRow(col.name)}
          on:dragstart={(e) => handleDragStart(e, col.name)}
          on:dragover={(e) => handleDragOver(e, i)}
          on:drop={handleDrop}
          on:dragend={handleDragEnd}
          on:click={(e) => {
            if (isRenamingRow) return;
            onFocusCollection(col.name);
            // The row is the disclosure: a click opens or closes its books.
            // Only the first click of a double-click toggles, so the second
            // doesn't undo it on the way into rename.
            if (e.detail <= 1) toggleExpand(col.name);
          }}
          on:dblclick={() => { if (!isRenamingRow) startRename(col.name); }}
          on:contextmenu={(e) => openContextMenu(e, col.name)}
        >
          <!-- The slot is reserved under every sort so the caret keeps its
               column when the sort changes; only custom order fills it. -->
          <span
            class="grip"
            class:filled={sortKey === 'custom'}
            title={sortKey === 'custom' ? 'Drag to reorder' : undefined}
            aria-hidden="true"
          >{sortKey === 'custom' ? '⠿' : ''}</span>
          {#if col.color}
            <!-- Pigment gem — this is where the color↔collection
                 mapping is taught; the same gem reappears in scope
                 chips and search-result index cells. -->
            <svg class="bkm" style={`color: ${col.color}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round" aria-hidden="true">
              <path d={GEM}/>
            </svg>
          {:else}
            <!-- Outline gem — uncolored, same grammar as the untagged shield -->
            <svg class="bkm" style="color: var(--text-tertiary)" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round" aria-hidden="true">
              <path d={GEM}/>
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
          {#if !isRenamingRow}
            <span class="tr" class:engaged={playing || muted || armed}>
              {#if !col.archived}
                <!-- Record-arm: point the file tree at this track. Purple
                     because it's a mode the user switched on; vermilion is
                     spoken for by mute and danger. -->
                <button
                  type="button"
                  class="tr-btn arm-btn"
                  class:armed
                  on:click|stopPropagation={() => onArm(col.name)}
                  aria-pressed={armed}
                  title={`${armed ? 'Disarm' : 'Arm'} ${col.name} (E)`}
                >
                  <svg class="arm-glyph" viewBox="64 64 512 512" fill="currentColor" aria-hidden="true"><path d={armed ? CIRCLE : CIRCLE_RING}/></svg>
                </button>
                <!-- Archived rows carry no transport — unarchive to play. -->
                <button
                  type="button"
                  class="tr-btn"
                  class:playing
                  on:click|stopPropagation={() => onTogglePlay(col.name)}
                  aria-pressed={playing}
                  title={`${playing ? 'Stop' : 'Play'} ${col.name} (P${slotOf.has(col.name) ? ` · ${slotChord(slotOf.get(col.name)!)}` : ''})`}
                >
                  {#if playing}
                    <span class="stop-mark" aria-hidden="true"></span>
                  {:else}
                    <!-- Font Awesome "play" icon (src/lib/ui/icons/play-solid-full.svg) -->
                    <svg viewBox="0 0 640 640" fill="currentColor" aria-hidden="true"><path d="M187.2 100.9C174.8 94.1 159.8 94.4 147.6 101.6C135.4 108.8 128 121.9 128 136L128 504C128 518.1 135.5 531.2 147.6 538.4C159.7 545.6 174.8 545.9 187.2 539.1L523.2 355.1C536 348.1 544 334.6 544 320C544 305.4 536 291.9 523.2 284.9L187.2 100.9z"/></svg>
                  {/if}
                </button>
              {/if}
              <button
                type="button"
                class="sm-btn"
                class:mute-on={muted}
                on:click|stopPropagation={() => onToggleMute(col.name)}
                aria-pressed={muted}
                title={muted ? `Unmute ${col.name} (M)` : `Mute ${col.name} (M)`}
              >M</button>
            </span>
          {/if}
          {#if picking && slotOf.has(col.name)}
            <span class="new-chord" aria-hidden="true">{slotChord(slotOf.get(col.name) ?? 0)}</span>
          {:else}
            <span class="row-count">{col.file_count}</span>
          {/if}
        </div>
        {#if isExpanded}
          {#each childFiles(col) as f (f.path)}
            {@const childKey = childNavKey(col.name, f.path)}
            <!-- svelte-ignore a11y-no-static-element-interactions a11y-click-events-have-key-events -->
            <div
              class="child-row"
              class:washed={playing && !muted}
              class:dimmed={picking ? !pickSet.has(col.name) : muted || (anyPlaying && !playing)}
              class:kb-focused={!picking && focusedName === childKey}
              title={f.path}
              data-cp-row={childKey}
              on:click={() => onFocusCollection(childKey)}
              on:pointerenter={() => (hoveredChildPath = f.path)}
              on:pointerleave={() => leaveChild(f.path)}
            >
              <span class="indent" aria-hidden="true"></span>
              <span class="child-name">{f.base}</span>
              {#if f.tag}
                <SystemBadge tag={f.tag} inline />
              {/if}
              <!-- This list is the only place a collection's contents are
                   enumerated, so it's where dropping one belongs. Keyed by
                   full path: two same-named PDFs render identical rows, and
                   removing by name would take the wrong one. -->
              <button
                type="button"
                class="child-remove"
                class:revealed={($hoverLive && hoveredChildPath === f.path) || focusedName === childKey}
                title={`Remove ${f.base} from ${col.name}${chordHint('collections.removeFile')}`}
                aria-label={`Remove ${f.base} from ${col.name}`}
                on:click|stopPropagation={() => onRemoveFile(col.name, f.path)}
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true">
                  <path d="M6 6l12 12M18 6L6 18"/>
                </svg>
              </button>
            </div>
          {/each}
          {#if col.file_paths.length === 0}
            <div class="child-row child-empty" class:washed={playing && !muted} class:dimmed={picking ? !pickSet.has(col.name) : muted || (anyPlaying && !playing)}>
              <span class="indent" aria-hidden="true"></span>
              <span class="child-name">No files yet</span>
            </div>
          {/if}
        {/if}
      </li>
    {/each}
  </ul>
  <!-- The ghost track: the next collection, waiting — a row's exact
       geometry drawn in outline, the way a DAW leaves an empty lane below
       its last track. Outside the scroll container, so it trails the last
       row while the list is short and stays in view once it overflows.
       Click, ⌘N, a drop or a folder's "New collection" all turn it into the
       row it will become, in place; nothing exists until that's committed,
       so Esc costs nothing. -->
  {#if creating !== null}
    <div class="row-container ghost naming">
      <span class="grip" aria-hidden="true"></span>
      <svg class="bkm" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round" aria-hidden="true">
        <path d={GEM}/>
      </svg>
      <input
        class="new-coll-input"
        bind:value={newValue}
        placeholder="Collection name&hellip;"
        aria-label="Name the new collection"
        on:keydown={handleCreateKeydown}
        on:blur={commitCreate}
        use:autofocusInput
      />
      <!-- A new collection lands armed: say so before it exists. Not a
           control — the real arm button arrives with the row. -->
      <span class="tr-btn arm-btn armed ghost-arm" aria-hidden="true">
        <svg class="arm-glyph" viewBox="64 64 512 512" fill="currentColor"><path d={CIRCLE}/></svg>
      </span>
    </div>
    <div class="ghost-keys micro-label" aria-hidden="true">
      <span><kbd>↵</kbd> create</span><span><kbd>esc</kbd> back</span>
    </div>
  {:else}
    <button
      class="row-container ghost"
      class:drop-into={dropIntoNew}
      on:click={onCreate}
      on:dragover={handleNewDragOver}
      on:dragleave={handlePathDragLeave}
      on:drop={handleNewDrop}
      title={`New collection${chordHint('collections.new')} — or drop books here`}
      aria-keyshortcuts={keyShortcut('collections.new') || undefined}
    >
      <span class="grip" aria-hidden="true"></span>
      <svg class="bkm" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round" aria-hidden="true">
        <path d={GEM}/>
      </svg>
      {#if dropIntoNew && newDropPreview}
        <!-- Under a drag, say what the drop will make. -->
        <span class="ghost-label">New collection from <em>{newDropPreview.label}</em></span>
        <span class="row-count">{newDropPreview.count}</span>
      {:else}
        <span class="ghost-label">New collection</span>
        <span class="new-chord" aria-hidden="true">{chord('collections.new')}</span>
      {/if}
    </button>
    {#if hasNone}
      <div class="empty"><span class="ledger-label">or drag books here from the tree</span></div>
    {/if}
  {/if}
</aside>

{#if ctxMenu}
  {@const col = collections[ctxMenu.name]}
  <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
  <div
    class="context-menu"
    role="menu"
    tabindex="-1"
    use:placeContextMenu
    style={`left: ${ctxMenu.x}px; top: ${ctxMenu.y}px; visibility: ${ctxPositioned ? 'visible' : 'hidden'}`}
    on:click|stopPropagation
    on:contextmenu|preventDefault|stopPropagation
  >
    <!-- Shelved tracks carry no transport, same as the row's button strip —
         unarchive to arm or play. Mute stays: it works on archived rows too. -->
    {#if !col?.archived}
      <button class="context-item" role="menuitem" on:click={() => ctxAction(onArm)}>
        {armedName === ctxMenu.name ? 'Disarm' : 'Arm'}
        <span class="menu-chord" class:bare={isBareKeyChord('collections.arm')} aria-hidden="true">{chord('collections.arm')}</span>
      </button>
      <button class="context-item" role="menuitem" on:click={() => ctxAction(onTogglePlay)}>
        {playingNames.has(ctxMenu.name) ? 'Stop' : 'Play'}
        <span class="menu-chord" class:bare={isBareKeyChord('collections.play')} aria-hidden="true">{chord('collections.play')}</span>
      </button>
    {/if}
    <button class="context-item" role="menuitem" on:click={() => ctxAction(onToggleMute)}>
      {mutedNames.has(ctxMenu.name) ? 'Unmute' : 'Mute'}
      <span class="menu-chord" class:bare={isBareKeyChord('collections.mute')} aria-hidden="true">{chord('collections.mute')}</span>
    </button>
    <hr class="menu-divider" />
    <div
      class="context-item has-submenu"
      class:open={ctxPigmentOpen}
      on:mouseenter={() => { ctxPigmentOpen = true; }}
      on:mouseleave={() => { ctxPigmentOpen = false; }}
      on:click={() => { ctxPigmentOpen = !ctxPigmentOpen; }}
      role="menuitem"
      tabindex="-1"
      aria-haspopup="menu"
      aria-expanded={ctxPigmentOpen}
    >
      <!-- "Gem" names the glyph the user sees; the palette entries behind
           it stay pigments in code. -->
      <span>Gem</span>
      <svg class="caret submenu-caret" viewBox="96 64 512 512" fill="currentColor" aria-hidden="true"><path d={CARET_RIGHT}/></svg>
      {#if ctxPigmentOpen}
        <div class="submenu" role="menu">
          {#each PIGMENTS as pig (pig.hex)}
            <button
              class="context-item"
              role="menuitemradio"
              aria-checked={col?.color === pig.hex}
              on:click|stopPropagation={() => ctxAction((name) => onSetColor(name, pig.hex))}
            >
              <span class="menu-pip" class:on={col?.color === pig.hex} aria-hidden="true"></span>
              <svg class="bkm" style={`color: ${pig.hex}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round" aria-hidden="true">
                <path d={GEM}/>
              </svg>
              <span>{pig.name}</span>
            </button>
          {/each}
          <hr class="menu-divider" />
          <button
            class="context-item"
            role="menuitemradio"
            aria-checked={!col?.color}
            on:click|stopPropagation={() => ctxAction((name) => onSetColor(name, null))}
          >
            <span class="menu-pip" class:on={!col?.color} aria-hidden="true"></span>
            <svg class="bkm" style="color: var(--text-tertiary)" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round" aria-hidden="true">
              <path d={GEM}/>
            </svg>
            <span>None</span>
          </button>
        </div>
      {/if}
    </div>
    <button class="context-item" role="menuitem" on:click={() => ctxAction(startRename)}>
      Rename collection
      <span class="menu-chord" class:bare={isBareKeyChord('collections.rename')} aria-hidden="true">{chord('collections.rename')}</span>
    </button>
    <button class="context-item" role="menuitem" on:click={() => ctxAction((name) => onToggleArchived(name, !col?.archived))}>
      {col?.archived ? 'Unarchive' : 'Archive'} collection
      <span class="menu-chord" class:bare={isBareKeyChord('collections.archive')} aria-hidden="true">{chord('collections.archive')}</span>
    </button>
    <hr class="menu-divider" />
    <!-- Display-only, like the tree menu's Reveal row: ⌘⌫ is a named key the
         menu's own dispatcher can't match, so it hints without claiming. -->
    <button class="context-item danger" role="menuitem" on:click={() => ctxAction(onDelete)}>
      Delete collection
      <span class="menu-chord" class:bare={isBareKeyChord('collections.delete')} aria-hidden="true">{chord('collections.delete')}</span>
    </button>
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
    /* Centred, not baseline-aligned, and padded like the scope bar: the
       plate's min-height sets the box, and the title sits in its middle
       the same way SCOPE does, instead of riding the mono control's
       taller line box off-centre. */
    align-items: center;
    gap: 0.5rem;
    padding: 0.3rem 0.75rem;
    margin-bottom: 0.3rem;
    flex-shrink: 0;
  }
  .panel-name {
    flex: 1;
  }

  /* Flex, not block: a block wrapper opens a line box at the panel's 16px
     body size, which made this plate taller than the filter panel's, whose
     control sits in the row directly. */
  .sort-wrapper {
    position: relative;
    display: flex;
  }
  /* Same voice as the plate's [sort], which it stands in for. */
  .pick-echo {
    font-family: var(--font-mono);
    font-size: 0.65rem;
    color: var(--text-accent);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .sort-menu {
    position: absolute;
    right: 0;
    top: calc(100% + 4px);
    background: var(--bg-container);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-dropdown);
    padding: 0.15rem 0;
    min-width: var(--menu-width);
    max-width: var(--menu-max-width);
    z-index: 200;
  }
  .sort-item {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    width: 100%;
    padding: 0.2rem 0.6rem;
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
    background: var(--bg-focused);
  }
  .menu-divider {
    margin: 0.15rem 0;
    border: none;
    border-top: 1px solid var(--border-subtle);
  }
  .sort-toggle {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.6rem;
    padding: 0.2rem 0.6rem;
    font-size: 0.8rem;
    color: var(--text-primary);
    cursor: pointer;
    transition: background var(--transition-fast);
  }
  .sort-toggle:hover {
    background: var(--bg-focused);
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
       of room, and the ghost track below it never leaves view. */
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
    /* Right gutter matches the filter panel's rows so the two panels'
       count readouts share a column down the dock. On the left, 0.25rem +
       the grip (0.55rem) + the gap (0.3rem) is the filter row's 1.1rem
       inset, so the gem lands in the same column as the filter panel's
       shields, with the grip in front of it. */
    padding: 0.22rem 0.75rem 0.22rem 0.25rem;
    /* Reserved for the solo rule so engaging S doesn't shift layout. */
    border-left: 3px solid transparent;
    cursor: pointer;
    transition: background var(--transition-fast);
    /* Shared with the filter panel's rows: above both panels' natural
       content height, so one number pins both to the same rhythm. */
    min-height: 30px;
  }
  .row-container.hovered {
    background: var(--bg-container);
  }
  /* Keyboard focus rings rather than fills, so the caret stays visible
     on a playing row instead of losing the background to it. */
  .row-container.kb-focused {
    box-shadow: var(--ring-focus);
  }
  /* Playing — armed into the search scope: parchment wash + purple rule,
     the same "this track is in the mix" grammar as the tree's solo. */
  .row-container.playing {
    background: color-mix(in srgb, var(--text-accent) 8%, transparent);
    border-left-color: var(--text-active);
  }
  /* While any collection plays, stopped rows dim to 45% (out of scope),
     never hidden. Hover restores legibility, mirroring the tree's muted
     rows. The transport stays full-strength — it's the way back in.
     The grip is excluded at rest so dimming doesn't override its
     hidden-until-hover opacity; the hover rule below still dims it. */
  .row-container.dimmed > :not(.tr):not(.grip) {
    opacity: var(--opacity-out-of-scope);
  }
  .row-container.dimmed.hovered > :not(.tr) {
    opacity: var(--opacity-out-of-scope-hover);
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

  /* Drag grip — fades in at the row's left edge on hover, custom order
     only. The slot itself is always in the markup, empty under the other
     sorts, so switching sort doesn't shift the caret's column. */
  .grip {
    width: 0.55rem;
    flex-shrink: 0;
    color: var(--text-tertiary);
    font-size: 0.7rem;
    letter-spacing: -0.05em;
    opacity: 0;
    transition: opacity var(--transition-fast);
  }
  /* Only the filled slot offers the grab — an empty spacer must not. */
  .grip.filled {
    cursor: grab;
  }
  .row-container.hovered .grip {
    opacity: 1;
  }

  /* The filter panel's shield size, so the two icon columns match. */
  .bkm {
    width: 0.8rem;
    height: 0.8rem;
    flex-shrink: 0;
    /* Tops the row's 0.3rem gap up to the filter rows' 0.45rem, so names
       start in one column down the dock. The gap itself stays 0.3rem: the
       grip-to-gem inset above depends on it. */
    margin-right: 0.15rem;
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

  /* LED count readout — the filter panel's channel count, same box, so a
     collection's size reads like a game system's. */
  .row-count {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    height: 18px;
    min-width: 18px;
    padding: 0 0.3rem;
    border-radius: var(--radius-sm);
    background: color-mix(in srgb, var(--text-tertiary) 18%, transparent);
    color: var(--text-secondary);
    font-size: 0.65rem;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    line-height: 1;
    flex-shrink: 0;
  }

  /* Transport — hidden at rest, revealed on row hover or keyboard
     focus, always visible while playing. One button per track: ▶ arms
     the collection into the search scope, the lit ■ stops it. */
  .tr {
    display: inline-flex;
    gap: 0.25rem;
    margin-left: auto;
    flex-shrink: 0;
    opacity: 0;
    transition: opacity var(--transition-fast);
  }
  .row-container.hovered .tr,
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
  /* Even sizes: a 9px glyph can't centre in the 16px interior on whole
     pixels (3.5px either side), so on a 1x screen the arm circle and the
     stop square sat half a pixel off their border. The arm circle draws
     at 8px (its viewBox is cropped to the circle) and the stop square is
     a 6px box. The ▶ stays 9px — it is deliberately off-centre (the
     optical centre of a triangle sits left of its box). */
  .tr-btn .arm-glyph {
    width: 8px;
    height: 8px;
  }
  .stop-mark {
    width: 6px;
    height: 6px;
    background: currentColor;
  }
  .tr-btn:hover {
    color: var(--text-secondary);
    border-color: var(--text-secondary);
  }
  .tr-btn:active {
    transform: scale(0.97);
  }
  .tr-btn.playing,
  .tr-btn.arm-btn.armed {
    color: var(--text-active);
    border-color: var(--text-active);
    background: color-mix(in srgb, var(--text-active) 15%, transparent);
    filter: var(--glow-active);
  }
  /* The armed row wears the same treatment the staged edit row does —
     one look for "this is the collection you're editing". */
  .row-container.armed {
    background: color-mix(in srgb, var(--text-accent) 25%, transparent);
    border-left-color: var(--text-active);
  }

  /* Expanded file rows — the collection's contents, indented under the
     folder row. A playing collection's files take the wash too. */
  .child-row {
    display: flex;
    align-items: center;
    gap: 0.3rem;
    padding: 0.18rem 0.75rem 0.18rem 0.75rem;
    border-left: 3px solid transparent;
    font-size: 0.9rem;
    color: var(--text-primary);
  }
  .child-row.washed {
    background: color-mix(in srgb, var(--text-accent) 8%, transparent);
  }
  .child-row.dimmed {
    opacity: var(--opacity-out-of-scope);
  }
  /* Same ring the head rows wear — children are peer stops for j/k now. */
  .child-row.kb-focused {
    box-shadow: var(--ring-focus);
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
    /* Takes the free width, pushing the capped system tag to the row's
       right edge beside the remove mark. */
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  /* Hover-revealed, same recipe as the row transport — but a bare stroked
     mark, not a boxed control: child rows carry no hardware. It sits in the
     count column (an 18px slot at the row's end, the collection row's count
     box above it), so every row in the panel ends on one edge. Tertiary
     when revealed, danger only under the pointer: color on intent, like a
     scope chip's ×, rather than a new hue arriving with a row hover. */
  .child-remove {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 18px;
    flex-shrink: 0;
    margin-left: auto;
    padding: 0;
    background: none;
    border: none;
    color: var(--text-tertiary);
    cursor: pointer;
    opacity: 0;
    transition: all var(--transition-fast);
  }
  .child-remove svg {
    width: 11px;
    height: 11px;
    display: block;
  }
  .child-remove.revealed {
    opacity: 1;
  }
  .child-remove:hover {
    color: var(--text-danger);
  }
  .child-remove:active {
    transform: scale(0.97);
  }

  /* The ghost track — the next collection, waiting. It wears .row-container,
     so it is a row's exact geometry, drawn in outline: a plain tertiary
     gem in the icon column (not dashed — dashes are Loose's, "in no
     collection", in the filter panel), an italic tertiary name, the ⌘N cap
     at its end. Hover is the rows' own grey step. */
  .ghost {
    width: 100%;
    flex-shrink: 0;
    background: none;
    border-top: none;
    border-right: none;
    border-bottom: none;
    font-family: var(--font-body);
    text-align: left;
    color: var(--text-tertiary);
  }
  .ghost:hover {
    background: var(--bg-container);
    color: var(--text-secondary);
  }
  .ghost-label {
    flex: 1;
    min-width: 0;
    font-size: 0.9rem;
    font-style: italic;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  /* Under a drag it says what the drop will make, framed in the app's
     dashed-parchment "prospective" outline. */
  .ghost.drop-into {
    outline: var(--outline-drop);
    outline-offset: -3px;
    background: color-mix(in srgb, var(--text-accent) 8%, transparent);
    color: var(--text-accent);
  }
  .ghost.drop-into .ghost-label {
    font-style: normal;
  }
  /* Naming in place: the slot already dresses as the row it will become —
     the armed wash and purple rule, and the caret's ring on the field. */
  .ghost.naming {
    cursor: default;
    background: color-mix(in srgb, var(--text-accent) 8%, transparent);
    border-left-color: var(--text-active);
    box-shadow: var(--ring-focus);
  }
  .new-coll-input {
    flex: 1;
    min-width: 0;
    -webkit-user-select: text;
    user-select: text;
    background: transparent;
    border: none;
    color: var(--text-primary);
    font-family: var(--font-body);
    font-size: 0.9rem;
    padding: 0;
    outline: none;
  }
  .new-coll-input::placeholder {
    color: var(--text-tertiary);
  }
  /* The arm the row will land with — purple ink, but no glow: a glow
     reports a state you switched on, and this one is only a promise until
     the name is committed (the rack-unit commit switch's rule). */
  .ghost-arm {
    cursor: default;
    filter: none;
  }
  /* Key hints under the naming row, starting in the name's column. */
  .ghost-keys {
    display: flex;
    gap: 0.75rem;
    padding: 0.2rem 0.75rem 0.35rem calc(3px + 1.1rem + 0.8rem + 0.3rem);
  }
  .ghost-keys kbd {
    font-family: var(--font-mono);
    letter-spacing: 0;
    text-transform: none;
    color: var(--text-secondary);
  }
  /* The same key cap as the search bar's ⌘K (Header.svelte .search-chord):
     a shortcut on a standing control reads as a cap, one in a menu row as
     plain text. */
  .new-chord {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 17px;
    height: 17px;
    padding: 0 4px;
    box-sizing: border-box;
    margin-left: auto;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    background: var(--bg-app);
    font-family: var(--font-body);
    font-size: 0.62rem;
    font-weight: 700;
    font-style: normal;
    color: var(--text-tertiary);
    flex-shrink: 0;
    white-space: nowrap;
    -webkit-user-select: none;
    user-select: none;
  }

  /* Drop target under a path drag. Dashed parchment reads as "this could
     become a member" and can't be confused with purple-armed, the engaged
     wash, or the reorder rules (which are inset box-shadows). Covers the
     expanded child list too, since that's part of the same target. */
  .item.drop-into {
    outline: var(--outline-drop);
    outline-offset: -1px;
    border-radius: var(--radius-sm);
    background: var(--bg-container);
  }

  /* Context menu — same visual family as the file tree's ContextMenu. */
  .context-menu {
    position: fixed;
    background: var(--bg-container);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-dropdown);
    min-width: var(--menu-width);
    max-width: var(--menu-max-width);
    padding: 0.15rem 0;
    z-index: 200;
    font-family: var(--font-body);
    font-size: 0.8rem;
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
    line-height: 1.3;
    font-family: var(--font-body);
    font-size: 0.8rem;
    color: var(--text-primary);
    transition: background var(--transition-fast);
  }
  .context-item:hover,
  .context-item.open {
    background: var(--bg-focused);
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
    background: var(--bg-container);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-dropdown);
    padding: 0.15rem 0;
    min-width: var(--submenu-width);
    max-width: var(--menu-max-width);
    z-index: 2;
  }

  .empty {
    padding: 0.3rem 0.75rem 0.5rem;
  }
</style>
