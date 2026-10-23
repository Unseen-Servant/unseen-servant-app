<script lang="ts">
  import { onMount } from 'svelte';
  import { invoke } from '@tauri-apps/api/core';
  import type { SearchSettings } from './searchSettings';
  import {
    DEFAULT_SEARCH_SETTINGS,
    RERANK_POOL_PRESETS,
    normalizeSearchSettings,
  } from './searchSettings';
  import { m } from '../paraglide/messages';

  // App-side display preference, persisted by the page — not a sidecar
  // setting, so it renders whatever state the pipeline section is in.
  export let dimWeakResults: boolean = true;
  export let onDimWeakResultsChange: (value: boolean) => void = () => {};

  let settings: SearchSettings | null = null;
  let loadError: string | null = null;
  let saveError: string | null = null;

  onMount(async () => {
    try {
      const raw = await invoke('get_search_settings');
      settings = normalizeSearchSettings(raw);
    } catch (e) {
      loadError = String(e);
    }
  });

  async function update(partial: Partial<SearchSettings>) {
    if (!settings) return;
    const previous = settings;
    // Optimistic: the control reflects the choice immediately; the echoed
    // (validated/clamped) server value is adopted on success, the previous
    // value restored on failure.
    settings = { ...settings, ...partial };
    saveError = null;
    try {
      const echoed = await invoke('update_search_settings', { partial });
      settings = normalizeSearchSettings(echoed);
    } catch (e) {
      settings = previous;
      saveError = String(e);
    }
  }

  function setBool(key: keyof SearchSettings) {
    return (e: Event) => {
      const value = (e.currentTarget as HTMLSelectElement).value === 'on';
      update({ [key]: value } as Partial<SearchSettings>);
    };
  }

  function commitPoolSize(e: Event) {
    const value = Number((e.currentTarget as HTMLSelectElement).value);
    if (settings && value !== settings.rerank_candidates) {
      update({ rerank_candidates: value });
    }
  }

  // The stored value can be a non-preset number (set directly over the
  // API) — surface it honestly as "Custom (N)" instead of rewriting it.
  $: poolIsCustom = settings
    ? !RERANK_POOL_PRESETS.some((p) => p.value === settings!.rerank_candidates)
    : false;

  function restoreDefaults() {
    update({ ...DEFAULT_SEARCH_SETTINGS });
  }
</script>

