<script lang="ts">
  import { onMount, onDestroy, tick } from 'svelte';
  import { invoke } from '@tauri-apps/api/core';
  import { listen } from '@tauri-apps/api/event';
  import { writeText } from '@tauri-apps/plugin-clipboard-manager';
  import { openPath, openUrl, revealItemInDir } from '@tauri-apps/plugin-opener';
  import { pdfFileUrl } from '../lib/pdfUrl';
  import { load } from '@tauri-apps/plugin-store';
  import type { FileItem, FileStatusEntry, IndexStatusResult, SyncResult, KnownGameSystem, KnownGameSystemsResult, StatsResult, CollectionInfo, CollectionsResult, CollectionMutationResult, SearchResultItem, SearchResponse, SyncPreferences, PromptCounts, SyncAction } from '../lib/types';
  import { DEFAULT_SYNC_PREFERENCES } from '../lib/types';
  import FileTree from '../lib/FileTree.svelte';
  import ContextMenu from '../lib/ContextMenu.svelte';
  import Header from '../lib/Header.svelte';
  import SearchResults from '../lib/SearchResults.svelte';
  import SearchInspector from '../lib/SearchInspector.svelte';
  import SearchScopeBar from '../lib/SearchScopeBar.svelte';
  import StatusBar from '../lib/StatusBar.svelte';
  import GettingStartedPage from '../lib/GettingStartedPage.svelte';
  import SettingsModal from '../lib/SettingsModal.svelte';
  import KeyboardHelpOverlay from '../lib/KeyboardHelpOverlay.svelte';
  import LaunchSplash from '../lib/LaunchSplash.svelte';
  import DocumentStatsModal from '../lib/DocumentStatsModal.svelte';
  import ConfirmDialog from '../lib/ConfirmDialog.svelte';
  import { confirmPrompt } from '../lib/confirmStore';
  import { holdLatch } from '../lib/holdLatch';
  import CollectionsPanel from '../lib/CollectionsPanel.svelte';
  import FilterPanel from '../lib/FilterPanel.svelte';
  import SystemsView from '../lib/SystemsView.svelte';
  import { jobNotification, pendingNotification } from '../lib/notificationStore';
  import { computeAncestorPaths, areAllDescendantsSelected, isPathOrAncestorIn } from '../lib/selectionUtils';
  import { computeVisibleRows, indexOfPath, rowHasIndexedMaterial, type VisibleRow } from '../lib/treeNav';
  import { materializeKey } from '../lib/paneFocus';
  import { resolveMix, resolveScopeSet, searchGameSystemsFilter, emptyScopeMessage, type CurationKey, type ScopeRef } from '../lib/searchScope';
  import { runSyncJob } from '../lib/syncJob';
  import {
    indexedPathsUnder,
    collectionsContaining,
    collectionsFullyContaining,
    uniqueCollectionName,
    computeFolderMembership,
    memberStateFor,
    addMembers,
    removeMembers,
  } from '../lib/collectionMembership';
  import { buildRibbonIndex, firstColorByPath } from '../lib/collectionRibbons';
  import { createCommitScheduler, mergeArmedCollection } from '../lib/collectionCommit';
  import { setTreePathsPayload, type TreePathsPayload } from '../lib/dragPayload';
  import { chord, isDeleteChord } from '../lib/keybindings';
  import {
    parseString,
    parseBoolean,
    parseStringArray,
    parseEnum,
  } from '../lib/storeParsers';
  import { parseScopeConsoleState } from '../lib/scopeConsole';
  import type { ScopeConsoleState } from '../lib/scopeConsole';

  let selectedFolder = '';
  let files: FileItem[] = [];
  let selectedPaths = new Set<string>;
  let syncedPaths = new Set<string>;
  let expandedPaths = new Set<string>();
  let error = '';

  let totalFilesFound = 0;

  async function refreshTotalFilesFound() {
    if (!selectedFolder) {
      totalFilesFound = 0;
      return;
    }
    try {
      totalFilesFound = await invoke<number>('count_pdfs_recursive', { folderPath: selectedFolder });
    } catch (e) {
      console.log('Could not count PDFs:', e);
      totalFilesFound = 0;
    }
  }

  // Pane focus is two axes, not one. `activePane` says which region answers
  // the arrow keys; the three nullable tokens below say where that region's
  // caret is drawn. Keeping them separate is what lets a click on a panel's
  // chrome hand it the keyboard without ringing a row the user never pointed
  // at — see docs/specs/keyboard/2026-08-09-pane-activation-design.md.
  //
  // Not nullable: the file region is the resting owner. Tree and systems nav
  // already accept arrows with no caret and materialize on their own, so
  // 'files' is simply the name for what used to be spelled "no token
  // anywhere".
  let activePane: 'files' | 'collections' | 'filters' = 'files';

  // File focus & context menu
  let focusedFilePath: string | null = null;
  // Mirror state for collection-row keyboard focus. At most one caret exists
  // at a time, and it belongs to the active pane.
  let focusedCollectionName: string | null = null;
  // Third pane: the filter console. Holds a filterRows key, not an index.
  let focusedFilterRow: string | null = null;

  // Switch ownership, clearing the carets of the panes being left. The target
  // pane's own caret is untouched — the setters below call this straight after
  // placing theirs. A no-op when the pane is already active.
  function setActivePane(pane: 'files' | 'collections' | 'filters') {
    if (activePane === pane) return;
    activePane = pane;
    if (pane !== 'files') focusedFilePath = null;
    if (pane !== 'collections') focusedCollectionName = null;
    if (pane !== 'filters') focusedFilterRow = null;
  }
  // A mousedown on empty or non-selectable space: point at the pane and select
  // nothing. Deselects *within* the pane too, which is the difference from
  // setActivePane — clicking the gap below a row drops that row's caret, the
  // way clicking away from a selection does anywhere else. Nothing is lost:
  // lastFocused* still remembers the row, so the next arrow brings it back.
  function pointAtEmpty(pane: 'files' | 'collections' | 'filters') {
    activePane = pane;
    focusedFilePath = null;
    focusedCollectionName = null;
    focusedFilterRow = null;
  }
  // Placing a caret implies claiming the arrows. Clearing a dock caret hands
  // them back to the file region — which is how Escape and panel-close
  // release ownership without needing their own callbacks. Clearing the file
  // caret changes nothing, since 'files' is already the resting state.
  function setFocusedFilePath(path: string | null) {
    focusedFilePath = path;
    if (path) setActivePane('files');
  }
  function setFocusedCollectionName(name: string | null) {
    focusedCollectionName = name;
    if (name) setActivePane('collections');
    else if (activePane === 'collections') setActivePane('files');
  }
  function setFocusedFilterRow(key: string | null) {
    focusedFilterRow = key;
    if (key) setActivePane('filters');
    else if (activePane === 'filters') setActivePane('files');
  }
  // Remember the last non-null focus in each pane so Cmd+Alt+←/→/↑/↓ can
  // restore the user to where they were instead of always landing on
  // row 0 of the target region.
  let lastFocusedFilePath: string | null = null;
  let lastFocusedCollectionName: string | null = null;
  let lastFocusedFilterRow: string | null = null;
  $: if (focusedFilePath !== null) lastFocusedFilePath = focusedFilePath;
  $: if (focusedCollectionName !== null) lastFocusedCollectionName = focusedCollectionName;
  $: if (focusedFilterRow !== null) lastFocusedFilterRow = focusedFilterRow;
  // Which of the dock's two panels the user was last in, so Cmd+Alt+←
  // returns there rather than always landing on Collections.
  let lastFocusedDockPane: 'collections' | 'filters' = 'collections';
  $: if (focusedCollectionName !== null) lastFocusedDockPane = 'collections';
  $: if (focusedFilterRow !== null) lastFocusedDockPane = 'filters';
  // `hideState` snapshots both the directly-hidden flag (path itself in
  // hiddenPaths) and the inherited flag (an ancestor folder is). The menu
  // shows Hide/Show only when `directlyHidden` is true or nothing is
  // hidden along the path — descendants of a hidden folder get no toggle.
  let contextMenu: {
    x: number;
    y: number;
    item: FileItem;
    isIndexed: boolean;
    initialSubmenu: 'add' | 'remove' | null;
    hideState: { directlyHidden: boolean; inheritedHidden: boolean };
  } | null = null;
  let renamingFilePath: string | null = null;
  let statsModalPath: string | null = null;

  // Game system tag editing
  let knownSystems: KnownGameSystem[] = [];

  // Collections state
  let collections: Record<string, CollectionInfo> = {};
  // Non-null while a new collection is being named in the panel's create
  // box. Holds the paths it will be seeded with (a folder's contents, or a
  // drop) and the name to suggest. Nothing exists until it's committed.
  let newCollectionSeed: { paths: string[]; name: string } | null = null;
  // The armed track. Arming rewires the file tree into a live membership
  // surface for this one collection; every toggle writes through the
  // scheduler. Never persisted: a mode that silently changes what a click
  // does must not survive a restart (the same line the app draws for
  // searchViewOpen).
  let armedCollection: string | null = null;
  // Last membership the sidecar acknowledged, so a failed write has
  // something to roll back to.
  let lastCommittedPaths: string[] = [];
  let collectionsPanelOpen = true;
  // The filter panel docks below the collections panel in the left pane;
  // both persist across launches independently.
  let filterPanelOpen = false;
  // Collections-panel sort. 'custom' is the DAW default — collections
  // are tracks, drag-reorderable; the order (a name array) persists with
  // the sort choice. Names missing from the array sort after it.
  type CollectionsSortKey = 'custom' | 'name' | 'size' | 'created';
  let collectionsSortKey: CollectionsSortKey = 'custom';
  let collectionsCustomOrder: string[] = [];

  async function persistCollectionsSort() {
    try {
      const store = await load('settings.json');
      await store.set('collectionsSortKey', collectionsSortKey);
      await store.set('collectionsCustomOrder', collectionsCustomOrder);
      await store.save();
    } catch (e) {
      console.log('Could not persist collections sort:', e);
    }
  }

  function setCollectionsSortKey(key: CollectionsSortKey) {
    collectionsSortKey = key;
    persistCollectionsSort();
  }

  function reorderCollections(order: string[]) {
    collectionsCustomOrder = order;
    persistCollectionsSort();
  }

  // Library narrowing — the scope doctrine (docs/specs/scope/
  // 2026-08-08-solo-mute-play-doctrine-design.md): the transport arms
  // material into the mix; S narrows within what's armed; M carves out
  // of it. playingCollections ∪-minus-mutedCollectionNames resolve to
  // the mix (the universe); three axes narrow within it by
  // intersection, each with DAW semantics (solos union within the
  // axis, solo overrides mute):
  //   - systems axis:    filterExcludedSystems (muted) + soloedSystems.
  //   - path axis:       scopeSolos + scopeMutes, keyed by tree
  //     folder/file path.
  //   - curation axis:   soloCuration + mutedCuration over the
  //     collected/loose domain.
  // The whole console persists across launches ("full console recall")
  // via the scopeConsole store key.
  let filterExcludedSystems = new Set<string>();
  let soloedSystems = new Set<string>();
  let scopeSolos = new Map<string, ScopeRef>();
  let scopeMutes = new Map<string, ScopeRef>();
  let playingCollections = new Set<string>();
  let mutedCollectionNames = new Set<string>();
  let soloCuration = new Set<CurationKey>();
  let mutedCuration = new Set<CurationKey>();
  // Focus lens — hide out-of-scope rows on browsing surfaces.
  let hideOutOfScope = false;

  // Display-only hidden flag. Stores explicitly-hidden paths (files or
  // folder roots); descendants of a hidden folder are hidden via prefix
  // match, not stored individually. Indexing is unaffected — hidden files
  // still get indexed, searched, and counted in SystemsView.
  let hiddenPaths = new Set<string>();
  let showHidden = false;
  // "Hide unindexed items" — a view mode over what the library knows,
  // not a narrowing, so it lives beside showHidden rather than in the
  // scope console (and survives [clear all], as the focus lens does).
  let hideUnindexed = false;

  // View mode for the file tree area. 'tree' = directory hierarchy (default),
  // 'systems' = flat list grouped by game system. Forced to 'tree' in
  // collection-edit mode (selection requires the directory tree).
  let viewMode: 'tree' | 'systems' = 'tree';

  // Index sync state
  let indexStatus: IndexStatusResult | null = null;
  let isLoadingStatus = false;
  let isSyncing = false;
  let statusTimeout: ReturnType<typeof setTimeout> | null = null;

  // Sidecar stats
  let storageBytes = 0;
  let totalChunks = 0;
  let reclaimableBytes = 0;

  // Sidecar health
  let sidecarConnected = false;
  let mcpConnected = false;
  let mcpActive = false;
  let lastSyncTime: Date | null = null;
  let autoSyncInterval: ReturnType<typeof setInterval> | null = null;
  let showSettings = false;
  let showHelpOverlay = false;
  let showSplash = true;
  // Gates the engage detent (app.css). See where it's set in onMount.
  let motionReady = false;
  let splashTimer: ReturnType<typeof setTimeout> | null = null;
  let settingsInitialTab: 'general' | 'library' | 'game-systems' | 'help' = 'general';
  let settingsInitialHelpSubTab: 'guides' | 'reference' | 'about' = 'guides';
  let healthInterval: ReturnType<typeof setInterval> | null = null;
  let mcpStatusInterval: ReturnType<typeof setInterval> | null = null;

  // User-configurable behavior
  let syncPreferences: SyncPreferences = { ...DEFAULT_SYNC_PREFERENCES };
  let dataDir = '';

  // Ollama health
  let ollamaRunning = false;
  let ollamaModelReady = false;

  // In-app search state
  let searchQuery = '';
  let committedQuery = '';
  // The search view is stateful, not derived: entered by focusing the
  // search bar, left only explicitly (view switch, Cmd+J/T, or the
  // Escape ladder). Never persisted — the app launches into the browse
  // view. searchActive (committed query) keeps meaning "has a query".
  let searchViewOpen = false;
  let searchResults: SearchResultItem[] = [];
  // Tracks which query produced the rows currently in `searchResults`.
  // Used to distinguish a fresh search-in-flight (committedQuery !==
  // resultsQuery, displayed rows are stale) from a "load more"
  // pagination (same query, rows still authoritative).
  let resultsQuery = '';
  let isSearching = false;
  let searchError: string | null = null;
  let searchSeq = 0;
  // Deliberately outside the activePane model, and non-nullable. This is a
  // selection with a downstream consumer — it drives SearchInspector — not a
  // caret, and the search view arbitrates arrows by real DOM focus rather
  // than by a pane token. There is also no gesture that lands it on row 0
  // unintentionally: the file pane's mousedown bails while search is open,
  // and the results list has no chrome handler.
  let selectedResultIndex = 0;
  let headerComponent: Header | undefined;
  let searchResultsComponent: SearchResults | undefined;
  let systemsViewComponent: SystemsView | undefined;
  let collectionsPanelComponent: CollectionsPanel | undefined;
  let filterPanelComponent: FilterPanel | undefined;
  // Lazy result loading: start with 25, grow by 25 each scroll-to-bottom,
  // hard cap at 100 to keep us out of the long tail of low-relevance hits.
  // reachedEnd flips when the backend returns fewer than requested — we've
  // drained the post-dedup pool, no point asking for more.
  const PAGE_SIZE_INITIAL = 25;
  const PAGE_SIZE_STEP = 25;
  const PAGE_SIZE_MAX = 100;
  let pageSize = PAGE_SIZE_INITIAL;
  let reachedEnd = false;
  $: searchActive = committedQuery.trim() !== '';
  // Which console sections are meaningful right now. System and curation
  // narrowing act on file metadata, not disk shape, so they're exposed
  // where the organizing axis IS the tag (systems view) or where the
  // filter actually applies (search backend). Tree view intentionally
  // hides them: narrowing a filesystem-shaped tree by content metadata
  // breaks the spatial mental model — folders and ancestors would
  // disappear for reasons the tree itself can't explain.
  $: systemsFilterRelevant = viewMode === 'systems' || searchViewOpen;
  $: curationFilterRelevant = viewMode === 'systems' || searchViewOpen;
  // Clamp selection when results shrink (e.g. new query returns fewer hits).
  $: if (selectedResultIndex >= searchResults.length) {
    selectedResultIndex = searchResults.length > 0 ? searchResults.length - 1 : 0;
  }
  $: selectedResult = searchResults.length > 0 ? searchResults[selectedResultIndex] ?? null : null;
  // A playing collection materializes a chip exactly as a solo does —
  // its bookmark takes the collection pigment — with the "play" prefix
  // naming the transport that armed it. Clicking the chip stops the
  // track. Folder/file solos and mutes stay on the tertiary fallback.
  $: collectionPlays = [...playingCollections].map((name) => ({
    key: name,
    label: name,
    // `|| null` (not ??): a cleared pigment is stored as '', which
    // must not reach the chip as a fill value.
    color: collections[name]?.color || null,
  }));
  $: collectionSolos = [...scopeSolos].map(([key, ref]) => ({ key, label: ref.label, color: null }));
  $: collectionMutes = [...scopeMutes].map(([key, ref]) => ({ key, label: ref.label, color: null }));
  // Collection-track mutes chip like plays — pigment ribbon, mute
  // dressing. Never suppressed: mute wins over play on the mix layer.
  $: collectionTrackMutes = [...mutedCollectionNames].map((name) => ({
    key: name,
    label: name,
    color: collections[name]?.color || null,
  }));
  function handleClearCollectionSolo(key: string) {
    scopeSolos.delete(key);
    scopeSolos = scopeSolos;
    persistScopeConsole();
    if (committedQuery) runSearch(committedQuery);
  }
  function handleClearCollectionMute(key: string) {
    scopeMutes.delete(key);
    scopeMutes = scopeMutes;
    persistScopeConsole();
    if (committedQuery) runSearch(committedQuery);
  }

  // File path → collection pigment for the search-result index cells.
  $: collectionColorByPath = firstColorByPath(collections);

  // File path → the collections holding it, for the tree and systems-view
  // ribbon strips. Archived collections are shelved and stay out of it.
  $: ribbonIndex = buildRibbonIndex(collections);

  // Path-axis solo/mute Maps resolved to raw file-path arrays. The
  // universe restriction (solo ∩ mix) happens inside resolveScopeSet.
  //
  // Plain function, not a `$:` value: the S/M and transport toggles
  // call runSearch synchronously after mutating their state, and
  // derived values don't flush until the end of the microtask.
  function scopeRefSets(solos: Map<string, ScopeRef>, mutes: Map<string, ScopeRef>) {
    const refFiles = (key: string, kind: ScopeRef['kind']) =>
      kind === 'folder'
        ? indexedPathsUnder(key, indexedPaths)
        : indexedPaths.has(key) ? [key] : [];
    return {
      soloSets: [...solos].map(([p, r]) => refFiles(p, r.kind)),
      muteSets: [...mutes].map(([p, r]) => refFiles(p, r.kind)),
    };
  }

  const EMPTY_SYSTEMS = new Set<string>();
  const EMPTY_PATHS = new Set<string>();
  const EMPTY_TAGS = new Map<string, string[]>();

  // Master bypass: the whole scope console passes through unresolved, so
  // every indexed file is in scope. Not persisted and not part of
  // ScopeConsoleState — it is a momentary A/B against your own scope, not
  // a setting, and coming back to a silently bypassed console next launch
  // would be a trap.
  let scopeBypassed = false;

  function toggleScopeBypass() {
    scopeBypassed = !scopeBypassed;
    // The scope feeds the query, so the results have to be re-asked for.
    if (committedQuery) runSearch(committedQuery);
  }

  // The resolved scope — mix ∩ all three axes — as the display sees it.
  // null = nothing engaged, every indexed file is in scope. Drives the
  // scope-bar denominator and every surface's out-of-scope dimming.
  $: resolvedScopeSet = (() => {
    if (scopeBypassed) return null;
    const { soloSets, muteSets } = scopeRefSets(scopeSolos, scopeMutes);
    return resolveScopeSet(
      resolveMix(playingCollections, mutedCollectionNames, collections, indexedPaths),
      soloSets,
      muteSets,
      soloCuration,
      mutedCuration,
      collectedPaths,
      soloedSystems,
      filterExcludedSystems,
      effectiveGameSystemMap,
      indexedPaths
    );
  })();
  // Same universe on both sides of the fallback (indexedPaths, which
  // includes to_remove entries whose chunks are still searchable), so
  // the denominator doesn't jump the moment narrowing engages.
  $: searchableFileCount = resolvedScopeSet !== null ? resolvedScopeSet.size : indexedPaths.size;
  // In-scope files plus their ancestor folders — the tree rows that
  // stay bright. null = no scope engaged, nothing dims.
  $: scopeBrightPaths = resolvedScopeSet === null
    ? null
    : new Set<string>([...resolvedScopeSet, ...computeAncestorPaths(resolvedScopeSet)]);
  // Folders containing at least one indexed file — the rows the dim
  // predicate is allowed to speak about.
  $: indexedFolderPaths = computeAncestorPaths(indexedPaths);

  async function runSearch(q: string) {
    const trimmed = q.trim();
    if (!trimmed) {
      searchResults = [];
      searchError = null;
      isSearching = false;
      return;
    }
    // Don't pre-check sidecarConnected: that flag is updated by a 10s
    // poll with a 3s health timeout, so a sidecar that's just busy (e.g.
    // mid-search after rapid filter toggles) can briefly look "down" even
    // though it's fine. Just attempt the invoke — the Rust command
    // surfaces an accurate connection error in the catch below if the
    // sidecar is genuinely unreachable.

    // Mix first: the transport layer resolves before any narrowing.
    // Computed fresh (not from the deriveds) — toggles call runSearch
    // synchronously after mutating state; see scopeRefSets.
    // Under bypass every axis resolves to "no narrowing" without the
    // console being touched, so releasing B puts the scope back exactly.
    const mix = scopeBypassed
      ? null
      : resolveMix(playingCollections, mutedCollectionNames, collections, indexedPaths);
    const mixEmpty = mix !== null && mix.size === 0;

    // Path + curation axes narrow within the mix. Systems stay out of
    // this resolution (empty sets) — the backend applies game_systems
    // per chunk. resolveScopeSet handles an empty mix fine (an empty
    // set in, an empty set out), so this runs unconditionally — the
    // empty-scope priority below picks the one message that wins.
    const { soloSets, muteSets } = scopeRefSets(scopeSolos, scopeMutes);
    const pathScope = scopeBypassed ? null : resolveScopeSet(
      mix, soloSets, muteSets,
      soloCuration, mutedCuration, collectedPaths,
      EMPTY_SYSTEMS, EMPTY_SYSTEMS, EMPTY_TAGS, indexedPaths
    );
    const sourcePaths = pathScope === null ? null : [...pathScope];
    const pathScopeEmpty = sourcePaths !== null && sourcePaths.length === 0;

    // Systems axis → backend game_systems include-list (issue #307:
    // the untagged bucket must be named explicitly under mutes).
    const gameSystems = scopeBypassed ? null : searchGameSystemsFilter(
      soloedSystems,
      filterExcludedSystems,
      gameSystemStats.map((s) => s.name)
    );
    const systemsEmpty = gameSystems !== null && gameSystems.length === 0;

    const emptyMsg = emptyScopeMessage({
      mixEmpty,
      anyLivePlaying: [...playingCollections].some((n) => Object.hasOwn(collections, n)),
      pathScopeEmpty,
      anySolosEngaged: scopeSolos.size > 0 || soloCuration.size > 0,
      systemsEmpty,
    });
    if (emptyMsg !== null) {
      searchError = emptyMsg;
      searchResults = [];
      isSearching = false;
      return;
    }

    searchSeq += 1;
    const seq = searchSeq;
    const requestedPageSize = pageSize;
    isSearching = true;
    searchError = null;
    try {
      const response = await invoke<SearchResponse>('search_index', {
        query: trimmed,
        nResults: requestedPageSize,
        sourcePaths,
        gameSystems,
      });
      if (seq !== searchSeq) return;
      const next = response.results ?? [];
      // Backend returned fewer than asked → there's nothing more to fetch
      // even if pageSize hasn't hit the cap. Stops scroll-load from spinning.
      reachedEnd = next.length < requestedPageSize;
      // Preserve selection across grow-fetches: when the new result list
      // contains the previously-selected row in place, leave selectedIndex
      // alone. Only reset for fresh queries (first page) or shrinkage.
      const wasGrowing = next.length > searchResults.length && searchResults.length > 0;
      searchResults = next;
      resultsQuery = trimmed;
      if (!wasGrowing) selectedResultIndex = 0;
    } catch (e) {
      if (seq !== searchSeq) return;
      searchError = String(e);
      searchResults = [];
      resultsQuery = '';
    } finally {
      if (seq === searchSeq) {
        isSearching = false;
      }
    }
  }

  function resetPageSize() {
    pageSize = PAGE_SIZE_INITIAL;
    reachedEnd = false;
  }

  function handleSearchDebounced(q: string) {
    const trimmed = q.trim();
    if (trimmed !== committedQuery) resetPageSize();
    committedQuery = trimmed;
    runSearch(q);
  }

  // Enter in the search input always (re-)submits. To open a result, the
  // user moves focus into the list with ArrowDown (or clicks a row) and
  // presses Enter there. This combobox split avoids the overloaded-Enter
  // ambiguity we tried earlier.
  function handleSearchSubmit(q: string) {
    const trimmed = q.trim();
    if (trimmed !== committedQuery) resetPageSize();
    committedQuery = trimmed;
    runSearch(q);
  }

  // Scroll-to-bottom in the result list bumps the page size and re-runs
  // the same query with a larger n_results. Re-querying (vs. true offset
  // pagination) is fine on a local sidecar — the embedding is cached and
  // ChromaDB's nearest-neighbor cost is sub-linear in N at this scale.
  function loadMoreResults() {
    if (isSearching || reachedEnd || pageSize >= PAGE_SIZE_MAX || !committedQuery) return;
    pageSize = Math.min(PAGE_SIZE_MAX, pageSize + PAGE_SIZE_STEP);
    runSearch(committedQuery);
  }

  function handleSearchClear() {
    searchQuery = '';
    committedQuery = '';
    searchResults = [];
    resultsQuery = '';
    searchError = null;
    isSearching = false;
    searchSeq += 1;
    selectedResultIndex = 0;
    resetPageSize();
  }

  function handleSearchFocus() {
    searchViewOpen = true;
  }

  function resolvePathForFilename(filename: string): string | null {
    const target = filename.toLowerCase();
    for (const entry of indexStatus?.up_to_date ?? []) {
      if (entry.filename?.toLowerCase() === target) return entry.path;
    }
    for (const entry of indexStatus?.to_update ?? []) {
      if (entry.filename?.toLowerCase() === target) return entry.path;
    }
    return null;
  }

  async function handleOpenResult(filename: string, page?: number | null) {
    const path = resolvePathForFilename(filename);
    if (!path) {
      jobNotification.show({
        type: 'error',
        message: `Could not locate "${filename}" on disk.`,
        duration: 4000,
      });
      return;
    }
    try {
      // With a page anchor, open via file:// URL so PDF viewers honouring
      // the standard `#page=N` fragment land on the right page (#113).
      // Viewers that ignore the fragment (notably macOS Preview) silently
      // open at page 1 — page 1 is also the openPath fallback below.
      if (page && page > 0) {
        await openUrl(pdfFileUrl(path, page));
      } else {
        await openPath(path);
      }
    } catch (e) {
      jobNotification.show({
        type: 'error',
        message: `Failed to open ${filename}: ${e}`,
        duration: 4000,
      });
    }
  }

  let unlistenSidecarFailed: (() => void) | null = null;
  // Set when the startup load surfaces a missing-folder toast; cleared
  // by loadFiles when a subsequent load succeeds — typically when the
  // user picks a new folder.
  let missingFolderToastId: string | null = null;

  onMount(async () => {
    splashTimer = setTimeout(() => {
      showSplash = false;
      splashTimer = null;
    }, 1200);

    // Sidecar failed to start at app launch — show one sticky banner so the
    // user gets a single clear failure message instead of N "failed to
    // connect" toasts on every per-call attempt. The setup() emit happens
    // before the webview is ready, so we also poll the stashed state here;
    // the listener covers any future failures (e.g. mid-session restart).
    function showSidecarFailure(payload: { log_path: string; message: string }) {
      jobNotification.show({
        type: 'error',
        message: `Indexer failed to start. See log: ${payload.log_path}`,
        duration: null,
      });
    }

    unlistenSidecarFailed = await listen<{ log_path: string; message: string }>(
      'sidecar://failed',
      (event) => showSidecarFailure(event.payload),
    );

    try {
      const stashed = await invoke<{ log_path: string; message: string } | null>(
        'get_sidecar_failure',
      );
      if (stashed) showSidecarFailure(stashed);
    } catch {
      // Non-fatal — command may not exist on older builds during dev rebuilds.
    }

    try {
      const store = await load('settings.json');
      const savedFolder = parseString(await store.get('selectedFolder'));
      const savedPaths = parseStringArray(await store.get('syncedPaths'))
        ?? parseStringArray(await store.get('selectedPaths'));
      syncPreferences = await loadSyncPreferences(store);

      if (savedFolder) {
        selectedFolder = savedFolder;
        await loadFiles(savedFolder);
        if (error) {
          // Library folder is gone (renamed, unmounted, deleted). Surface
          // it on startup so the user notices now, not later when they
          // try to act on a stale tree. Sticky — but cleared automatically
          // by the next loadFiles() success (e.g. when they pick a new
          // folder), via dismissIf below.
          missingFolderToastId = jobNotification.show({
            type: 'error',
            message: `Library folder is no longer accessible: ${savedFolder}`,
            duration: null,
          });
        }
      }
      if (savedPaths) {
        selectedPaths = new Set(savedPaths);
        syncedPaths = new Set(savedPaths);
        if (savedPaths.length > 0) {
          await refreshIndexStatus();
        }
      }
      const savedPanelOpen = parseBoolean(await store.get('collectionsPanelOpen'));
      if (savedPanelOpen !== undefined) {
        collectionsPanelOpen = savedPanelOpen;
      }
      const savedFilterPanelOpen = parseBoolean(await store.get('filterPanelOpen'));
      if (savedFilterPanelOpen !== undefined) {
        filterPanelOpen = savedFilterPanelOpen;
      }
      const savedCollectionsSort = parseEnum(
        await store.get('collectionsSortKey'),
        ['custom', 'name', 'size', 'created'] as const,
      );
      if (savedCollectionsSort) {
        collectionsSortKey = savedCollectionsSort;
      }
      const savedCustomOrder = parseStringArray(await store.get('collectionsCustomOrder'));
      if (savedCustomOrder) {
        collectionsCustomOrder = savedCustomOrder;
      }
      // libraryFilter persistence intentionally removed: filter state is
      // session-scoped now. We delete the old key to avoid confusion if a
      // user inspects settings.json — and so older versions don't reload
      // a filter the new build doesn't honor anyway.
      try { await store.delete('libraryFilter'); } catch {}
      const savedHidden = parseStringArray(await store.get('hiddenPaths'));
      if (savedHidden) {
        hiddenPaths = new Set(savedHidden);
      }
      const savedShowHidden = parseBoolean(await store.get('showHidden'));
      if (savedShowHidden !== undefined) {
        showHidden = savedShowHidden;
      }
      const savedHideUnindexed = parseBoolean(await store.get('hideUnindexed'));
      if (savedHideUnindexed !== undefined) {
        hideUnindexed = savedHideUnindexed;
      }
      const savedViewMode = parseEnum(
        await store.get('viewMode'),
        ['tree', 'systems'] as const,
      );
      if (savedViewMode) {
        viewMode = savedViewMode;
      }
      await loadCollections();

      // Full console recall — the session reopens as it was left. Read
      // first: if a console was ever persisted, it wins outright and the
      // one-time radio migration below is moot (its legacy keys are
      // deleted either way).
      const savedConsole = parseScopeConsoleState(await store.get('scopeConsole'));
      if (savedConsole) {
        playingCollections = new Set(savedConsole.playing);
        mutedCollectionNames = new Set(savedConsole.mutedCollections);
        soloedSystems = new Set(savedConsole.soloedSystems);
        filterExcludedSystems = new Set(savedConsole.mutedSystems);
        scopeSolos = new Map(savedConsole.scopeSolos);
        scopeMutes = new Map(savedConsole.scopeMutes);
        soloCuration = new Set(savedConsole.curationSolos);
        mutedCuration = new Set(savedConsole.curationMutes);
        hideOutOfScope = savedConsole.hideOutOfScope;
      } else {
        // One-time migration of the old Curation radios into the curation
        // axis: "show only collection" → solo Collected, "show only loose"
        // → solo Loose (focus wins if a stray state had both, matching the
        // old radio's tie-break). Only reachable pre-console: persist the
        // result immediately so it survives a quit with no further toggle,
        // rather than evaporating as session-only state used to.
        const savedShowOnlyUncollected = parseBoolean(await store.get('showOnlyUncollected'));
        const savedFocusActiveCollection = parseBoolean(await store.get('focusActiveCollection'));
        if (savedFocusActiveCollection) {
          soloCuration.add('collected');
          soloCuration = soloCuration;
          persistScopeConsole();
        } else if (savedShowOnlyUncollected) {
          soloCuration.add('loose');
          soloCuration = soloCuration;
          persistScopeConsole();
        }
      }
      try { await store.delete('showOnlyUncollected'); } catch {}
      try { await store.delete('focusActiveCollection'); } catch {}
    } catch (e) {
      // No saved state on first run — that's fine
      console.log('No saved state:', e);
    }

    // Arm the detent only once the restored console has been applied. A
    // CSS animation also runs when an element is *created* already
    // carrying the class, so without this every lamp the session restored
    // would snap on launch as though the user had just thrown it.
    await tick();
    motionReady = true;

    try {
      dataDir = await invoke<string>('get_data_dir');
    } catch (e) {
      console.log('Could not fetch data dir:', e);
    }

    // Poll sidecar + Ollama health
    checkSidecarHealth();
    checkOllamaHealth();
    healthInterval = setInterval(() => {
      checkSidecarHealth();
      checkOllamaHealth();
    }, 10000);

    // Poll MCP status more frequently so the active-query pulse is
    // caught (backend keeps the active flag for 5s after a query).
    checkMcpStatus();
    mcpStatusInterval = setInterval(checkMcpStatus, 5000);

    restartAutoSyncInterval();
  });

  function restartAutoSyncInterval() {
    if (autoSyncInterval) {
      clearInterval(autoSyncInterval);
      autoSyncInterval = null;
    }
    if (!selectedFolder) return;
    const seconds = syncPreferences.backgroundCheckInterval;
    if (seconds <= 0) return;
    autoSyncInterval = setInterval(async () => {
      if (!sidecarConnected || isSyncing) return;
      // Skip during inline rename — re-rendering the tree would wipe the input
      if (renamingFilePath !== null) return;
      if (selectedFolder) await loadFiles(selectedFolder);
      if (selectedPaths.size > 0) refreshIndexStatus();
    }, seconds * 1000);
  }

  async function loadSyncPreferences(store: Awaited<ReturnType<typeof load>>): Promise<SyncPreferences> {
    const saved = await store.get<Record<string, unknown>>('syncPreferences');
    if (saved && typeof saved === 'object') {
      // Migrate prior boolean shape if present
      const merged: SyncPreferences = { ...DEFAULT_SYNC_PREFERENCES, ...(saved as Partial<SyncPreferences>) };
      if ('backgroundChecks' in saved && !('backgroundCheckInterval' in saved)) {
        merged.backgroundCheckInterval = saved.backgroundChecks ? 60 : 0;
      }
      return merged;
    }
    // Migrate legacy syncMode if present, then persist new shape and remove old key
    const legacy = await store.get<string>('syncMode');
    let migrated: SyncPreferences = { ...DEFAULT_SYNC_PREFERENCES };
    if (legacy === 'prompt') {
      migrated = { ...migrated, diskEventsPolicy: 'ask' };
    } else if (legacy === 'manual') {
      migrated = { ...migrated, backgroundCheckInterval: 0 };
    }
    if (legacy) {
      try {
        await store.set('syncPreferences', migrated);
        await store.delete('syncMode');
        await store.save();
      } catch (e) {
        console.log('Could not migrate syncMode:', e);
      }
    }
    return migrated;
  }

  async function handleSyncPreferencesChange(partial: Partial<SyncPreferences>) {
    syncPreferences = { ...syncPreferences, ...partial };
    try {
      const store = await load('settings.json');
      await store.set('syncPreferences', syncPreferences);
      await store.save();
    } catch (e) {
      console.log('Could not persist sync preferences:', e);
    }
    restartAutoSyncInterval();
    if (syncPreferences.backgroundCheckInterval === 0) {
      pendingNotification.dismiss();
    }
  }

  function handleOpenDataDir() {
    if (dataDir) openPath(dataDir);
  }

  onDestroy(() => {
    // Best effort: land any membership still sitting in the debounce.
    void armCommitter.flush();
    if (healthInterval) clearInterval(healthInterval);
    if (mcpStatusInterval) clearInterval(mcpStatusInterval);
    if (autoSyncInterval) clearInterval(autoSyncInterval);
    if (splashTimer) clearTimeout(splashTimer);
    if (unlistenSidecarFailed) unlistenSidecarFailed();
  });

  async function checkSidecarHealth() {
    try {
      sidecarConnected = await invoke<boolean>('check_sidecar_health');
    } catch {
      sidecarConnected = false;
    }
  }

  async function setViewMode(mode: 'tree' | 'systems') {
    // Selecting a view is also the exit from the search view. Blur the
    // bar if it holds focus — Cmd+J/T can fire from inside it, and a
    // focused input would keep feeding a view no longer on screen.
    searchViewOpen = false;
    const ae = document.activeElement as HTMLElement | null;
    if (ae?.classList.contains('search-input')) ae.blur();
    viewMode = mode;
    try {
      const store = await load('settings.json');
      await store.set('viewMode', mode);
      await store.save();
    } catch (e) {
      console.log('Could not persist viewMode:', e);
    }
  }

  // Indexed entries with metadata (path, filename, game_system) for the
  // systems view. Excludes pending removals and the to-add bucket.
  $: indexedEntries = (() => {
    if (!indexStatus) return [];
    return [...indexStatus.up_to_date, ...indexStatus.to_update];
  })();

  function toggleSystemFilter(system: string) {
    if (filterExcludedSystems.has(system)) {
      filterExcludedSystems.delete(system);
    } else {
      filterExcludedSystems.add(system);
    }
    filterExcludedSystems = filterExcludedSystems;
    persistScopeConsole();
    if (committedQuery) runSearch(committedQuery);
  }

  // Solos union within the axis (solo two systems = files in either),
  // so toggling one leaves the others engaged. Solo overrides mute.
  function toggleSystemSolo(system: string) {
    if (soloedSystems.has(system)) {
      soloedSystems.delete(system);
    } else {
      soloedSystems.add(system);
    }
    soloedSystems = soloedSystems;
    persistScopeConsole();
    if (committedQuery) runSearch(committedQuery);
  }

  // Collection-axis S/M for tree folders and files. Union semantics:
  // soloing does not release other solos or the active collection —
  // every narrowing stacks as its own chip in the scope bar.
  function toggleScopeSolo(item: FileItem) {
    if (scopeSolos.has(item.path)) {
      scopeSolos.delete(item.path);
    } else if (rowHasIndexedMaterial(item.path, item.is_dir, indexedPaths, indexedFolderPaths)) {
      scopeSolos.set(item.path, { kind: item.is_dir ? 'folder' : 'file', label: item.name });
    } else {
      // Nothing indexed to act on — a solo here could only empty the
      // scope. The affordances gate on the same predicate; guard here
      // too for any other entry point (keyboard S on any focused row).
      return;
    }
    scopeSolos = scopeSolos;
    persistScopeConsole();
    if (committedQuery) runSearch(committedQuery);
  }

  function toggleScopeMute(item: FileItem) {
    if (scopeMutes.has(item.path)) {
      scopeMutes.delete(item.path);
    } else if (rowHasIndexedMaterial(item.path, item.is_dir, indexedPaths, indexedFolderPaths)) {
      scopeMutes.set(item.path, { kind: item.is_dir ? 'folder' : 'file', label: item.name });
    } else {
      // Same gate as solo — a mute with nothing indexed would only be
      // a dead chip.
      return;
    }
    scopeMutes = scopeMutes;
    persistScopeConsole();
    if (committedQuery) runSearch(committedQuery);
  }

  // Play/stop from the collections panel — same axis and union
  // semantics as folder/file solos, keyed by collection name. The scope
  // bar's play chips call this too: a chip only exists while its track
  // plays, so toggling is always "stop".
  function togglePlayCollection(name: string) {
    if (playingCollections.has(name)) {
      playingCollections.delete(name);
    } else {
      playingCollections.add(name);
    }
    playingCollections = playingCollections;
    persistScopeConsole();
    if (committedQuery) runSearch(committedQuery);
  }

  // Mute a collection — carve its files from the mix (or from the
  // whole library while the transport is idle). Mute wins over play;
  // the armed state survives and unmuting restores the contribution.
  function toggleCollectionMute(name: string) {
    if (mutedCollectionNames.has(name)) {
      mutedCollectionNames.delete(name);
    } else {
      mutedCollectionNames.add(name);
    }
    mutedCollectionNames = mutedCollectionNames;
    persistScopeConsole();
    if (committedQuery) runSearch(committedQuery);
  }

  function toggleHideOutOfScope() {
    hideOutOfScope = !hideOutOfScope;
    persistScopeConsole();
  }

  // Footer [clear all] in the filter console: resets every solo/mute on
  // all three axes, stops every playing collection, and unmutes every
  // muted one — the same action as clearing each chip in the scope bar.
  // The focus lens is a view mode, not a narrowing, so it stays as-is.
  function clearAllFilters() {
    filterExcludedSystems = new Set();
    soloedSystems = new Set();
    scopeSolos = new Map();
    scopeMutes = new Map();
    playingCollections = new Set();
    mutedCollectionNames = new Set();
    soloCuration = new Set();
    mutedCuration = new Set();
    persistScopeConsole();
    if (committedQuery) runSearch(committedQuery);
  }

  $: hiddenCount = hiddenPaths.size;

  function isPathHidden(path: string): boolean {
    return isPathOrAncestorIn(path, hiddenPaths);
  }

  async function persistHidden() {
    try {
      const store = await load('settings.json');
      await store.set('hiddenPaths', Array.from(hiddenPaths));
      await store.set('showHidden', showHidden);
      await store.set('hideUnindexed', hideUnindexed);
      await store.save();
    } catch (e) {
      console.log('Could not persist hidden state:', e);
    }
  }

  function snapshotScopeConsole(): ScopeConsoleState {
    return {
      playing: [...playingCollections],
      mutedCollections: [...mutedCollectionNames],
      soloedSystems: [...soloedSystems],
      mutedSystems: [...filterExcludedSystems],
      scopeSolos: [...scopeSolos],
      scopeMutes: [...scopeMutes],
      curationSolos: [...soloCuration],
      curationMutes: [...mutedCuration],
      hideOutOfScope,
    };
  }

  async function persistScopeConsole() {
    try {
      const store = await load('settings.json');
      await store.set('scopeConsole', snapshotScopeConsole());
      await store.save();
    } catch (e) {
      console.log('Could not persist scope console:', e);
    }
  }

  function toggleHidden(item: FileItem) {
    // If the item is hidden by ancestor inheritance (not directly), do
    // nothing — the context menu omits the action in that case, but guard
    // here too in case the path is reached via another entry point.
    if (hiddenPaths.has(item.path)) {
      hiddenPaths.delete(item.path);
    } else if (isPathHidden(item.path)) {
      return;
    } else if (!item.is_dir && indexedPaths.has(item.path)) {
      // Indexed files are library material — their disappearing verb is
      // mute (+ the focus lens). Hide is display-only and would leave
      // them searchable but invisible. Hide keeps working for unindexed
      // files and folders; unhide above always works.
      return;
    } else {
      hiddenPaths.add(item.path);
    }
    hiddenPaths = hiddenPaths;
    // Once nothing is hidden, the "Show hidden" toggle has no meaningful
    // state — snap it back to the default so reopening the filter menu
    // shows a clean default rather than a stuck-on toggle.
    if (hiddenPaths.size === 0) showHidden = false;
    persistHidden();
  }

  function clearHidden() {
    hiddenPaths = new Set();
    showHidden = false;
    persistHidden();
  }

  function toggleShowHidden() {
    showHidden = !showHidden;
    persistHidden();
  }

  // No auto-reset guard of the kind toggleHidden applies to showHidden:
  // the equivalent check ("is anything unindexed?") would need a
  // whole-tree scan, and the switch is a harmless no-op when everything
  // the tree shows is already library material.
  function toggleHideUnindexed() {
    hideUnindexed = !hideUnindexed;
    persistHidden();
  }

  // Curation-axis S/M over the collected/loose domain. Same union/
  // intersect/solo-overrides-mute semantics as the other axes.
  function toggleCurationSolo(key: CurationKey) {
    if (soloCuration.has(key)) {
      soloCuration.delete(key);
    } else {
      soloCuration.add(key);
    }
    soloCuration = soloCuration;
    persistScopeConsole();
    if (committedQuery) runSearch(committedQuery);
  }

  function toggleCurationMute(key: CurationKey) {
    if (mutedCuration.has(key)) {
      mutedCuration.delete(key);
    } else {
      mutedCuration.add(key);
    }
    mutedCuration = mutedCuration;
    persistScopeConsole();
    if (committedQuery) runSearch(committedQuery);
  }

  async function checkMcpStatus() {
    try {
      const status = await invoke<{ connected: boolean; active: boolean }>('check_mcp_status');
      mcpConnected = status.connected;
      mcpActive = status.active;
    } catch {
      mcpConnected = false;
      mcpActive = false;
    }
  }

  async function checkOllamaHealth() {
    try {
      const status = await invoke<{ running: boolean; has_model: boolean }>('check_ollama_health');
      ollamaRunning = status.running;
      ollamaModelReady = status.has_model;
    } catch {
      ollamaRunning = false;
      ollamaModelReady = false;
    }
  }

  async function fetchIndexStatus(): Promise<IndexStatusResult | null> {
    isLoadingStatus = true;
    try {
      const status = await invoke<IndexStatusResult>(
        'get_index_status',
        { paths: Array.from(selectedPaths) }
      );
      indexStatus = status;

      if (knownSystems.length === 0) {
        await refreshKnownSystems();
      }

      invoke<StatsResult>('get_stats')
        .then(r => { storageBytes = r.storage_bytes; totalChunks = r.total_chunks; reclaimableBytes = r.reclaimable_bytes; })
        .catch(() => { storageBytes = 0; totalChunks = 0; reclaimableBytes = 0; });

      lastSyncTime = new Date();
      return status;
    } catch (e) {
      console.log('Could not fetch index status:', e);
      indexStatus = null;
      return null;
    } finally {
      isLoadingStatus = false;
    }
  }

  function decideSyncAction(
    status: IndexStatusResult,
    prefs: SyncPreferences,
    userTriggered: boolean
  ): SyncAction {
    if (prefs.backgroundCheckInterval === 0 && !userTriggered) {
      return { kind: 'noop' };
    }

    const { add, remove, update, errors, rename, auto_remove, stale } = status.summary;
    const diskTotal = rename + auto_remove + stale;

    const askDisk = prefs.diskEventsPolicy === 'ask' && diskTotal > 0;
    const askAdd = prefs.selectionPolicy === 'ask' && add > 0;
    const askRemove = prefs.deselectionPolicy === 'ask' && remove > 0;
    const askUpdate = prefs.modificationPolicy === 'ask' && update > 0;
    const anyAsk = askDisk || askAdd || askRemove || askUpdate;

    const silentDisk = prefs.diskEventsPolicy === 'silent' && diskTotal > 0;
    const silentAdd = prefs.selectionPolicy === 'silent' && add > 0;
    const silentRemove = prefs.deselectionPolicy === 'silent' && remove > 0;
    const silentUpdate = prefs.modificationPolicy === 'silent' && update > 0;
    const anySilent = silentDisk || silentAdd || silentRemove || silentUpdate;

    if (!anyAsk && !anySilent && errors === 0) {
      return { kind: 'noop' };
    }

    if (!anyAsk && errors === 0) {
      return { kind: 'silent' };
    }

    return {
      kind: 'prompt',
      counts: {
        disk: askDisk ? diskTotal : 0,
        add: askAdd ? add : 0,
        remove: askRemove ? remove : 0,
        update: askUpdate ? update : 0,
        errors,
      },
    };
  }

  async function applySyncAction(action: SyncAction) {
    if (action.kind === 'noop') {
      pendingNotification.dismiss();
      return;
    }
    if (action.kind === 'silent') {
      if (!isSyncing) handleSync();
      return;
    }
    showSyncPrompt(action.counts);
  }

  async function refreshIndexStatus(options: { userTriggered?: boolean } = {}) {
    const status = await fetchIndexStatus();
    if (!status) return;
    const action = decideSyncAction(status, syncPreferences, options.userTriggered ?? false);
    await applySyncAction(action);
  }

  function showSyncPrompt(counts: PromptCounts) {
    if (!indexStatus) return;

    const parts: string[] = [];
    if (counts.disk > 0) parts.push(`${counts.disk} disk change${counts.disk === 1 ? '' : 's'}`);
    if (counts.add > 0) parts.push(`${counts.add} to add`);
    if (counts.remove > 0) parts.push(`${counts.remove} to remove`);
    if (counts.update > 0) parts.push(`${counts.update} to update`);
    if (counts.errors > 0) parts.push(`${counts.errors} error${counts.errors === 1 ? '' : 's'}`);

    if (parts.length === 0) {
      pendingNotification.dismiss();
      return;
    }

    pendingNotification.show({
      type: 'action',
      message: parts.join(', '),
      actionLabel: isSyncing ? 'Sync queued' : 'Sync Now',
      actionDisabled: isSyncing,
      onAction: isSyncing ? undefined : handleSync,
      onDismiss: revertToSyncedPaths,
      duration: null,
    });
  }

  async function revertToSyncedPaths() {
    selectedPaths = new Set(syncedPaths);
    await saveState();
    await refreshIndexStatus();
  }

  function scheduleStatusRefresh() {
    if (statusTimeout) clearTimeout(statusTimeout);
    statusTimeout = setTimeout(() => refreshIndexStatus(), 500);
  }

  async function saveState() {
    const store = await load('settings.json');
    await store.set('selectedFolder', selectedFolder);
    await store.set('selectedPaths', Array.from(selectedPaths));
    await store.save();
  }

  async function handleSelectFolder() {
    const wasEmpty = !selectedFolder;
    try {
      const folder = await invoke<string>('select_folder');
      selectedFolder = folder;
      expandedPaths = new Set();
      await loadFiles(selectedFolder);
      error = '';
      await saveState();
      if (wasEmpty) restartAutoSyncInterval();
    } catch (e) {
      // User cancelled the dialog — keep the current folder
      if (!selectedFolder) {
        error = String(e);
      }
    }
  }

  async function handleDeselectFolder() {
    selectedFolder = '';
    files = [];
    expandedPaths = new Set();
    error = '';
    // The workspace unmounts with the folder; never re-mount into search.
    searchViewOpen = false;
    await saveState();
    restartAutoSyncInterval();
  }

  async function loadFiles(path: string) {
    try {
      const newFiles = await invoke<FileItem[]>('list_files', { folderPath: path });
      // Rehydrate any currently-expanded folders before the swap so
      // visibleTreeRows matches the rendered tree the moment files updates.
      // FileTree.svelte's afterUpdate would self-heal anyway, but only into
      // its component-local item — the root files array would stay stale,
      // breaking keyboard nav for any focus inside an expanded folder.
      // Sort shallowest-first so a child can find its parent populated.
      // Splits on both separators so Windows paths (\\) sort correctly too.
      const sortedExpanded = Array.from(expandedPaths)
        .sort((a, b) => a.split(/[/\\]/).length - b.split(/[/\\]/).length);
      for (const expandedPath of sortedExpanded) {
        const node = findTreeNode(newFiles, expandedPath);
        if (node && node.is_dir && node.children === null) {
          try {
            node.children = await invoke<FileItem[]>('list_files', { folderPath: expandedPath });
          } catch (e) {
            console.error('Failed to rehydrate folder:', expandedPath, e);
            node.children = [];
          }
        }
      }
      files = newFiles;
      error = '';
      refreshTotalFilesFound();
      if (missingFolderToastId) {
        jobNotification.dismissIf(missingFolderToastId);
        missingFolderToastId = null;
      }
    } catch (e) {
      error = String(e);
      files = [];
      totalFilesFound = 0;
    }
  }

  let lastIndexClickedPath: string | null = null;

  function flattenVisibleFilePaths(items: FileItem[]): string[] {
    const out: string[] = [];
    function walk(list: FileItem[]) {
      for (const item of list) {
        if (item.is_dir) {
          if (expandedPaths.has(item.path) && item.children) {
            walk(item.children);
          }
        } else {
          out.push(item.path);
        }
      }
    }
    walk(items);
    return out;
  }

  function applyRangeToggle(
    target: Set<string>,
    anchor: string,
    current: string,
    requireIndexed: boolean,
  ): boolean {
    const flat = flattenVisibleFilePaths(files);
    const a = flat.indexOf(anchor);
    const b = flat.indexOf(current);
    if (a === -1 || b === -1) return false;
    const lo = Math.min(a, b);
    const hi = Math.max(a, b);
    const shouldSelect = !target.has(current);
    for (let i = lo; i <= hi; i++) {
      const p = flat[i];
      if (requireIndexed && !indexedPaths.has(p)) continue;
      if (shouldSelect) target.add(p);
      else target.delete(p);
    }
    return true;
  }

  async function toogleSelection(path: string, isDir: boolean, item: FileItem, shiftKey: boolean = false) {
    if (shiftKey && !isDir && lastIndexClickedPath) {
      const ok = applyRangeToggle(selectedPaths, lastIndexClickedPath, path, false);
      if (ok) {
        selectedPaths = selectedPaths;
        lastIndexClickedPath = path;
        await saveState();
        scheduleStatusRefresh();
        return;
      }
    }

    if (isDir) {
      // Toggle folder: recursively add/remove all PDFs
      await toggleFolderRecursive(item);
    } else {
      // Toggle single PDF file
      if (selectedPaths.has(path)) {
        selectedPaths.delete(path);
      } else {
        selectedPaths.add(path);
      }
      selectedPaths = selectedPaths; // Trigger reactivity
      lastIndexClickedPath = path;
      await saveState();
      scheduleStatusRefresh();
    }
  }

  async function toggleFolderRecursive(folder: FileItem) {
    // If children are not loaded, load them first
    if (folder.children === null) {
      try {
        folder.children = await invoke<FileItem[]>('list_files', { folderPath: folder.path });
        files = files; // Trigger reactivity
      } catch (e) {
        console.error('Failed to load folder:', e);
        folder.children = [];
      }
    }
    
    // Deselect only when ALL descendants are selected; otherwise select all
    const allSelected = areAllDescendantsSelected(folder, selectedPaths);
    const shouldSelect = !allSelected;

    // Recursively add/remove all children
    if (folder.children) {
      for (const child of folder.children) {
        if (child.is_dir) {
          await setFolderSelection(child, shouldSelect);
        } else {
          // It's a PDF file
          if (shouldSelect) {
            selectedPaths.add(child.path);
          } else {
            selectedPaths.delete(child.path);
          }
        }
      }
    }
    selectedPaths = selectedPaths; // Trigger reactivity
    await saveState();
    scheduleStatusRefresh();
  }

  async function setFolderSelection(folder: FileItem, select: boolean) {
    if (!folder.is_dir) return;

    if (folder.children === null) {
      try {
        folder.children = await invoke<FileItem[]>('list_files', { folderPath: folder.path });
        files = files; // Trigger reactivity
      } catch (e) {
        console.error('Failed to load folder:', e);
        folder.children = [];
      }
    }

    if (folder.children) {
      for (const child of folder.children) {
        if (child.is_dir) {
          await setFolderSelection(child, select);
        } else {
          if (select) {
            selectedPaths.add(child.path);
          } else {
            selectedPaths.delete(child.path);
          }
        }
      }
    }
  }

  // Derive which folders contain selected items — purely from path strings, no tree walking
  $: foldersWithSelections = computeAncestorPaths(selectedPaths);

  // Build a map of file path → game system from index status data
  $: gameSystemMap = buildGameSystemMap(indexStatus);

  // Optimistic overrides: when the user toggles a tag, flip the local map
  // immediately so the menu shows the change instantly, while the sidecar
  // request and index-status refresh proceed in the background. Each entry
  // clears itself once the server-derived map matches the optimistic value.
  let pendingTagOverrides: Map<string, string[]> = new Map();
  $: if (pendingTagOverrides.size > 0) {
    let changed = false;
    for (const [path, expected] of pendingTagOverrides) {
      const actual = gameSystemMap.get(path) ?? [];
      if (sameTagList(actual, expected)) {
        pendingTagOverrides.delete(path);
        changed = true;
      }
    }
    if (changed) pendingTagOverrides = pendingTagOverrides;
  }
  $: effectiveGameSystemMap = pendingTagOverrides.size > 0
    ? new Map([...gameSystemMap, ...pendingTagOverrides])
    : gameSystemMap;

  function sameTagList(a: string[], b: string[]): boolean {
    if (a.length !== b.length) return false;
    for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return false;
    return true;
  }

  // Track which files are in the index (so untagged indexed files show the "+" button).
  // Stabilize identity: a refresh that returns the same content keeps the same Set
  // reference, so FileTree (which receives indexedPaths as a prop) doesn't re-render
  // every node on no-op refreshes.
  let indexedPaths = new Set<string>();
  $: indexedPaths = reuseIfSame(indexedPaths, buildIndexedPaths(indexStatus));

  function reuseIfSame(prev: Set<string>, next: Set<string>): Set<string> {
    if (prev.size !== next.size) return next;
    for (const p of next) if (!prev.has(p)) return next;
    return prev;
  }

  // Count files per game system, sorted by count descending. A multi-tagged
  // file contributes to every tag's count (e.g. a 5E/PF2E book +1 to both).
  $: gameSystemStats = (() => {
    if (!indexStatus) return [];
    const counts = new Map<string, number>();
    for (const e of [...indexStatus.up_to_date, ...indexStatus.to_update, ...indexStatus.to_remove]) {
      const tags = e.game_systems && e.game_systems.length > 0
        ? e.game_systems
        : (e.game_system && e.game_system !== 'unknown' ? [e.game_system] : []);
      for (const tag of tags) {
        counts.set(tag, (counts.get(tag) ?? 0) + 1);
      }
    }
    return [...counts.entries()]
      .sort((a, b) => b[1] - a[1])
      .map(([name, count]) => ({ name, count }));
  })();
  $: gameSystemCount = gameSystemStats.length;
  $: gameSystemNames = gameSystemStats.map(s => s.name);

  // Indexed files with no game-system tag — the "Untagged" bucket in the
  // filter menu (issue #307). Same entry sets as gameSystemStats so the
  // counts stay consistent.
  $: untaggedFileCount = (() => {
    if (!indexStatus) return 0;
    let n = 0;
    for (const e of [...indexStatus.up_to_date, ...indexStatus.to_update, ...indexStatus.to_remove]) {
      const tags = e.game_systems && e.game_systems.length > 0
        ? e.game_systems
        : (e.game_system && e.game_system !== 'unknown' ? [e.game_system] : []);
      if (tags.length === 0) n++;
    }
    return n;
  })();

  $: topGameSystem = gameSystemStats.length > 0
    ? `Top system: ${gameSystemStats[0].name} with ${gameSystemStats[0].count} file${gameSystemStats[0].count === 1 ? '' : 's'}`
    : '';

  // Collection mode derived state
  // Lit states for the tree's S/M buttons. The dim itself comes from
  // scopeBrightPaths (out-of-scope membership), not from these.
  $: mutedScopePaths = new Set(scopeMutes.keys());
  $: soloedScopePaths = new Set(scopeSolos.keys());

  // Union of every collection's file paths. Powers the "uncategorized"
  // filter and any membership check that's library-wide rather than
  // single-collection.
  $: collectedPaths = (() => {
    const out = new Set<string>();
    for (const col of Object.values(collections)) {
      for (const p of col.file_paths) out.add(p);
    }
    return out;
  })();

  // PDFs on disk that aren't in any collection. The frontend tree
  // lazy-loads children one level at a time, so it only knows about
  // expanded folders — instead, draw the universe from indexStatus,
  // which the sidecar built by walking the whole library:
  //   on-disk = up_to_date ∪ to_update ∪ to_add
  // (to_remove / to_auto_remove are paths the index still tracks but
  // that have already been deleted from disk, so they're excluded.)
  $: uncollectedFilePaths = (() => {
    const out = new Set<string>();
    if (!indexStatus) return out;
    const consider = (entries: FileStatusEntry[]) => {
      for (const e of entries) {
        if (!collectedPaths.has(e.path)) out.add(e.path);
      }
    };
    consider(indexStatus.up_to_date);
    consider(indexStatus.to_update);
    consider(indexStatus.to_add);
    return out;
  })();
  $: uncollectedCount = uncollectedFilePaths.size;

  // Counterpart of uncollectedCount for the Collected channel: on-disk
  // PDFs that belong to at least one collection. Same universe as
  // uncollectedFilePaths so the two LED counts partition the library.
  $: collectedCount = (() => {
    if (!indexStatus) return 0;
    let n = 0;
    const consider = (entries: FileStatusEntry[]) => {
      for (const e of entries) {
        if (collectedPaths.has(e.path)) n++;
      }
    };
    consider(indexStatus.up_to_date);
    consider(indexStatus.to_update);
    consider(indexStatus.to_add);
    return n;
  })();

  // Whether the Curation section in the filter console has anything to
  // channel: the collected/loose split is meaningless until a collection
  // exists.
  $: collectionFilterAvailable = Object.keys(collections).length > 0;

  // Filter for what the file tree shows. Composes scope + library filters:
  // 1. Focus mode picks the base file pool. A playing collection just
  //    highlights — the tree shows the whole library so users can see
  //    those files in context.
  // 2. Uncategorized filter narrows to files not in any collection.
  // 3. Add ancestor folders so the tree structure stays intact.
  // Returns null = show everything, no narrowing.
  // System mute/solo never narrows a view: muted groups dim in place in
  // the systems view (a muted channel never leaves the mixer), and the
  // tree is a spatial model that content tags shouldn't reshape. The
  // filter applies to search only.
  $: displayPaths = (() => {
    // Metadata-based narrowing (curation solos) is gated to systems view.
    // Tree view is a spatial model — folders and ancestors should never
    // disappear because of collection membership. Highlight via playing
    // collections (which compose orthogonally) is the right tree-view
    // affordance.
    let baseFiles: Set<string>;
    if (viewMode === 'systems' && soloCuration.size > 0) {
      // Curation solos union within the axis: Collected = files in some
      // collection, Loose = files in none.
      baseFiles = new Set<string>();
      if (soloCuration.has('collected')) {
        for (const p of collectedPaths) baseFiles.add(p);
      }
      if (soloCuration.has('loose')) {
        for (const p of uncollectedFilePaths) baseFiles.add(p);
      }
    } else {
      return null;
    }

    if (baseFiles.size === 0) return new Set<string>();
    return new Set<string>([...baseFiles, ...computeAncestorPaths(baseFiles)]);
  })();

  // Flat list of currently-visible tree rows for keyboard nav. Mirrors what
  // FileTree renders, so consecutive entries here are visually adjacent.
  $: visibleTreeRows = computeVisibleRows(files, expandedPaths, displayPaths, hiddenPaths, showHidden, {
    scopeBrightPaths, indexedFolderPaths, indexedPaths, hideOutOfScope,
  }, {
    indexedPaths, indexedFolderPaths, selectedPaths, foldersWithSelections, hideUnindexed,
  });

  function buildGameSystemMap(status: IndexStatusResult | null): Map<string, string[]> {
    const map = new Map<string, string[]>();
    if (!status) return map;
    for (const entry of [...status.up_to_date, ...status.to_update, ...status.to_remove]) {
      const tags = entry.game_systems && entry.game_systems.length > 0
        ? entry.game_systems
        : (entry.game_system && entry.game_system !== 'unknown' ? [entry.game_system] : []);
      if (tags.length > 0) {
        map.set(entry.path, tags);
      }
    }
    return map;
  }

  function buildIndexedPaths(status: IndexStatusResult | null): Set<string> {
    const paths = new Set<string>();
    if (!status) return paths;
    for (const entry of [...status.up_to_date, ...status.to_update, ...status.to_remove]) {
      paths.add(entry.path);
    }
    return paths;
  }

  async function refreshKnownSystems() {
    try {
      const result = await invoke<KnownGameSystemsResult>('get_known_game_systems');
      knownSystems = result.systems.sort((a, b) =>
        a.tag.toLowerCase().localeCompare(b.tag.toLowerCase())
      );
    } catch (e) {
      console.error('Failed to load known systems:', e);
    }
  }

  async function handleSetGameSystems(path: string, filename: string, tags: string[]) {
    pendingTagOverrides.set(path, tags);
    pendingTagOverrides = pendingTagOverrides;
    try {
      await invoke('set_game_systems', { filename, gameSystems: tags });
    } catch (e) {
      // Only the write failing justifies dropping the optimistic value —
      // otherwise the menu would keep claiming a tag that was never stored.
      console.error('Failed to set game systems:', e);
      pendingTagOverrides.delete(path);
      pendingTagOverrides = pendingTagOverrides;
      return;
    }
    // The tag is stored. A refresh that fails here must not roll it back:
    // the override just persists until a later refresh reconciles it.
    try {
      await refreshIndexStatus();
    } catch (e) {
      console.error('Index status refresh failed after tagging:', e);
    }
  }


  // ---------------------------------------------------------------------------
  // File focus, context menu & file operations
  // ---------------------------------------------------------------------------

  function findTreeNode(items: FileItem[], target: string): FileItem | null {
    for (const item of items) {
      if (item.path === target) return item;
      if (item.is_dir && item.children) {
        const found = findTreeNode(item.children, target);
        if (found) return found;
      }
    }
    return null;
  }

  // Loaded children must live in the root `files` array (not just inside
  // the FileTree component instance) so derived views like visibleTreeRows
  // can walk into them. Without this, keyboard nav skipped over freshly
  // expanded folders.
  async function ensureChildrenLoaded(path: string) {
    const node = findTreeNode(files, path);
    if (!node || !node.is_dir || node.children !== null) return;
    try {
      node.children = await invoke<FileItem[]>('list_files', { folderPath: path });
    } catch (e) {
      console.error('Failed to load folder:', e);
      node.children = [];
    }
    files = files;
  }

  async function handleToggleExpand(path: string) {
    if (expandedPaths.has(path)) {
      expandedPaths.delete(path);
      expandedPaths = expandedPaths;
    } else {
      await ensureChildrenLoaded(path);
      expandedPaths.add(path);
      expandedPaths = expandedPaths;
    }
  }

  function collapseAll() {
    expandedPaths = new Set();
  }

  async function focusTreeRow(path: string) {
    // Go through the setter so the focusedCollectionName mutex clears too —
    // assigning focusedFilePath directly leaves a stale collection focus
    // and the tree-nav gate keeps blocking ↓ in the tree.
    setFocusedFilePath(path);
    await tick();
    const el = document.querySelector(`[data-tree-row="${CSS.escape(path)}"]`);
    el?.scrollIntoView({ block: 'nearest' });
  }

  function moveTreeFocus(delta: number) {
    if (visibleTreeRows.length === 0) return;
    const current = indexOfPath(visibleTreeRows, focusedFilePath);
    // No caret yet — the region owns the arrows but nothing is ringed. Place
    // the caret rather than stepping, so the first press lands *on* the
    // restored row instead of one past it.
    if (current < 0) {
      const entry = materializeKey(
        visibleTreeRows.map((r) => r.path),
        lastFocusedFilePath,
        delta > 0 ? 1 : -1,
      );
      if (entry) focusTreeRow(entry);
      return;
    }
    const next = Math.min(visibleTreeRows.length - 1, Math.max(0, current + delta));
    focusTreeRow(visibleTreeRows[next].path);
  }

  // Cmd+Alt+← target. Opens the collections panel if it's collapsed, then
  // hands off to the panel's claim() so the rendering details (sort,
  // archive filter, draft row) stay encapsulated there.
  async function focusCollectionsRegion() {
    if (focusedCollectionName !== null) return;
    if (!collectionsPanelOpen) await togglePanel();
    await tick();
    collectionsPanelComponent?.claim(lastFocusedCollectionName);
  }

  // Cmd+Alt+↑/↓ move within the left dock. The dock stacks Collections over
  // Filters, so the chords are vertical and literal. A closed panel is
  // skipped; with neither open the chord is a no-op rather than opening one
  // — a chord that opens panels is hard to undo by accident.
  function focusFilterRegion() {
    if (focusedFilterRow !== null) return;
    if (!filterPanelOpen) return;
    filterPanelComponent?.claim(lastFocusedFilterRow);
  }

  // Cmd+Alt+← target: the dock's last-focused panel, not always Collections.
  // Falls through to focusCollectionsRegion, which still opens the dock when
  // it is closed — today's behavior for that chord is preserved.
  async function focusDockRegion() {
    if (focusedCollectionName !== null || focusedFilterRow !== null) return;
    const preferFilters = lastFocusedDockPane === 'filters' || !collectionsPanelOpen;
    if (filterPanelOpen && preferFilters) { focusFilterRegion(); return; }
    await focusCollectionsRegion();
  }

  // Cmd+Alt+→ target. Tree mode uses the locally-known visibleTreeRows;
  // systems mode delegates so SystemsView can resolve the right entry
  // (multi-tagged files have multiple visible-entries indices).
  function focusFileRegion() {
    if (focusedFilePath !== null) return;
    if (viewMode === 'systems') {
      systemsViewComponent?.claim(lastFocusedFilePath);
      return;
    }
    if (visibleTreeRows.length === 0) return;
    const restore = lastFocusedFilePath && indexOfPath(visibleTreeRows, lastFocusedFilePath) >= 0
      ? lastFocusedFilePath
      : visibleTreeRows[0].path;
    focusTreeRow(restore);
  }

  // A mousedown on the file pane's empty or non-selectable space — the scope
  // bar, a systems-view group header, the gap below the last row — points at
  // the region and deselects. Rows are skipped so their own click (which fires
  // after mousedown) owns the caret, and so dragging a row doesn't clear it.
  // Skip in search mode, which owns its own selectedResultIndex.
  function handleFileTreeAreaMousedown(event: MouseEvent) {
    if (searchViewOpen) return;
    const target = event.target as HTMLElement | null;
    if (target?.closest('[data-tree-row], [data-sv-row]')) return;
    pointAtEmpty('files');
  }

  // Returns true if the event was handled and shouldn't bubble further.
  function handleTreeNavKey(event: KeyboardEvent): boolean {
    const meta = event.metaKey || event.ctrlKey;
    const lk = event.key.toLowerCase();

    // Vim-style aliases: hjkl mirror the arrow keys. Only when no modifier
    // is held so chords like Cmd+J keep their meaning. h/l free up because
    // the hide action moved to '.', matching the Cmd+Shift+. show-hidden chord.
    const bareLetter = !meta && !event.shiftKey && !event.altKey;
    const isDown  = event.key === 'ArrowDown'  || (bareLetter && lk === 'j');
    const isUp    = event.key === 'ArrowUp'    || (bareLetter && lk === 'k');
    const isLeft  = event.key === 'ArrowLeft'  || (bareLetter && lk === 'h');
    const isRight = event.key === 'ArrowRight' || (bareLetter && lk === 'l');

    if (isDown) { event.preventDefault(); moveTreeFocus(1);  return true; }
    if (isUp)   { event.preventDefault(); moveTreeFocus(-1); return true; }

    if (event.key === 'Home' && !meta) {
      event.preventDefault();
      if (visibleTreeRows.length > 0) focusTreeRow(visibleTreeRows[0].path);
      return true;
    }
    if (event.key === 'End' && !meta) {
      event.preventDefault();
      if (visibleTreeRows.length > 0) focusTreeRow(visibleTreeRows[visibleTreeRows.length - 1].path);
      return true;
    }

    const idx = indexOfPath(visibleTreeRows, focusedFilePath);
    if (idx < 0) return false;
    const row = visibleTreeRows[idx];

    if (isRight) {
      event.preventDefault();
      if (row.item.is_dir) {
        if (!expandedPaths.has(row.path)) {
          // Expand and follow into the first child once children load.
          // Matches IDE convention (single-press to enter a folder) and
          // dodges the race where a fast ↓ would walk visibleTreeRows
          // before the lazy-load resolved. Guard on focusedFilePath so we
          // don't yank focus if the user moved on during the load.
          handleToggleExpand(row.path).then(() => {
            if (focusedFilePath !== row.path) return;
            const childIdx = visibleTreeRows.findIndex((r) => r.parentPath === row.path);
            if (childIdx > -1) focusTreeRow(visibleTreeRows[childIdx].path);
          });
        } else {
          // Already expanded — move to first child if any are visible.
          const childIdx = visibleTreeRows.findIndex((r, i) => i > idx && r.parentPath === row.path);
          if (childIdx > -1) focusTreeRow(visibleTreeRows[childIdx].path);
        }
      }
      return true;
    }
    if (isLeft) {
      event.preventDefault();
      if (row.item.is_dir && expandedPaths.has(row.path)) {
        handleToggleExpand(row.path);
      } else if (row.parentPath) {
        focusTreeRow(row.parentPath);
      }
      return true;
    }

    // X ticks the row's checkbox, whichever meaning it currently carries:
    // indexing normally, collection membership while armed. Space and Enter
    // are unbound here — →/← walk folders, ⌘O opens, R renames.
    if (bareLetter && lk === 'x') {
      event.preventDefault();
      if (armState) toggleMembership(row.item);
      else toogleSelection(row.path, row.item.is_dir, row.item, false);
      return true;
    }

    return false;
  }

  // Resolve the currently-focused row's path + FileItem in either view
  // mode. Tree mode reads from visibleTreeRows; systems mode delegates
  // to the SystemsView component (which owns the multi-occurrence
  // focusedIdx). Returns null when nothing is focused or the focused
  // path is no longer visible.
  function getFocusedFileItem(): { path: string; item: FileItem } | null {
    if (!focusedFilePath) return null;
    if (viewMode === 'systems') {
      const item = systemsViewComponent?.getFocusedItem();
      return item ? { path: item.path, item } : null;
    }
    const idx = indexOfPath(visibleTreeRows, focusedFilePath);
    if (idx < 0) return null;
    const row = visibleTreeRows[idx];
    return { path: row.path, item: row.item };
  }

  // Action keys on the focused file — R/S/./M/C plus Cmd+O reveal and
  // Shift+F10 / ContextMenu key. Lifted out of handleTreeNavKey so it
  // runs in both tree and systems modes. The caller already gates on
  // !inAnyInput, !renamingFilePath, !competingMenuOpen.
  function handleFocusedFileActionKey(event: KeyboardEvent): boolean {
    const focused = getFocusedFileItem();
    if (!focused) return false;

    const meta = event.metaKey || event.ctrlKey;
    const lk = event.key.toLowerCase();
    const bareLetter = !meta && !event.shiftKey && !event.altKey;

    // Cmd/Ctrl+O opens the file, which is what Cmd+O means everywhere. Reveal
    // moves to Alt+Cmd+R, matching VS Code's "Reveal in Finder". event.code
    // because Option rewrites event.key to a symbol on macOS layouts (⌥R → ®).
    if (meta && event.altKey && event.code === 'KeyR') {
      event.preventDefault();
      revealItemInDir(focused.path);
      return true;
    }

    if (meta && !event.shiftKey && !event.altKey && lk === 'o') {
      event.preventDefault();
      if (!focused.item.is_dir) openPath(focused.path);
      return true;
    }

    if (event.key === 'ContextMenu' || (event.shiftKey && event.key === 'F10')) {
      event.preventDefault();
      openContextMenuAtFocusedRow();
      return true;
    }

    // ⌘⌫ / Del — the same chord the collections panel spends on deleting a
    // track. Confirmed before anything moves, like the menu item it mirrors.
    if (isDeleteChord(event)) {
      event.preventDefault();
      deleteItem(focused.item);
      return true;
    }

    // Plain letters only — no modifiers. Hide is on '.' (not 'h') so
    // hjkl stays free for vim-style nav and '.' mirrors the Cmd+Shift+.
    // global chord. Period key on the main row OR on the numpad —
    // event.code is layout-independent (some layouts produce a different
    // event.key for the numpad period, e.g. ',' on German).
    if (bareLetter) {
      // R is the rename key across every pane.
      if (lk === 'r') {
        event.preventDefault();
        renamingFilePath = focused.path;
        return true;
      }
      // S/M are the one narrowing model on both axes. In tree view they
      // solo/mute the focused row on the collection axis; in systems
      // view they fall through to SystemsView's own handler, which
      // works the systems axis. The context menu moves to Shift+F10 /
      // the Menu key (M used to open it).
      if (lk === 's' && viewMode !== 'systems') {
        event.preventDefault();
        if (event.repeat) return true;
        const item = focused.item;
        holdLatch.press('s', () => toggleScopeSolo(item));
        return true;
      }
      if (lk === 'm' && viewMode !== 'systems') {
        event.preventDefault();
        if (event.repeat) return true;
        const item = focused.item;
        holdLatch.press('m', () => toggleScopeMute(item));
        return true;
      }
      if (lk === 'c') { event.preventDefault(); openContextMenuAtFocusedRow('add'); return true; }
      if (event.key === '.' || event.code === 'NumpadDecimal') {
        event.preventDefault();
        toggleHidden(focused.item);
        return true;
      }
    }

    return false;
  }

  function openContextMenuAtFocusedRow(initialSubmenu: 'add' | 'remove' | null = null) {
    const focused = getFocusedFileItem();
    if (!focused) return;
    // Try the tree row first, fall back to the systems-view row. Both
    // views share the focused-row anchor convention via a data-* attr;
    // multi-tagged files appear at multiple [data-sv-row] nodes, but the
    // first DOM match is good enough for menu placement (matches
    // SystemsView.scrollFocusedIntoView's fallback path).
    const el =
      (document.querySelector(`[data-tree-row="${CSS.escape(focused.path)}"]`) ??
        document.querySelector(`[data-sv-row="${CSS.escape(focused.path)}"]`)) as HTMLElement | null;
    const rect = el?.getBoundingClientRect();
    const synthetic = {
      clientX: rect ? rect.left + 24 : 100,
      clientY: rect ? rect.bottom : 100,
    } as MouseEvent;
    handleContextMenu(synthetic, focused.item, initialSubmenu);
  }

  // Escape ladder (closing precedence, top-most first):
  //   1. Open context menu               → close
  //   2. Inline rename in flight         → cancel
  //   3. Competing popover               → its own handler
  //   4. Search view, focus not in bar   → focus the search bar
  //   5. Search view, focus in bar       → leave to the browse view
  //   6. Focused tree row                → clear focus
  //   (modal Esc handled by Modal.svelte; the docked filter panel claims
  //   its own Esc while focus is inside it)
  function dismissSplash() {
    if (!showSplash) return;
    showSplash = false;
    if (splashTimer) {
      clearTimeout(splashTimer);
      splashTimer = null;
    }
  }

  // The release half of every hold. Unconditional on purpose: whatever
  // gating applied when the key went down, the key coming back up must
  // always reach the latch, or a control stays stuck in its held state.
  function handleGlobalKeyup(event: KeyboardEvent) {
    holdLatch.release(event.key.toLowerCase());
  }

  function handleGlobalKeydown(event: KeyboardEvent) {
    // While the launch splash is up, swallow the first keypress to dismiss
    // it. Users who hit a shortcut on launch shouldn't have it interpreted
    // as both "skip splash" and "trigger shortcut".
    if (showSplash) {
      dismissSplash();
      event.preventDefault();
      return;
    }

    // When a native <dialog> is open via showModal(), the browser inerts
    // the rest of the page (clicks, focus, screen-readers all skip), but
    // window-level keydown listeners still fire because keydown bubbles
    // through the focused dialog. Bail here so app-wide chords (Cmd+B,
    // Cmd+J, Cmd+Alt+←/→, Esc ladder, tree-nav letters, etc.) don't run
    // behind the modal. The dialog has its own handlers for what it
    // needs (Esc → cancel, Enter → submit, Tab cycles inside).
    if (document.querySelector('dialog[open]')) return;

    const target = event.target as HTMLElement | null;
    const inSearchInput = target?.classList.contains('search-input') === true;
    const inAnyInput =
      target?.matches('input, textarea, [contenteditable="true"]') === true;

    if (event.key === 'Escape') {
      // Yield to ContextMenu's own Esc handler — it knows about submenu
      // state, so it can step back from a submenu to the parent menu
      // before closing the whole thing. Closing here would skip that
      // step and slam the menu shut. focusedFilePath is intentionally
      // left intact across menu open/close.
      if (contextMenu) return;
      if (renamingFilePath) { renamingFilePath = null; return; }
      // A competing popover (sort menu / dropdown / the collections
      // panel's context menu) handles its own Esc. Don't reach the
      // branches below — that would close the search view or wipe the
      // tree highlight as a side effect of closing a menu.
      if (document.querySelector('.sort-menu, .dropdown, .context-menu')) return;
      // Escape mid-IME-composition just cancels the composition — never
      // step the ladder on it.
      if (event.isComposing) return;
      // Search-view ladder: anywhere in the view funnels focus to the
      // bar; the bar steps out to the browse view. The query is never
      // cleared here — × is the only clear, and it isn't an exit.
      if (searchViewOpen) {
        if (inSearchInput) {
          event.preventDefault();
          searchViewOpen = false;
          (target as HTMLInputElement).blur();
          // The browse view isn't in the DOM until Svelte flushes the
          // swap; focusFileRegion queries rows / the SystemsView binding.
          void tick().then(() => focusFileRegion());
        } else if (activePane === 'files') {
          event.preventDefault();
          headerComponent?.focus();
        }
        // An active dock pane keeps its own Esc semantics (its window
        // handler clears the highlight and releases the arrows); the next
        // Esc funnels to the bar.
        return;
      }
      if (focusedFilePath) { focusedFilePath = null; }
    }

    const meta = event.metaKey || event.ctrlKey;
    const lk = event.key.toLowerCase();

    // Cmd/Ctrl+F: focus the search input from anywhere in the app.
    if (meta && !event.shiftKey && lk === 'f') {
      event.preventDefault();
      headerComponent?.focus();
      return;
    }

    // Cmd/Ctrl+,: open Settings (always available).
    if (meta && !event.shiftKey && event.key === ',') {
      event.preventDefault();
      settingsInitialTab = 'general';
      showSettings = true;
      return;
    }

    // Cmd/Ctrl+B: toggle Collections sidebar.
    if (meta && !event.shiftKey && lk === 'b' && selectedFolder) {
      event.preventDefault();
      togglePanel();
      return;
    }

    // Cmd/Ctrl+1: Tree view, or collapse the whole tree when already there
    // (the view switch's repeat action). Cmd/Ctrl+2: Systems view. Numbered
    // rather than lettered because that's Finder's view-mode pattern, and
    // because the old ⌘T / ⌘J both collided with strong browser defaults
    // (new tab, downloads) while meaning nothing mnemonically.
    //
    // Gated on the search view being closed: while it's open Cmd+1-9 jumps to
    // result N, and one number cannot mean both. Escape remains the way out of
    // search, so no exit is lost — only the shortcut that used to double as one.
    if (meta && !event.shiftKey && !searchViewOpen && selectedFolder && (event.key === '1' || event.key === '2')) {
      event.preventDefault();
      if (event.key === '2') {
        setViewMode('systems');
      } else if (viewMode === 'tree') {
        collapseAll();
      } else {
        setViewMode('tree');
      }
      return;
    }

    // Cmd/Ctrl+Alt+←/→: jump keyboard focus between the collections panel
    // and the file pane (tree or systems). Restores the last-focused row
    // in the target region if it's still visible, else lands on the first
    // visible row. Skipped during search (the search input owns ←/→ for
    // text editing).
    if (meta && event.altKey && !event.shiftKey && selectedFolder && !searchViewOpen
        && (event.key === 'ArrowLeft' || event.key === 'ArrowRight')) {
      event.preventDefault();
      if (event.key === 'ArrowLeft') focusDockRegion();
      else focusFileRegion();
      return;
    }

    // Cmd+Alt+↑/↓: move between the two panels stacked in the left dock.
    if (meta && event.altKey && !event.shiftKey && selectedFolder && !searchViewOpen
        && (event.key === 'ArrowUp' || event.key === 'ArrowDown')) {
      event.preventDefault();
      if (event.key === 'ArrowDown') {
        // Collections sits above Filters.
        if (activePane === 'collections') { setFocusedCollectionName(null); focusFilterRegion(); }
      } else if (activePane === 'filters' && collectionsPanelOpen) {
        // Guarded on the panel being open: focusCollectionsRegion force-opens
        // it, and a dock-navigation chord must skip a closed panel rather
        // than open one — the down direction already does.
        setFocusedFilterRow(null);
        void focusCollectionsRegion();
      }
      return;
    }

    // Cmd/Ctrl+R: re-detect changes from disk (the lighter "what changed?"
    // action). Always preventDefault to keep the Tauri webview from
    // reloading the app even when this isn't available.
    if (meta && !event.shiftKey && lk === 'r') {
      event.preventDefault();
      if (selectedFolder && !isSyncing) handleManualSync();
      return;
    }

    // Cmd/Ctrl+S: commit selected files to the index — the real sync work
    // (same handler the "Sync Now" banner button calls). Standalone chord
    // because this is the headline action of the app.
    if (meta && !event.shiftKey && lk === 's') {
      event.preventDefault();
      if (selectedFolder && !isSyncing) handleSync();
      return;
    }

    // Cmd/Ctrl+Z is deliberately NOT bound. It used to revert the pending sync
    // selection, but ⌘Z is the most over-learned shortcut there is and it means
    // "undo what I just did" — not "discard the whole staged set". Someone
    // reflexively undoing a rename would have wiped their selection instead.
    // Reverting stays available on the banner's X, where it reads as the
    // deliberate act it is.

    // Cmd/Ctrl+I: show document info for the focused row. Mac muscle
    // memory from Finder ("Get Info"). indexedPaths.has implies the row
    // is a file (folders aren't tracked there) AND that get_document_stats
    // has data to return — matches the context menu's gating.
    if (meta && !event.shiftKey && lk === 'i' && !inAnyInput) {
      if (focusedFilePath && indexedPaths.has(focusedFilePath)) {
        event.preventDefault();
        statsModalPath = focusedFilePath;
        return;
      }
    }

    // Cmd/Ctrl+Shift+F: toggle the Filters panel (docked below the collections
    // panel in the left pane). Deliberately the shift-variant of Cmd+F: that
    // focuses search, this opens the console that shapes what search covers,
    // so the pair reads as a family. It replaced Cmd+E, which meant nothing
    // mnemonically and collided twice — macOS binds Cmd+E to "Use Selection
    // for Find" in any text field, and Finder binds it to Eject.
    //
    // The Cmd+F branch above excludes shift, so this can't be shadowed by it.
    if (meta && event.shiftKey && lk === 'f' && selectedFolder) {
      event.preventDefault();
      toggleFilterPanel();
      return;
    }

    // Cmd/Ctrl+Shift+.: toggle "Show hidden" (Finder convention).
    if (meta && event.shiftKey && (event.key === '.' || event.key === '>') && selectedFolder) {
      event.preventDefault();
      toggleShowHidden();
      return;
    }

    // Cmd/Ctrl+Shift+O: reveal the library root folder in the OS file
    // explorer (same handler the status-bar folder button calls). Skipped
    // when an input has focus to match Cmd+Z's behavior.
    if (meta && event.shiftKey && lk === 'o' && selectedFolder && !inAnyInput) {
      event.preventDefault();
      revealItemInDir(selectedFolder);
      return;
    }

    // Cmd/Ctrl+N: start a new collection. Auto-opens the sidebar if it's
    // closed so the draft row is visible immediately.
    if (meta && !event.shiftKey && lk === 'n' && selectedFolder && !inAnyInput) {
      event.preventDefault();
      (async () => {
        if (!collectionsPanelOpen) await togglePanel();
        inlineCreateCollection();
      })();
      return;
    }

    // Cmd/Ctrl+Enter: save the in-progress collection (draft or files
    // edit). Works from anywhere, including inside the rename input —
    // it commits the rename via that input's own handler first, then
    // this branch fires because metaKey + Enter wasn't preventDefault'd
    // by the input's logic. Guard on having pending state so the chord
    // is a clear no-op when nothing's being edited.
    // `?` — show keyboard shortcuts overlay. Match on event.key (the
    // produced character) rather than Shift+/ so any layout that emits
    // `?` from a different physical key still triggers. Bare chord, gated
    // out of inputs so typing a literal `?` works as expected.
    if (event.key === '?' && !meta && !event.altKey && !inAnyInput) {
      event.preventDefault();
      showHelpOverlay = true;
      return;
    }

    // Master bypass — the console's "hear it raw" switch. Tap latches,
    // hold is momentary (holdLatch), same as S/M on a row. Deliberately
    // does not clear anything: the chips and lamps stay lit while the
    // signal passes through them, so you can see what you're bypassing.
    if (lk === 'b' && !meta && !event.altKey && !event.shiftKey && !inAnyInput) {
      event.preventDefault();
      if (event.repeat) return;
      holdLatch.press('b', toggleScopeBypass);
      return;
    }

    // ── Tree-row navigation ─────────────────────────────────────────────
    // Active when a library is loaded, the search view is closed, no
    // menu/rename is open.
    // Other popovers (filter menu, sort menu, dropdowns) attach their own
    // keydown listeners but they fire AFTER this one — so we have to skip
    // here when the DOM tells us a competing menu is open. Querying by
    // class is pragmatic; once chunk c is fully shipped these could share
    // a small open-menus store instead.
    const competingMenuOpen = !!document.querySelector('.filter-menu, .sort-menu, .dropdown');

    // Action keys (R/S/./M/C, Cmd+O reveal, Shift+F10/ContextMenu) work
    // on the focused file in both tree and systems modes. Runs ahead of
    // the tree-only nav block so action keys don't fall through to view-
    // specific handlers in either mode.
    const fileActionGate =
      selectedFolder && !searchViewOpen && !contextMenu && !renamingFilePath &&
      !competingMenuOpen && activePane === 'files' && !inAnyInput;
    if (fileActionGate && handleFocusedFileActionKey(event)) return;

    // Tree-row arrow navigation. Systems view owns its own arrow nav,
    // so this block is gated to tree mode only. Gating on activePane rather
    // than on a null collection token also stops ↓ stealing the caret out of
    // the filter panel, which the old check never considered.
    if (selectedFolder && !searchViewOpen && !contextMenu && !renamingFilePath && !competingMenuOpen && activePane === 'files' && viewMode === 'tree') {
      if (!inAnyInput && handleTreeNavKey(event)) return;
    }

    // Gate on the view being on screen, not on the committed query —
    // after exiting, query and results persist while tree/systems is
    // visible, and Cmd+1–9 must not jump to rows that aren't rendered.
    if (!searchViewOpen || searchResults.length === 0) return;

    const inInput = inSearchInput;
    const inList = target?.closest('.search-results') !== null;

    // Cmd/Ctrl + 1..9: jump to result N and move focus to it so Enter
    // opens. Works regardless of where focus currently lives.
    if ((event.metaKey || event.ctrlKey) && /^[1-9]$/.test(event.key)) {
      const idx = parseInt(event.key, 10) - 1;
      if (idx < searchResults.length) {
        event.preventDefault();
        selectedResultIndex = idx;
        searchResultsComponent?.focusRow(idx);
      }
      return;
    }

    // Combobox flow: ArrowDown from the input pops focus into the list at
    // the current selection. Arrow nav within the list moves both
    // selection and focus together. ArrowUp from the first row pops back
    // to the input. Enter on a focused row opens; Escape is handled by
    // the ladder above.
    if (event.key === 'ArrowDown') {
      if (inInput) {
        event.preventDefault();
        searchResultsComponent?.focusRow(selectedResultIndex);
      } else if (inList) {
        event.preventDefault();
        selectedResultIndex = Math.min(searchResults.length - 1, selectedResultIndex + 1);
        searchResultsComponent?.focusRow(selectedResultIndex);
      }
    } else if (event.key === 'ArrowUp' && inList) {
      event.preventDefault();
      if (selectedResultIndex > 0) {
        selectedResultIndex -= 1;
        searchResultsComponent?.focusRow(selectedResultIndex);
      } else {
        headerComponent?.focus();
      }
    } else if (event.key === 'Enter' && inList) {
      event.preventDefault();
      const sel = searchResults[selectedResultIndex];
      if (sel) handleOpenResult(sel.filename, sel.page_start);
    }
  }

  function handleContextMenu(event: MouseEvent, item: FileItem, initialSubmenu: 'add' | 'remove' | null = null) {
    // Highlight whatever was right-clicked / triggered via M, including
    // folders — keyboard nav allows folder focus since chunk b.
    setFocusedFilePath(item.path);
    // Snapshot isIndexed at click time so the open menu doesn't keep a live
    // reactive dependency on indexedPaths.
    const directlyHidden = hiddenPaths.has(item.path);
    contextMenu = {
      x: event.clientX,
      y: event.clientY,
      item,
      isIndexed: indexedPaths.has(item.path),
      initialSubmenu,
      hideState: {
        directlyHidden,
        inheritedHidden: !directlyHidden && isPathHidden(item.path),
      },
    };
  }

  async function handleContextOpen() {
    if (contextMenu) {
      await openPath(contextMenu.item.path);
      contextMenu = null;
    }
  }

  function handleContextReveal() {
    if (contextMenu) {
      revealItemInDir(contextMenu.item.path);
      contextMenu = null;
    }
  }

  function handleContextRename() {
    if (contextMenu) {
      renamingFilePath = contextMenu.item.path;
      contextMenu = null;
    }
  }

  async function handleContextReindex() {
    if (!contextMenu) return;
    const item = contextMenu.item;
    contextMenu = null;
    // Not danger: rebuilding chunks destroys nothing, so the prompt focuses
    // Confirm and Enter rips straight through it.
    const confirmed = await confirmPrompt.request({
      title: 'Re-index file',
      message: `Re-index "${item.name}"? This rebuilds its chunks.`,
      confirmLabel: 'Re-index',
    });
    if (!confirmed) return;
    try {
      await invoke('reindex_file', { path: item.path });
      await refreshIndexStatus();
      jobNotification.show({ type: 'success', message: `Re-indexed ${item.name}`, duration: 3000 });
    } catch (e) {
      jobNotification.show({ type: 'error', message: `Re-index failed: ${String(e)}`, duration: 5000 });
    }
  }

  function handleContextShowStats() {
    if (!contextMenu) return;
    statsModalPath = contextMenu.item.path;
    contextMenu = null;
  }

  function handleContextAddToCollection(name: string) {
    if (!contextMenu) return;
    const item = contextMenu.item;
    contextMenu = null;
    addToCollection(name, item);
  }

  function handleContextRemoveFromCollection(name: string) {
    if (!contextMenu) return;
    const item = contextMenu.item;
    contextMenu = null;
    removeFromCollection(name, item);
  }

  function handleContextToggleSolo() {
    if (!contextMenu) return;
    const item = contextMenu.item;
    contextMenu = null;
    toggleScopeSolo(item);
  }

  function handleContextToggleMute() {
    if (!contextMenu) return;
    const item = contextMenu.item;
    contextMenu = null;
    toggleScopeMute(item);
  }

  function handleContextToggleHidden() {
    if (!contextMenu) return;
    const item = contextMenu.item;
    contextMenu = null;
    toggleHidden(item);
  }

  function handleContextAddToNewCollection() {
    if (!contextMenu) return;
    const item = contextMenu.item;
    contextMenu = null;
    createCollectionFromItem(item);
  }

  async function handleContextDelete() {
    if (!contextMenu) return;
    const item = contextMenu.item;
    contextMenu = null;
    await deleteItem(item);
  }

  // Confirm-then-trash for one row. Shared by the context menu's Delete item
  // and the ⌘⌫ / Del chord on the focused row — both act on a single item,
  // never on the checkbox selection.
  async function deleteItem(item: FileItem) {
    const label = item.is_dir ? 'folder' : 'file';
    const confirmed = await confirmPrompt.request({
      title: `Delete ${label}`,
      message: `Move "${item.name}" to Trash?`,
      confirmLabel: 'Delete',
      danger: true,
    });
    if (!confirmed) return;

    try {
      if (item.is_dir) {
        await invoke('delete_folder', { path: item.path });
        const prefix = item.path + '/';
        for (const p of selectedPaths) {
          if (p.startsWith(prefix)) selectedPaths.delete(p);
        }
        selectedPaths = selectedPaths;
        for (const p of syncedPaths) {
          if (p.startsWith(prefix)) syncedPaths.delete(p);
        }
        for (const p of expandedPaths) {
          if (p.startsWith(prefix) || p === item.path) expandedPaths.delete(p);
        }
        expandedPaths = expandedPaths;
      } else {
        await invoke('delete_file', { path: item.path });
        if (focusedFilePath === item.path) focusedFilePath = null;
      }
      if (selectedFolder) await loadFiles(selectedFolder);
      refreshIndexStatus();
    } catch (e) {
      jobNotification.show({ type: 'error', message: `Delete failed: ${String(e)}`, duration: 5000 });
    }
  }

  function updatePathPrefix(paths: Set<string>, oldPrefix: string, newPrefix: string): Set<string> {
    const childPrefix = oldPrefix + '/';
    const updated = new Set<string>();
    for (const p of paths) {
      updated.add(p.startsWith(childPrefix) ? newPrefix + p.slice(oldPrefix.length) : p);
    }
    return updated;
  }

  // Path solo/mute migration for renames — unlike updatePathPrefix (which
  // only re-keys descendants), a scope ref can be keyed exactly at the
  // renamed path itself, so that entry moves too and picks up the new
  // basename as its label. Descendant entries (folder rename only) keep
  // their own basename — only their ancestor's segment of the path changed.
  function updateScopeRefMap(
    map: Map<string, ScopeRef>,
    oldPath: string,
    newPath: string,
    newLabel: string
  ): { result: Map<string, ScopeRef>; changed: boolean } {
    const childPrefix = oldPath + '/';
    let changed = false;
    const updated = new Map<string, ScopeRef>();
    for (const [path, ref] of map) {
      if (path === oldPath) {
        updated.set(newPath, { ...ref, label: newLabel });
        changed = true;
      } else if (path.startsWith(childPrefix)) {
        updated.set(newPath + path.slice(oldPath.length), ref);
        changed = true;
      } else {
        updated.set(path, ref);
      }
    }
    return { result: updated, changed };
  }

  async function handleRenameSubmit(oldPath: string, newName: string, isDir: boolean = false) {
    try {
      let newPath: string;
      if (isDir) {
        newPath = await invoke<string>('rename_folder', { oldPath, newName });
        selectedPaths = updatePathPrefix(selectedPaths, oldPath, newPath);
        syncedPaths = updatePathPrefix(syncedPaths, oldPath, newPath);
        expandedPaths = updatePathPrefix(expandedPaths, oldPath, newPath);
      } else {
        newPath = await invoke<string>('rename_file', { oldPath, newName });
        if (focusedFilePath === oldPath) focusedFilePath = newPath;
        // Swap the path in selectedPaths so compute_diff can match old→new by content hash
        if (selectedPaths.has(oldPath)) {
          selectedPaths.delete(oldPath);
          selectedPaths.add(newPath);
          selectedPaths = selectedPaths;
        }
      }
      // Scope solos/mutes follow the rename too — same treatment
      // renameCollection gives its name sets. Without this, a soloed
      // folder renamed in-app leaves a stale ref that empties the scope
      // on a path that's still live.
      const soloUpdate = updateScopeRefMap(scopeSolos, oldPath, newPath, newName);
      const muteUpdate = updateScopeRefMap(scopeMutes, oldPath, newPath, newName);
      if (soloUpdate.changed) scopeSolos = soloUpdate.result;
      if (muteUpdate.changed) scopeMutes = muteUpdate.result;
      if (soloUpdate.changed || muteUpdate.changed) {
        persistScopeConsole();
        if (committedQuery) runSearch(committedQuery);
      }
      renamingFilePath = null;
      if (selectedFolder) await loadFiles(selectedFolder);
      refreshIndexStatus();
    } catch (e) {
      console.error('Rename failed', { oldPath, newName, isDir, error: e });
      // "File not found" / "Folder not found" almost always means the
      // entry shown in the UI is stale — the file was moved or renamed
      // outside the app, and our cached list still references the old
      // path. Point the user at the re-detect chord rather than just
      // surfacing the raw rust error.
      const msg = String(e);
      const isMissing = msg === 'File not found' || msg === 'Folder not found';
      const message = isMissing
        ? `${msg} — the ${isDir ? 'folder' : 'file'} may have been moved or renamed outside the app. Press ${chord('sync.run')} to refresh and try again.`
        : `Rename failed: ${msg}`;
      jobNotification.show({ type: 'error', message, duration: 8000 });
      renamingFilePath = null;
    }
  }

  function handleRenameCancel() {
    renamingFilePath = null;
  }

  // ---------------------------------------------------------------------------
  // Collections
  // ---------------------------------------------------------------------------

  async function loadCollections() {
    try {
      const result = await invoke<CollectionsResult>('get_collections');
      // A sync completing mid-session calls through here. Without the
      // merge, disk state would overwrite clicks the scheduler hasn't
      // written yet — and the next flush would then persist that revert.
      collections = mergeArmedCollection(
        result.collections,
        armedCollection,
        armCommitter.pending() && armedCollection
          ? collections[armedCollection]?.file_paths ?? null
          : null
      );
    } catch (e) {
      console.log('Could not fetch collections:', e);
    }
  }

  // ---- Arming a track -------------------------------------------------
  //
  // Arm a collection and the file tree becomes a live membership surface
  // for it: clicking a book files or unfiles it on the spot. No Save, no
  // Cancel — each toggle is its own undo.

  const armCommitter = createCommitScheduler({
    write: async (name, filePaths) => {
      await invoke<CollectionMutationResult>('update_collection', { name, filePaths });
      lastCommittedPaths = filePaths;
    },
    onError: (name, err) => {
      // The failed write carried every un-persisted click, so they are
      // gone by construction. Put the row back to what the sidecar last
      // acknowledged, and leave the mode rather than invite more losses.
      const col = collections[name];
      if (col) {
        collections = {
          ...collections,
          [name]: { ...col, file_paths: lastCommittedPaths, file_count: lastCommittedPaths.length },
        };
      }
      armCommitter.cancel();
      armedCollection = null;
      jobNotification.show({
        type: 'error',
        message: `Could not save "${name}" — reverted to the last saved state. ${String(err)}`,
        duration: 8000,
      });
    },
  });

  // Everything the tree needs to draw and answer the arm slot. Bundled so
  // the recursive component threads one prop instead of five.
  $: armState = (() => {
    if (!armedCollection) return null;
    const col = collections[armedCollection];
    if (!col) return null;
    const paths = new Set(col.file_paths);
    return {
      name: col.name,
      color: col.color,
      paths,
      folders: computeFolderMembership(indexedPaths, paths),
    };
  })();

  // A collection deleted out from under the arm (or archived away) takes
  // the mode with it rather than leaving slots pointing at nothing.
  $: if (armedCollection && !collections[armedCollection]) armedCollection = null;

  async function armCollection(name: string) {
    if (armedCollection === name) {
      await disarmCollection();
      return;
    }
    // A draft isn't a track yet — you can't arm what doesn't exist.
    if (!collections[name]) return;
    await armCommitter.flush();
    armedCollection = name;
    lastCommittedPaths = collections[name].file_paths;
    collectionsPanelOpen = true;
  }

  async function disarmCollection() {
    if (!armedCollection) return;
    await armCommitter.flush();
    armedCollection = null;
  }

  /**
   * The one path every membership change takes — the tree's arm toggle, a
   * drop, the panel's remove ×. Armed collections patch locally and commit
   * through the scheduler; anything else writes straight through.
   *
   * `collections` is patched optimistically because it's the single source
   * of truth: the ribbon index, the panel's file count, and the curation
   * channels all derive from it and stay honest for free.
   */
  async function applyMembership(
    name: string,
    paths: string[],
    present: boolean
  ): Promise<number | null> {
    const col = collections[name];
    if (!col || paths.length === 0) return 0;
    const result = present
      ? addMembers(col.file_paths, paths)
      : removeMembers(col.file_paths, new Set(paths));
    const changed = 'added' in result ? result.added : result.removed;
    if (changed === 0) return 0;

    const next = result.next;
    collections = {
      ...collections,
      [name]: { ...col, file_paths: next, file_count: next.length },
    };

    if (armedCollection === name) {
      armCommitter.schedule(name, next);
    } else {
      try {
        await invoke<CollectionMutationResult>('update_collection', { name, filePaths: next });
      } catch (e) {
        await loadCollections();
        jobNotification.show({
          type: 'error',
          message: `Could not update "${name}": ${String(e)}`,
          duration: 5000,
        });
        return null;
      }
    }
    return changed;
  }

  // ---- Dragging rows onto a collection --------------------------------

  // Resolve what a row actually contributes at dragstart, where
  // indexedPaths is in scope. A row with nothing indexed under it returns
  // null and the drag is refused outright — better than a dead drag that
  // ends in an apology.
  function beginPathDrag(path: string, name: string, isDir: boolean): TreePathsPayload | null {
    const paths = indexedPathsUnder(path, indexedPaths);
    if (paths.length === 0) return null;
    const payload = {
      paths,
      label: isDir ? name : name.replace(/\.pdf$/i, ''),
    };
    setTreePathsPayload(payload);
    return payload;
  }

  async function dropPathsOnCollection(name: string, paths: string[]) {
    const added = await applyMembership(name, paths, true);
    if (added === null) return; // already reported
    jobNotification.show(
      added > 0
        ? {
            type: 'success',
            message: `Added ${added} file${added === 1 ? '' : 's'} to "${name}"`,
            duration: 4000,
          }
        : { type: 'info', message: `Already in "${name}"`, duration: 3000 }
    );
  }

  function dropPathsOnNewCollection(paths: string[], label: string) {
    beginCreateCollection(paths, label);
  }

  // The × on a panel row's expanded file list.
  async function removeFileFromCollection(name: string, path: string) {
    const removed = await applyMembership(name, [path], false);
    if (removed) {
      jobNotification.show({
        type: 'success',
        message: `Removed 1 file from "${name}"`,
        duration: 3000,
      });
    }
  }

  // Tree/systems-view arm slot. A partly-enrolled folder fills; a full one
  // empties, so a second click always undoes the first.
  const onToggleMembership = (item: FileItem, shiftKey = false) => toggleMembership(item, shiftKey);

  // Anchor for shift-range membership, mirroring lastIndexClickedPath.
  let lastCollectClickedPath: string | null = null;

  function toggleMembership(item: FileItem, shiftKey = false) {
    if (!armState) return;

    // Shift extends from the last row filed, the same gesture the indexing
    // checkbox and the systems view both offer. Only indexed rows in the
    // span take part — the rest can't be members.
    if (shiftKey && !item.is_dir && lastCollectClickedPath) {
      const flat = flattenVisibleFilePaths(files);
      const a = flat.indexOf(lastCollectClickedPath);
      const b = flat.indexOf(item.path);
      if (a !== -1 && b !== -1) {
        const span = flat
          .slice(Math.min(a, b), Math.max(a, b) + 1)
          .filter((p) => indexedPaths.has(p));
        if (span.length > 0) {
          const adding = !armState.paths.has(item.path);
          lastCollectClickedPath = item.path;
          if (adding) curationAdd(span);
          else curationRemove(span);
          return;
        }
      }
    }

    const paths = item.is_dir ? indexedPathsUnder(item.path, indexedPaths) : [item.path];
    if (paths.length === 0) return;
    const full = memberStateFor(item.path, item.is_dir, armState.paths, armState.folders) === 'all';
    if (!item.is_dir) lastCollectClickedPath = item.path;
    if (full) curationRemove(paths);
    else curationAdd(paths);
  }

  // The systems view's checkboxes and the tree's arm slot both come
  // through here, so the two surfaces can never disagree.
  function curationAdd(paths: string[]) {
    if (armedCollection) void applyMembership(armedCollection, paths, true);
  }

  function curationRemove(paths: string[]) {
    if (armedCollection) void applyMembership(armedCollection, paths, false);
  }

  /**
   * Make a collection, for real, right away — Finder's "untitled folder",
   * not a form you fill in and submit. It lands named, focused, armed and
   * in rename mode, so naming it and filling it are one motion instead of
   * a staged act with its own row, its own path set and its own modal
   * rules. Creating from a folder or a drop seeds it in the same call.
   *
   * The escape hatch for a stray ⌘N is discardNewIfEmpty below, not a
   * Cancel button: backing out is rare, so it shouldn't cost a permanent
   * affordance on every new row.
   */
  async function createCollection(base: string, paths: string[] = []) {
    const name = uniqueCollectionName(base, collections);
    try {
      // `description` is a required arg on the Rust side even though
      // nothing in the UI authors one — omitting it fails arg
      // deserialization before the call ever reaches the sidecar.
      await invoke<CollectionMutationResult>('create_collection', {
        name,
        filePaths: paths,
        description: '',
      });
      await loadCollections();
      collectionsPanelOpen = true;
      setFocusedCollectionName(name);
      await armCollection(name);
      // Seeded from a folder or a drop: say how much landed. An empty one
      // needs no toast — the new row appearing is the feedback.
      if (paths.length > 0) {
        jobNotification.show({
          type: 'success',
          message: `Created "${name}" with ${paths.length} file${paths.length === 1 ? '' : 's'}`,
          duration: 4000,
        });
      }
    } catch (e) {
      jobNotification.show({
        type: 'error',
        message: `Could not create "${name}": ${String(e)}`,
        duration: 5000,
      });
    }
  }

  /**
   * Open the panel's create box to name a new collection. Every route in
   * — ⌘N, the box itself, a folder's context menu, a drop — lands here, so
   * there's one place a collection gets named and one place it gets made.
   * `paths` seeds it; `suggested` pre-fills the field.
   */
  function beginCreateCollection(paths: string[] = [], suggested = '') {
    if (armedCollection) void disarmCollection();
    collectionsPanelOpen = true;
    newCollectionSeed = { paths, name: suggested };
  }

  function commitNewCollection(name: string) {
    const seed = newCollectionSeed;
    newCollectionSeed = null;
    if (seed) void createCollection(name, seed.paths);
  }

  function cancelNewCollection() {
    newCollectionSeed = null;
  }

  async function requestDeleteCollection(name: string) {
    const confirmed = await confirmPrompt.request({
      title: 'Delete collection',
      message: `Delete "${name}"? Its files are freed to Loose — nothing in your library is deleted.`,
      confirmLabel: 'Delete',
      danger: true,
    });
    if (!confirmed) return;
    // Drop the arm first: a pending flush would PUT a name that no longer
    // exists and surface a 404 as a save failure.
    if (armedCollection === name) {
      armCommitter.cancel();
      armedCollection = null;
    }
    try {
      await invoke('delete_collection', { name });
      // Playing and muted state on the deleted collection clear with it
      // — the chips disappear rather than scoping on a ghost.
      const wasPlaying = playingCollections.delete(name);
      if (wasPlaying) playingCollections = playingCollections;
      const wasMuted = mutedCollectionNames.delete(name);
      if (wasMuted) mutedCollectionNames = mutedCollectionNames;
      if (wasPlaying || wasMuted) persistScopeConsole();
      if (collectionsCustomOrder.includes(name)) {
        collectionsCustomOrder = collectionsCustomOrder.filter((n) => n !== name);
        persistCollectionsSort();
      }
      await loadCollections();
      if ((wasPlaying || wasMuted) && committedQuery) runSearch(committedQuery);
      jobNotification.show({ type: 'success', message: `Deleted "${name}"`, duration: 4000 });
    } catch (e) {
      jobNotification.show({ type: 'error', message: `Delete failed: ${String(e)}`, duration: 5000 });
    }
  }

  // ---------------------------------------------------------------------------
  // Bulk collection actions (right-click menu)
  // ---------------------------------------------------------------------------

  async function addToCollection(name: string, item: FileItem) {
    const col = collections[name];
    if (!col) return;
    const candidates = item.is_dir ? indexedPathsUnder(item.path, indexedPaths) : [item.path];
    if (candidates.length === 0) {
      jobNotification.show({
        type: 'info',
        message: `No indexed PDFs under "${item.name}"`,
        duration: 4000,
      });
      return;
    }
    const before = col.file_paths.length;
    const merged = Array.from(new Set([...col.file_paths, ...candidates]));
    const added = merged.length - before;
    if (added === 0) {
      jobNotification.show({
        type: 'info',
        message: `Already in "${name}"`,
        duration: 3000,
      });
      return;
    }
    try {
      await invoke<CollectionMutationResult>('update_collection', {
        name,
        filePaths: merged,
        description: col.description,
      });
      await loadCollections();
      jobNotification.show({
        type: 'success',
        message: `Added ${added} file${added === 1 ? '' : 's'} to "${name}"`,
        duration: 4000,
      });
    } catch (e) {
      jobNotification.show({
        type: 'error',
        message: `Could not add to "${name}": ${String(e)}`,
        duration: 5000,
      });
    }
  }

  async function removeFromCollection(name: string, item: FileItem) {
    const col = collections[name];
    if (!col) return;
    const targets = new Set(item.is_dir ? indexedPathsUnder(item.path, indexedPaths) : [item.path]);
    const remaining = col.file_paths.filter(p => !targets.has(p));
    const removed = col.file_paths.length - remaining.length;
    if (removed === 0) return;
    try {
      await invoke<CollectionMutationResult>('update_collection', {
        name,
        filePaths: remaining,
        description: col.description,
      });
      await loadCollections();
      jobNotification.show({
        type: 'success',
        message: `Removed ${removed} file${removed === 1 ? '' : 's'} from "${name}"`,
        duration: 4000,
      });
    } catch (e) {
      jobNotification.show({
        type: 'error',
        message: `Could not remove from "${name}": ${String(e)}`,
        duration: 5000,
      });
    }
  }

  // Create a collection seeded with the indexed PDFs under `item`.
  function createCollectionFromItem(item: FileItem) {
    const candidates = item.is_dir
      ? indexedPathsUnder(item.path, indexedPaths)
      : [item.path];
    if (candidates.length === 0) {
      jobNotification.show({
        type: 'info',
        message: `No indexed PDFs under "${item.name}"`,
        duration: 4000,
      });
      return;
    }
    const baseName = item.is_dir ? item.name : item.name.replace(/\.pdf$/i, '');
    beginCreateCollection(candidates, baseName);
  }

  // ---------------------------------------------------------------------------
  // Collections panel + metadata dialog
  // ---------------------------------------------------------------------------

  async function togglePanel() {
    // Closing the panel takes away the only ● that can turn the mode off,
    // so leave the mode with it.
    if (collectionsPanelOpen && armedCollection) await disarmCollection();
    collectionsPanelOpen = !collectionsPanelOpen;
    // Closing unmounts the panel and its window keydown handler, so an
    // off-screen region could never release the arrows on its own — and
    // nothing would answer ↓. The setter hands ownership back to the file
    // region as it clears the caret.
    if (!collectionsPanelOpen) setFocusedCollectionName(null);
    try {
      const store = await load('settings.json');
      await store.set('collectionsPanelOpen', collectionsPanelOpen);
      await store.save();
    } catch (e) {
      console.log('Could not persist panel state:', e);
    }
  }

  async function toggleFilterPanel() {
    filterPanelOpen = !filterPanelOpen;
    // Same reasoning as togglePanel: an unmounted pane must not keep the
    // arrows, or the next ↓ goes nowhere.
    if (!filterPanelOpen) setFocusedFilterRow(null);
    try {
      const store = await load('settings.json');
      await store.set('filterPanelOpen', filterPanelOpen);
      await store.save();
    } catch (e) {
      console.log('Could not persist panel state:', e);
    }
  }

  // Panel "+" handler, and ⌘N. Opens the create box with an empty field.
  function inlineCreateCollection() {
    beginCreateCollection();
  }

  // Inline rename of an existing collection (R / double-click on the
  // panel row). Collisions surface as a notification; the row snaps back.
  async function renameCollection(name: string, newName: string) {
    if (newName === name) return;
    // Land any armed writes under the old name — after the rename they
    // would 404.
    if (armedCollection === name) await armCommitter.flush();
    try {
      await invoke<CollectionMutationResult>('rename_collection', {
        name,
        newName,
      });
      // Re-key the local record before anything else reads it: the arm
      // clears itself when its collection isn't in `collections`, so
      // moving the arm to a name the map doesn't carry yet would disarm
      // in the window before loadCollections lands.
      const renamed = collections[name];
      if (renamed) {
        const { [name]: _gone, ...rest } = collections;
        collections = { ...rest, [newName]: { ...renamed, name: newName } };
      }
      // The arm follows the rename, like the transport state below.
      if (armedCollection === name) armedCollection = newName;
      // Migrate any playing state keyed by the old name so an armed
      // track (and its chip) follows the rename instead of going stale.
      if (playingCollections.has(name)) {
        playingCollections.delete(name);
        playingCollections.add(newName);
        playingCollections = playingCollections;
      }
      if (mutedCollectionNames.has(name)) {
        mutedCollectionNames.delete(name);
        mutedCollectionNames.add(newName);
        mutedCollectionNames = mutedCollectionNames;
      }
      persistScopeConsole();
      // Custom sort order follows the rename in place.
      if (collectionsCustomOrder.includes(name)) {
        collectionsCustomOrder = collectionsCustomOrder.map((n) => (n === name ? newName : n));
        persistCollectionsSort();
      }
      jobNotification.show({
        type: 'success',
        message: `Renamed to "${newName}"`,
        duration: 4000,
      });
      await loadCollections();
      if (committedQuery) runSearch(committedQuery);
    } catch (e) {
      jobNotification.show({
        type: 'error',
        message: `Rename failed: ${String(e)}`,
        duration: 5000,
      });
    }
  }

  // Pigment change from the panel's context menu — bookmarks, chips, and
  // index cells all derive from `collections`, so a reload updates them.
  async function setCollectionColor(name: string, color: string | null) {
    try {
      await invoke('update_collection', { name, color: color ?? '' });
      await loadCollections();
    } catch (e) {
      jobNotification.show({
        type: 'error',
        message: `Could not set pigment: ${String(e)}`,
        duration: 5000,
      });
    }
  }

  async function toggleArchived(name: string, archived: boolean) {
    // A shelved track has no transport, and no record-arm either.
    if (archived && armedCollection === name) await disarmCollection();
    try {
      await invoke('update_collection', { name, archived });
      // Archiving a playing collection stops it — a shelved track can't
      // stay in the search scope, so its chip clears with it.
      if (archived && playingCollections.has(name)) {
        playingCollections.delete(name);
        playingCollections = playingCollections;
        persistScopeConsole();
        if (committedQuery) runSearch(committedQuery);
      }
      await loadCollections();
      jobNotification.show({
        type: 'success',
        message: archived ? `Archived "${name}"` : `Unarchived "${name}"`,
        duration: 3000,
      });
    } catch (e) {
      jobNotification.show({
        type: 'error',
        message: `Could not ${archived ? 'archive' : 'unarchive'} "${name}": ${String(e)}`,
        duration: 5000,
      });
    }
  }

  // Copy MCP config to clipboard
  async function handleCopyMcpConfig() {
    try {
      const config = await invoke<string>('get_mcp_config');
      await writeText(config);
      jobNotification.show({
        type: 'success',
        message: 'MCP config copied to clipboard!',
        duration: 4000,
      });
    } catch (e) {
      jobNotification.show({
        type: 'error',
        message: `Copy failed: ${String(e)}`,
        duration: 5000,
      });
    }
  }

  // Compact the database to reclaim unused space
  async function handleCompact() {
    try {
      const result = await invoke<{ reclaimed: number }>('compact_database');
      const msg = result.reclaimed > 0
        ? `Reclaimed ${formatSize(result.reclaimed)}`
        : 'Nothing to reclaim';
      jobNotification.show({ type: 'success', message: msg, duration: 4000 });
      await refreshIndexStatus(); // refresh stats to update reclaimable_bytes
    } catch (e) {
      jobNotification.show({ type: 'error', message: `Compact failed: ${String(e)}`, duration: 5000 });
    }
  }

  function formatSize(bytes: number): string {
    if (bytes >= 1_073_741_824) return (bytes / 1_073_741_824).toFixed(1) + ' GB';
    if (bytes >= 1_048_576) return (bytes / 1_048_576).toFixed(1) + ' MB';
    if (bytes >= 1_024) return (bytes / 1_024).toFixed(0) + ' KB';
    return bytes + ' B';
  }

  async function refreshIndexAndCollections() {
    await refreshIndexStatus();
    // Get armed writes on the wire before the fetch, so loadCollections
    // has nothing local left to preserve.
    await armCommitter.flush();
    await loadCollections();
  }

  function buildSyncResultMessage(result: SyncResult): { message: string; isError: boolean } {
    const parts: string[] = [];
    if (result.added > 0) parts.push(`${result.added} added`);
    if (result.removed > 0) parts.push(`${result.removed} removed`);
    if (result.auto_removed > 0) parts.push(`${result.auto_removed} removed (deleted from disk)`);
    if (result.renamed > 0) parts.push(`${result.renamed} renamed`);
    if (result.updated > 0) parts.push(`${result.updated} updated`);
    if (result.errors.length > 0) parts.push(`${result.errors.length} error(s)`);
    const chunkStr = result.chunks_total > 0
      ? ` ${result.chunks_total.toLocaleString()} chunks.`
      : '';
    const message = parts.length > 0
      ? `Synced: ${parts.join(', ')}.${chunkStr}`
      : 'Nothing to sync.';
    return { message, isError: result.errors.length > 0 };
  }

  // Sync index: add new, remove deselected, re-index modified
  async function handleSync() {
    if (isSyncing) return;
    isSyncing = true;
    pendingNotification.dismiss();
    try {
      const result = await runSyncJob<SyncResult>({
        command: 'sync_index',
        args: { paths: Array.from(selectedPaths) },
        startMessage: 'Starting sync...',
        errorPrefix: 'Sync failed',
        streamsProgress: true,
        buildResultMessage: buildSyncResultMessage,
        onComplete: async (r) => {
          // Reconcile selectedPaths with renames / auto-removals / stale paths
          for (const { old_path, new_path } of r.renames ?? []) {
            selectedPaths.delete(old_path);
            selectedPaths.add(new_path);
          }
          for (const path of r.auto_removed_paths ?? []) selectedPaths.delete(path);
          for (const path of r.stale_paths ?? []) selectedPaths.delete(path);
          if ((r.renames?.length || 0) + (r.auto_removed_paths?.length || 0) + (r.stale_paths?.length || 0) > 0) {
            selectedPaths = selectedPaths;
          }

          // Persist synced selection so uncommitted changes don't survive a restart
          syncedPaths = new Set(selectedPaths);
          const store = await load('settings.json');
          await store.set('syncedPaths', Array.from(selectedPaths));
          await store.save();
        },
      }, refreshIndexAndCollections);

      if (result) {
        lastSyncTime = new Date();
        refreshTotalFilesFound();
        // Refresh file tree if renames, auto-removals, or stale cleanups occurred
        if (((result.renames?.length || 0) + (result.auto_removed_paths?.length || 0) + (result.stale_paths?.length || 0) > 0) && selectedFolder) {
          await loadFiles(selectedFolder);
        }
      }
    } finally {
      isSyncing = false;
      refreshIndexStatus();
    }
  }

  function handleManualSync() {
    if (!sidecarConnected || isSyncing) return;
    if (selectedFolder) loadFiles(selectedFolder);
    if (selectedPaths.size > 0) refreshIndexStatus({ userTriggered: true });
  }

  async function handleReindexAll() {
    if (isSyncing) return;
    isSyncing = true;
    pendingNotification.dismiss();
    try {
      const result = await runSyncJob<SyncResult>({
        command: 'reindex_all',
        startMessage: 'Starting re-index...',
        errorPrefix: 'Re-index failed',
        streamsProgress: true,
        buildResultMessage: (r) => {
          const parts: string[] = [];
          if (r.updated > 0) parts.push(`${r.updated} reprocessed`);
          if (r.errors.length > 0) parts.push(`${r.errors.length} error(s)`);
          const chunkStr = r.chunks_total > 0
            ? ` ${r.chunks_total.toLocaleString()} chunks.`
            : '';
          const message = parts.length > 0
            ? `Re-indexed: ${parts.join(', ')}.${chunkStr}`
            : 'Nothing to re-index.';
          return { message, isError: r.errors.length > 0 };
        },
      }, refreshIndexAndCollections);
      if (result) lastSyncTime = new Date();
    } finally {
      isSyncing = false;
      refreshIndexStatus();
    }
  }

  async function handleDeleteIndex() {
    if (isSyncing) return;
    isSyncing = true;
    pendingNotification.dismiss();
    try {
      await runSyncJob<{ removed_files: number; removed_chunks: number }>({
        command: 'delete_index',
        startMessage: 'Deleting index...',
        errorPrefix: 'Delete failed',
        streamsProgress: false,
        buildResultMessage: (r) => {
          const fileWord = r.removed_files === 1 ? 'file' : 'files';
          const chunkWord = r.removed_chunks === 1 ? 'chunk' : 'chunks';
          return {
            message: `Index cleared: ${r.removed_files} ${fileWord}, ${r.removed_chunks.toLocaleString()} ${chunkWord} removed.`,
            isError: false,
          };
        },
      }, refreshIndexAndCollections);
    } finally {
      isSyncing = false;
      refreshIndexStatus();
    }
  }

