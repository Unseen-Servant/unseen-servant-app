<script lang="ts">
  import { onMount, onDestroy, tick, flushSync, type Snippet } from 'svelte';
  import { invoke } from '@tauri-apps/api/core';
  import { listen } from '@tauri-apps/api/event';
  import { writeText } from '@tauri-apps/plugin-clipboard-manager';
  import { openPath, openUrl, revealItemInDir } from '@tauri-apps/plugin-opener';
  import { pdfFileUrl } from './pdfUrl';
  import { sendTargets, sendToCommand, type SendTargets } from './sendToCommand';
  import { load } from '@tauri-apps/plugin-store';
  import type { FileItem, FileStatusEntry, IndexStatusResult, SyncResult, KnownGameSystem, KnownGameSystemsResult, StatsResult, CollectionInfo, CollectionsResult, CollectionMutationResult, SearchResultItem, SearchResponse, SyncPreferences, PromptCounts, SyncAction } from './types';
  import { decideSyncAction } from './syncPolicy';
  import { DEFAULT_SYNC_PREFERENCES } from './types';
  import FileTree from './FileTree.svelte';
  import ContextMenu from './ContextMenu.svelte';
  import Header from '../shell/Header.svelte';
  import SearchResults from './SearchResults.svelte';
  import SearchInspector from './SearchInspector.svelte';
  import SearchScopeBar from './SearchScopeBar.svelte';
  import InspectorPlate from './InspectorPlate.svelte';
  import StatusBar from '../shell/StatusBar.svelte';
  import GettingStartedPage from './GettingStartedPage.svelte';
  import SettingsModal from '../shell/SettingsModal.svelte';
  import KeyboardHelpOverlay from '../shell/KeyboardHelpOverlay.svelte';
  import DocumentStatsModal from './DocumentStatsModal.svelte';
  import { confirmPrompt } from '../shell/confirmStore';
  import { holdLatch } from '../ui/holdLatch';
  import CollectionsPanel from './CollectionsPanel.svelte';
  import FilterPanel from './FilterPanel.svelte';
  import SystemsView from './SystemsView.svelte';
  import { jobNotification, pendingNotification } from '../shell/notificationStore';
  import { computeAncestorPaths, areAllDescendantsSelected, isPathOrAncestorIn, renamePathKeys } from './selectionUtils';
  import { computeVisibleRows, indexOfPath, rowHasIndexedMaterial, visibleFileSpan, type VisibleRow } from './treeNav';
  import { materializeKey } from '../shell/paneFocus';
  import { resolveMix, resolveScopeSet, searchGameSystemsFilter, emptyScopeMessage, type CurationKey, type ScopeRef } from './searchScope';
  import { runSyncJob } from './syncJob';
  import { clearSummary, reindexSummary, syncPromptMessage, syncSummary } from './syncMessages';
  import {
    indexedPathsUnder,
    collectionsContaining,
    collectionsFullyContaining,
    uniqueCollectionName,
    computeFolderMembership,
    memberStateFor,
    addMembers,
    removeMembers,
  } from './collectionMembership';
  import { buildRibbonIndex, firstColorByPath } from './collectionRibbons';
  import { createCommitScheduler, mergeArmedCollection } from './collectionCommit';
  import { renameNavKey } from './collectionsNav';
  import { setTreePathsPayload, type TreePathsPayload } from './dragPayload';
  import { chord, digitChord, isDeleteChord, jumpEdge } from '../shell/keybindings';
  import { filterByQuery, playOnly, stepPick, transportNames } from './collectionOrder';
  import { menuSlotHeld } from '../shell/menuSlot';
  import { viewFilter } from '../shell/mention';
  import { filterTree, filterWords, nameMatches } from './nameFilter';
  import {
    parseString,
    parseBoolean,
    parseStringArray,
    parseEnum,
  } from '../shell/storeParsers';
  import { parseScopeConsoleState } from './scopeConsole';
  import type { ScopeConsoleState } from './scopeConsole';

  /** False while another panel's tab is showing (PANELS.md): the window's
   *  keyboard belongs to that panel then. */
  export let active = true;
  // The host's dock toggle, drawn at the right end of the header (PANELS.md).
  export let windowKey: Snippet | undefined = undefined;

  let selectedFolder = '';
  let files: FileItem[] = [];
  let selectedPaths = new Set<string>;
  let syncedPaths = new Set<string>;
  let expandedPaths = new Set<string>();
  // The whole library, every level down — the / filter has to see inside
  // folders nobody has opened, and `files` only holds what has been. Walked
  // on the filter's first keystroke in the tree, and again after every
  // reload while the filter is up; the last walk stays on screen until the
  // next lands, so a background check never blinks the tree unfiltered.
  // fullTreeWalk tells a live walk from one a reload has overtaken (0 = walk
  // again when next needed); fullTreeRoot keeps another folder's walk out.
  let fullTree: FileItem[] | null = null;
  let fullTreeRoot = '';
  let fullTreeWalk = 0;
  let fullTreeSeq = 0;
  // Folds as they stood before the filter opened its own; handed back when
  // it ends. Never persisted, like the rest of the expansion state.
  // filterFoldsFor is the words the current folds were opened for.
  let expandedBeforeFilter: Set<string> | null = null;
  let filterFoldsFor: string | null = null;
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
  // at.
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
    initialSubmenu: 'collection' | null;
    hideState: { directlyHidden: boolean; inheritedHidden: boolean };
    /** Set when the menu is a search hit's: it can go to Command. */
    result?: SearchResultItem;
    sendTargets?: SendTargets | 'loading';
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

  // Library narrowing — the scope doctrine: the transport arms material
  // into the mix; S narrows within what's armed; M carves out of it. playingCollections ∪-minus-mutedCollectionNames resolve to
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

  // Sidecar health
  let sidecarConnected = false;
  let mcpConnected = false;
  let mcpActive = false;
  let lastSyncTime: Date | null = null;
  let autoSyncInterval: ReturnType<typeof setInterval> | null = null;
  let showSettings = false;
  let showHelpOverlay = false;
  // Gates the engage detent (app.css). See where it's set in onMount.
  let motionReady = false;
  let settingsInitialTab: 'general' | 'library' | 'game-systems' | 'help' = 'general';
  let settingsInitialHelpSubTab: 'guides' | 'reference' | 'about' = 'guides';
  let healthInterval: ReturnType<typeof setInterval> | null = null;
  let mcpStatusInterval: ReturnType<typeof setInterval> | null = null;

  // User-configurable behavior
  let syncPreferences: SyncPreferences = { ...DEFAULT_SYNC_PREFERENCES };
  // Weak search results fade back in the list (General settings).
  let dimWeakResults = true;
  let dataDir = '';

  // Ollama health
  let ollamaRunning = false;
  let ollamaModelReady = false;

  // In-app search state
  let searchQuery = '';
  let committedQuery = '';
  // Whether committedQuery came from search-as-you-type with its last word
  // possibly unfinished. Scope toggles and load-more re-run the same query,
  // so they re-send the same flag; Enter clears it.
  let committedPartial = false;
  // The search view is stateful, not derived: entered by the first real
  // query in the search bar (focus alone, or an @-word, stays in the
  // browse view), left only explicitly (view switch or the Escape
  // ladder). Never persisted — the app launches into the browse
  // view. searchActive (committed query) keeps meaning "has a query".
  let searchViewOpen = false;
  // A bar that leads with / is a name filter on the browse view, not a
  // search (mention.ts). It lives exactly as long as that text in the bar:
  // focus can leave, × or Esc in the bar ends it. Typing one steps out of
  // the search view — the filter narrows the tree or systems view, so that
  // has to be what's on screen.
  $: nameFilter = viewFilter(searchQuery);
  $: filterWordList = nameFilter === null ? [] : filterWords(nameFilter);
  $: if (nameFilter !== null) searchViewOpen = false;
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
  let searchInspectorComponent: SearchInspector | undefined;
  let systemsViewComponent: SystemsView | undefined;
  let collectionsPanelComponent: CollectionsPanel | undefined;
  let filterPanelComponent: FilterPanel | undefined;
  // Lazy result loading: start with 25, grow by 25 each scroll-to-bottom,
  // hard cap at 100 to keep us out of the long tail of low-relevance hits.
  // reachedEnd follows the backend's `exhausted` flag — it drained its
  // candidate pool, no point asking for more.
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
  // its gem takes the collection pigment — with the "play" prefix
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
  // Collection-track mutes chip like plays — pigment gem, mute
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

  async function runSearch(q: string, focusResults = false) {
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

    // The full intersection, systems axis included — what the scope-bar
    // meter's denominator shows. Catches cross-axis empties the per-axis
    // checks above can't (a soloed system with no file under a soloed
    // folder), so the meter never reads "of 0 files" beside a generic
    // no-results message. Computed fresh for the same reason as the rest.
    const fullScope = scopeBypassed ? null : resolveScopeSet(
      mix, soloSets, muteSets,
      soloCuration, mutedCuration, collectedPaths,
      soloedSystems, filterExcludedSystems, effectiveGameSystemMap, indexedPaths
    );

    const emptyMsg = emptyScopeMessage({
      mixEmpty,
      anyLivePlaying: [...playingCollections].some((n) => Object.hasOwn(collections, n)),
      pathScopeEmpty,
      anySolosEngaged: scopeSolos.size > 0 || soloCuration.size > 0 || soloedSystems.size > 0,
      systemsEmpty,
      scopeEmpty: fullScope !== null && fullScope.size === 0,
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
        partial: committedPartial,
      });
      if (seq !== searchSeq) return;
      const next = response.results ?? [];
      // The backend says whether its pool ran dry. A short list doesn't:
      // dedupe, near-dup collapse and packing all shorten a response that
      // a larger request would still grow.
      reachedEnd = response.exhausted;
      // Preserve selection across grow-fetches: when the new result list
      // contains the previously-selected row in place, leave selectedIndex
      // alone. Only reset for fresh queries (first page) or shrinkage.
      const wasGrowing = next.length > searchResults.length && searchResults.length > 0;
      searchResults = next;
      resultsQuery = trimmed;
      if (!wasGrowing) selectedResultIndex = 0;
      if (focusResults && next.length > 0) {
        // Only while the bar still holds focus — a click or chord during
        // the wait has already put the user somewhere else.
        const active = document.activeElement as HTMLElement | null;
        if (active?.classList.contains('search-input')) {
          await tick();
          searchResultsComponent?.focusRow(selectedResultIndex);
        }
      }
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
    // Search-as-you-type: without a trailing space the last word may
    // be unfinished, so the sidecar completes rather than corrects it.
    committedPartial = !/\s$/.test(q);
    runSearch(q);
  }

  // Enter in the search input always (re-)submits, then hands focus to the
  // first result once the list lands — Enter there opens it. With no hits
  // focus stays in the bar to retype. The bar is re-entered with ⌘K (or a
  // click), never by arrowing up out of the list.
  function handleSearchSubmit(q: string) {
    const trimmed = q.trim();
    if (trimmed !== committedQuery) resetPageSize();
    committedQuery = trimmed;
    committedPartial = false; // Enter commits the query as typed
    runSearch(q, true);
  }

  // Scroll-to-bottom in the result list bumps the page size and re-runs
  // the same query with a larger n_results. Re-querying (vs. true offset
  // pagination) is fine on a local sidecar — the embedding is cached and
  // the store's nearest-neighbour scan costs the same at any page size.
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
    // The bar sits on the file side in either view, so focusing it points
    // the pane model there. A dock caret left over would otherwise stay
    // ringed — and, since the dock stays keyboard-live, keep the arrows —
    // while the user types. Nothing is lost: lastFocused* remembers every
    // position.
    pointAtEmpty('files');
  }

  function handleSearchQuery() {
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

  async function handleOpenResult(source: string, filename: string, page?: number | null) {
    // The index already knows the hit's exact path — duplicate filenames
    // in different folders must not open the wrong book. The filename
    // scan stays as the fallback for a file moved since indexing, which
    // the status tracks at its new path under the same name.
    const path = indexedPaths.has(source) ? source : resolvePathForFilename(filename);
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
    // Sidecar failed to start at app launch — show one sticky banner so the
    // user gets a single clear failure message instead of N "failed to
    // connect" toasts on every per-call attempt. The boot emits it before
    // this window even exists, so we also poll the stashed state here;
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
      const savedDimWeakResults = parseBoolean(await store.get('dimWeakResults'));
      if (savedDimWeakResults !== undefined) {
        dimWeakResults = savedDimWeakResults;
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

  async function handleDimWeakResultsChange(value: boolean) {
    dimWeakResults = value;
    try {
      const store = await load('settings.json');
      await store.set('dimWeakResults', dimWeakResults);
      await store.save();
    } catch (e) {
      console.log('Could not persist dimWeakResults:', e);
    }
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
    // bar if it holds focus there — a focused input would keep feeding a
    // view no longer on screen. Outside it the bar is empty or a / filter
    // on the view being swapped in, so it keeps focus and Tab can flip
    // again while you type.
    if (searchViewOpen) {
      const ae = document.activeElement as HTMLElement | null;
      if (ae?.classList.contains('search-input')) ae.blur();
    }
    searchViewOpen = false;
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

  // Track select (⌘1–9, the search bar's @-pick): play this collection alone — or
  // stop it, when it already plays alone.
  function playOnlyCollection(name: string) {
    playingCollections = playOnly(playingCollections, name);
    persistScopeConsole();
    if (committedQuery) runSearch(committedQuery);
  }

  // Slot N is the Nth transport row as the panel sorts it.
  $: collectionSlots = transportNames(Object.values(collections), collectionsSortKey, collectionsCustomOrder);

  // The @-pick: the search bar's @-word (minus the @; null while there is
  // none) played out on the collections panel. The bar keeps focus and
  // forwards its keys here; the panel draws the matches and the cursor.
  let mentionQuery: string | null = null;
  $: pickMatches = mentionQuery === null ? [] : filterByQuery(collectionSlots, mentionQuery);
  // A new @-word re-aims at its best match; ↑/↓ move from there.
  let pickCursor: string | null = null;
  $: pickCursor = pickMatches[0] ?? null;
  // A closed panel opens for the pick and closes behind it — the pick
  // happens on the console, so the console has to be on screen.
  $: collectionsPanelShown = collectionsPanelOpen || mentionQuery !== null;

  function handleMentionKey(event: KeyboardEvent): boolean {
    if (event.metaKey || event.ctrlKey || event.altKey) return false;
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      pickCursor = stepPick(pickMatches, pickCursor, event.key === 'ArrowDown' ? 1 : -1);
      return true;
    }
    if (event.key === 'Enter') {
      // ↵ plays the cursor's collection alone and hands the bar back its
      // query; ⇧↵ toggles it in the mix and leaves the @-word open for the
      // next pick.
      if (pickCursor && event.shiftKey) {
        togglePlayCollection(pickCursor);
      } else if (pickCursor) {
        playOnlyCollection(pickCursor);
        void headerComponent?.consumeMention();
      }
      return true;
    }
    return false;
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

  // Masthead [reset] in the filter console: clears every solo/mute on
  // all three axes, stops every playing collection, unmutes every muted
  // one, and returns the three view switches to off. It sits in the
  // panel's masthead, above every section, so it answers for the whole
  // panel — the earlier split, where it cleared the narrowing axes but
  // left the view switches lit, made the masthead lie about its reach.
  //
  // It stops at hiddenPaths. Everything above is a switch thrown in one
  // gesture and restored in one; the hidden set is built a file at a time
  // and this app has no undo, so a reset that wiped it could cost an
  // afternoon of curation. The Hidden items section keeps its own Clear
  // for that, scoped to the section that owns it.
  function clearAllFilters() {
    filterExcludedSystems = new Set();
    soloedSystems = new Set();
    scopeSolos = new Map();
    scopeMutes = new Map();
    playingCollections = new Set();
    mutedCollectionNames = new Set();
    soloCuration = new Set();
    mutedCuration = new Set();
    showHidden = false;
    hideOutOfScope = false;
    hideUnindexed = false;
    persistScopeConsole();
    persistHidden();
    if (committedQuery) runSearch(committedQuery);
  }

  // The narrowings bypass actually suppresses — every S/M and transport
  // term, none of the view switches (those are display filters bypass
  // leaves alone). Mirror of the scope bar's anyBypassable, and the gate
  // for keyboard B: the key must refuse exactly what the switch refuses.
  $: scopeNarrowingEngaged =
    filterExcludedSystems.size > 0 ||
    soloedSystems.size > 0 ||
    scopeSolos.size > 0 ||
    scopeMutes.size > 0 ||
    playingCollections.size > 0 ||
    mutedCollectionNames.size > 0 ||
    soloCuration.size > 0 ||
    mutedCuration.size > 0;

  // Whether [reset] has anything to do — the narrowing terms above plus
  // one term for each view switch clearAllFilters() puts back, so the two
  // can't drift into a button that fires a no-op or one that sits dim over
  // a live console. Bypass is deliberately not a term: it suspends the
  // scope without discarding it, and the chips it dims are exactly what
  // reset exists to clear. hiddenPaths isn't one either — reset doesn't
  // touch it.
  $: scopeConsoleEngaged =
    scopeNarrowingEngaged ||
    showHidden ||
    hideOutOfScope ||
    hideUnindexed;

  // Header lamps split scopeNarrowingEngaged by the panel that throws each
  // term: the collections transport (play, mute, arm) on one key, the
  // filter console's axes — systems, curation, tree paths — on the other.
  $: collectionsEngaged =
    playingCollections.size > 0 || mutedCollectionNames.size > 0 || armedCollection !== null;
  $: filtersEngaged =
    filterExcludedSystems.size > 0 ||
    soloedSystems.size > 0 ||
    scopeSolos.size > 0 ||
    scopeMutes.size > 0 ||
    soloCuration.size > 0 ||
    mutedCuration.size > 0;

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
      const status = await invoke<{
        models: { role: string; runtime_up: boolean; ready: boolean }[];
      }>('check_models_status');
      const embed = status.models.find((m) => m.role === 'embed');
      ollamaRunning = embed?.runtime_up ?? false;
      ollamaModelReady = embed?.ready ?? false;
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
        .then(r => { storageBytes = r.storage_bytes; totalChunks = r.total_chunks; })
        .catch(() => { storageBytes = 0; totalChunks = 0; });

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
    const action = decideSyncAction(status.summary, syncPreferences, options.userTriggered ?? false);
    await applySyncAction(action);
  }

  function showSyncPrompt(counts: PromptCounts) {
    if (!indexStatus) return;

    const message = syncPromptMessage(counts);
    if (!message) {
      pendingNotification.dismiss();
      return;
    }

    pendingNotification.show({
      type: 'action',
      message,
      actionLabel: isSyncing ? 'sync queued' : 'sync',
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
      // Under a / filter the tree renders from the walk, so only the folds
      // the filter will hand back need loading here.
      const sortedExpanded = Array.from(expandedBeforeFilter ?? expandedPaths)
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
      fullTreeWalk = 0;
      error = '';
      refreshTotalFilesFound();
      if (missingFolderToastId) {
        jobNotification.dismissIf(missingFolderToastId);
        missingFolderToastId = null;
      }
    } catch (e) {
      error = String(e);
      files = [];
      fullTree = null;
      fullTreeWalk = 0;
      totalFilesFound = 0;
    }
  }

  let lastIndexClickedPath: string | null = null;

  function applyRangeToggle(
    target: Set<string>,
    anchor: string,
    current: string,
    requireIndexed: boolean,
  ): boolean {
    const span = visibleFileSpan(visibleTreeRows, anchor, current);
    if (span === null) return false;
    const shouldSelect = !target.has(current);
    for (const p of span) {
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
    // Under bypass the narrowing is suspended, not cleared — the rows it
    // removed come back, like every other dim and drop on this surface.
    if (!scopeBypassed && viewMode === 'systems' && soloCuration.size > 0) {
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

  // The / filter in the tree: walk the whole library once, then keep the
  // rows filterTree picks and open the folders on the way to each match.
  // Until the walk lands the tree shows as it is — a blink on a local disk.
  $: treeFiltering = filterWordList.length > 0 && viewMode === 'tree' && !!selectedFolder;
  $: if (treeFiltering && fullTreeWalk === 0) void loadFullTree(selectedFolder);
  $: treeFilter = treeFiltering && fullTree && fullTreeRoot === selectedFolder
    ? filterTree(fullTree, filterWordList)
    : null;
  $: syncFilterFolds(treeFilter, filterWordList.join(' '));
  $: treeRoots = treeFilter && fullTree ? fullTree : files;
  $: treeDisplayPaths = treeFilter ? treeFilter.show : displayPaths;

  async function loadFullTree(folder: string) {
    const walk = ++fullTreeSeq;
    fullTreeWalk = walk;
    try {
      const tree = await invoke<FileItem[]>('list_tree', { folderPath: folder });
      if (fullTreeWalk === walk) { fullTree = tree; fullTreeRoot = folder; }
    } catch (e) {
      console.error('Failed to walk the library:', e);
      if (fullTreeWalk === walk) { fullTree = files; fullTreeRoot = folder; }
    }
  }

  // Each change of words re-opens the way to every match; folding while
  // filtering lasts until the next keystroke, and a fresh walk of the same
  // words leaves the folds alone. The folds from before come back when the
  // filter ends.
  function syncFilterFolds(filter: typeof treeFilter, words: string) {
    if (filter) {
      if (expandedBeforeFilter === null) expandedBeforeFilter = expandedPaths;
      if (words !== filterFoldsFor) {
        expandedPaths = new Set(filter.open);
        filterFoldsFor = words;
      }
    } else if (expandedBeforeFilter !== null) {
      expandedPaths = expandedBeforeFilter;
      expandedBeforeFilter = null;
      filterFoldsFor = null;
    }
  }

  // Flat list of currently-visible tree rows for keyboard nav. Mirrors what
  // FileTree renders, so consecutive entries here are visually adjacent.
  $: visibleTreeRows = computeVisibleRows(treeRoots, expandedPaths, treeDisplayPaths, hiddenPaths, showHidden, {
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

  async function handleSetGameSystems(path: string, tags: string[]) {
    pendingTagOverrides.set(path, tags);
    pendingTagOverrides = pendingTagOverrides;
    try {
      await invoke('set_game_systems', { path, gameSystems: tags });
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
      // Under the filter the walked tree already holds every level.
      if (!treeFilter) await ensureChildrenLoaded(path);
      expandedPaths.add(path);
      expandedPaths = expandedPaths;
    }
  }

  function collapseAll() {
    expandedPaths = new Set();
  }

  async function collapseAllKeepingCaret() {
    const was = focusedFilePath;
    collapseAll();
    if (!was) return;
    await tick();
    const top = visibleTreeRows.find((r) => was === r.path || was.startsWith(r.path + '/'));
    if (top) focusTreeRow(top.path);
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

  // ↓ or ↵ out of a / filter lands on the first row it matched, not back
  // where the caret was — that row may be anywhere, or filtered away.
  function focusFirstMatch() {
    if (focusedFilePath !== null) return;
    if (viewMode === 'systems') {
      systemsViewComponent?.claim(null);
      return;
    }
    const row = visibleTreeRows.find((r) => nameMatches(r.item.name, filterWordList)) ?? visibleTreeRows[0];
    if (row) focusTreeRow(row.path);
  }

  // A mousedown on the file pane's empty or non-selectable space — the scope
  // bar, a systems-view group header, the gap below the last row — points at
  // the region and deselects. Rows are skipped so their own click (which fires
  // after mousedown) owns the caret, and so dragging a row doesn't clear it.
  // In search mode the whole area is the search side: any click here — result
  // rows included — reclaims the arrows from a dock pane. Result selection is
  // not a pane caret, so nothing there needs the row skip.
  function handleFileTreeAreaMousedown(event: MouseEvent) {
    if (searchViewOpen) {
      pointAtEmpty('files');
      return;
    }
    const target = event.target as HTMLElement | null;
    if (target?.closest('[data-tree-row], [data-sv-row]')) return;
    pointAtEmpty('files');
  }

  // Returns true if the event was handled and shouldn't bubble further.
  function handleTreeNavKey(event: KeyboardEvent): boolean {
    const meta = event.metaKey || event.ctrlKey;
    const lk = event.key.toLowerCase();

    // Vim-style aliases: hjkl mirror the arrow keys. Only when no modifier
    // is held so chords like Cmd+K keep their meaning. h/l free up because
    // the hide action moved to '.', matching the Cmd+Shift+. show-hidden chord.
    const bareLetter = !meta && !event.shiftKey && !event.altKey;
    const isDown  = event.key === 'ArrowDown'  || (bareLetter && lk === 'j');
    const isUp    = event.key === 'ArrowUp'    || (bareLetter && lk === 'k');
    const isLeft  = event.key === 'ArrowLeft'  || (bareLetter && lk === 'h');
    const isRight = event.key === 'ArrowRight' || (bareLetter && lk === 'l');

    const edge = jumpEdge(event);
    if (edge) {
      event.preventDefault();
      if (visibleTreeRows.length > 0) {
        focusTreeRow(visibleTreeRows[edge === 'first' ? 0 : visibleTreeRows.length - 1].path);
      }
      return true;
    }

    // ⇧← / ⇧H: collapse the whole tree — the row's collapse key, shifted
    // up to every folder. The caret climbs to the top-level row that held
    // it, so it never sits on a row that just vanished.
    if (event.shiftKey && !meta && !event.altKey && (event.key === 'ArrowLeft' || lk === 'h')) {
      event.preventDefault();
      void collapseAllKeepingCaret();
      return true;
    }

    if (isDown) { event.preventDefault(); moveTreeFocus(1);  return true; }
    if (isUp)   { event.preventDefault(); moveTreeFocus(-1); return true; }

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
    // indexing normally, collection membership while armed. ⇧X extends from
    // the last tick, the keyboard half of shift-click. Space stays unbound —
    // →/← walk folders, Enter and ⌘O open, R renames.
    if (!meta && !event.altKey && lk === 'x') {
      event.preventDefault();
      if (armState) toggleMembership(row.item, event.shiftKey);
      else toogleSelection(row.path, row.item.is_dir, row.item, event.shiftKey);
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

    // Enter opens a file or folds a folder — the results list's Enter, and
    // the treeview default. Stands down on a focused button so the button
    // keeps its own activation.
    if (event.key === 'Enter' && !meta && !event.shiftKey && !event.altKey
        && !(event.target as HTMLElement | null)?.closest('button, a[href], [role="button"]')) {
      event.preventDefault();
      if (focused.item.is_dir) handleToggleExpand(focused.path);
      else openPath(focused.path);
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
      // view they fall through to SystemsView's own handler — bare
      // letters work the focused file, ⇧S/⇧M its group. The context
      // menu moves to Shift+F10 / the Menu key (M used to open it).
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
      if (lk === 'c') { event.preventDefault(); openContextMenuAtFocusedRow('collection'); return true; }
      if (event.key === '.' || event.code === 'NumpadDecimal') {
        event.preventDefault();
        toggleHidden(focused.item);
        return true;
      }
    }

    return false;
  }

  function openContextMenuAtFocusedRow(initialSubmenu: 'collection' | null = null) {
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
  //   4. Search view                     → leave to the browse view
  //   5. Focus in bar                    → drop a / filter, else back to
  //                                         the browse view's rows
  //   6. Row under a / filter            → focus the search bar
  //   7. Focused tree row                → clear focus
  //   (modal Esc handled by Modal.svelte; the docked filter panel claims
  //   its own Esc while focus is inside it)

  // The release half of every hold. Unconditional on purpose: whatever
  // gating applied when the key went down, the key coming back up must
  // always reach the latch, or a control stays stuck in its held state.
  function handleGlobalKeyup(event: KeyboardEvent) {
    holdLatch.release(event.key.toLowerCase());
  }

  function handleGlobalKeydown(event: KeyboardEvent) {
    if (!active) return;
    // When a native <dialog> is open via showModal(), the browser inerts
    // the rest of the page (clicks, focus, screen-readers all skip), but
    // window-level keydown listeners still fire because keydown bubbles
    // through the focused dialog. Bail here so app-wide chords (Cmd+B,
    // Cmd+Alt+←/→, Esc ladder, tree-nav letters, etc.) don't run
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
      // tree highlight as a side effect of closing a menu. Every popover
      // claims the menu slot at open, so the slot is the one authority.
      if (menuSlotHeld()) return;
      // Escape mid-IME-composition just cancels the composition — never
      // step the ladder on it.
      if (event.isComposing) return;
      // Search view: Esc from the bar or the results steps straight out
      // to the browse view — the bar is reached only with ⌘K (or a click),
      // never on the way out. The query is never cleared here — × is the
      // only clear, and it isn't an exit.
      if (searchViewOpen) {
        if (inSearchInput || activePane === 'files') {
          event.preventDefault();
          searchViewOpen = false;
          (document.activeElement as HTMLElement | null)?.blur?.();
          // The browse view isn't in the DOM until Svelte flushes the
          // swap; focusFileRegion queries rows / the SystemsView binding.
          void tick().then(() => focusFileRegion());
        }
        // An active dock pane keeps its own Esc semantics (its window
        // handler clears the highlight and releases the arrows); the next
        // Esc leaves the search view.
        return;
      }
      // The bar outside the search view. A / filter goes first, the way an
      // @-word does; then focus goes back to the rows the bar sits above.
      if (inSearchInput) {
        event.preventDefault();
        if (nameFilter !== null) {
          searchQuery = '';
          return;
        }
        (target as HTMLInputElement).blur();
        focusFileRegion();
        return;
      }
      // Rows under a / filter funnel to the bar — the filter is edited,
      // and ended, there.
      if (nameFilter !== null && activePane === 'files' && !inAnyInput) {
        event.preventDefault();
        headerComponent?.focus();
        return;
      }
      if (focusedFilePath) { focusedFilePath = null; }
    }

    const meta = event.metaKey || event.ctrlKey;
    const lk = event.key.toLowerCase();

    // Cmd/Ctrl+K: focus the search input from anywhere in the app, query
    // selected so typing replaces it and → edits it. Not ⌘F — that's the
    // browser/OS find-in-page chord, and here it opens the Filters panel
    // instead (below). ⌘K is the command-bar convention.
    if (meta && !event.shiftKey && lk === 'k') {
      event.preventDefault();
      headerComponent?.focusAndSelect();
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

    // Cmd/Ctrl + digit. Bare: play only collection N (again stops it) —
    // track select, the way a DAW numbers its tracks, and live from
    // anywhere, search input included. ⇧: add N to the mix or take it out.
    const digit = selectedFolder ? digitChord(event) : null;
    if (digit) {
      event.preventDefault();
      if (digit.alt) return;
      const name = collectionSlots[digit.digit - 1];
      if (!name) return;
      if (digit.shift) togglePlayCollection(name);
      else playOnlyCollection(name);
      return;
    }

    // Tab: flip between the tree and the systems view — Ableton's
    // Session/Arrangement key, for the same two-views-of-one-set job. Only
    // in the browse view and only off text fields and menus, so Tab keeps
    // its meaning wherever there is something to type into or pick from.
    // The search bar is the exception: its Tab stops (× and the dock
    // behind it) are the mouse's, so there Tab flips too — out of the
    // search view, as either half of the view switch does.
    // ⇧Tab flips too: with two views, direction means nothing.
    const tabFlips = inSearchInput ? !event.isComposing : !searchViewOpen && !inAnyInput;
    if (event.key === 'Tab' && !meta && !event.altKey && selectedFolder && tabFlips
        && !contextMenu && !renamingFilePath && !menuSlotHeld()) {
      event.preventDefault();
      void setViewMode(viewMode === 'tree' ? 'systems' : 'tree');
      return;
    }

    // Cmd/Ctrl+Alt+←/→: jump keyboard focus between the collections panel
    // and the file pane (tree, systems, or the search results). Restores
    // the last-focused row in the target region if it's still visible,
    // else lands on the first visible row. During search the chords keep
    // working — the console must stay reachable while the mix is audible —
    // but ← first blurs the input or result row so the dock's window
    // handlers stop yielding to it, and → means "back to the results".
    if (meta && event.altKey && !event.shiftKey && selectedFolder
        && (event.key === 'ArrowLeft' || event.key === 'ArrowRight')) {
      event.preventDefault();
      if (event.key === 'ArrowLeft') {
        if (searchViewOpen) (document.activeElement as HTMLElement | null)?.blur?.();
        void focusDockRegion();
      } else if (searchViewOpen) {
        setActivePane('files');
        if (searchResults.length > 0) searchResultsComponent?.focusRow(selectedResultIndex);
        else headerComponent?.focus();
      } else {
        focusFileRegion();
      }
      return;
    }

    // Cmd+Alt+↑/↓: move between the two panels stacked in the left dock.
    if (meta && event.altKey && !event.shiftKey && selectedFolder
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
    // (same handler the "Sync" banner button calls). Standalone chord
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
    // has data to return — matches the context menu's gating. In the
    // search view the selection is the focused thing — the inspector's
    // file is what "info" can only mean there.
    if (meta && !event.shiftKey && lk === 'i' && !inAnyInput) {
      const infoPath = searchViewOpen
        ? searchResults[selectedResultIndex]?.source
        : focusedFilePath;
      if (infoPath && indexedPaths.has(infoPath)) {
        event.preventDefault();
        statsModalPath = infoPath;
        return;
      }
    }

    // Cmd/Ctrl+F: toggle the Filters panel (docked below the collections panel
    // in the left pane). F for filter, on the chord everything else spends on
    // find — the panel is where you narrow what a search covers, so the two
    // read as a pair with search on ⌘K. It was ⌘⇧F, and before that ⌘E, which
    // meant nothing mnemonically and collided twice — macOS binds Cmd+E to
    // "Use Selection for Find" in any text field, and Finder binds it to Eject.
    if (meta && !event.shiftKey && lk === 'f' && selectedFolder) {
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
    // when an input has focus.
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

    // `?` — show keyboard shortcuts overlay. Match on event.key (the
    // produced character) rather than Shift+/ so any layout that emits
    // `?` from a different physical key still triggers. Bare chord, gated
    // out of inputs so typing a literal `?` works as expected.
    if (event.key === '?' && !meta && !event.altKey && !inAnyInput) {
      event.preventDefault();
      showHelpOverlay = true;
      return;
    }

    // Cmd/Ctrl+/: the same sheet (Docs, Slack, Linear). Live inside inputs
    // too — the one way to reach the sheet from the search bar, where a
    // bare `?` has to type.
    if (meta && event.key === '/' && !event.altKey) {
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
      // Same gate as the scope bar's switch: nothing to bypass, nothing
      // to latch — a lit BYPASS lamp over an empty console would be a
      // no-op wearing a mode light. Bypassed always passes so the key
      // can throw the switch back.
      if (!scopeBypassed && !scopeNarrowingEngaged) return;
      holdLatch.press('b', toggleScopeBypass);
      return;
    }

    // ── Tree-row navigation ─────────────────────────────────────────────
    // Active when a library is loaded, the search view is closed, no
    // menu/rename is open. Every popover claims the menu slot at open,
    // so the slot is the state-based answer to "is a menu open?" — no
    // DOM query, no race with Svelte's microtask flush.
    const competingMenuOpen = menuSlotHeld();

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

    // ↓ from the bar outside the search view drops into the browse view's
    // rows — the same move that takes the search view into its results.
    // Under a / filter ↵ does too (there is nothing to submit), and both
    // land on the first match.
    if (inSearchInput && !searchViewOpen && selectedFolder
        && (event.key === 'ArrowDown' || (event.key === 'Enter' && nameFilter !== null))
        && !meta && !event.altKey && !event.shiftKey && !event.isComposing
        && activePane === 'files') {
      event.preventDefault();
      (target as HTMLInputElement).blur();
      if (nameFilter !== null) focusFirstMatch();
      else focusFileRegion();
      return;
    }

    // Gate on the view being on screen, not on the committed query —
    // after exiting, query and results persist while tree/systems is
    // visible, and the list's keys must not act on rows that aren't rendered.
    if (!searchViewOpen || searchResults.length === 0) return;

    const inList = target?.closest('.search-results') !== null;
    const bareLetter = !meta && !event.shiftKey && !event.altKey;

    // While a dock pane holds the arrows (⌘⌥← mid-search), the list's
    // keys stand down — the pane's window handler owns the keyboard
    // until Esc, ⌘⌥→, or a click on the search side hands it back.
    if (activePane !== 'files') return;

    // Enter in the bar lands focus on the first result (handleSearchSubmit);
    // the arrows never cross between bar and list — ↑ on the first row
    // stays put. Arrow nav within the list moves both selection and focus
    // together (j/k ride along). Enter or ⌘O opens; Escape is handled by
    // the ladder above.
    const isDown = inList && (event.key === 'ArrowDown' || (bareLetter && lk === 'j'));
    const isUp = inList && (event.key === 'ArrowUp' || (bareLetter && lk === 'k'));
    const edge = inList ? jumpEdge(event) : null;
    if (edge) {
      event.preventDefault();
      selectedResultIndex = edge === 'first' ? 0 : searchResults.length - 1;
      searchResultsComponent?.focusRow(selectedResultIndex);
    } else if (isDown) {
      event.preventDefault();
      selectedResultIndex = Math.min(searchResults.length - 1, selectedResultIndex + 1);
      searchResultsComponent?.focusRow(selectedResultIndex);
    } else if (isUp) {
      event.preventDefault();
      if (selectedResultIndex > 0) {
        selectedResultIndex -= 1;
        searchResultsComponent?.focusRow(selectedResultIndex);
      }
    } else if (event.key === 'Enter' && inList) {
      event.preventDefault();
      const sel = searchResults[selectedResultIndex];
      if (sel) handleOpenResult(sel.source, sel.filename, sel.page_start);
    } else if (meta && !event.shiftKey && !event.altKey && lk === 'o') {
      // ⌘O opens the selection from anywhere in the search view — the
      // input included — matching the browse views' "open the focused
      // thing" muscle memory.
      event.preventDefault();
      const sel = searchResults[selectedResultIndex];
      if (sel) handleOpenResult(sel.source, sel.filename, sel.page_start);
    } else if (bareLetter && inList && (lk === 's' || lk === 'm')) {
      // Bare S/M act on the selected result's file — the same
      // row-you're-on grammar the tree and systems rows follow, on the
      // same hold latch, so a held M peeks the search without the book
      // and release restores it.
      event.preventDefault();
      if (event.repeat) return;
      const sel = searchResults[selectedResultIndex];
      if (sel) {
        const item = resultToFileItem(sel);
        holdLatch.press(lk, () =>
          lk === 's' ? toggleScopeSolo(item) : toggleScopeMute(item),
        );
      }
    } else if (bareLetter && inList && lk === 'g') {
      // G brings the preview back to the match after reading around it.
      event.preventDefault();
      searchInspectorComponent?.returnToMatch();
    } else if (bareLetter && inList && lk === 'x' && armState) {
      // X files the selected result into the armed collection — "tick
      // the box you can see", the key both browse views spend on it.
      event.preventDefault();
      const sel = searchResults[selectedResultIndex];
      if (sel) {
        if (armState.paths.has(sel.source)) curationRemove([sel.source]);
        else curationAdd([sel.source]);
      }
    }
  }

  // A search hit resolved to the row shape every file affordance already
  // takes — `source` is the index's absolute path, so the context menu,
  // the drag payload, and the scope toggles all work on it unchanged.
  function resultToFileItem(result: SearchResultItem): FileItem {
    return { name: result.filename, path: result.source, is_dir: false, children: null };
  }

  function handleResultContextMenu(event: MouseEvent, result: SearchResultItem) {
    handleContextMenu(event, resultToFileItem(result));
    if (!contextMenu) return;
    contextMenu = { ...contextMenu, result, sendTargets: 'loading' };
    sendTargets()
      .then((targets) => {
        if (contextMenu?.result === result) contextMenu = { ...contextMenu, sendTargets: targets };
      })
      .catch(() => {
        if (contextMenu?.result === result) contextMenu = { ...contextMenu, sendTargets: { campaign: null, tracks: [] } };
      });
  }

  async function handleSendToCommand(track: string | null) {
    const result = contextMenu?.result;
    contextMenu = null;
    if (!result) return;
    try {
      const sent = await sendToCommand(result, track);
      const name = sent.path.split('/').pop()?.replace(/\.md$/, '') ?? sent.path;
      jobNotification.show({ type: 'success', message: `Sent to Command: ${name} in ${sent.campaign} › ${track ?? 'Shelf'}`, duration: 4000 });
    } catch (e) {
      jobNotification.show({ type: 'error', message: `Couldn't send to Command: ${e}`, duration: 5000 });
    }
  }

  // ⌘O on a collections-panel child row.
  async function openCollectionFile(path: string) {
    try {
      await openPath(path);
    } catch (e) {
      jobNotification.show({ type: 'error', message: `Failed to open file: ${String(e)}`, duration: 4000 });
    }
  }

  function handleContextMenu(event: MouseEvent, item: FileItem, initialSubmenu: 'collection' | null = null) {
    // A right-click on another row while the menu is up has to mount a new
    // menu, not re-point the open one: ContextMenu places itself and resets
    // its cursor only as it mounts, so a reused menu stayed at the first
    // row's spot while acting on the second.
    if (contextMenu) {
      contextMenu = null;
      flushSync();
    }
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

  // Both leave the menu standing, like the Game system rows: filing into
  // several collections is one errand, and the pip is the receipt. The
  // membership props are computed from `collections`, so loadCollections()
  // flips the row under the cursor. Everything else in the menu still
  // closes on click — these two are the only repeatable actions.
  function handleContextAddToCollection(name: string) {
    if (!contextMenu) return;
    addToCollection(name, contextMenu.item);
  }

  function handleContextRemoveFromCollection(name: string) {
    if (!contextMenu) return;
    removeFromCollection(name, contextMenu.item);
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

  // Path solo/mute migration for renames — like renamePathKeys, the entry
  // keyed exactly at the renamed path moves too, and it also picks up the
  // new basename as its label. Descendant entries (folder rename only) keep
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
        selectedPaths = renamePathKeys(selectedPaths, oldPath, newPath);
        syncedPaths = renamePathKeys(syncedPaths, oldPath, newPath);
        expandedPaths = renamePathKeys(expandedPaths, oldPath, newPath);
        if (focusedFilePath !== null && (focusedFilePath === oldPath || focusedFilePath.startsWith(oldPath + '/'))) {
          focusedFilePath = newPath + focusedFilePath.slice(oldPath.length);
        }
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
      // Hidden flags follow the rename, or the renamed folder or file
      // reappears and its old path stays in settings for good.
      if ([...hiddenPaths].some((p) => p === oldPath || p.startsWith(oldPath + '/'))) {
        hiddenPaths = renamePathKeys(hiddenPaths, oldPath, newPath);
        persistHidden();
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
      // The sidecar moved the path in every collection holding it: reload,
      // or the book's gems vanish and the next membership write sends the
      // old path back.
      await loadCollections();
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
      const visible = visibleFileSpan(visibleTreeRows, lastCollectClickedPath, item.path);
      if (visible !== null) {
        const span = visible.filter((p) => indexedPaths.has(p));
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
    // The name and the file count are both in hand, so the prompt states them
    // as figures rather than folding them into a sentence. The Files row is a
    // reassurance, not damage — the books are freed to Loose, not deleted —
    // so it is marked `unchanged` and renders calm. A collection absent from
    // `collections` (deleted from another surface mid-flight) drops the row
    // rather than reading `undefined`.
    const info = collections[name];
    const confirmed = await confirmPrompt.request({
      title: 'Delete collection',
      rows: [
        { label: 'Track', value: name },
        ...(info
          ? [
              { label: 'Files', value: String(info.file_count), to: 'Loose', unchanged: true },
            ]
          : []),
      ],
      message: 'The track goes; its books stay in your library.',
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
  // Resolves whether the rename took, so the panel can carry the row's
  // expansion over.
  async function renameCollection(name: string, newName: string): Promise<boolean> {
    if (newName === name) return false;
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
      // The keyboard's place follows too, in the same tick: a ring on a
      // name the map no longer carries is a ring on nothing.
      focusedCollectionName = renameNavKey(focusedCollectionName, name, newName);
      lastFocusedCollectionName = renameNavKey(lastFocusedCollectionName, name, newName);
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
      return true;
    } catch (e) {
      jobNotification.show({
        type: 'error',
        message: `Rename failed: ${String(e)}`,
        duration: 5000,
      });
      return false;
    }
  }

  // Pigment change from the panel's context menu — gems, chips, and
  // index cells all derive from `collections`, so a reload updates them.
  async function setCollectionColor(name: string, color: string | null) {
    try {
      await invoke('update_collection', { name, color: color ?? '' });
      await loadCollections();
    } catch (e) {
      jobNotification.show({
        type: 'error',
        message: `Could not set gem: ${String(e)}`,
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

  async function refreshIndexAndCollections() {
    await refreshIndexStatus();
    // Get armed writes on the wire before the fetch, so loadCollections
    // has nothing local left to preserve.
    await armCommitter.flush();
    await loadCollections();
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
        buildResultMessage: syncSummary,
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
        buildResultMessage: reindexSummary,
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
        startMessage: 'Clearing index...',
        errorPrefix: 'Delete failed',
        streamsProgress: false,
        buildResultMessage: clearSummary,
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


<main class="app-layout" class:motion-ready={motionReady}>
  <Header
    bind:this={headerComponent}
    bind:searchQuery
    disabled={!selectedFolder}
    panelOpen={collectionsPanelOpen}
    panelToggleVisible={!!selectedFolder}
    {filterPanelOpen}
    onToggleFilterPanel={toggleFilterPanel}
    {collectionsEngaged}
    {filtersEngaged}
    onSubmit={handleSearchSubmit}
    onDebouncedChange={handleSearchDebounced}
    onClear={handleSearchClear}
    onFocus={handleSearchFocus}
    onQuery={handleSearchQuery}
    onTogglePanel={togglePanel}
    onCollapseAll={collapseAll}
    viewToggleVisible={!!selectedFolder}
    {searchViewOpen}
    {viewMode}
    onSetViewMode={setViewMode}
    onMentionChange={(q) => (mentionQuery = q)}
    onMentionKey={handleMentionKey}
    {windowKey}
  />

  {#if selectedFolder}
    <div class="workspace">
      {#if collectionsPanelShown || filterPanelOpen}
        <!-- Left dock: collections on top, filters below. Each panel
             scrolls its own rows; the dock owns the width, and each
             panel's nameplate divides it from the one above.

             Both panes stay keyboard-live while the search view is open —
             the console must stay reachable while the mix is audible.
             Arbitration is by activePane alone: entering search (and any
             click on the search side) points it at 'files', the search
             block yields whenever a dock pane holds it, and ⌘⌥←/→ move
             between the two sides. -->
        <div class="left-dock">
          {#if collectionsPanelShown}
            <CollectionsPanel
              bind:this={collectionsPanelComponent}
              {collections}
              armedName={armedCollection}
              onArm={armCollection}
              onDropPaths={dropPathsOnCollection}
              onDropNewCollection={dropPathsOnNewCollection}
              onRemoveFile={removeFileFromCollection}
              onOpenFile={openCollectionFile}
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
              active={active && activePane === 'collections'}
              onActivate={() => pointAtEmpty('collections')}
              onFocusCollection={setFocusedCollectionName}
              pickQuery={mentionQuery}
              {pickMatches}
              {pickCursor}
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
              canReset={scopeConsoleEngaged}
              focusedRow={focusedFilterRow}
              lastFocusedRow={lastFocusedFilterRow}
              active={active && activePane === 'filters'}
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
        {#snippet scopeBar()}
          <SearchScopeBar
            {scopeBypassed}
            onToggleBypass={toggleScopeBypass}
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
        {/snippet}
        {#if searchViewOpen}
          <!-- In search mode the bar splits at the list/inspector seam: the
               scope readout over the list, the inspector's plate — the
               selected section's path and [open] — over the text. Both
               columns size as the split's panes do, so the seam runs
               straight down. -->
          <div class="search-plates">
            <div class="search-list-pane">{@render scopeBar()}</div>
            <div class="search-inspector-pane">
              <InspectorPlate result={selectedResult} onOpenResult={handleOpenResult} />
            </div>
          </div>
        {:else}
          {@render scopeBar()}
        {/if}
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
                dimWeak={dimWeakResults}
                onSelect={(i) => { selectedResultIndex = i; setActivePane('files'); }}
                onLoadMore={loadMoreResults}
                onOpenResult={handleOpenResult}
                onBeginDrag={beginPathDrag}
                onContextMenu={handleResultContextMenu}
                curating={armState !== null}
                collectionPaths={armState?.paths ?? EMPTY_PATHS}
                onCollectionAdd={curationAdd}
                onCollectionRemove={curationRemove}
                {knownSystems}
                gameSystemMap={effectiveGameSystemMap}
                onSetGameSystems={handleSetGameSystems}
              />
            </div>
            <div class="search-inspector-pane">
              <SearchInspector
                bind:this={searchInspectorComponent}
                result={selectedResult}
                query={committedQuery}
                onOpenResult={handleOpenResult}
              />
            </div>
          </div>
        {:else if viewMode === 'systems'}
          <SystemsView
            bind:this={systemsViewComponent}
            entries={indexedEntries}
            {displayPaths}
            filterWords={filterWordList}
            {scopeBrightPaths}
            {hideOutOfScope}
            {scopeBypassed}
            excludedSystems={filterExcludedSystems}
            {soloedSystems}
            onToggleSystemFilter={toggleSystemFilter}
            onToggleSystemSolo={toggleSystemSolo}
            {soloedScopePaths}
            {mutedScopePaths}
            onToggleScopeSolo={toggleScopeSolo}
            onToggleScopeMute={toggleScopeMute}
            {hiddenPaths}
            {showHidden}
            libraryRoot={selectedFolder}
            {focusedFilePath}
            lastFocusedPath={lastFocusedFilePath}
            active={active && activePane === 'files'}
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
          {:else if treeFilter && treeFilter.show.size === 0}
            <div class="scope-empty">No folder or file name matches.</div>
          {/if}
          {#each treeRoots as file (file.path)}
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
              displayPaths={treeDisplayPaths}
              filterWords={filterWordList}
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
      onSetGameSystems={(tags) => handleSetGameSystems(contextMenu!.item.path, tags)}
      fullyContainingCollections={collectionsFullyContaining(contextMenu.item.path, contextMenu.item.is_dir, collections, indexedPaths)}
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
      sendTargets={contextMenu.result ? (contextMenu.sendTargets ?? 'loading') : null}
      onSendToCommand={handleSendToCommand}
      canRename={!searchViewOpen}
      onClose={() => { contextMenu = null; }}
    />
  {/if}

  {#if statsModalPath}
    <DocumentStatsModal
      path={statsModalPath}
      onClose={() => { statsModalPath = null; }}
    />
  {/if}

  <StatusBar
    {selectedFolder}
    {sidecarConnected}
    embedderRunning={ollamaRunning}
    embedderReady={ollamaModelReady}
    {mcpConnected}
    {mcpActive}
    selectedCount={selectedPaths.size}
    indexedCount={(indexStatus?.summary?.up_to_date ?? 0) + (indexStatus?.summary?.update ?? 0) + (indexStatus?.summary?.remove ?? 0)}
    {gameSystemCount}
    {topGameSystem}
    {totalChunks}
    {storageBytes}
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
  outdatedFileCount={indexStatus?.summary?.outdated ?? 0}
  {totalFilesFound}
  {totalChunks}
  {storageBytes}
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
  onReindexAll={handleReindexAll}
  onDeleteIndex={handleDeleteIndex}
  onSyncPreferencesChange={handleSyncPreferencesChange}
  {dimWeakResults}
  onDimWeakResultsChange={handleDimWeakResultsChange}
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
    height: 100%;
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
    /* 4px: the seam between the dock's plates and the scope plate, which
       share a grey and sit side by side, needs more than a hairline. */
    border-right: 4px solid var(--border-subtle);
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
  /* The scope bar is a nameplate, and a plate runs edge to edge like the
     dock's; out of search mode the area's side padding would inset it, so
     it bleeds back over that padding. Search mode has none to undo. */
  .file-tree-area:not(.search-mode) > :global(.scope-bar) {
    margin-inline: -0.75rem;
  }

  .file-tree-area.search-mode {
    display: flex;
    flex-direction: column;
    overflow: hidden;
    padding: 0;
  }

  .search-plates {
    flex-shrink: 0;
    display: flex;
  }

  /* The scope bar fills its column's height, so a chip row that wraps
     grows both plates together. */
  .search-plates > .search-list-pane > :global(.scope-bar) {
    flex: 1;
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
    background: color-mix(in srgb, var(--text-danger) 10%, transparent);
    color: var(--text-danger);
    border-top: 1px solid color-mix(in srgb, var(--text-danger) 30%, transparent);
    font-size: 0.85rem;
    flex-shrink: 0;
  }
</style>
