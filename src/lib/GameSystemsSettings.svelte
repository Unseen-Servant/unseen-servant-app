<script lang="ts">
  import { invoke } from '@tauri-apps/api/core';
  import type { KnownGameSystem } from './types';

  export let knownSystems: KnownGameSystem[] = [];
  export let onSystemsChanged: () => void = () => {};

  // Group systems by game_system (family name)
  $: grouped = groupByFamily(knownSystems);

  // "Add custom system" form state
  let newTag = '';
  let newFamily = '';
  let newKeywords = '';
  let addError = '';

  // Edit state
  let editingTag: string | null = null;
  let editTag = '';
  let editFamily = '';
  let editKeywords = '';
  let editError = '';

  function groupByFamily(systems: KnownGameSystem[]): Map<string, KnownGameSystem[]> {
    const map = new Map<string, KnownGameSystem[]>();
    for (const sys of systems) {
      const family = sys.game_system;
      if (!map.has(family)) map.set(family, []);
      map.get(family)!.push(sys);
    }
    return map;
  }

  async function handleAdd() {
    const tag = newTag.trim();
    const family = newFamily.trim() || tag;
    if (!tag) { addError = 'Tag is required'; return; }

    const keywords = newKeywords
      .split(',')
      .map(k => k.trim().toLowerCase())
      .filter(k => k.length > 0);

    try {
      await invoke('create_custom_game_system', {
        tag, gameSystem: family, keywords,
      });
      newTag = '';
      newFamily = '';
      newKeywords = '';
      addError = '';
      onSystemsChanged();
    } catch (e: any) {
      addError = e?.toString() || 'Failed to add system';
    }
  }

  function startEdit(sys: KnownGameSystem) {
    editingTag = sys.tag;
    editTag = sys.tag;
    editFamily = sys.game_system;
    editKeywords = (sys.keywords || []).join(', ');
    editError = '';
  }

  function cancelEdit() {
    editingTag = null;
    editError = '';
  }

  async function saveEdit() {
    if (!editingTag) return;
    const tag = editTag.trim();
    const family = editFamily.trim() || tag;
    if (!tag) { editError = 'Tag is required'; return; }

    const keywords = editKeywords
      .split(',')
      .map(k => k.trim().toLowerCase())
      .filter(k => k.length > 0);

    try {
      await invoke('update_custom_game_system', {
        originalTag: editingTag, tag, gameSystem: family, keywords,
      });
      editingTag = null;
      editError = '';
      onSystemsChanged();
    } catch (e: any) {
      editError = e?.toString() || 'Failed to update system';
    }
  }

  async function handleDelete(tag: string) {
    try {
      await invoke('delete_custom_game_system', { tag });
      onSystemsChanged();
    } catch (e: any) {
      // Silently fail — shouldn't happen for custom systems
    }
  }

  async function handleToggle(tag: string, currentlyEnabled: boolean) {
    try {
      await invoke('toggle_builtin_game_system', {
        tag, disabled: currentlyEnabled,
      });
      onSystemsChanged();
    } catch (e: any) {
      // Silently fail
    }
  }
</script>