<div class="general-settings">
  <section class="field">
    <div class="field-head">
      <h3 class="field-title section-title">{m.lore_general_results()}</h3>
      <p class="field-desc">{m.lore_general_results_desc()}</p>
    </div>

    <div class="setting-row">
      <div class="setting-row-head">
        <div class="setting-row-title">{m.lore_general_dim()}</div>
        <div class="setting-row-desc">
          {m.lore_general_dim_desc()}
        </div>
      </div>
      <select
        class="setting-select"
        value={dimWeakResults ? 'on' : 'off'}
        on:change={(e) => onDimWeakResultsChange(e.currentTarget.value === 'on')}
      >
        <option value="on">{m.lore_general_on()}</option>
        <option value="off">{m.lore_general_off()}</option>
      </select>
    </div>
  </section>

  {#if loadError}
    <section class="field">
      <div class="field-head">
        <h3 class="field-title section-title">{m.lore_general_pipeline()}</h3>
        <p class="field-desc error-text">
          {m.lore_general_load_error({ error: loadError })}
        </p>
      </div>
    </section>
  {:else if !settings}
    <p class="field-desc">{m.lore_general_loading()}</p>
  {:else}
    <section class="field">
      <div class="field-head">
        <h3 class="field-title section-title">{m.lore_general_pipeline()}</h3>
        <p class="field-desc">
          {m.lore_general_pipeline_desc()}
        </p>
      </div>

      <div class="setting-row">
        <div class="setting-row-head">
          <div class="setting-row-title">{m.lore_general_rerank()}</div>
          <div class="setting-row-desc">
            {m.lore_general_rerank_desc()}
          </div>
        </div>
        <select
          class="setting-select"
          value={settings.rerank ? 'on' : 'off'}
          on:change={setBool('rerank')}
        >
          <option value="on">{m.lore_general_on()}</option>
          <option value="off">{m.lore_general_off()}</option>
        </select>
      </div>

      <div class="setting-row" class:dimmed={!settings.rerank}>
        <div class="setting-row-head">
          <div class="setting-row-title">{m.lore_general_pool()}</div>
          <div class="setting-row-desc">
            {m.lore_general_pool_desc()}
          </div>
        </div>
        <select
          class="setting-select"
          value={String(settings.rerank_candidates)}
          disabled={!settings.rerank}
          on:change={commitPoolSize}
        >
          {#if poolIsCustom}
            <option value={String(settings.rerank_candidates)}>
              {m.lore_general_pool_custom({ size: settings.rerank_candidates })}
            </option>
          {/if}
          {#each RERANK_POOL_PRESETS as preset}
            <option value={String(preset.value)}>
              {m.lore_general_pool_preset({ label: preset.label(), size: preset.value })}
            </option>
          {/each}
        </select>
      </div>

      <div class="setting-row">
        <div class="setting-row-head">
          <div class="setting-row-title">{m.lore_general_spell()}</div>
          <div class="setting-row-desc">
            {m.lore_general_spell_desc()}
          </div>
        </div>
        <select
          class="setting-select"
          value={settings.spell_correction ? 'on' : 'off'}
          on:change={setBool('spell_correction')}
        >
          <option value="on">{m.lore_general_on()}</option>
          <option value="off">{m.lore_general_off()}</option>
        </select>
      </div>

      <div class="setting-row">
        <div class="setting-row-head">
          <div class="setting-row-title">{m.lore_general_hybrid()}</div>
          <div class="setting-row-desc">
            {m.lore_general_hybrid_desc()}
          </div>
        </div>
        <select
          class="setting-select"
          value={settings.hybrid ? 'on' : 'off'}
          on:change={setBool('hybrid')}
        >
          <option value="on">{m.lore_general_on()}</option>
          <option value="off">{m.lore_general_off()}</option>
        </select>
      </div>

      <fieldset class="experimental-group">
        <legend class="experimental-legend readout-label">{m.lore_general_experimental()}</legend>

        <div class="setting-row">
          <div class="setting-row-head">
            <div class="setting-row-title">{m.lore_general_variants()}</div>
            <div class="setting-row-desc">
              {m.lore_general_variants_desc()}
            </div>
          </div>
          <select
            class="setting-select"
            value={settings.variant_expansion ? 'on' : 'off'}
            on:change={setBool('variant_expansion')}
          >
            <option value="on">{m.lore_general_on()}</option>
            <option value="off">{m.lore_general_off()}</option>
          </select>
        </div>
      </fieldset>

      {#if saveError}
        <p class="field-desc error-text">{m.lore_general_save_error({ error: saveError })}</p>
      {/if}

      <div class="meta-row">
        <button type="button" class="btn-link" on:click={restoreDefaults}>
          {m.lore_general_restore()}
        </button>
      </div>
    </section>
  {/if}
</div>

<style>
  .general-settings {
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
    transition: opacity var(--transition-fast);
  }
  .setting-row.dimmed {
    opacity: 0.45;
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
    /* Fixed width so every control in the pane lines up regardless of
       its longest option ("Exhaustive (200)"). */
    width: 8rem;
  }
  .setting-select:focus {
    outline: 1px solid var(--text-accent);
    outline-offset: -1px;
  }
  .setting-select:disabled {
    cursor: default;
  }

  .experimental-group {
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
  }
  /* Sized to its text: WebKit stretches a flex fieldset's legend to the
     full width, cutting the top border away up to the far corner. */
  .experimental-legend {
    width: fit-content;
    padding: 0 0.3rem;
  }

  .meta-row {
    display: flex;
    align-items: baseline;
    gap: 0.6rem;
    padding: 0.15rem 0.1rem;
  }

  .btn-link {
    flex-shrink: 0;
  }
</style>
