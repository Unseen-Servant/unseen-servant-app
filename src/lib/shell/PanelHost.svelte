<script lang="ts">
  // The main window: one tab per tool panel. Every docked panel stays mounted
  // and only the selected one is shown and active; a popped-out panel is
  // unmounted here and its tab holds the way back to it (PANELS.md).
  import ActionButton from '../ui/ActionButton.svelte';
  import PanelView from './PanelView.svelte';
  import { PANELS, panelTitle, type PanelId } from './panels';
  import { appContext, dock, popOut, poppedPanels, setCampaign } from './shellState';

  // TEMP: cross-window sync proof — remove with the picker below once
  // Command owns campaigns.
  const CAMPAIGNS = ['Curse of Strahd', 'Into the Odd'];

  let selected: PanelId = 'legend-lore';

  $: popped = new Set($poppedPanels.popped);

  // A panel back from its own window becomes the selected tab, whether it
  // came back through [dock back] or the window's close button.
  let lastPopped: PanelId[] = [];
  function selectDockedBack(now: PanelId[]) {
    const back = lastPopped.find((id) => !now.includes(id));
    if (back) selected = back;
    lastPopped = now;
  }
  $: selectDockedBack($poppedPanels.popped);

  function report(action: Promise<void>, what: string) {
    action.catch((err) => console.error(`Failed to ${what}:`, err));
  }

  function onCampaignChange(event: Event) {
    const value = (event.currentTarget as HTMLSelectElement).value;
    report(setCampaign(value || null), 'set the campaign');
  }
</script>

<div class="host">
  <nav class="strip">
    <div class="tabs" role="tablist" aria-label="Tools">
      {#each PANELS as panel (panel.id)}
        <div class="tab" class:current={selected === panel.id} class:away={popped.has(panel.id)}>
          <button
            class="tab-name"
            role="tab"
            aria-selected={selected === panel.id}
            on:click={() => (selected = panel.id)}
          >
            {panel.title}
          </button>
          <button
            class="pop-out"
            title={popped.has(panel.id) ? `Bring the ${panel.title} window forward` : `Pop ${panel.title} out into its own window`}
            aria-label={`Pop ${panel.title} out`}
            on:click={() => report(popOut(panel.id), `pop ${panel.title} out`)}
          >
            <!-- Font Awesome "arrow-up-right-from-square" icon (src/lib/ui/icons/arrow-up-right-from-square-solid-full.svg) -->
            <svg viewBox="0 0 640 640" fill="currentColor" aria-hidden="true">
              <path d="M384 64C366.3 64 352 78.3 352 96C352 113.7 366.3 128 384 128L466.7 128L265.3 329.4C252.8 341.9 252.8 362.2 265.3 374.7C277.8 387.2 298.1 387.2 310.6 374.7L512 173.3L512 256C512 273.7 526.3 288 544 288C561.7 288 576 273.7 576 256L576 96C576 78.3 561.7 64 544 64L384 64zM144 160C99.8 160 64 195.8 64 240L64 496C64 540.2 99.8 576 144 576L400 576C444.2 576 480 540.2 480 496L480 416C480 398.3 465.7 384 448 384C430.3 384 416 398.3 416 416L416 496C416 504.8 408.8 512 400 512L144 512C135.2 512 128 504.8 128 496L128 240C128 231.2 135.2 224 144 224L224 224C241.7 224 256 209.7 256 192C256 174.3 241.7 160 224 160L144 160z"/>
            </svg>
          </button>
        </div>
      {/each}
    </div>

    <!-- TEMP: cross-window sync proof. -->
    <label class="campaign">
      <span>campaign</span>
      <select value={$appContext.campaign ?? ''} on:change={onCampaignChange}>
        <option value="">none</option>
        {#each CAMPAIGNS as name}
          <option value={name}>{name}</option>
        {/each}
      </select>
    </label>
  </nav>

  {#each PANELS as panel (panel.id)}
    <div class="slot" class:shown={selected === panel.id} role="tabpanel">
      {#if popped.has(panel.id)}
        <div class="away-note">
          <p><em>{panelTitle(panel.id)}</em> is in its own window.</p>
          <div class="away-actions">
            <ActionButton label="focus" onClick={() => report(popOut(panel.id), `focus ${panel.title}`)} />
            <ActionButton label="dock back" onClick={() => report(dock(panel.id), `dock ${panel.title}`)} />
          </div>
        </div>
      {:else}
        <PanelView id={panel.id} active={selected === panel.id} />
      {/if}
    </div>
  {/each}
</div>

<style>
  .host {
    height: 100vh;
    display: flex;
    flex-direction: column;
    background: var(--bg-app);
  }

  .strip {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    padding: 0.25rem 0.75rem;
    border-bottom: 1px solid var(--border-subtle);
  }

  .tabs {
    display: flex;
    gap: 2px;
  }

  /* A picker, not a mode — one tool is always showing — so the current tab
     sits on a raised fill like Header's view switch instead of lighting
     purple. */
  .tab {
    display: flex;
    align-items: center;
    border-radius: var(--radius-md);
    color: var(--text-tertiary);
    transition: background var(--transition-fast), color var(--transition-fast);
  }

  .tab.current {
    background: var(--bg-header);
    color: var(--text-primary);
  }

  .tab.away .tab-name {
    opacity: var(--opacity-out-of-scope);
  }

  .tab-name,
  .pop-out {
    background: transparent;
    border: none;
    color: inherit;
    cursor: pointer;
    transition: color var(--transition-fast);
  }

  .tab-name {
    padding: 0.15rem 0.3rem 0.15rem 0.6rem;
    font-family: var(--font-heading);
    font-size: 0.95rem;
  }

  .pop-out {
    display: flex;
    padding: 0.25rem 0.5rem 0.25rem 0.25rem;
  }

  .pop-out svg {
    width: 11px;
    height: 11px;
  }

  .tab-name:hover,
  .pop-out:hover {
    color: var(--text-primary);
  }

  .tab-name:active,
  .pop-out:active {
    transform: scale(0.97);
  }

  .campaign {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    font-size: 0.8rem;
    color: var(--text-tertiary);
  }

  .campaign select {
    font-family: var(--font-body);
    font-size: 0.8rem;
    padding: 0.15rem 0.4rem;
    background: var(--bg-focused);
    color: var(--text-accent);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    cursor: pointer;
  }

  .slot {
    flex: 1;
    min-height: 0;
    display: none;
  }

  .slot.shown {
    display: block;
  }

  .away-note {
    height: 100%;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    color: var(--text-secondary);
  }

  .away-note p {
    margin: 0;
  }

  .away-note em {
    font-family: var(--font-heading);
    font-style: normal;
    color: var(--text-primary);
  }

  .away-actions {
    display: flex;
    gap: 1rem;
  }
</style>