<div class="game-systems-settings">
  <div class="systems-list">
    {#each [...grouped] as [family, systems]}
      <div class="family-group">
        <div class="family-header">{family}</div>
        {#each systems as sys}
          {#if editingTag === sys.tag}
            <div class="system-row editing">
              <div class="edit-form">
                <div class="edit-fields">
                  <input class="edit-input" bind:value={editTag} placeholder="Tag" />
                  <input class="edit-input" bind:value={editFamily} placeholder="Family name" />
                  <input class="edit-input wide" bind:value={editKeywords} placeholder="Keywords (comma-separated)" />
                </div>
                {#if editError}
                  <div class="error-msg">{editError}</div>
                {/if}
                <div class="edit-actions">
                  <button class="btn btn-save" on:click={saveEdit}>Save</button>
                  <button class="btn btn-cancel" on:click={cancelEdit}>Cancel</button>
                </div>
              </div>
            </div>
          {:else}
            <div class="system-row">
              <span class="system-tag">{sys.tag}</span>
              <span class="system-keywords">{(sys.keywords || []).slice(0, 3).join(', ')}{(sys.keywords || []).length > 3 ? '...' : ''}</span>
              <div class="system-actions">
                {#if sys.is_builtin}
                  <span class="builtin-label">built-in</span>
                {:else}
                  <button class="icon-btn" title="Edit" on:click={() => startEdit(sys)}>
                    <svg viewBox="0 0 512 512" fill="currentColor" width="12" height="12"><path d="M410.3 231l11.3-11.3-33.9-33.9-62.1-62.1L291.7 89.8l-11.3 11.3-22.6 22.6L150.4 230.7l-2 2-1 1.3-.6 1.6-20 57.1c-4.6 13.1 7.5 25.2 20.6 20.6l57.1-20 1.6-.6 1.3-1 2-2L316.3 182.9l22.6-22.6 22.6-22.6 11.3-11.3 11.3-11.3 26.1 26.1zM169.1 349.9l-3.3 .9-4.7 1.6-13.3 4.7-9.3 3.3 3.3-9.3 4.7-13.3 1.6-4.7 .9-3.3 68-68 25 25-68 68-5 5z"/></svg>
                  </button>
                  <button class="icon-btn danger" title="Delete" on:click={() => handleDelete(sys.tag)}>
                    <svg viewBox="0 0 448 512" fill="currentColor" width="12" height="12"><path d="M135.2 17.7L128 32H32C14.3 32 0 46.3 0 64s14.3 32 32 32h384c17.7 0 32-14.3 32-32s-14.3-32-32-32H320l-7.2-14.3C307.4 6.8 296.3 0 284.2 0H163.8c-12.1 0-23.2 6.8-28.6 17.7zM416 128H32l21.2 339C55.5 487.8 73.8 512 100.8 512h246.4c27 0 45.3-24.2 47.6-45l21.2-339z"/></svg>
                  </button>
                {/if}
              </div>
            </div>
          {/if}
        {/each}
      </div>
    {/each}
  </div>

  <div class="add-section">
    <div class="add-header">Add custom system</div>
    <div class="add-form">
      <div class="add-row">
        <input class="add-input" bind:value={newTag} placeholder="Tag (e.g. Cairn)" on:keydown={(e) => e.key === 'Enter' && handleAdd()} />
        <input class="add-input" bind:value={newFamily} placeholder="Family name (optional)" on:keydown={(e) => e.key === 'Enter' && handleAdd()} />
      </div>
      <input class="add-input wide" bind:value={newKeywords} placeholder="Keywords for auto-detection (comma-separated)" on:keydown={(e) => e.key === 'Enter' && handleAdd()} />
      {#if addError}
        <div class="error-msg">{addError}</div>
      {/if}
      <button class="btn btn-add" on:click={handleAdd}>Add System</button>
    </div>
  </div>
</div>

<style>
  .game-systems-settings {
    display: flex;
    flex-direction: column;
    height: 100%;
  }

  .systems-list {
    flex: 1;
    overflow-y: auto;
    padding: 0.5rem 0;
  }

  .family-group {
    margin-bottom: 0.75rem;
  }

  .family-header {
    font-family: var(--font-heading);
    font-size: 0.8rem;
    color: var(--text-accent);
    padding: 0.25rem 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .system-row {
    display: flex;
    align-items: center;
    padding: 0.3rem 0.75rem;
    gap: 0.5rem;
    transition: background var(--transition-fast);
  }
  .system-row:hover {
    background: var(--bg-focused);
  }
  .system-row.editing {
    background: var(--bg-focused);
    padding: 0.5rem 0.75rem;
  }

  .system-tag {
    font-size: 0.8rem;
    color: var(--text-primary);
    font-weight: 600;
    min-width: 80px;
    flex-shrink: 0;
  }

  .system-keywords {
    font-size: 0.75rem;
    color: var(--text-tertiary);
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .system-actions {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    flex-shrink: 0;
  }

  .builtin-label {
    font-size: 0.65rem;
    color: var(--text-tertiary);
    padding: 0.1rem 0.3rem;
    border: 1px solid var(--border-subtle);
    border-radius: 3px;
  }

  .icon-btn {
    background: none;
    border: none;
    color: var(--text-secondary);
    padding: 0.15rem;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    border-radius: 3px;
    transition: color var(--transition-fast);
  }
  .icon-btn:hover {
    color: var(--text-accent);
  }
  .icon-btn.danger:hover {
    color: var(--text-danger);
  }

  .edit-form {
    width: 100%;
  }
  .edit-fields {
    display: flex;
    gap: 0.4rem;
    flex-wrap: wrap;
  }
  .edit-actions {
    display: flex;
    gap: 0.4rem;
    margin-top: 0.4rem;
  }

  .edit-input, .add-input {
    font-family: var(--font-body);
    font-size: 0.8rem;
    padding: 0.3rem 0.5rem;
    background: var(--bg-app);
    border: 1px solid var(--border-subtle);
    border-radius: 4px;
    color: var(--text-primary);
    outline: none;
    flex: 1;
    min-width: 0;
  }
  .edit-input:focus, .add-input:focus {
    border-color: var(--text-accent);
  }
  .edit-input.wide, .add-input.wide {
    flex: 1 1 100%;
  }

  .error-msg {
    font-size: 0.75rem;
    color: var(--text-danger);
    margin-top: 0.25rem;
  }

  .btn {
    font-family: var(--font-body);
    font-size: 0.75rem;
    padding: 0.25rem 0.6rem;
    border-radius: 4px;
    cursor: pointer;
    border: 1px solid var(--border-subtle);
    transition: all var(--transition-fast);
  }
  .btn-save {
    background: var(--bg-active);
    color: var(--text-primary);
    border-color: var(--bg-active);
  }
  .btn-save:hover {
    background: var(--bg-active-focused);
  }
  .btn-cancel {
    background: none;
    color: var(--text-secondary);
  }
  .btn-cancel:hover {
    color: var(--text-primary);
  }
  .btn-add {
    background: var(--bg-active);
    color: var(--text-primary);
    border-color: var(--bg-active);
    margin-top: 0.4rem;
  }
  .btn-add:hover {
    background: var(--bg-active-focused);
  }

  .add-section {
    border-top: 1px solid var(--border-subtle);
    padding: 0.75rem;
    flex-shrink: 0;
  }

  .add-header {
    font-family: var(--font-heading);
    font-size: 0.8rem;
    color: var(--text-accent);
    margin-bottom: 0.5rem;
  }

  .add-form {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }

  .add-row {
    display: flex;
    gap: 0.4rem;
  }
</style>
