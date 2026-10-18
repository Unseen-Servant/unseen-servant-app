<script lang="ts">
  import type { BackgroundCheckInterval, BucketPolicy, SyncPreferences } from './types';
  import { BACKGROUND_CHECK_OPTIONS, DEFAULT_SYNC_PREFERENCES } from './types';
  import { FOLDER, FOLDER_OPEN } from '../ui/iconPaths';
  import ActionButton from '../ui/ActionButton.svelte';
  import { confirmPrompt } from '../shell/confirmStore';

  export let selectedFolder: string = '';
  export let indexedFileCount: number = 0;
  export let outdatedFileCount: number = 0;
  export let totalFilesFound: number = 0;
  export let totalChunks: number = 0;
  export let storageBytes: number = 0;
  export let gameSystemCount: number = 0;
  export let isSyncing: boolean = false;
  export let syncPreferences: SyncPreferences = { ...DEFAULT_SYNC_PREFERENCES };
  export let dataDir: string = '';
  export let lastSyncTime: Date | null = null;
  export let onSelectFolder: () => void = () => {};
  export let onDeselectFolder: () => void = () => {};
  export let onReindexAll: () => void = () => {};
  export let onDeleteIndex: () => void = () => {};
  export let onSyncPreferencesChange: (partial: Partial<SyncPreferences>) => void = () => {};
  export let onOpenDataDir: () => void = () => {};
  export let onSync: () => void = () => {};

  type PolicyKey = 'diskEventsPolicy' | 'selectionPolicy' | 'deselectionPolicy' | 'modificationPolicy';
  const policyGroups: Array<{
    key: PolicyKey;
    title: string;
    desc: string;
  }> = [
    {
      key: 'diskEventsPolicy',
      title: 'Renames, missing files, and stale selections',
      desc: 'Same content, but the filename or location changed — or the file is no longer there.',
    },
    {
      key: 'selectionPolicy',
      title: 'New files you select',
      desc: 'Embedding work; defaults to asking so you can batch.',
    },
    {
      key: 'deselectionPolicy',
      title: 'Files you deselect',
      desc: 'Drops chunks. Re-selecting later requires re-embedding.',
    },
    {
      key: 'modificationPolicy',
      title: 'Files modified on disk',
      desc: 'Same filename, but the contents are different — needs re-indexing.',
    },
  ];

  function setPolicy(key: PolicyKey, value: BucketPolicy) {
    onSyncPreferencesChange({ [key]: value } as Partial<SyncPreferences>);
  }

  function setCheckInterval(value: BackgroundCheckInterval) {
    onSyncPreferencesChange({ backgroundCheckInterval: value });
  }

  // Both of these used to arm in place and fire on a second click — the app's
  // one surviving second idiom for "are you sure". They raise a confirmation
  // unit now, like every other destructive action, and the armed label that
  // named the damage ("Reprocess 128 files?") becomes the prompt's readout
  // rows, which say the same thing with the figures spelled out. This is the
  // one surface where those figures are genuinely dramatic, which is what
  // settled the design's open decision 1.

  async function handleReindexClick() {
    if (isSyncing || indexedFileCount === 0) return;
    // No `danger`: re-indexing rebuilds and destroys nothing, so the prompt is
    // an activation — purple, lit, Enter commits. The zone names the blast
    // radius; the flag names the kind of change.
    //
    // Bare counts, not "128 files": the label column already says FILES, and
    // the delete prompt below states the same figure the same way. A readout
    // column holds figures; the unit belongs to the label.
    if (!(await confirmPrompt.request({
      title: 'Re-index all files',
      rows: [
        { label: 'Files', value: String(indexedFileCount), to: 'reprocessed' },
        { label: 'Chunks', value: totalChunks.toLocaleString(), to: 'rebuilt' },
      ],
      message: 'Every file is re-extracted and re-embedded. Nothing is deleted.',
      confirmLabel: 'Re-index all',
    }))) return;
    onReindexAll();
  }

  async function handleDeleteClick() {
    if (isSyncing || indexedFileCount === 0) return;
    // A removal, and the one prompt in the app whose readout is the whole
    // argument: three figures going to zero, and a fourth that does not move.
    if (!(await confirmPrompt.request({
      title: 'Delete the index',
      rows: [
        { label: 'Files', value: String(indexedFileCount), to: '0' },
        { label: 'Chunks', value: totalChunks.toLocaleString(), to: '0' },
        // Dropped rather than shown as "0 B → 0 B" when the store reports
        // nothing: storageBytes can be 0 with files still indexed, and a row
        // whose before and after are the same figure states nothing. The
        // Database section guards the same value the same way.
        ...(storageBytes > 0
          ? [{ label: 'Storage', value: formatSize(storageBytes), to: '0 B' }]
          : []),
        { label: 'PDFs', value: String(indexedFileCount), to: 'untouched', unchanged: true },
      ],
      message: 'Your library folder is not touched. The index rebuilds on the next sync.',
      confirmLabel: 'Delete index',
      danger: true,
    }))) return;
    onDeleteIndex();
  }

  function formatSize(bytes: number): string {
    if (bytes >= 1_073_741_824) return (bytes / 1_073_741_824).toFixed(1) + ' GB';
    if (bytes >= 1_048_576) return (bytes / 1_048_576).toFixed(1) + ' MB';
    if (bytes >= 1_024) return (bytes / 1_024).toFixed(0) + ' KB';
    return bytes + ' B';
  }

  $: coveragePct = totalFilesFound > 0
    ? Math.min(100, (indexedFileCount / totalFilesFound) * 100)
    : 0;

  function formatRelative(date: Date | null): string {
    if (!date) return 'Never';
    const seconds = Math.floor((Date.now() - date.getTime()) / 1000);
    if (seconds < 30) return 'just now';
    if (seconds < 60) return `${seconds}s ago`;
    const minutes = Math.floor(seconds / 60);
    if (minutes === 1) return '1 minute ago';
    if (minutes < 60) return `${minutes} minutes ago`;
    const hours = Math.floor(minutes / 60);
    if (hours === 1) return '1 hour ago';
    if (hours < 24) return `${hours} hours ago`;
    const days = Math.floor(hours / 24);
    if (days === 1) return '1 day ago';
    return `${days} days ago`;
  }

  $: lastSyncRelative = formatRelative(lastSyncTime);
  $: lastSyncAbsolute = lastSyncTime ? lastSyncTime.toLocaleString() : '';
