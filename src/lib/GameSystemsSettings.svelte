<script lang="ts">
  import { invoke } from '@tauri-apps/api/core';
  import type { KnownGameSystem } from './types';
  import ActionButton from './ActionButton.svelte';

  export let knownSystems: KnownGameSystem[] = [];
  export let onSystemsChanged: () => void = () => {};

  // Sort state
  let sortDirection: 'asc' | 'desc' = 'asc';

  function toggleSort() {
    sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
  }

  $: sorted = [...knownSystems].sort((a, b) => {
    const cmp = a.tag.localeCompare(b.tag, undefined, { sensitivity: 'base' });
    return sortDirection === 'desc' ? -cmp : cmp;
  });

  // Modal state
  let showModal = false;
  let modalMode: 'add' | 'edit' = 'add';
  let modalTag = '';
  let modalKeywords = '';
  let modalError = '';
  let editOriginalTag = '';
  let editIsBuiltin = false;
  let editIsCustomized = false;

  function openAddModal() {
    modalMode = 'add';
    modalTag = '';
    modalKeywords = '';
    modalError = '';
    editOriginalTag = '';
    editIsBuiltin = false;
    editIsCustomized = false;
    showModal = true;
  }

  function openEditModal(sys: KnownGameSystem) {
    modalMode = 'edit';
    modalTag = sys.tag;
    modalKeywords = (sys.keywords || []).join(', ');
    modalError = '';
    editOriginalTag = sys.tag;
    editIsBuiltin = sys.is_builtin ?? false;
    editIsCustomized = sys.is_customized ?? false;
    showModal = true;
  }

  function closeModal() {
    showModal = false;
    modalError = '';
  }

  function handleModalKeydown(e: KeyboardEvent) {
    if (e.key === 'Escape') closeModal();
  }

  function handleBackdrop(e: MouseEvent) {
    if (e.target === e.currentTarget) closeModal();
  }

  function parseKeywords(raw: string): string[] {
    return raw.split(',').map(k => k.trim().toLowerCase()).filter(k => k.length > 0);
  }

  async function handleSave() {
    const tag = modalTag.trim();
    if (!tag) { modalError = 'Tag is required'; return; }
    const keywords = parseKeywords(modalKeywords);

    try {
      if (modalMode === 'add') {
        await invoke('create_custom_game_system', { tag, keywords });
      } else {
        // Edit mode: works for both custom and built-in (backend creates override if needed)
        await invoke('update_custom_game_system', { originalTag: editOriginalTag, tag, keywords });
      }
      closeModal();
      onSystemsChanged();
    } catch (e: any) {
      modalError = e?.toString()?.replace(/^.*?:\s*/, '') || 'Failed to save';
    }
  }

  async function handleDelete() {
    try {
      await invoke('delete_custom_game_system', { tag: editOriginalTag });
      closeModal();
      onSystemsChanged();
    } catch (e: any) {
      modalError = e?.toString()?.replace(/^.*?:\s*/, '') || 'Failed to delete';
    }
  }

  async function handleReset() {
    try {
      await invoke('delete_custom_game_system', { tag: editOriginalTag });
      closeModal();
      onSystemsChanged();
    } catch (e: any) {
      modalError = e?.toString()?.replace(/^.*?:\s*/, '') || 'Failed to reset';
    }
  }
</script>

