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
</script>

<svelte:window on:click={handleWindowClick} on:keydown={handleKey} />

{#if open}
  <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
  <div class="filter-menu" bind:this={menuEl} on:click|stopPropagation>
    {#if systems.length > 0}
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
      <div class="empty">No game systems detected yet. Index some files first.</div>
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