</script>

<div class="library-settings">
  <section class="field">
    <div class="field-head">
      <h3 class="field-title section-title">Library stats</h3>
    </div>

    {#if indexedFileCount > 0 || totalFilesFound > 0}
      <div class="stat-block" role="group" aria-label="Library stats">
        <div class="stat-cell">
          <div class="readout-label">INDEXED</div>
          <div class="stat-value">
            {indexedFileCount.toLocaleString()}{#if totalFilesFound > 0}&nbsp;<span class="stat-muted">/&nbsp;{totalFilesFound.toLocaleString()}</span>&nbsp;<span class="stat-pct">{coveragePct.toFixed(1)}%</span>{/if}
          </div>
        </div>
        <div class="stat-cell">
          <div class="readout-label">CHUNKS</div>
          <div class="stat-value">{totalChunks.toLocaleString()}</div>
        </div>
        <div class="stat-cell">
          <div class="readout-label">SYS</div>
          <div class="stat-value">{gameSystemCount}</div>
        </div>
      </div>
    {:else}
      <p class="field-desc">No files indexed yet.</p>
    {/if}
  </section>

  <section class="field">
    <div class="field-head">
      <h3 class="field-title section-title">Library folder</h3>
      <p class="field-desc">
        Legend Lore indexes PDFs from this folder. Changing the folder doesn't
        remove anything that's already indexed — use Re-index all below to rebuild.
      </p>
    </div>

    <div class="path-row">
      <input
        type="text"
        class="path-input"
        readonly
        value={selectedFolder}
        placeholder="No folder selected"
        title={selectedFolder}
      />
      <button
        type="button"
        class="btn-icon"
        on:click={onSelectFolder}
        disabled={isSyncing}
        title="Change library folder"
        aria-label="Change library folder"
      >
        <svg class="btn-icon-svg" viewBox="0 0 640 640" fill="currentColor" aria-hidden="true">
          <path class="folder-shut" d={FOLDER}/>
          <path class="folder-opened" d={FOLDER_OPEN}/>
        </svg>
      </button>
    </div>

    {#if selectedFolder}
      <div class="meta-row">
        <button
          type="button"
          class="btn-link"
          on:click={onDeselectFolder}
          disabled={isSyncing}
          title="Clear the library folder and return to the Getting Started screen"
        >
          deselect folder
        </button>
      </div>
    {/if}
  </section>

  <section class="field">
    <div class="field-head">
      <h3 class="field-title section-title">Sync behavior</h3>
      <p class="field-desc">
        How Legend Lore keeps the index in sync with your library folder.
      </p>
    </div>

    <div class="setting-row">
      <div class="setting-row-head">
        <div class="setting-row-title">Check for changes</div>
        <div class="setting-row-desc">
          How often to scan the library folder. "Never" means the index only
          updates when you click Sync.
        </div>
      </div>
      <select
        class="setting-select"
        value={syncPreferences.backgroundCheckInterval}
        on:change={(e) => setCheckInterval(Number(e.currentTarget.value) as BackgroundCheckInterval)}
      >
        {#each BACKGROUND_CHECK_OPTIONS as opt}
          <option value={opt.value}>{opt.label}</option>
        {/each}
      </select>
    </div>

    <fieldset class="policy-group" disabled={syncPreferences.backgroundCheckInterval === 0}>
      <legend class="policy-legend readout-label">When changes are detected</legend>

      {#each policyGroups as group}
        <div class="setting-row">
          <div class="setting-row-head">
            <div class="setting-row-title">{group.title}</div>
            <div class="setting-row-desc">{group.desc}</div>
          </div>
          <select
            class="setting-select"
            value={syncPreferences[group.key]}
            on:change={(e) => setPolicy(group.key, e.currentTarget.value as BucketPolicy)}
          >
            <option value="silent">Apply silently</option>
            <option value="ask">Show a notification</option>
          </select>
        </div>
      {/each}
    </fieldset>

    <div class="meta-row">
      <span class="meta-label readout-label">Last checked</span>
      <span class="meta-value" title={lastSyncAbsolute}>
        {isSyncing ? 'Syncing…' : lastSyncRelative}
      </span>
      <button
        type="button"
        class="btn-link"
        on:click={onSync}
        disabled={isSyncing}
        title="Check the library folder for changes"
      >
        sync
      </button>
    </div>
  </section>

  <section class="field">
    <div class="field-head">
      <h3 class="field-title section-title">Database</h3>
      <p class="field-desc">
        Where the index is stored on disk, and how much space it takes.
      </p>
    </div>

    <div class="path-row">
      <input
        type="text"
        class="path-input"
        readonly
        value={dataDir}
        placeholder="Resolving…"
        title={dataDir}
      />
      <button
        type="button"
        class="btn-icon"
        on:click={onOpenDataDir}
        disabled={!dataDir}
        title="Open database folder"
        aria-label="Open database folder"
      >
        <svg class="btn-icon-svg" viewBox="0 0 640 640" fill="currentColor" aria-hidden="true">
          <path class="folder-shut" d={FOLDER}/>
          <path class="folder-opened" d={FOLDER_OPEN}/>
        </svg>
      </button>
    </div>

    <div class="meta-row">
      <span class="meta-label readout-label">Storage</span>
      <span class="meta-value">
        {storageBytes > 0 ? formatSize(storageBytes) : '—'}
      </span>
    </div>
  </section>

  <!-- A bay, not a panel of its own: the same tinted well the game-system unit
       uses for its destructive secondaries. Neither control commits here —
       both raise a prompt — so both wear bracketed text and no switch face. A
       face carries a key, and nothing on this surface implements one. See the
       design's "A face is a promise, and only a commit may make it".
       The two differ in hue because they differ in kind: re-indexing is an
       activation and takes the confirm accent, deleting is a removal and takes
       danger. Only the frame and the caption say "this bay is where the heavy
       levers live". -->
  <section class="modal-bay" aria-label="Danger zone">
    <span class="ledger-label danger-caption">Danger zone</span>
    <div class="modal-well danger-bay">
      <div class="modal-well-row action-row">
        <span class="row-text">
          <span class="row-title">Re-index all files</span>
          Re-extracts and re-embeds every file in your index. Use after the
          extractor has been upgraded, or if search results look stale.
          {#if outdatedFileCount > 0}
            <span class="row-note">
              {outdatedFileCount} {outdatedFileCount === 1 ? 'file was' : 'files were'} indexed
              with an older pipeline — re-index to pick up the current one.
            </span>
          {/if}
        </span>
        <ActionButton
          label={isSyncing ? 'sync in progress…' : 're-index all'}
          onClick={handleReindexClick}
          disabled={isSyncing || indexedFileCount === 0}
        />
      </div>
      <div class="modal-well-row action-row">
        <span class="row-text">
          <span class="row-title">Delete the index</span>
          Removes every chunk and embedding. Your PDFs are untouched; the
          index is rebuilt from scratch on the next sync.
        </span>
        <ActionButton
          danger
          label="delete index"
          onClick={handleDeleteClick}
          disabled={isSyncing || indexedFileCount === 0}
        />
      </div>
    </div>
  </section>
</div>

<style>
  .library-settings {
    padding: var(--modal-pad);
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
  }

  .field-title {
    margin: 0 0 0.35rem;
  }

  .field-desc {
    font-family: var(--font-body);
    font-size: 0.85rem;
    color: var(--text-secondary);
    line-height: 1.45;
    margin: 0;
  }

  .path-row {
    display: flex;
    gap: 0.5rem;
    align-items: center;
  }

  .path-input {
    flex: 1;
    min-width: 0;
    font-family: var(--font-mono);
    font-size: 0.7rem;
    padding: 0.4rem 0.6rem;
    background: var(--bg-focused);
    color: var(--text-primary);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
  }
  .path-input:focus {
    outline: 1px solid var(--text-accent);
    outline-offset: -1px;
  }
  .path-input::placeholder {
    color: var(--text-secondary);
    font-style: italic;
  }

  .stat-block {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0.5rem;
    padding: 0.5rem 0.25rem;
    border-top: 1px solid var(--border-subtle);
    border-bottom: 1px solid var(--border-subtle);
  }

  .stat-cell {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.1rem;
  }

  .stat-value {
    font-family: var(--font-mono);
    font-size: 0.7rem;
    color: var(--text-primary);
    font-variant-numeric: tabular-nums;
  }

  .stat-muted {
    color: var(--text-secondary);
  }

  .stat-pct {
    color: var(--text-accent);
  }
  .stat-pct::before,
  .stat-pct::after {
    color: var(--text-secondary);
  }
  .stat-pct::before {
    content: '[';
    margin-right: 0.15rem;
  }
  .stat-pct::after {
    content: ']';
    margin-left: 0.15rem;
  }

  .meta-row {
    display: flex;
    align-items: baseline;
    gap: 0.6rem;
    padding: 0.15rem 0.1rem;
  }

  .meta-label {
    flex-shrink: 0;
  }

  .meta-value {
    font-family: var(--font-mono);
    font-size: 0.7rem;
    color: var(--text-primary);
    font-variant-numeric: tabular-nums;
    min-width: 0;
  }

  .btn-link {
    flex-shrink: 0;
  }

  .setting-row {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 0.75rem;
    align-items: center;
    padding: 0.4rem 0.1rem;
  }

  .setting-row-head {
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
    min-width: 0;
  }

  .setting-row-title {
    font-family: var(--font-heading, var(--font-body));
    font-size: 0.8rem;
    color: var(--text-primary);
  }

  .setting-row-desc {
    font-family: var(--font-body);
    font-size: 0.75rem;
    color: var(--text-secondary);
    line-height: 1.35;
  }

  .setting-select {
    font-family: var(--font-body);
    font-size: 0.8rem;
    padding: 0.3rem 0.5rem;
    background: var(--bg-focused);
    color: var(--text-primary);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    cursor: pointer;
    min-width: 11rem;
  }
  .setting-select:focus {
    outline: 1px solid var(--text-accent);
    outline-offset: -1px;
  }
  .setting-select:disabled {
    cursor: default;
  }

  .policy-group {
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    padding: 0.4rem 0.6rem 0.6rem;
    margin: 0;
    width: 100%;
    box-sizing: border-box;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 0.1rem;
    transition: opacity var(--transition-fast);
  }
  .policy-group:disabled {
    opacity: 0.45;
  }
  .policy-group .setting-row + .setting-row {
    border-top: 1px solid var(--border-subtle);
  }

  /* Sized to its text: WebKit stretches a flex fieldset's legend to the
     full width, cutting the top border away up to the far corner. */
  .policy-legend {
    width: fit-content;
    padding: 0 0.3rem;
  }

  /* Not the bracket links, which are app.css's .btn-link. :where keeps
     this rule's weight under .btn-icon's. */
  button:not(:where(.btn-link)) {
    font-family: var(--font-body);
    font-size: 0.85rem;
    padding: 0.4rem 0.75rem;
    border-radius: var(--radius-md);
    cursor: pointer;
    transition: all var(--transition-fast);
  }

  button:not(:where(.btn-link)):disabled {
    cursor: default;
    opacity: 0.5;
  }

  /* The bay's caption. `.ledger-label` is the bay voice everywhere else and
     only the hue changes here, because this is the one bay whose name is a
     warning. Stepped back to 0.85 for the same reason the well's frame is
     tinted rather than solid: a caption that shouts louder than the controls
     it introduces is structure outranking them. Everything else about the
     zone — the frame, the rows, the row voice — is global (.danger-bay,
     .action-row, .row-text, .row-title in app.css). */
  .danger-caption {
    color: var(--text-danger);
    opacity: 0.85;
  }

  .row-note {
    display: block;
    margin-top: 4px;
    color: var(--text-accent);
  }

  .btn-icon {
    background: transparent;
    border: none;
    color: var(--text-secondary);
    padding: 0.35rem;
    line-height: 0;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }
  .btn-icon:hover:not(:disabled) {
    color: var(--text-accent);
  }
  .btn-icon-svg {
    width: 16px;
    height: 16px;
  }
</style>
