<script lang="ts">
  // Command's pane in Settings: where the campaigns live, and whether
  // launching a beat spends it (design §4). The sidecar keeps both.
  import { onMount } from 'svelte';
  import { commandApi } from './api';
  import type { CommandSettings } from './types';

  let settings: CommandSettings | null = null;
  let loadError: string | null = null;
  let saveError: string | null = null;

  onMount(async () => {
    try {
      settings = await commandApi.getSettings();
    } catch (e) {
      loadError = String(e);
    }
  });

  async function setSpendOnLaunch(enabled: boolean) {
    if (!settings) return;
    const previous = settings;
    settings = { ...settings, spend_on_launch: enabled };
    saveError = null;
    try {
      settings = await commandApi.setSpendOnLaunch(enabled);
    } catch (e) {
      settings = previous;
      saveError = String(e);
    }
  }
</script>

<div class="command-settings">
  <section class="field">
    <div class="field-head">
      <h3 class="field-title section-title">Play</h3>
      <p class="field-desc">How Command keeps track of a session at the table.</p>
    </div>

    {#if loadError}
      <p class="field-desc error-text">Could not load Command's settings — is the sidecar running? ({loadError})</p>
    {:else if settings}
      <div class="setting-row">
        <div class="setting-row-head">
          <div class="setting-row-title">Spend beats on launch</div>
          <div class="setting-row-desc">
            Launching a beat marks it spent, so it isn't carried into the next session. Off, you tick
            beats off by hand.
          </div>
        </div>
        <select
          class="setting-select"
          value={settings.spend_on_launch ? 'on' : 'off'}
          on:change={(e) => setSpendOnLaunch(e.currentTarget.value === 'on')}
        >
          <option value="on">On</option>
          <option value="off">Off</option>
        </select>
      </div>
      {#if saveError}<p class="field-desc error-text">{saveError}</p>{/if}

      <div class="setting-row">
        <div class="setting-row-head">
          <div class="setting-row-title">Campaigns folder</div>
          <div class="setting-row-desc path" title={settings.root ?? ''}>
            {settings.root ?? 'Not chosen yet — choose it from Command.'}
          </div>
        </div>
      </div>
    {:else}
      <p class="field-desc">Loading…</p>
    {/if}
  </section>
</div>

<style>
  /* The settings pane recipe (GeneralSettings.svelte), kept local as each
     pane keeps it. */
  .command-settings {
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

  .error-text {
    color: var(--text-danger);
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

  .path {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-family: var(--font-mono);
    font-size: 0.72rem;
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
    width: 8rem;
  }

  .setting-select:focus {
    outline: 1px solid var(--text-accent);
    outline-offset: -1px;
  }
</style>