<div class="game-systems-settings">
  <div class="list-header">
    <button class="col-header col-tag" on:click={toggleSort}>Tag</button>
    <span class="col-header col-keywords">Keywords</span>
    <button class="add-btn" title="Add custom system" on:click={openAddModal}>+</button>
  </div>
  <div class="systems-list">
    {#each sorted as sys}
      <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
      <div class="system-row" on:click={() => openEditModal(sys)}>
        <span class="system-tag">{sys.tag}</span>
        <span class="system-keywords">{(sys.keywords || []).slice(0, 3).join(', ')}{(sys.keywords || []).length > 3 ? '...' : ''}</span>
        <div class="system-labels">
          {#if sys.is_builtin}
            <span class="label builtin-label">{sys.is_customized ? 'customized' : 'built-in'}</span>
          {:else}
            <span class="label custom-label">custom</span>
          {/if}
        </div>
      </div>
    {/each}
  </div>
</div>

{#if showModal}
  <!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
  <div class="modal-backdrop" role="dialog" aria-modal="true" aria-label="{modalMode === 'add' ? 'Add' : 'Edit'} Game System" tabindex="-1" on:click={handleBackdrop} on:keydown={handleModalKeydown}>
    <div class="modal">
      <div class="modal-header">
        <span class="modal-title font-heading">{modalMode === 'add' ? 'Add Game System' : 'Edit Game System'}</span>
        <button class="close-btn" on:click={closeModal} aria-label="Close">&times;</button>
      </div>
      <div class="modal-body">
        <label class="field-label" for="sys-tag">Tag</label>
        <input id="sys-tag" class="field-input" bind:value={modalTag} placeholder="e.g. Cairn" on:keydown={(e) => e.key === 'Enter' && handleSave()} />

        <label class="field-label" for="sys-keywords">Keywords</label>
        <input id="sys-keywords" class="field-input" bind:value={modalKeywords} placeholder="Comma-separated keywords for auto-detection" on:keydown={(e) => e.key === 'Enter' && handleSave()} />

        {#if modalError}
          <div class="error-msg">{modalError}</div>
        {/if}
      </div>
      <div class="modal-footer">
        <div class="footer-left">
          {#if modalMode === 'edit' && editIsBuiltin && editIsCustomized}
            <button class="btn btn-reset" on:click={handleReset}>Reset to defaults</button>
          {/if}
          {#if modalMode === 'edit' && !editIsBuiltin}
            <button class="btn btn-delete" on:click={handleDelete}>Delete</button>
          {/if}
        </div>
        <div class="footer-right">
          <ActionButton kind="discard" label="Cancel" onClick={closeModal} />
          <ActionButton kind="confirm" label={modalMode === 'add' ? 'Add System' : 'Save'} onClick={handleSave} />
        </div>
      </div>
    </div>
  </div>
{/if}

<style>
  .game-systems-settings {
    display: flex;
    flex-direction: column;
    height: 100%;
  }

  .list-header {
    display: flex;
    align-items: center;
    padding: 0.35rem 0.75rem;
    gap: 0.5rem;
    border-bottom: 1px solid var(--border-subtle);
    flex-shrink: 0;
  }

  .col-header {
    background: none;
    border: none;
    font-family: var(--font-body);
    font-size: 0.7rem;
    font-weight: 600;
    color: var(--text-secondary);
    text-align: left;
    padding: 0;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    transition: color var(--transition-fast);
  }

  button.col-header {
    cursor: pointer;
  }
  button.col-header:hover {
    color: var(--text-primary);
  }

  .col-tag {
    min-width: 80px;
    flex-shrink: 0;
  }

  .col-keywords {
    flex: 1;
    cursor: default;
  }

  .add-btn {
    background: none;
    border: 1px solid var(--border-subtle);
    color: var(--text-secondary);
    font-size: 1rem;
    line-height: 1;
    width: 1.5rem;
    height: 1.5rem;
    border-radius: 4px;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    transition: all var(--transition-fast);
  }
  .add-btn:hover {
    color: var(--text-accent);
    border-color: var(--text-accent);
  }

  .systems-list {
    flex: 1;
    overflow-y: auto;
    padding: 0.25rem 0;
  }

  .system-row {
    display: flex;
    align-items: center;
    padding: 0.35rem 0.75rem;
    gap: 0.5rem;
    cursor: pointer;
    transition: background var(--transition-fast);
  }
  .system-row:hover {
    background: var(--bg-focused);
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

  .system-labels {
    display: flex;
    gap: 0.25rem;
    flex-shrink: 0;
  }

  .label {
    font-size: 0.65rem;
    padding: 0.1rem 0.3rem;
    border-radius: 3px;
  }

  .builtin-label {
    color: var(--text-tertiary);
    border: 1px solid var(--border-subtle);
  }

  .custom-label {
    color: var(--text-accent);
    border: 1px solid var(--border-accent);
  }

  /* Modal */
  .modal-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 110;
  }

  .modal {
    background: var(--bg-container);
    border: 1px solid var(--border-subtle);
    border-radius: 8px;
    width: min(400px, 85vw);
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
    display: flex;
    flex-direction: column;
  }

  .modal-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.75rem 1rem;
    border-bottom: 1px solid var(--border-subtle);
  }

  .modal-title {
    font-size: 1rem;
    color: var(--text-accent);
  }

  .close-btn {
    background: none;
    border: none;
    color: var(--text-secondary);
    font-size: 1.4rem;
    line-height: 1;
    padding: 0.1rem 0.4rem;
    border-radius: 4px;
    cursor: pointer;
    transition: color var(--transition-fast);
  }
  .close-btn:hover {
    color: var(--text-primary);
  }

  .modal-body {
    padding: 1rem;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .field-label {
    font-family: var(--font-body);
    font-size: 0.75rem;
    color: var(--text-secondary);
    margin-bottom: -0.25rem;
  }

  .field-input {
    font-family: var(--font-body);
    font-size: 0.85rem;
    padding: 0.4rem 0.6rem;
    background: var(--bg-app);
    border: 1px solid var(--border-subtle);
    border-radius: 4px;
    color: var(--text-primary);
    outline: none;
    width: 100%;
    box-sizing: border-box;
  }
  .field-input:focus {
    border-color: var(--text-accent);
  }

  .error-msg {
    font-size: 0.75rem;
    color: var(--text-danger);
  }

  .modal-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.75rem 1rem;
    border-top: 1px solid var(--border-subtle);
    gap: 0.5rem;
  }

  .footer-left, .footer-right {
    display: flex;
    gap: 0.4rem;
  }

  .btn {
    font-family: var(--font-body);
    font-size: 0.8rem;
    padding: 0.3rem 0.75rem;
    border-radius: 4px;
    cursor: pointer;
    border: 1px solid var(--border-subtle);
    transition: all var(--transition-fast);
  }

  .btn-delete {
    background: none;
    color: var(--text-danger);
    border-color: var(--text-danger);
  }
  .btn-delete:hover {
    background: var(--text-danger);
    color: var(--text-inverse);
  }

  .btn-reset {
    background: none;
    color: var(--text-secondary);
  }
  .btn-reset:hover {
    color: var(--text-primary);
  }
</style>
