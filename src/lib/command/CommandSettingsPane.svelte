<script lang="ts">
  // Command's pane in Settings: where the campaigns live, and whether
  // launching a beat spends it (design §4). The sidecar keeps both.
  import { onMount } from 'svelte';
  import { FOLDER, FOLDER_OPEN } from '../ui/iconPaths';
  import { commandApi } from './api';
  import type { CommandSettings } from './types';
  import { m } from '../paraglide/messages';

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

  /** Command closes the open campaign and opens a fresh Untitled in the
   *  folder chosen (command_choose_root). */
  async function chooseRoot() {
    saveError = null;
    try {
      settings = (await commandApi.chooseRoot()) ?? settings;
    } catch (e) {
      saveError = String(e);
    }
  }
</script>

<div class="command-settings">
  {#if loadError}
    <p class="field-desc error-text">{m.command_settings_load_error({ error: loadError })}</p>
  {:else if settings}
    <section class="field">
      <div class="field-head">
        <h3 class="field-title section-title">{m.command_settings_folder()}</h3>
        <p class="field-desc">{m.command_settings_folder_desc()}</p>
      </div>

      <!-- Legend Lore's library folder row (LibrarySettings.svelte), copied. -->
      <div class="path-row">
        <input
          type="text"
          class="path-input"
          readonly
          value={settings.root ?? ''}
          placeholder={m.command_settings_no_folder()}
          title={settings.root ?? ''}
        />
        <button
          type="button"
          class="btn-icon"
          on:click={chooseRoot}
          title={m.command_settings_change_folder()}
          aria-label={m.command_settings_change_folder()}
        >
          <svg class="btn-icon-svg" viewBox="0 0 640 640" fill="currentColor" aria-hidden="true">
            <path class="folder-shut" d={FOLDER}/>
            <path class="folder-opened" d={FOLDER_OPEN}/>
          </svg>
        </button>
      </div>
    </section>

    <section class="field">
      <div class="field-head">
        <h3 class="field-title section-title">{m.command_settings_play()}</h3>
        <p class="field-desc">{m.command_settings_play_desc()}</p>
      </div>

      <div class="setting-row">
        <div class="setting-row-head">
          <div class="setting-row-title">{m.command_settings_spend()}</div>
          <div class="setting-row-desc">{m.command_settings_spend_desc()}</div>
        </div>
        <select
          class="setting-select"
          value={settings.spend_on_launch ? 'on' : 'off'}
          on:change={(e) => setSpendOnLaunch(e.currentTarget.value === 'on')}
        >
          <option value="on">{m.command_settings_on()}</option>
          <option value="off">{m.command_settings_off()}</option>
        </select>
      </div>
    </section>
    {#if saveError}<p class="field-desc error-text">{saveError}</p>{/if}
  {:else}
    <p class="field-desc">{m.command_settings_loading()}</p>
  {/if}
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

  .btn-icon {
    background: transparent;
    border: none;
    color: var(--text-secondary);
    padding: 0.35rem;
    line-height: 0;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: var(--radius-md);
    cursor: pointer;
    transition: all var(--transition-fast);
  }
  .btn-icon:hover {
    color: var(--text-accent);
  }
  .btn-icon-svg {
    width: 16px;
    height: 16px;
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