</script>

<!-- keyup/blur are the release half of the hold latch (holdLatch.ts). They
     live here, at window level, because the press can come from any pane
     and focus may have moved by the time the key comes back up. -->
<svelte:window
  on:keydown={handleGlobalKeydown}
  on:keyup={handleGlobalKeyup}
  on:blur={() => holdLatch.cancel()}
  on:contextmenu|preventDefault
/>

<LaunchSplash visible={showSplash} onDismiss={dismissSplash} />

<main class="app-layout" class:motion-ready={motionReady}>
  <Header
    bind:this={headerComponent}
    bind:searchQuery
    disabled={!selectedFolder}
    panelOpen={collectionsPanelOpen}
    panelToggleVisible={!!selectedFolder}
    {filterPanelOpen}
    onToggleFilterPanel={toggleFilterPanel}
    onSubmit={handleSearchSubmit}
    onDebouncedChange={handleSearchDebounced}
    onClear={handleSearchClear}
    onFocus={handleSearchFocus}
    onTogglePanel={togglePanel}
    onCollapseAll={collapseAll}
    viewToggleVisible={!!selectedFolder}
    {searchViewOpen}
    {viewMode}
    onSetViewMode={setViewMode}
  />

  {#if selectedFolder}
    <div class="workspace">
      {#if collectionsPanelOpen || filterPanelOpen}
        <!-- Left dock: collections on top, filters below. Each panel
             scrolls its own rows; the dock owns the width and the
             dividing rules.

             Both panes stay mounted while the search view is open, so
             `active` is ANDed with !searchViewOpen: search owns the arrows
             there, and without this a dock pane left active from browse mode
             would step its caret alongside the result selection. -->
        <div class="left-dock">
          {#if collectionsPanelOpen}
            <CollectionsPanel
              bind:this={collectionsPanelComponent}
              {collections}
              armedName={armedCollection}
              onArm={armCollection}
              onDropPaths={dropPathsOnCollection}
              onDropNewCollection={dropPathsOnNewCollection}
              onRemoveFile={removeFileFromCollection}
              creating={newCollectionSeed}
              onCommitCreate={commitNewCollection}
              onCancelCreate={cancelNewCollection}
              playingNames={playingCollections}
              mutedNames={mutedCollectionNames}
              gameSystemMap={effectiveGameSystemMap}
              sortKey={collectionsSortKey}
              customOrder={collectionsCustomOrder}
              onDelete={requestDeleteCollection}
              onToggleArchived={toggleArchived}
              onCreate={inlineCreateCollection}
              onRename={renameCollection}
              onSetColor={setCollectionColor}
              onTogglePlay={togglePlayCollection}
              onToggleMute={toggleCollectionMute}
              onSetSortKey={setCollectionsSortKey}
              onReorder={reorderCollections}
              focusedName={focusedCollectionName}
              lastFocusedName={lastFocusedCollectionName}
              active={activePane === 'collections' && !searchViewOpen}
              onActivate={() => pointAtEmpty('collections')}
              onFocusCollection={setFocusedCollectionName}
            />
          {/if}
          {#if filterPanelOpen}
            <FilterPanel
              bind:this={filterPanelComponent}
              excludedSystems={filterExcludedSystems}
              {soloedSystems}
              systems={gameSystemStats}
              untaggedCount={untaggedFileCount}
              showSystemFilter={systemsFilterRelevant}
              onToggleSystem={toggleSystemFilter}
              onToggleSolo={toggleSystemSolo}
              {showHidden}
              {hiddenCount}
              onToggleShowHidden={toggleShowHidden}
              onClearHidden={clearHidden}
              {hideOutOfScope}
              onToggleHideOutOfScope={toggleHideOutOfScope}
              {hideUnindexed}
              onToggleHideUnindexed={toggleHideUnindexed}
              showCollectionFilter={collectionFilterAvailable && curationFilterRelevant}
              {collectedCount}
              {uncollectedCount}
              curationSolos={soloCuration}
              curationMutes={mutedCuration}
              onToggleCurationSolo={toggleCurationSolo}
              onToggleCurationMute={toggleCurationMute}
              onClearAll={clearAllFilters}
              focusedRow={focusedFilterRow}
              lastFocusedRow={lastFocusedFilterRow}
              active={activePane === 'filters' && !searchViewOpen}
              onActivate={() => pointAtEmpty('filters')}
              onFocusRow={setFocusedFilterRow}
            />
          {/if}
        </div>
      {/if}

      <!-- svelte-ignore a11y-no-static-element-interactions -->
      <div class="file-tree-area" class:search-mode={searchViewOpen} on:mousedown={handleFileTreeAreaMousedown}>
        <!-- The scope bar is the readout in every mode: chips for each
             narrowing, plus the hits meter while a search is active. The
             console itself is the docked FilterPanel. -->
        <SearchScopeBar
          {collectionPlays}
          {collectionSolos}
          {collectionMutes}
          {collectionTrackMutes}
          excludedSystems={filterExcludedSystems}
          {soloedSystems}
          curationSolos={soloCuration}
          curationMutes={mutedCuration}
          {showHidden}
          {hideOutOfScope}
          {hideUnindexed}
          resultCount={searchResults.length}
          indexedFileCount={searchableFileCount}
          isLoading={isSearching}
          searchActive={searchViewOpen && searchActive}
          onClearCollectionPlay={togglePlayCollection}
          onClearCollectionSolo={handleClearCollectionSolo}
          onClearCollectionMute={handleClearCollectionMute}
          onClearCollectionTrackMute={toggleCollectionMute}
          onToggleSystemFilter={toggleSystemFilter}
          onToggleSystemSolo={toggleSystemSolo}
          onToggleCurationSolo={toggleCurationSolo}
          onToggleCurationMute={toggleCurationMute}
          onToggleShowHidden={toggleShowHidden}
          onToggleHideOutOfScope={toggleHideOutOfScope}
          onToggleHideUnindexed={toggleHideUnindexed}
        />
        {#if searchViewOpen}
          <div class="search-split">
            <div class="search-list-pane">
              <SearchResults
                bind:this={searchResultsComponent}
                results={searchResults}
                isLoading={isSearching}
                stale={isSearching && committedQuery !== resultsQuery}
                query={committedQuery}
                error={searchError}
                {ollamaRunning}
                indexedFileCount={searchableFileCount}
                libraryEmpty={indexedPaths.size === 0}
                selectedIndex={selectedResultIndex}
                canLoadMore={!isSearching && !reachedEnd && pageSize < PAGE_SIZE_MAX}
                {hiddenPaths}
                {collectionColorByPath}
                onSelect={(i) => { selectedResultIndex = i; }}
                onLoadMore={loadMoreResults}
                onOpenResult={handleOpenResult}
              />
            </div>
            <div class="search-inspector-pane">
              <SearchInspector
                result={selectedResult}
                {hiddenPaths}
                {knownSystems}
                gameSystemMap={effectiveGameSystemMap}
                onOpenResult={handleOpenResult}
                onSetGameSystems={handleSetGameSystems}
              />
            </div>
          </div>
        {:else if viewMode === 'systems'}
          <SystemsView
            bind:this={systemsViewComponent}
            entries={indexedEntries}
            {displayPaths}
            {scopeBrightPaths}
            {hideOutOfScope}
            excludedSystems={filterExcludedSystems}
            {soloedSystems}
            onToggleSystemFilter={toggleSystemFilter}
            onToggleSystemSolo={toggleSystemSolo}
            {hiddenPaths}
            {showHidden}
            libraryRoot={selectedFolder}
            {focusedFilePath}
            lastFocusedPath={lastFocusedFilePath}
            active={activePane === 'files'}
            onFocusFile={setFocusedFilePath}
            onContextMenu={handleContextMenu}
            {renamingFilePath}
            onRenameSubmit={handleRenameSubmit}
            onRenameCancel={handleRenameCancel}
            contextMenuOpen={!!contextMenu}
            {ribbonIndex}
            onBeginDrag={beginPathDrag}
            curating={armState !== null}
            collectionPaths={armState?.paths ?? EMPTY_PATHS}
            onCollectionAdd={curationAdd}
            onCollectionRemove={curationRemove}
          />
        {:else}
          {#if hideOutOfScope && scopeBrightPaths !== null && scopeBrightPaths.size === 0}
            <div class="scope-empty">Everything is out of scope.</div>
          {:else if hideUnindexed && indexedPaths.size === 0 && selectedPaths.size === 0}
            <div class="scope-empty">Nothing in the library yet.</div>
          {/if}
          {#each files as file (file.path)}
            <FileTree
              item={file}
              level={0}
              {selectedPaths}
              {foldersWithSelections}
              gameSystemMap={effectiveGameSystemMap}
              {knownSystems}
              {indexedPaths}
              onToggle={toogleSelection}
              onSetGameSystems={handleSetGameSystems}
              {expandedPaths}
              onToggleExpand={handleToggleExpand}
              {focusedFilePath}
              onFocusFile={setFocusedFilePath}
              onContextMenu={handleContextMenu}
              {renamingFilePath}
              onRenameSubmit={handleRenameSubmit}
              onRenameCancel={handleRenameCancel}
              {displayPaths}
              {hiddenPaths}
              {showHidden}
              {soloedScopePaths}
              {mutedScopePaths}
              {scopeBrightPaths}
              {indexedFolderPaths}
              {hideOutOfScope}
              {hideUnindexed}
              {ribbonIndex}
              arm={armState}
              {onToggleMembership}
              onBeginDrag={beginPathDrag}
              onToggleScopeSolo={toggleScopeSolo}
              onToggleScopeMute={toggleScopeMute}
            />
          {/each}
        {/if}
      </div>
    </div>
  {:else}
    <GettingStartedPage
      {ollamaRunning}
      {ollamaModelReady}
      onSelectFolder={handleSelectFolder}
      onOpenHelp={() => {
        settingsInitialTab = 'help';
        settingsInitialHelpSubTab = 'guides';
        showSettings = true;
      }}
    />
  {/if}

  {#if error}
    <div class="error-banner">Error: {error}</div>
  {/if}

  {#if contextMenu}
    <ContextMenu
      x={contextMenu.x}
      y={contextMenu.y}
      item={contextMenu.item}
      isIndexed={contextMenu.isIndexed}
      {collections}
      canAddToCollection={contextMenu.item.is_dir
        ? indexedPathsUnder(contextMenu.item.path, indexedPaths).length > 0
        : indexedPaths.has(contextMenu.item.path)}
      canScope={scopeSolos.has(contextMenu.item.path) || scopeMutes.has(contextMenu.item.path) ||
        rowHasIndexedMaterial(contextMenu.item.path, contextMenu.item.is_dir, indexedPaths, indexedFolderPaths)}
      isSoloed={scopeSolos.has(contextMenu.item.path)}
      isMuted={scopeMutes.has(contextMenu.item.path)}
      containingCollections={collectionsContaining(contextMenu.item.path, contextMenu.item.is_dir, collections, indexedPaths)}
      knownSystems={knownSystems}
      currentTags={effectiveGameSystemMap.get(contextMenu.item.path) ?? []}
      onSetGameSystems={(tags) => handleSetGameSystems(contextMenu!.item.path, contextMenu!.item.name, tags)}
      excludeFromAdd={collectionsFullyContaining(contextMenu.item.path, contextMenu.item.is_dir, collections, indexedPaths)}
      initialSubmenu={contextMenu.initialSubmenu}
      onOpen={handleContextOpen}
      onReveal={handleContextReveal}
      onRename={handleContextRename}
      onDelete={handleContextDelete}
      onReindex={handleContextReindex}
      onShowStats={handleContextShowStats}
      onToggleSolo={handleContextToggleSolo}
      onToggleMute={handleContextToggleMute}
      onAddToCollection={handleContextAddToCollection}
      onAddToNewCollection={handleContextAddToNewCollection}
      onRemoveFromCollection={handleContextRemoveFromCollection}
      directlyHidden={contextMenu.hideState.directlyHidden}
      inheritedHidden={contextMenu.hideState.inheritedHidden}
      onToggleHidden={handleContextToggleHidden}
      onClose={() => { contextMenu = null; }}
    />
  {/if}

  {#if statsModalPath}
    <DocumentStatsModal
      path={statsModalPath}
      onClose={() => { statsModalPath = null; }}
    />
  {/if}

  <!-- One prompt for the whole app; confirmStore decides when it shows. -->
  <ConfirmDialog />

  <StatusBar
    {selectedFolder}
    {sidecarConnected}
    {mcpConnected}
    {mcpActive}
    selectedCount={selectedPaths.size}
    indexedCount={(indexStatus?.summary?.up_to_date ?? 0) + (indexStatus?.summary?.update ?? 0) + (indexStatus?.summary?.remove ?? 0)}
    {gameSystemCount}
    {topGameSystem}
    {totalChunks}
    {storageBytes}
    {reclaimableBytes}
    {isSyncing}
    {scopeBypassed}
    {lastSyncTime}
    onSync={handleManualSync}
    onOpenFolder={() => { if (selectedFolder) revealItemInDir(selectedFolder); }}
    onOpenSettings={() => { settingsInitialTab = 'general'; showSettings = true; }}
    onShowHelp={() => { showHelpOverlay = true; }}
  />
</main>

<SettingsModal
  visible={showSettings}
  onClose={() => { showSettings = false; }}
  initialTab={settingsInitialTab}
  initialHelpSubTab={settingsInitialHelpSubTab}
  {knownSystems}
  onSystemsChanged={refreshKnownSystems}
  {selectedFolder}
  indexedFileCount={(indexStatus?.summary?.up_to_date ?? 0) + (indexStatus?.summary?.update ?? 0) + (indexStatus?.summary?.remove ?? 0)}
  {totalFilesFound}
  {totalChunks}
  {storageBytes}
  {reclaimableBytes}
  {gameSystemCount}
  {isSyncing}
  {syncPreferences}
  {dataDir}
  {lastSyncTime}
  {ollamaRunning}
  {ollamaModelReady}
  filesIndexed={(indexStatus?.summary?.up_to_date ?? 0) > 0}
  collectionsCreated={Object.keys(collections).length > 0}
  {mcpConnected}
  onSelectFolder={handleSelectFolder}
  onDeselectFolder={handleDeselectFolder}
  onCompact={handleCompact}
  onReindexAll={handleReindexAll}
  onDeleteIndex={handleDeleteIndex}
  onSyncPreferencesChange={handleSyncPreferencesChange}
  onOpenDataDir={handleOpenDataDir}
  onSync={handleManualSync}
  onCopyMcpConfig={handleCopyMcpConfig}
/>

<KeyboardHelpOverlay
  visible={showHelpOverlay}
  onClose={() => { showHelpOverlay = false; }}
/>

<style>
  .app-layout {
    display: flex;
    flex-direction: column;
    height: 100vh;
    overflow: hidden;
    background: var(--bg-app);
  }

  .workspace {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: row;
    overflow: hidden;
  }

  /* Left dock — the two panels stack vertically and share the column.
     Collections takes the free space; the filter panel keeps to its
     content height (capped so a long systems list can't crowd the
     collections out) and scrolls internally past the cap. */
  .left-dock {
    width: 280px;
    flex-shrink: 0;
    min-height: 0;
    display: flex;
    flex-direction: column;
    background: var(--bg-app);
    border-right: 1px solid var(--border-subtle);
  }
  .left-dock > :global(.panel) {
    flex: 1 1 auto;
    min-height: 0;
  }
  .left-dock > :global(.filter-panel) {
    flex: 0 1 auto;
    min-height: 0;
    max-height: 60%;
  }
  /* When the filter panel is alone in the dock it may grow. */
  .left-dock > :global(.filter-panel:only-child) {
    flex: 1 1 auto;
    max-height: none;
  }
  .left-dock > :global(* + *) {
    border-top: 1px solid var(--border-subtle);
  }

  .file-tree-area {
    flex: 1;
    min-width: 0;
    overflow-y: auto;
    overflow-anchor: none;
    /* No top padding: the sticky scope bar must sit flush under the
       header, or scrolled rows peek through the slit above it. */
    padding: 0 0.75rem 0.25rem;
  }

  .scope-empty {
    padding: 1rem 0.8rem;
    font-style: italic;
    color: var(--text-tertiary);
  }

  /* Search mode replaces the scrollable single column with a fixed scope
     bar on top and a split (list / inspector) below. The .file-tree-area
     itself stops scrolling — child panes manage their own overflow. */
  .file-tree-area.search-mode {
    display: flex;
    flex-direction: column;
    overflow: hidden;
    padding: 0;
  }

  .search-split {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: row;
    overflow: hidden;
  }

  .search-list-pane {
    flex: 0 0 38%;
    min-width: 280px;
    max-width: 520px;
    border-right: 1px solid var(--border-subtle);
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }

  .search-inspector-pane {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }


  .error-banner {
    padding: 0.4rem 1rem;
    background: rgba(239, 68, 68, 0.1);
    color: var(--text-danger);
    border-top: 1px solid rgba(239, 68, 68, 0.3);
    font-size: 0.85rem;
    flex-shrink: 0;
  }
</style>
