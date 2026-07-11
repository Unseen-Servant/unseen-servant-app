<script lang="ts">
  import { onMount } from 'svelte';
  import { invoke } from '@tauri-apps/api/core';
  import type { SearchSettings } from './searchSettings';
  import {
    DEFAULT_SEARCH_SETTINGS,
    RERANK_POOL_MAX,
    RERANK_POOL_MIN,
    clampPoolSize,
    normalizeSearchSettings,
  } from './searchSettings';

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
    const input = e.currentTarget as HTMLInputElement;
    const clamped = clampPoolSize(Number(input.value));
    input.value = String(clamped);
    if (settings && clamped !== settings.rerank_candidates) {
      update({ rerank_candidates: clamped });
    }
  }

  function restoreDefaults() {
    update({ ...DEFAULT_SEARCH_SETTINGS });
  }
</script>

<div class="general-settings">
  {#if loadError}
    <section class="field">
      <div class="field-head">
        <h3 class="field-title font-heading">Search pipeline</h3>
        <p class="field-desc error-text">
          Could not load search settings — is the sidecar running? ({loadError})
        </p>
      </div>
    </section>
  {:else if !settings}
    <p class="field-desc">Loading…</p>
  {:else}
    <section class="field">
      <div class="field-head">
        <h3 class="field-title font-heading">Search pipeline</h3>
        <p class="field-desc">
          How search ranks results. Applies to the app's search bar 
	  and MCP calls alike.
        </p>
      </div>

      <div class="setting-row">
        <div class="setting-row-head">
          <div class="setting-row-title">Re-rank results</div>
          <div class="setting-row-desc">
            Rescores the top candidates with a cross-encoder for a more
            accurate ordering. Strong impact on relevance, but also performance.
	    Turn off if search is deemed too slow.
          </div>
        </div>
        <select
          class="setting-select"
          value={settings.rerank ? 'on' : 'off'}
          on:change={setBool('rerank')}
        >
          <option value="on">On</option>
          <option value="off">Off</option>
        </select>
      </div>

      <div class="setting-row" class:dimmed={!settings.rerank}>
        <div class="setting-row-head">
          <div class="setting-row-title">Re-rank pool size</div>
          <div class="setting-row-desc">
            How many candidates the re-ranker rescores
            ({RERANK_POOL_MIN}–{RERANK_POOL_MAX}). Larger pools reach deeper
            into the library but slow every search down.
          </div>
        </div>
        <input
          type="number"
          class="setting-number"
          min={RERANK_POOL_MIN}
          max={RERANK_POOL_MAX}
          value={settings.rerank_candidates}
          disabled={!settings.rerank}
          on:change={commitPoolSize}
        />
      </div>

      <div class="setting-row">
        <div class="setting-row-head">
          <div class="setting-row-title">Spell correction</div>
          <div class="setting-row-desc">
            Fixes typos against your library's own vocabulary before
            searching.
          </div>
        </div>
        <select
          class="setting-select"
          value={settings.spell_correction ? 'on' : 'off'}
          on:change={setBool('spell_correction')}
        >
          <option value="on">On</option>
          <option value="off">Off</option>
        </select>
      </div>

      <fieldset class="experimental-group">
        <legend class="experimental-legend">Experimental</legend>

        <div class="setting-row">
          <div class="setting-row-head">
            <div class="setting-row-title">Hybrid keyword search</div>
            <div class="setting-row-desc">
              Blends exact-keyword (BM25) matches into semantic results.
              Helps rare exact terms.
            </div>
          </div>
          <select
            class="setting-select"
            value={settings.hybrid ? 'on' : 'off'}
            on:change={setBool('hybrid')}
          >
            <option value="on">On</option>
            <option value="off">Off</option>
          </select>
        </div>

        <div class="setting-row">
          <div class="setting-row-head">
            <div class="setting-row-title">Spacing-variant expansion</div>
            <div class="setting-row-desc">
              Searches spacing variants ("chainmail" / "chain mail").
            </div>
          </div>
          <select
            class="setting-select"
            value={settings.variant_expansion ? 'on' : 'off'}
            on:change={setBool('variant_expansion')}
          >
            <option value="on">On</option>
            <option value="off">Off</option>
          </select>
        </div>
      </fieldset>

      {#if saveError}
        <p class="field-desc error-text">Could not save: {saveError}</p>
      {/if}

      <div class="meta-row">
        <button type="button" class="btn-link" on:click={restoreDefaults}>
          Restore defaults
        </button>
      </div>
    </section>
  {/if}
</div>

<style>
  .general-settings {
    padding: 1rem;
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
    font-size: 0.95rem;
    color: var(--text-primary);
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
    color: var(--text-danger, #c0392b);
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
    border-radius: 4px;
    cursor: pointer;
    min-width: 5.5rem;
  }
  .setting-select:focus {
    outline: 1px solid var(--text-accent);
    outline-offset: -1px;
  }

  .setting-number {
    font-family: var(--font-mono, ui-monospace, monospace);
    font-size: 0.8rem;
    padding: 0.3rem 0.5rem;
    background: var(--bg-focused);
    color: var(--text-primary);
    border: 1px solid var(--border-subtle);
    border-radius: 4px;
    width: 5.5rem;
    box-sizing: border-box;
    font-variant-numeric: tabular-nums;
  }
  .setting-number:focus {
    outline: 1px solid var(--text-accent);
    outline-offset: -1px;
  }
  .setting-number:disabled {
    cursor: not-allowed;
  }

  .experimental-group {
    border: 1px solid var(--border-subtle);
    border-radius: 4px;
    padding: 0.4rem 0.6rem 0.6rem;
    margin: 0;
    width: 100%;
    box-sizing: border-box;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 0.1rem;
  }
  .experimental-group .setting-row + .setting-row {
    border-top: 1px solid var(--border-subtle);
  }

  .experimental-legend {
    font-family: var(--font-heading, var(--font-body));
    font-size: 0.7rem;
    letter-spacing: 0.08em;
    color: var(--text-secondary);
    text-transform: uppercase;
    padding: 0 0.3rem;
  }

  .meta-row {
    display: flex;
    align-items: baseline;
    gap: 0.6rem;
    padding: 0.15rem 0.1rem;
  }

  .btn-link {
    background: transparent;
    border: none;
    padding: 0;
    font-family: var(--font-mono, ui-monospace, monospace);
    font-size: 0.7rem;
    color: var(--text-accent);
    cursor: pointer;
    flex-shrink: 0;
    transition: filter var(--transition-fast);
  }
  .btn-link::before,
  .btn-link::after {
    color: var(--text-secondary);
    transition: color var(--transition-fast);
  }
  .btn-link::before {
    content: '[';
    margin-right: 0.15rem;
  }
  .btn-link::after {
    content: ']';
    margin-left: 0.15rem;
  }
  .btn-link:hover {
    filter: brightness(1.25);
  }
  .btn-link:hover::before,
  .btn-link:hover::after {
    color: var(--text-accent);
  }
</style>
