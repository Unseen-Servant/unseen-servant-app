<script lang="ts">
  // Filter popover. Same anchor pattern as the sort menu in CollectionsPanel:
  // outside-click and Escape close it.

  export let open: boolean = false;
  export let anchorEl: HTMLElement | undefined = undefined;

  // Game systems to EXCLUDE. Empty = show all. Persisting "excluded" rather
  // than "selected" means newly-detected systems show up automatically.
  export let excludedSystems: Set<string> = new Set();
  export let onToggleSystem: (system: string) => void = () => {};
  export let onClearSystems: () => void = () => {};

  // Available systems (with counts) — typically gameSystemStats from +page.
  export let systems: { name: string; count: number }[] = [];

  // Whether the Game systems section is meaningful in the current context.
  // System tags are the organizing axis of the systems view, so we only
  // expose the filter there — in tree view it's a foreign content filter
  // over a filesystem-shaped structure.
  export let showSystemFilter: boolean = true;

  // Hidden items section. `hiddenCount` is the number of explicitly-hidden
  // paths (folders count as 1 each — descendants are implicit). The row
  // toggles `showHidden`; when count is 0 the row is disabled.
  export let showHidden: boolean = false;
  export let hiddenCount: number = 0;
  export let onToggleShowHidden: () => void = () => {};
  export let onClearHidden: () => void = () => {};

  // Curation section. Three mutually-exclusive radios live here,
  // dispatched by the parent via `*FilterAvailable` flags:
  //   - Show all: no narrowing
  //   - Show only collection: focus on the active collection
  //   - Show only loose: files not in any collection
  // The parent gates the entire section via `showCollectionFilter`.
  export let showCollectionFilter: boolean = false;
  export let uncategorizedFilterAvailable: boolean = false;
  export let focusFilterAvailable: boolean = false;
  export let activeContextName: string | null = null;
  export let showOnlyUncollected: boolean = false;
  export let uncollectedCount: number = 0;
  export let focusActiveCollection: boolean = false;
  export let onToggleShowOnlyUncollected: () => void = () => {};
  export let onToggleFocusActiveCollection: () => void = () => {};

  export let onClose: () => void = () => {};

  let menuEl: HTMLDivElement;

  function handleWindowClick(event: MouseEvent) {
    if (!open) return;
    const target = event.target as Node;
    if (anchorEl && (anchorEl === target || anchorEl.contains(target))) return;
    if (menuEl && menuEl.contains(target)) return;
    onClose();
  }

  function handleKey(event: KeyboardEvent) {
    if (open && event.key === 'Escape') {
      event.preventDefault();
      onClose();
    }
  }

  $: hasSystemFilter = excludedSystems.size > 0;
  $: hasHidden = hiddenCount > 0;

  // The Collections section presents three mutually-exclusive radio
  // options. The radio reflects the *effective* state, but the two
  // underlying preferences (focusActiveCollection, showOnlyUncollected)
  // are persisted independently — so a user who prefers loose-mode keeps
  // that preference even after a context activation temporarily shifts
  // the effective state. Switching modes clears the other flag so the
  // mutex is enforced by the handler regardless of how persisted state
  // started.
  $: collectionsMode = (() => {
    if (focusFilterAvailable && focusActiveCollection) return 'collection';
    if (uncategorizedFilterAvailable && showOnlyUncollected) return 'loose';
    return 'all';
  })();
  function handleCollectionsMode(value: 'all' | 'collection' | 'loose') {
    const desiredFocus = value === 'collection';
    const desiredLoose = value === 'loose';
    if (focusFilterAvailable && desiredFocus !== focusActiveCollection) {
      onToggleFocusActiveCollection();
    }
    if (uncategorizedFilterAvailable && desiredLoose !== showOnlyUncollected) {
      onToggleShowOnlyUncollected();
    }
  }
</script>

<svelte:window on:click={handleWindowClick} on:keydown={handleKey} />

