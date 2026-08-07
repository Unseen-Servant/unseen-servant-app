<script lang="ts">
  import { onMount, onDestroy, tick } from 'svelte';
  import { invoke } from '@tauri-apps/api/core';
  import { listen } from '@tauri-apps/api/event';
  import { writeText } from '@tauri-apps/plugin-clipboard-manager';
  import { openPath, openUrl, revealItemInDir } from '@tauri-apps/plugin-opener';
  import { pdfFileUrl } from '../lib/pdfUrl';
  import { confirm } from '@tauri-apps/plugin-dialog';
  import { load } from '@tauri-apps/plugin-store';
  import type { FileItem, FileStatusEntry, IndexStatusResult, SyncResult, KnownGameSystem, KnownGameSystemsResult, StatsResult, CollectionInfo, CollectionsResult, CollectionMutationResult, ActiveContextResult, SearchResultItem, SearchResponse, SyncPreferences, PromptCounts, SyncAction } from '../lib/types';
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
  import CollectionsPanel from '../lib/CollectionsPanel.svelte';
  import CollectionEditDialog from '../lib/CollectionEditDialog.svelte';
  import SystemsView from '../lib/SystemsView.svelte';
  import { jobNotification, pendingNotification } from '../lib/notificationStore';
  import { computeAncestorPaths, areAllDescendantsSelected, isPathOrAncestorIn } from '../lib/selectionUtils';
  import { computeVisibleRows, indexOfPath, type VisibleRow } from '../lib/treeNav';
  import { searchGameSystemsFilter, searchSourcePathsFilter, UNTAGGED_KEY, type ScopeRef } from '../lib/searchScope';
  import { runSyncJob } from '../lib/syncJob';
  import { chord } from '../lib/keybindings';
  import {
    parseString,
    parseBoolean,
    parseStringArray,
    parseEnum,
  } from '../lib/storeParsers';

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

  // File focus & context menu
  let focusedFilePath: string | null = null;
  // Mirror state for collection-row keyboard focus. focusedFilePath and
  // focusedCollectionName are mutually exclusive — only one region claims
  // the keyboard at a time, which is how arrow keys know where to route.
  let focusedCollectionName: string | null = null;

  function setFocusedFilePath(path: string | null) {
    focusedFilePath = path;
    if (path) focusedCollectionName = null;
  }
  function setFocusedCollectionName(name: string | null) {
    focusedCollectionName = name;
    if (name) focusedFilePath = null;
  }
  // Remember the last non-null focus on each side so Cmd+Alt+←/→ can
  // restore the user to where they were instead of always landing on
  // row 0 of the target region.
  let lastFocusedFilePath: string | null = null;
  let lastFocusedCollectionName: string | null = null;
  $: if (focusedFilePath !== null) lastFocusedFilePath = focusedFilePath;
  $: if (focusedCollectionName !== null) lastFocusedCollectionName = focusedCollectionName;
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
  let editingCollectionName: string | null = null;
  // Proposed name of an in-progress new collection that hasn't been saved
  // yet. Mutually exclusive with editingCollectionName: either we're
  // editing an existing row or shaping a draft, never both.
  let draftName: string | null = null;
  let collectionEditPaths = new Set<string>();
  let collectionEditName = '';
  let collectionEditDescription = '';
  let activeContextName: string | null = null;
  let collectionsPanelOpen = true;
  let editingMetadataFor: string | null = null;

  // Library narrowing — one model, two axes, DAW semantics on each:
  // solos union within an axis, axes intersect, solo overrides mute.
  //   - systems axis:    filterExcludedSystems (muted) + soloedSystems.
  //   - collection axis: mutedCollections + soloCollections, keyed by
  //     path (tree folders and files); the active collection joins the
  //     solo side via its own backend state (activeContextName).
  // All four are session-scoped: they reset on app launch (no Tauri
  // store persistence), so each session starts with a clean library.
  let filterExcludedSystems = new Set<string>();
  let soloedSystems = new Set<string>();
  let soloCollections = new Map<string, ScopeRef>();
  let mutedCollections = new Map<string, ScopeRef>();

  // Display-only hidden flag. Stores explicitly-hidden paths (files or
  // folder roots); descendants of a hidden folder are hidden via prefix
  // match, not stored individually. Indexing is unaffected — hidden files
  // still get indexed, searched, and counted in SystemsView.
  let hiddenPaths = new Set<string>();
  let showHidden = false;

  // Library filter: when on, narrow the tree to files not in any
  // collection — a curation gap-finder. Inert when the view is already
  // scoped to a collection (active context or edit mode), since
  // "uncategorized within a collection" is empty by definition.
  let showOnlyUncollected = false;

  // Focus mode for the active collection. Default off: activating a
  // collection just highlights its files in the tree (the library map
  // stays whole). When on, the tree narrows to that collection — the
  // pre-highlight focused-view behavior, kept for live-play workflows.
  let focusActiveCollection = false;

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
  let searchResults: SearchResultItem[] = [];
  // Tracks which query produced the rows currently in `searchResults`.
  // Used to distinguish a fresh search-in-flight (committedQuery !==
  // resultsQuery, displayed rows are stale) from a "load more"
  // pagination (same query, rows still authoritative).
  let resultsQuery = '';
  let isSearching = false;
  let searchError: string | null = null;
  let searchSeq = 0;
  let selectedResultIndex = 0;
  let headerComponent: Header | undefined;
  let searchResultsComponent: SearchResults | undefined;
  let systemsViewComponent: SystemsView | undefined;
  let collectionsPanelComponent: CollectionsPanel | undefined;
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
  // Clamp selection when results shrink (e.g. new query returns fewer hits).
  $: if (selectedResultIndex >= searchResults.length) {
    selectedResultIndex = searchResults.length > 0 ? searchResults.length - 1 : 0;
  }
  $: selectedResult = searchResults.length > 0 ? searchResults[selectedResultIndex] ?? null : null;
  // The active collection surfaces as a solo chip on the collection
  // axis (its bookmark takes the collection pigment); folder/file solos
  // and mutes ride along with the tertiary fallback. Clearing the
  // active-collection chip must clear the backend context, so it gets a
  // sentinel key that can't collide with an absolute path.
  const ACTIVE_CONTEXT_CHIP_KEY = 'active-context';
  $: collectionSolos = (() => {
    if (isCollectionEditMode) return [];
    const chips: { key: string; label: string; color: string | null }[] = [];
    if (activeContextName) {
      chips.push({
        key: ACTIVE_CONTEXT_CHIP_KEY,
        label: activeContextName,
        color: collections[activeContextName]?.color ?? null,
      });
    }
    for (const [path, ref] of soloCollections) {
      chips.push({ key: path, label: ref.label, color: null });
    }
    return chips;
  })();
  $: collectionMutes = isCollectionEditMode
    ? []
    : [...mutedCollections].map(([path, ref]) => ({ key: path, label: ref.label, color: null as string | null }));
  function handleClearCollectionSolo(key: string) {
    if (key === ACTIVE_CONTEXT_CHIP_KEY) {
      clearActiveContext();
      return;
    }
    soloCollections.delete(key);
    soloCollections = soloCollections;
    if (committedQuery) runSearch(committedQuery);
  }
  function handleClearCollectionMute(key: string) {
    mutedCollections.delete(key);
    mutedCollections = mutedCollections;
    if (committedQuery) runSearch(committedQuery);
  }
  $: indexedPathsSet = new Set<string>(
    (indexStatus?.up_to_date ?? []).map((e) => e.path)
      .concat((indexStatus?.to_update ?? []).map((e) => e.path))
  );

  // File path → collection pigment for the search-result index cells.
  // Color is reserved for collections; a file in several colored
  // collections takes the alphabetically-first one for determinism.
  $: collectionColorByPath = (() => {
    const m = new Map<string, string>();
    const sorted = Object.values(collections).sort((a, b) => a.name.localeCompare(b.name));
    for (const col of sorted) {
      if (!col.color) continue;
      for (const p of col.file_paths) {
        if (!m.has(p)) m.set(p, col.color);
      }
    }
    return m;
  })();

  // Collection-axis narrowing resolved to a backend include-list (null =
  // no narrowing on this axis). When the active collection is the only
  // narrowing, stay null: the backend auto-scopes search to the active
  // context on its own, and solo-overrides-mute makes any mutes moot the
  // moment a solo (which the active collection is) engages.
  //
  // Plain function, not just a `$:` value: the S/M toggles call runSearch
  // synchronously after mutating their Maps, and derived values don't
  // flush until the end of the microtask — runSearch must compute the
  // include-list fresh. The reactive mirror below feeds display
  // consumers (searchableFileCount) with its dependencies spelled out.
  function computeCollectionAxisInclude(
    solos: Map<string, ScopeRef>,
    mutes: Map<string, ScopeRef>,
    activeName: string | null,
    cols: Record<string, CollectionInfo>,
    indexed: Set<string>
  ): string[] | null {
    const refFiles = (path: string, kind: 'folder' | 'file') =>
      kind === 'folder'
        ? indexedPdfsUnderPath(path)
        : indexed.has(path) ? [path] : [];
    const soloSets = [...solos].map(([p, r]) => refFiles(p, r.kind));
    if (activeName && cols[activeName]) {
      if (soloSets.length === 0) return null;
      soloSets.push(cols[activeName].file_paths.filter((p) => indexed.has(p)));
    }
    const muteSets = [...mutes].map(([p, r]) => refFiles(p, r.kind));
    return searchSourcePathsFilter(soloSets, muteSets, indexed);
  }
  $: collectionAxisInclude = computeCollectionAxisInclude(
    soloCollections, mutedCollections, activeContextName, collections, indexedPaths
  );

  // The "of N files" denominator in the SearchScopeBar — mirrors the same
  // narrowing primitives runSearch passes to the backend (collection
  // axis, then system exclusion). When no filters are set, this collapses
  // to the full indexed-paths count.
  $: searchableFileCount = (() => {
    let universe: string[];
    if (collectionAxisInclude !== null) {
      universe = collectionAxisInclude;
    } else if (activeContextName && collections[activeContextName]) {
      universe = collections[activeContextName].file_paths.filter((p) => indexedPathsSet.has(p));
    } else {
      universe = Array.from(indexedPathsSet);
    }
    if (filterExcludedSystems.size === 0 && soloedSystems.size === 0) return universe.length;
    // A file passes when at least one of its tags survives the active
    // filter — matches the include-list semantics of `gameSystems` in
    // runSearch. Solo overrides mute when active; under solos, untagged
    // files (no tags) never pass. Under mute, untagged files pass unless
    // the Untagged bucket itself is muted (issue #307).
    let count = 0;
    for (const path of universe) {
      const tags = effectiveGameSystemMap.get(path) ?? [];
      if (soloedSystems.size > 0) {
        if (tags.some((t) => soloedSystems.has(t))) count++;
      } else if (tags.length === 0) {
        if (!filterExcludedSystems.has(UNTAGGED_KEY)) count++;
      } else if (tags.some((t) => !filterExcludedSystems.has(t))) {
        count++;
      }
    }
    return count;
  })();

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

    // Collection axis (folder/file solos and mutes; the active
    // collection auto-scopes backend-side when this stays null).
    // Computed fresh — see computeCollectionAxisInclude for why the
    // derived value can't be read here.
    const sourcePaths = computeCollectionAxisInclude(
      soloCollections, mutedCollections, activeContextName, collections, indexedPaths
    );
    if (sourcePaths !== null && sourcePaths.length === 0) {
      searchError = soloCollections.size > 0 || activeContextName
        ? 'Nothing indexed under the soloed items.'
        : 'Everything is muted.';
      searchResults = [];
      isSearching = false;
      return;
    }

    // Library filter resolution (DAW semantics): solo overrides mute;
    // mute keeps every non-muted system plus the untagged bucket unless
    // it was muted itself (issue #307 — untagged chunks store
    // game_system "unknown", so the include-list must name it).
    const gameSystems = searchGameSystemsFilter(
      soloedSystems,
      filterExcludedSystems,
      gameSystemStats.map((s) => s.name)
    );
    if (gameSystems !== null && gameSystems.length === 0) {
      searchError = 'All game systems are filtered out.';
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
      const savedShowOnlyUncollected = parseBoolean(await store.get('showOnlyUncollected'));
      if (savedShowOnlyUncollected !== undefined) {
        showOnlyUncollected = savedShowOnlyUncollected;
      }
      const savedFocusActiveCollection = parseBoolean(await store.get('focusActiveCollection'));
      if (savedFocusActiveCollection !== undefined) {
        focusActiveCollection = savedFocusActiveCollection;
      }
      const savedViewMode = parseEnum(
        await store.get('viewMode'),
        ['tree', 'systems'] as const,
      );
      if (savedViewMode) {
        viewMode = savedViewMode;
      }
      await loadCollections();
    } catch (e) {
      // No saved state on first run — that's fine
      console.log('No saved state:', e);
    }

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
    if (committedQuery) runSearch(committedQuery);
  }

  // Collection-axis S/M for tree folders and files. Union semantics:
  // soloing does not release other solos or the active collection —
  // every narrowing stacks as its own chip in the scope bar.
  function toggleScopeSolo(item: FileItem) {
    if (soloCollections.has(item.path)) {
      soloCollections.delete(item.path);
    } else {
      soloCollections.set(item.path, { kind: item.is_dir ? 'folder' : 'file', label: item.name });
    }
    soloCollections = soloCollections;
    if (committedQuery) runSearch(committedQuery);
  }

  function toggleScopeMute(item: FileItem) {
    if (mutedCollections.has(item.path)) {
      mutedCollections.delete(item.path);
    } else {
      mutedCollections.set(item.path, { kind: item.is_dir ? 'folder' : 'file', label: item.name });
    }
    mutedCollections = mutedCollections;
    if (committedQuery) runSearch(committedQuery);
  }

  // Section-level "Reset" link: clears both mute and solo at once. The
  // user reads "Game systems" as one filter — splitting the two clears
  // would be more clicks for a single conceptual action.
  function clearSystemFilter() {
    filterExcludedSystems = new Set();
    soloedSystems = new Set();
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
      await store.save();
    } catch (e) {
      console.log('Could not persist hidden state:', e);
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

  async function persistShowOnlyUncollected() {
    try {
      const store = await load('settings.json');
      await store.set('showOnlyUncollected', showOnlyUncollected);
      await store.save();
    } catch (e) {
      console.log('Could not persist showOnlyUncollected:', e);
    }
  }

  function toggleShowOnlyUncollected() {
    showOnlyUncollected = !showOnlyUncollected;
    persistShowOnlyUncollected();
  }

  async function persistFocusActiveCollection() {
    try {
      const store = await load('settings.json');
      await store.set('focusActiveCollection', focusActiveCollection);
      await store.save();
    } catch (e) {
      console.log('Could not persist focusActiveCollection:', e);
    }
  }

  function toggleFocusActiveCollection() {
    focusActiveCollection = !focusActiveCollection;
    persistFocusActiveCollection();
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
    if (isCollectionEditMode) return;
    const action = decideSyncAction(status, syncPreferences, options.userTriggered ?? false);
    await applySyncAction(action);
  }

  function showSyncPrompt(counts: PromptCounts) {
    if (!indexStatus || isCollectionEditMode) return;

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
  $: isCollectionEditMode = editingCollectionName !== null || draftName !== null;
  // The highlight means "soloed": the active collection's files plus any
  // folder/file solos take the parchment wash + left rule rather than
  // filtering everything else out. Ancestors are included so the
  // highlight propagates up through collapsed folders — without that,
  // a scattered collection's files would be invisible until every
  // containing folder was manually expanded. Edit mode handles its own
  // membership UI (checkboxes) and shouldn't compete with highlights.
  $: highlightPaths = (() => {
    if (isCollectionEditMode) return new Set<string>();
    const files = new Set<string>();
    const col = activeContextName ? collections[activeContextName] : undefined;
    if (col) for (const p of col.file_paths) files.add(p);
    for (const [path, ref] of soloCollections) {
      files.add(path);
      if (ref.kind === 'folder') {
        const prefix = path + '/';
        for (const p of indexedPaths) if (p.startsWith(prefix)) files.add(p);
      }
    }
    if (files.size === 0) return files;
    return new Set<string>([...files, ...computeAncestorPaths(files)]);
  })();

  // Rows muted on the collection axis dim in the tree (45%, never
  // hidden). Descendants of a muted folder inherit via prefix match,
  // same as hiddenPaths.
  $: mutedScopePaths = new Set(mutedCollections.keys());
  $: soloedScopePaths = new Set(soloCollections.keys());

  // Per-collection count of files currently hidden in the tree. Surfaced
  // in the collections panel so users notice their curated set holds
  // tucked-away items even when the tree is compressed.
  $: hiddenCountByCollection = (() => {
    const out: Record<string, number> = {};
    if (hiddenPaths.size === 0) return out;
    for (const col of Object.values(collections)) {
      let n = 0;
      for (const p of col.file_paths) {
        if (isPathOrAncestorIn(p, hiddenPaths)) n++;
      }
      if (n > 0) out[col.name] = n;
    }
    return out;
  })();

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

  // Whether the Collections section in the filter menu has anything to
  // show. Three mutually-exclusive radio options live there:
  //   - Show all              — default, no narrowing
  //   - Show only collection  — focus mode, requires an active context
  //   - Show only loose       — uncategorized files, requires that any
  //                             collection exists (works alongside an
  //                             active collection — useful when
  //                             scouting candidates to add)
  // Edit mode forces its own UI, so the section is hidden there.
  $: collectionFilterAvailable =
    !isCollectionEditMode &&
    (activeContextName !== null || Object.keys(collections).length > 0);
  $: uncategorizedFilterAvailable =
    !isCollectionEditMode && Object.keys(collections).length > 0;
  $: focusFilterAvailable =
    collectionFilterAvailable && activeContextName !== null;

  // Filter for what the file tree shows. Composes scope + library filters:
  // 1. Edit mode and focus mode pick the base file pool. An active
  //    collection without focus mode just highlights — the tree shows
  //    the whole library so users can see those files in context.
  // 2. Uncategorized filter narrows to files not in any collection.
  // 3. Add ancestor folders so the tree structure stays intact.
  // Returns null = show everything, no narrowing.
  // System mute/solo never narrows a view: muted groups dim in place in
  // the systems view (a muted channel never leaves the mixer), and the
  // tree is a spatial model that content tags shouldn't reshape. The
  // filter applies to search only.
  $: displayPaths = (() => {
    // Metadata-based narrowing (collection focus, loose-only) is gated
    // to systems view. Tree view is a spatial model — folders and
    // ancestors should never disappear because of collection membership.
    // Highlight via activeContextName (which composes orthogonally) is
    // the right tree-view affordance.
    const inSystemsView = viewMode === 'systems';
    const focusActive = inSystemsView && focusActiveCollection && focusFilterAvailable;
    // Focus and loose are radio-mutex through the menu, but a stray
    // persisted state could in principle have both set. Treat focus as
    // canonical so the tree never collapses to empty (collection ∩ not-
    // in-any-collection = ∅).
    const uncollectedActive =
      inSystemsView && !focusActive && showOnlyUncollected && uncategorizedFilterAvailable;

    let baseFiles: Set<string> | null;
    if (isCollectionEditMode) {
      baseFiles = new Set(indexedPaths);
    } else if (focusActive && activeContextName) {
      const col = collections[activeContextName];
      baseFiles = col ? new Set(col.file_paths) : null;
    } else if (uncollectedActive) {
      baseFiles = new Set(uncollectedFilePaths);
    } else {
      return null;
    }

    if (!baseFiles) return null;

    let visible = baseFiles;
    if (uncollectedActive) {
      visible = new Set([...visible].filter((p) => !collectedPaths.has(p)));
    }

    if (visible.size === 0) return new Set<string>();
    return new Set<string>([...visible, ...computeAncestorPaths(visible)]);
  })();

  // Flat list of currently-visible tree rows for keyboard nav. Mirrors what
  // FileTree renders, so consecutive entries here are visually adjacent.
  $: visibleTreeRows = computeVisibleRows(files, expandedPaths, displayPaths, hiddenPaths, showHidden);

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
      await refreshIndexStatus();
    } catch (e) {
      console.error('Failed to set game systems:', e);
      pendingTagOverrides.delete(path);
      pendingTagOverrides = pendingTagOverrides;
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
    let next: number;
    if (current < 0) {
      next = delta > 0 ? 0 : visibleTreeRows.length - 1;
    } else {
      next = Math.min(visibleTreeRows.length - 1, Math.max(0, current + delta));
    }
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

  function activateFocusedTreeRow() {
    const idx = indexOfPath(visibleTreeRows, focusedFilePath);
    if (idx < 0) return;
    const row = visibleTreeRows[idx];
    if (row.item.is_dir) {
      handleToggleExpand(row.path);
    } else {
      openPath(row.path).catch((e) => console.error('Failed to open file:', e));
    }
  }

  // Click anywhere in the file-tree pane chrome (not on a specific row)
  // claims the file-side region with the first visible row, mirroring how
  // the collections panel claims itself on chrome clicks. Skip in search
  // mode (search owns its own selectedResultIndex). Systems mode delegates
  // to SystemsView.claimFirst() because .systems-view only spans the
  // height of its content, so clicks in the empty area below the last
  // group still land here.
  function handleFileTreeAreaMousedown(event: MouseEvent) {
    if (searchActive) return;
    if (focusedFilePath !== null) return;
    const target = event.target as HTMLElement | null;
    if (viewMode === 'systems') {
      if (target?.closest('[data-sv-row]')) return;
      systemsViewComponent?.claim();
      return;
    }
    if (target?.closest('[data-tree-row]')) return;
    if (visibleTreeRows.length > 0) setFocusedFilePath(visibleTreeRows[0].path);
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

    if (event.key === ' ') {
      event.preventDefault();
      toogleSelection(row.path, row.item.is_dir, row.item, false);
      return true;
    }

    if (event.key === 'Enter') {
      event.preventDefault();
      activateFocusedTreeRow();
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

    if (meta && !event.shiftKey && lk === 'o') {
      event.preventDefault();
      revealItemInDir(focused.path);
      return true;
    }

    if (event.key === 'ContextMenu' || (event.shiftKey && event.key === 'F10')) {
      event.preventDefault();
      openContextMenuAtFocusedRow();
      return true;
    }

    // Plain letters only — no modifiers. Hide is on '.' (not 'h') so
    // hjkl stays free for vim-style nav and '.' mirrors the Cmd+Shift+.
    // global chord. Period key on the main row OR on the numpad —
    // event.code is layout-independent (some layouts produce a different
    // event.key for the numpad period, e.g. ',' on German).
    if (bareLetter) {
      if (lk === 'r') { event.preventDefault(); renamingFilePath = focused.path; return true; }
      // S/M are the one narrowing model on both axes. In tree view they
      // solo/mute the focused row on the collection axis; in systems
      // view they fall through to SystemsView's own handler, which
      // works the systems axis. The context menu moves to Shift+F10 /
      // the Menu key (M used to open it).
      if (lk === 's' && viewMode !== 'systems') { event.preventDefault(); toggleScopeSolo(focused.item); return true; }
      if (lk === 'm' && viewMode !== 'systems') { event.preventDefault(); toggleScopeMute(focused.item); return true; }
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
  //   1. Open context menu        → close
  //   2. Inline rename in flight   → cancel
  //   3. Empty search input        → blur and hand focus to tree
  //   4. Focused tree row          → clear focus
  //   5. (modal Esc handled by Modal.svelte)
  //   6. (search results → input handled below)
  //   7. (search input text handled in Header.svelte)
  function dismissSplash() {
    if (!showSplash) return;
    showSplash = false;
    if (splashTimer) {
      clearTimeout(splashTimer);
      splashTimer = null;
    }
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
      // A competing popover (filter / sort / dropdown) handles its own Esc.
      // Don't reach the focus-clear branch below — that would wipe the
      // user's tree highlight as a side effect of closing a menu.
      if (document.querySelector('.filter-menu, .sort-menu, .dropdown')) return;
      // Empty search input: blur and place keyboard focus in the tree so
      // arrows immediately navigate. If a tree row was already focused,
      // we leave it where it is.
      if (inSearchInput && searchQuery === '' && !searchActive) {
        (target as HTMLInputElement).blur();
        if (!focusedFilePath && visibleTreeRows.length > 0) {
          focusTreeRow(visibleTreeRows[0].path);
        }
        event.preventDefault();
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

    // Cmd/Ctrl+J: toggle Tree ↔ Systems view (matches the visible button:
    // hidden during search, so the chord no-ops there too). 'J' was chosen
    // over '\' because backslash isn't a single key on Canadian CSA and
    // several other ISO layouts.
    if (meta && !event.shiftKey && lk === 'j' && selectedFolder && !searchActive) {
      event.preventDefault();
      setViewMode(viewMode === 'systems' ? 'tree' : 'systems');
      return;
    }

    // Cmd/Ctrl+Alt+←/→: jump keyboard focus between the collections panel
    // and the file pane (tree or systems). Restores the last-focused row
    // in the target region if it's still visible, else lands on the first
    // visible row. Skipped during search (the search input owns ←/→ for
    // text editing).
    if (meta && event.altKey && !event.shiftKey && selectedFolder && !searchActive
        && (event.key === 'ArrowLeft' || event.key === 'ArrowRight')) {
      event.preventDefault();
      if (event.key === 'ArrowLeft') focusCollectionsRegion();
      else focusFileRegion();
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

    // Cmd/Ctrl+Z: revert pending (unsynced) selection changes — same effect
    // as clicking the X on the "N to add, M to remove" banner. Skipped when
    // an input has focus so native text undo still works while typing.
    if (meta && !event.shiftKey && lk === 'z' && !inAnyInput) {
      if (pendingNotification.dismissByUser()) {
        event.preventDefault();
        return;
      }
    }

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

    // Cmd/Ctrl+Shift+F: open the filter menu.
    if (meta && event.shiftKey && lk === 'f' && selectedFolder) {
      event.preventDefault();
      headerComponent?.toggleFilter();
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
    if (meta && !event.shiftKey && event.key === 'Enter' && (draftName || editingCollectionName)) {
      event.preventDefault();
      saveCollection();
      return;
    }

    // `?` — show keyboard shortcuts overlay. Match on event.key (the
    // produced character) rather than Shift+/ so any layout that emits
    // `?` from a different physical key still triggers. Bare chord, gated
    // out of inputs so typing a literal `?` works as expected.
    if (event.key === '?' && !meta && !event.altKey && !inAnyInput) {
      event.preventDefault();
      showHelpOverlay = true;
      return;
    }

    // ── Tree-row navigation ─────────────────────────────────────────────
    // Active when a library is loaded, search is not active, no menu/rename
    // is open. ArrowDown from an empty search input also enters the tree
    // (parallel to the search-results combobox).
    // Other popovers (filter menu, sort menu, dropdowns) attach their own
    // keydown listeners but they fire AFTER this one — so we have to skip
    // here when the DOM tells us a competing menu is open. Querying by
    // class is pragmatic; once chunk c is fully shipped these could share
    // a small open-menus store instead.
    const competingMenuOpen = !!document.querySelector('.filter-menu, .sort-menu, .dropdown');

    // Action keys (R/F/./M/C, Cmd+O reveal, Shift+F10/ContextMenu) work
    // on the focused file in both tree and systems modes. Runs ahead of
    // the tree-only nav block so action keys don't fall through to view-
    // specific handlers in either mode.
    const fileActionGate =
      selectedFolder && !searchActive && !contextMenu && !renamingFilePath &&
      !competingMenuOpen && !focusedCollectionName && !inAnyInput;
    if (fileActionGate && handleFocusedFileActionKey(event)) return;

    // Tree-row arrow navigation. Systems view owns its own arrow nav,
    // so this block is gated to tree mode only.
    if (selectedFolder && !searchActive && !contextMenu && !renamingFilePath && !competingMenuOpen && !focusedCollectionName && viewMode === 'tree') {
      if (event.key === 'ArrowDown' && inSearchInput && searchQuery === '') {
        if (visibleTreeRows.length > 0) {
          event.preventDefault();
          (target as HTMLInputElement).blur();
          focusTreeRow(visibleTreeRows[0].path);
        }
        return;
      }

      if (!inAnyInput && handleTreeNavKey(event)) return;
    }

    if (!searchActive || searchResults.length === 0) return;

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
    // to the input. Enter on a focused row opens; Escape returns to input.
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
    } else if (event.key === 'Escape' && inList) {
      event.preventDefault();
      headerComponent?.focus();
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
    const confirmed = await confirm(`Re-index "${item.name}"? This rebuilds its chunks.`, { title: 'Re-index file' });
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

  function handleContextCreateCollectionFromFolder() {
    if (!contextMenu) return;
    const item = contextMenu.item;
    contextMenu = null;
    createCollectionFromItem(item);
  }

  function handleContextToggleSolo() {
    if (!contextMenu) return;
    const item = contextMenu.item;
    contextMenu = null;
    toggleScopeSolo(item);
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

    const label = item.is_dir ? 'folder' : 'file';
    const confirmed = await confirm(`Move "${item.name}" to Trash?`, { title: `Delete ${label}`, kind: 'warning' });
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

  async function handleRenameSubmit(oldPath: string, newName: string, isDir: boolean = false) {
    try {
      if (isDir) {
        const newPath = await invoke<string>('rename_folder', { oldPath, newName });
        selectedPaths = updatePathPrefix(selectedPaths, oldPath, newPath);
        syncedPaths = updatePathPrefix(syncedPaths, oldPath, newPath);
        expandedPaths = updatePathPrefix(expandedPaths, oldPath, newPath);
      } else {
        const newPath = await invoke<string>('rename_file', { oldPath, newName });
        if (focusedFilePath === oldPath) focusedFilePath = newPath;
        // Swap the path in selectedPaths so compute_diff can match old→new by content hash
        if (selectedPaths.has(oldPath)) {
          selectedPaths.delete(oldPath);
          selectedPaths.add(newPath);
          selectedPaths = selectedPaths;
        }
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
      collections = result.collections;
      activeContextName = result.active_context;
    } catch (e) {
      console.log('Could not fetch collections:', e);
    }
  }

  async function setActiveContext(name: string) {
    try {
      const result = await invoke<ActiveContextResult>('set_active_context', { name });
      activeContextName = result.active_context;
      // Activating a collection feels best in systems view: a curated
      // subset reads as a list, not a directory tree. The user can still
      // flip back to tree via the toggle if they prefer.
      setViewMode('systems');
      jobNotification.show({
        type: 'info',
        message: `Active context: ${name}`,
        duration: 3000,
      });
      await loadCollections();
      if (committedQuery) runSearch(committedQuery);
    } catch (e) {
      jobNotification.show({
        type: 'error',
        message: `Couldn't set active context: ${e}`,
        duration: 5000,
      });
    }
  }

  async function clearActiveContext() {
    try {
      await invoke<ActiveContextResult>('clear_active_context');
      activeContextName = null;
      jobNotification.show({
        type: 'info',
        message: 'Active context cleared',
        duration: 3000,
      });
      if (committedQuery) runSearch(committedQuery);
    } catch (e) {
      jobNotification.show({
        type: 'error',
        message: `Couldn't clear active context: ${e}`,
        duration: 5000,
      });
    }
  }

  function toggleActiveContext(name: string) {
    if (activeContextName === name) {
      clearActiveContext();
    } else {
      setActiveContext(name);
    }
  }

  function startEditCollection(name: string) {
    const col = collections[name];
    if (!col) return;
    collectionEditName = col.name;
    collectionEditDescription = col.description;
    collectionEditPaths = new Set(col.file_paths);
    editingCollectionName = name;
    draftName = null;
    setViewMode('systems');
    // The Save/Cancel controls now live inline on the panel row, so the
    // panel must be visible while editing.
    collectionsPanelOpen = true;
  }

  // Open a draft for a new (unsaved) collection. The draft renders as a
  // synthetic top row in the panel; nothing hits the database until Save.
  function startDraftCollection(name: string, paths: Iterable<string> = []) {
    collectionEditName = name;
    collectionEditDescription = '';
    collectionEditPaths = new Set(paths);
    draftName = name;
    editingCollectionName = null;
    setViewMode('systems');
    collectionsPanelOpen = true;
  }

  function cancelCollectionEdit() {
    editingCollectionName = null;
    draftName = null;
    collectionEditPaths = new Set();
    collectionEditName = '';
    collectionEditDescription = '';
  }

  async function saveCollection() {
    const filePaths = Array.from(collectionEditPaths);
    try {
      if (draftName) {
        await invoke<CollectionMutationResult>('create_collection', {
          name: draftName,
          filePaths,
          description: collectionEditDescription,
        });
        jobNotification.show({ type: 'success', message: `Created "${draftName}"`, duration: 4000 });
      } else if (editingCollectionName) {
        await invoke<CollectionMutationResult>('update_collection', {
          name: editingCollectionName,
          filePaths,
          description: collectionEditDescription,
        });
        jobNotification.show({ type: 'success', message: `Updated "${editingCollectionName}"`, duration: 4000 });
      } else {
        return;
      }
      cancelCollectionEdit();
      await loadCollections();
    } catch (e) {
      jobNotification.show({ type: 'error', message: `Save failed: ${String(e)}`, duration: 5000 });
    }
  }

  let pendingDeleteCollection: string | null = null;

  function requestDeleteCollection(name: string) {
    pendingDeleteCollection = name;
  }

  async function confirmDeleteCollection() {
    if (!pendingDeleteCollection) return;
    const name = pendingDeleteCollection;
    pendingDeleteCollection = null;
    try {
      await invoke('delete_collection', { name });
      cancelCollectionEdit();
      await loadCollections();
      jobNotification.show({ type: 'success', message: `Deleted "${name}"`, duration: 4000 });
    } catch (e) {
      jobNotification.show({ type: 'error', message: `Delete failed: ${String(e)}`, duration: 5000 });
    }
  }

  // ---------------------------------------------------------------------------
  // Bulk collection actions (right-click menu)
  // ---------------------------------------------------------------------------

  function indexedPdfsUnderPath(target: string): string[] {
    if (indexedPaths.has(target)) return [target];
    const prefix = target + '/';
    return [...indexedPaths].filter(p => p.startsWith(prefix));
  }

  function collectionsContaining(target: string, isDir: boolean): string[] {
    const targets = isDir ? new Set(indexedPdfsUnderPath(target)) : new Set([target]);
    if (targets.size === 0) return [];
    return Object.values(collections)
      .filter(c => c.file_paths.some(p => targets.has(p)))
      .map(c => c.name);
  }

  // Collections that already contain ALL of the target's indexed pdfs.
  // Used to suppress them from the "Add to collection" submenu — adding
  // would be a no-op. For folders this differs from collectionsContaining
  // (which is "any") because partial overlap still permits adding the rest.
  function collectionsFullyContaining(target: string, isDir: boolean): string[] {
    const targets = isDir ? new Set(indexedPdfsUnderPath(target)) : new Set([target]);
    if (targets.size === 0) return [];
    return Object.values(collections)
      .filter(c => {
        const cFiles = new Set(c.file_paths);
        for (const t of targets) if (!cFiles.has(t)) return false;
        return true;
      })
      .map(c => c.name);
  }

  async function addToCollection(name: string, item: FileItem) {
    const col = collections[name];
    if (!col) return;
    const candidates = item.is_dir ? indexedPdfsUnderPath(item.path) : [item.path];
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
    const targets = new Set(item.is_dir ? indexedPdfsUnderPath(item.path) : [item.path]);
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

  // Pick a name based on `base`, suffixing " 2", " 3" etc. on collision.
  function uniqueCollectionName(base: string): string {
    if (!collections[base]) return base;
    let suffix = 2;
    while (collections[`${base} ${suffix}`]) suffix++;
    return `${base} ${suffix}`;
  }

  // Open a draft seeded with the indexed PDFs under `item`. The draft
  // appears as a synthetic top row in the panel and doesn't hit the
  // database until Save.
  function createCollectionFromItem(item: FileItem) {
    const candidates = item.is_dir
      ? indexedPdfsUnderPath(item.path)
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
    startDraftCollection(uniqueCollectionName(baseName), candidates);
  }

  // ---------------------------------------------------------------------------
  // Collections panel + metadata dialog
  // ---------------------------------------------------------------------------

  async function togglePanel() {
    collectionsPanelOpen = !collectionsPanelOpen;
    try {
      const store = await load('settings.json');
      await store.set('collectionsPanelOpen', collectionsPanelOpen);
      await store.save();
    } catch (e) {
      console.log('Could not persist panel state:', e);
    }
  }

  // Panel "+" handler — opens a fresh draft with an auto-generated name.
  // CollectionsPanel auto-enters rename mode when the draft appears, so
  // the user can immediately type a name. Focusing the draft also lets
  // Esc-on-draft discard it via the panel's window keydown handler.
  function inlineCreateCollection() {
    const name = uniqueCollectionName('Untitled');
    startDraftCollection(name);
    setFocusedCollectionName(name);
  }

  // Inline rename of the active draft. Only updates local state; nothing
  // hits the database until Save. Collisions are deferred to the backend
  // on Save (notification surfaces the error).
  function handleDraftRename(name: string) {
    if (!draftName) return;
    draftName = name;
    collectionEditName = name;
  }

  function startEditMetadata(name: string) {
    editingMetadataFor = name;
  }

  async function saveMetadata(changes: {
    name: string;
    description: string;
    color: string;
    archived: boolean;
  }) {
    const original = editingMetadataFor;
    if (!original) return;
    const col = collections[original];
    if (!col) {
      editingMetadataFor = null;
      return;
    }
    editingMetadataFor = null;

    const renaming = changes.name !== original;
    const metadataChanged =
      changes.description !== col.description ||
      (changes.color || null) !== col.color ||
      changes.archived !== col.archived;

    try {
      let effectiveName = original;
      if (renaming) {
        await invoke<CollectionMutationResult>('rename_collection', {
          name: original,
          newName: changes.name,
        });
        effectiveName = changes.name;
      }
      if (metadataChanged) {
        await invoke('update_collection', {
          name: effectiveName,
          description: changes.description,
          color: changes.color,
          archived: changes.archived,
        });
      }
      jobNotification.show({
        type: 'success',
        message: renaming ? `Renamed to "${changes.name}"` : `Updated "${changes.name}"`,
        duration: 4000,
      });
      // If the user archived the active context, clear it.
      if (changes.archived && activeContextName === original) {
        await invoke('clear_active_context');
      }
      await loadCollections();
    } catch (e) {
      jobNotification.show({
        type: 'error',
        message: `Save failed: ${String(e)}`,
        duration: 5000,
      });
    }
  }

  async function toggleArchived(name: string, archived: boolean) {
    try {
      await invoke('update_collection', { name, archived });
      if (archived && activeContextName === name) {
        await invoke('clear_active_context');
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

  function handleCollectionAdd(paths: string[]) {
    for (const p of paths) collectionEditPaths.add(p);
    collectionEditPaths = collectionEditPaths;
  }

  function handleCollectionRemove(paths: string[]) {
    for (const p of paths) collectionEditPaths.delete(p);
    collectionEditPaths = collectionEditPaths;
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
        startMessage: 'Starting reindex...',
        errorPrefix: 'Reindex failed',
        streamsProgress: true,
        buildResultMessage: (r) => {
          const parts: string[] = [];
          if (r.updated > 0) parts.push(`${r.updated} reprocessed`);
          if (r.errors.length > 0) parts.push(`${r.errors.length} error(s)`);
          const chunkStr = r.chunks_total > 0
            ? ` ${r.chunks_total.toLocaleString()} chunks.`
            : '';
          const message = parts.length > 0
            ? `Reindexed: ${parts.join(', ')}.${chunkStr}`
            : 'Nothing to reindex.';
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

<svelte:window on:keydown={handleGlobalKeydown} on:contextmenu|preventDefault />

<LaunchSplash visible={showSplash} onDismiss={dismissSplash} />

<main class="app-layout">
  <Header
    bind:this={headerComponent}
    bind:searchQuery
    disabled={!selectedFolder || isCollectionEditMode}
    panelOpen={collectionsPanelOpen}
    panelToggleVisible={!!selectedFolder}
    filterVisible={!!selectedFolder}
    excludedSystems={filterExcludedSystems}
    {soloedSystems}
    availableSystems={gameSystemStats}
    untaggedCount={untaggedFileCount}
    onSubmit={handleSearchSubmit}
    onDebouncedChange={handleSearchDebounced}
    onClear={handleSearchClear}
    onTogglePanel={togglePanel}
    onToggleSystemFilter={toggleSystemFilter}
    onToggleSystemSolo={toggleSystemSolo}
    onClearSystemFilter={clearSystemFilter}
    {showHidden}
    {hiddenCount}
    onToggleShowHidden={toggleShowHidden}
    onClearHidden={clearHidden}
    {collectionFilterAvailable}
    {uncategorizedFilterAvailable}
    {focusFilterAvailable}
    {activeContextName}
    {showOnlyUncollected}
    {uncollectedCount}
    {focusActiveCollection}
    onToggleShowOnlyUncollected={toggleShowOnlyUncollected}
    onToggleFocusActiveCollection={toggleFocusActiveCollection}
    collapseAllVisible={!!selectedFolder && !searchActive}
    collapseAllDisabled={viewMode === 'systems' || expandedPaths.size === 0}
    onCollapseAll={collapseAll}
    viewToggleVisible={!!selectedFolder && !searchActive}
    {viewMode}
    onSetViewMode={setViewMode}
    {searchActive}
  />

  {#if selectedFolder}
    <div class="workspace">
      {#if collectionsPanelOpen}
        <CollectionsPanel
          bind:this={collectionsPanelComponent}
          {collections}
          {hiddenCountByCollection}
          activeName={activeContextName}
          editingName={editingCollectionName}
          {draftName}
          editFileCount={collectionEditPaths.size}
          onSetActive={setActiveContext}
          onClearActive={clearActiveContext}
          onEdit={startEditMetadata}
          onEditFiles={startEditCollection}
          onDelete={requestDeleteCollection}
          onToggleArchived={toggleArchived}
          onCreate={inlineCreateCollection}
          onSaveFiles={saveCollection}
          onCancelFiles={cancelCollectionEdit}
          onDraftRename={handleDraftRename}
          focusedName={focusedCollectionName}
          onFocusCollection={setFocusedCollectionName}
        />
      {/if}

      <!-- svelte-ignore a11y-no-static-element-interactions -->
      <div class="file-tree-area" class:search-mode={searchActive} on:mousedown={handleFileTreeAreaMousedown}>
        {#if searchActive}
          <SearchScopeBar
            {collectionSolos}
            {collectionMutes}
            excludedSystems={filterExcludedSystems}
            {soloedSystems}
            {showHidden}
            resultCount={searchResults.length}
            indexedFileCount={searchableFileCount}
            isLoading={isSearching}
            onClearCollectionSolo={handleClearCollectionSolo}
            onClearCollectionMute={handleClearCollectionMute}
            onToggleSystemFilter={toggleSystemFilter}
            onToggleSystemSolo={toggleSystemSolo}
            onToggleShowHidden={toggleShowHidden}
          />
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
                indexedFileCount={indexedPathsSet.size}
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
            excludedSystems={filterExcludedSystems}
            {soloedSystems}
            onToggleSystemFilter={toggleSystemFilter}
            onToggleSystemSolo={toggleSystemSolo}
            {hiddenPaths}
            {showHidden}
            {highlightPaths}
            libraryRoot={selectedFolder}
            {focusedFilePath}
            {focusedCollectionName}
            onFocusFile={setFocusedFilePath}
            onContextMenu={handleContextMenu}
            {renamingFilePath}
            onRenameSubmit={handleRenameSubmit}
            onRenameCancel={handleRenameCancel}
            contextMenuOpen={!!contextMenu}
            {isCollectionEditMode}
            collectionPaths={collectionEditPaths}
            onCollectionAdd={handleCollectionAdd}
            onCollectionRemove={handleCollectionRemove}
          />
        {:else}
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
              {highlightPaths}
              {displayPaths}
              {hiddenPaths}
              {showHidden}
              {soloedScopePaths}
              {mutedScopePaths}
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
        ? indexedPdfsUnderPath(contextMenu.item.path).length > 0
        : indexedPaths.has(contextMenu.item.path)}
      canSolo={contextMenu.item.is_dir
        ? indexedPdfsUnderPath(contextMenu.item.path).length > 0
        : indexedPaths.has(contextMenu.item.path)}
      isSoloed={soloCollections.has(contextMenu.item.path)}
      containingCollections={collectionsContaining(contextMenu.item.path, contextMenu.item.is_dir)}
      knownSystems={knownSystems}
      currentTags={effectiveGameSystemMap.get(contextMenu.item.path) ?? []}
      onSetGameSystems={(tags) => handleSetGameSystems(contextMenu!.item.path, contextMenu!.item.name, tags)}
      excludeFromAdd={collectionsFullyContaining(contextMenu.item.path, contextMenu.item.is_dir)}
      initialSubmenu={contextMenu.initialSubmenu}
      onOpen={handleContextOpen}
      onReveal={handleContextReveal}
      onRename={handleContextRename}
      onDelete={handleContextDelete}
      onReindex={handleContextReindex}
      onShowStats={handleContextShowStats}
      onToggleSolo={handleContextToggleSolo}
      onAddToCollection={handleContextAddToCollection}
      onAddToNewCollection={handleContextAddToNewCollection}
      onRemoveFromCollection={handleContextRemoveFromCollection}
      onCreateCollectionFromFolder={handleContextCreateCollectionFromFolder}
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

  {#if pendingDeleteCollection}
    <ConfirmDialog
      title="Delete collection"
      message={`Delete "${pendingDeleteCollection}"? Files in your library are not affected.`}
      confirmLabel="Delete"
      danger
      onConfirm={confirmDeleteCollection}
      onCancel={() => { pendingDeleteCollection = null; }}
    />
  {/if}

  {#if editingMetadataFor && collections[editingMetadataFor]}
    <CollectionEditDialog
      collection={collections[editingMetadataFor]}
      onSave={saveMetadata}
      onCancel={() => { editingMetadataFor = null; }}
    />
  {/if}

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

  .file-tree-area {
    flex: 1;
    min-width: 0;
    overflow-y: auto;
    overflow-anchor: none;
    padding: 0.25rem 0.75rem;
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