{#if open}
  <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
  <div class="filter-menu" bind:this={menuEl} on:click|stopPropagation>
    <div class="section">
      <div class="section-head">
        <span class="section-label">Hidden items</span>
        {#if hasHidden}
          <button class="reset-link" on:click={onClearHidden}>Clear</button>
        {/if}
      </div>
      <label class="row" class:row-disabled={!hasHidden} title={hasHidden ? 'Reveal hidden files and folders in the tree' : 'Right-click any file or folder to hide it'}>
        <span class="row-name">Show hidden items</span>
        <span class="row-count">{hiddenCount}</span>
        <input
          class="app-checkbox"
          type="checkbox"
          checked={showHidden}
          disabled={!hasHidden}
          on:change={onToggleShowHidden}
        />
      </label>
    </div>

    {#if showCollectionFilter}
      <hr class="section-divider" />
      <div class="section">
        <div class="section-head">
          <span class="section-label">Curation</span>
        </div>
        <label class="row" title="Show every file in the library">
          <span class="row-name">Show all</span>
          <input
            class="app-radio"
            type="radio"
            name="collections-mode"
            checked={collectionsMode === 'all'}
            on:change={() => handleCollectionsMode('all')}
          />
        </label>
        <label
          class="row"
          class:row-disabled={!focusFilterAvailable}
          title={focusFilterAvailable
            ? `Narrow the tree to just ${activeContextName}'s files`
            : 'Activate a collection from the panel to enable'}
        >
          <span class="row-name">Show only collection</span>
          <input
            class="app-radio"
            type="radio"
            name="collections-mode"
            checked={collectionsMode === 'collection'}
            disabled={!focusFilterAvailable}
            on:change={() => handleCollectionsMode('collection')}
          />
        </label>
        <label
          class="row"
          title="Show only files that aren't in any collection — useful for scouting curation candidates"
        >
          <span class="row-name">Show only loose</span>
          <span class="row-count">{uncollectedCount}</span>
          <input
            class="app-radio"
            type="radio"
            name="collections-mode"
            checked={collectionsMode === 'loose'}
            on:change={() => handleCollectionsMode('loose')}
          />
        </label>
      </div>
    {/if}

    {#if showSystemFilter}
      {#if systems.length > 0}
        <hr class="section-divider" />
        <div class="section">
          <div class="section-head">
            <span class="section-label">Game systems</span>
            {#if hasSystemFilter}
              <button class="reset-link" on:click={onClearSystems}>Reset</button>
            {/if}
          </div>
          <div class="systems">
            {#each systems as { name, count }}
              <label class="row" title={name}>
                <span class="row-name">{name}</span>
                <span class="row-count">{count}</span>
                <input
                  class="app-checkbox"
                  type="checkbox"
                  checked={!excludedSystems.has(name)}
                  on:change={() => onToggleSystem(name)}
                />
              </label>
            {/each}
          </div>
        </div>
      {:else}
        <hr class="section-divider" />
        <div class="empty">No game systems detected yet. Index some files first.</div>
      {/if}
    {/if}
  </div>
{/if}

<style>
  .filter-menu {
    position: absolute;
    top: calc(100% + 4px);
    left: 0;
    background: var(--bg-focused);
    border: 1px solid var(--bg-category);
    border-radius: 4px;
    box-shadow: var(--shadow-dropdown);
    padding: 0.4rem 0;
    min-width: 220px;
    max-width: 280px;
    z-index: 60;
    font-family: var(--font-body);
  }

  .section {
    padding: 0.15rem 0;
  }

  .section-head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    padding: 0.25rem 0.7rem 0.15rem;
  }

  .section-label {
    display: block;
    padding: 0.25rem 0.7rem 0.15rem;
    font-family: var(--font-heading, var(--font-body));
    font-size: 0.65rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--text-secondary);
  }
  .section-head .section-label {
    padding: 0;
  }

  .reset-link {
    background: none;
    border: none;
    color: var(--text-tertiary);
    font-family: var(--font-body);
    font-size: 0.7rem;
    padding: 0;
    cursor: pointer;
    transition: color var(--transition-fast);
  }
  .reset-link:hover {
    color: var(--text-secondary);
  }

  .systems {
    max-height: 12rem;
    overflow-y: auto;
  }

  .row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.3rem 0.7rem;
    font-size: 0.8rem;
    color: var(--text-primary);
    cursor: pointer;
    transition: background var(--transition-fast);
  }
  .row:hover {
    background: var(--bg-category);
  }
  .row-disabled {
    color: var(--text-tertiary);
    cursor: default;
  }
  .row-disabled:hover {
    background: transparent;
  }
  .row-disabled .row-count {
    color: var(--text-tertiary);
  }

  .section-divider {
    margin: 0.3rem 0;
    border: none;
    border-top: 1px solid var(--bg-category);
  }
  .row-name {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .row-count {
    font-size: 0.7rem;
    color: var(--text-secondary);
    flex-shrink: 0;
  }

  .empty {
    padding: 0.5rem 0.7rem;
    font-size: 0.75rem;
    color: var(--text-tertiary);
  }
</style>
