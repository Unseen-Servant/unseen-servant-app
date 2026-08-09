<script lang="ts">
  import { invoke } from '@tauri-apps/api/core';
  import type { KnownGameSystem } from './types';
  import Modal from './Modal.svelte';
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
  // Stored color rides along untouched on edit — nothing in the UI reads
  // or writes system colors anymore (color belongs to collections).
  let modalColor: string | null = null;
  let modalError = '';
  let editOriginalTag = '';
  let editOriginalKeywords = '';
  let editIsBuiltin = false;
  let editIsCustomized = false;

  let tagInput: HTMLInputElement;

  // Auto-focus the first input when the modal opens.
  $: if (showModal && tagInput) tagInput.focus();

  // Save is enabled only when there is a tag and either we're adding
  // or the user actually changed something — same convention as the
  // Collection modal.
  $: dirty = modalMode === 'add' || (
    modalTag.trim() !== editOriginalTag ||
    modalKeywords !== editOriginalKeywords
  );
  $: canSave = modalTag.trim().length > 0 && dirty;

  function openAddModal() {
    modalMode = 'add';
    modalTag = '';
    modalKeywords = '';
    modalColor = null;
    modalError = '';
    editOriginalTag = '';
    editOriginalKeywords = '';
    editIsBuiltin = false;
    editIsCustomized = false;
    showModal = true;
  }

  function openEditModal(sys: KnownGameSystem) {
    modalMode = 'edit';
    modalTag = sys.tag;
    modalKeywords = (sys.keywords || []).join(', ');
    modalColor = sys.color ?? null;
    modalError = '';
    editOriginalTag = sys.tag;
    editOriginalKeywords = modalKeywords;
    editIsBuiltin = sys.is_builtin ?? false;
    editIsCustomized = sys.is_customized ?? false;
    showModal = true;
  }

  function closeModal() {
    showModal = false;
    modalError = '';
  }

  function handleWindowKey(event: KeyboardEvent) {
    if (!showModal) return;
    if (event.key !== 'Enter' || !canSave) return;
    // Plain Enter saves from any text input (matches the rest of the
    // app's "Enter commits" feel); Cmd/Ctrl+Enter still works globally.
    const target = event.target as HTMLElement | null;
    const inTextInput = target instanceof HTMLInputElement && target.type === 'text';
    if (event.metaKey || event.ctrlKey || inTextInput) {
      event.preventDefault();
      handleSave();
    }
  }

  function parseKeywords(raw: string): string[] {
    return raw.split(',').map(k => k.trim().toLowerCase()).filter(k => k.length > 0);
  }

  async function handleSave() {
    const tag = modalTag.trim();
    if (!tag) { modalError = 'Tag is required'; return; }
    const keywords = parseKeywords(modalKeywords);
    const color = modalColor || null;

    try {
      if (modalMode === 'add') {
        await invoke('create_custom_game_system', { tag, keywords, color });
      } else {
        // Edit mode: works for both custom and built-in (backend creates override if needed)
        await invoke('update_custom_game_system', { originalTag: editOriginalTag, tag, keywords, color });
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

<svelte:window on:keydown={handleWindowKey} />

<div class="game-systems-settings">
  <div class="list-header">
    <button class="col-header col-tag ledger-label" on:click={toggleSort}>Tag</button>
    <span class="col-header col-keywords ledger-label">Keywords</span>
    <button class="add-btn" title="Add custom system" on:click={openAddModal}>+</button>
  </div>
  <div class="systems-list">
    {#each sorted as sys}
      <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
      <div class="system-row" on:click={() => openEditModal(sys)}>
        <span class="system-icon" aria-hidden="true">
          <!-- Font Awesome "dice-d6" -->
          <svg viewBox="0 0 640 640" fill="currentColor">
            <path d="M288.4 72.3C308 61.2 332 61.2 351.6 72.3L527.6 172C547.6 183.4 560 204.6 560 227.7L560 425.1C560 448.1 547.6 469.4 527.6 480.8L351.6 580.5C332 591.6 308 591.6 288.5 580.5L112.5 480.8C92.4 469.5 80 448.2 80 425.2L80 227.8C80 204.8 92.4 183.5 112.4 172.1L288.4 72.4zM166.6 219.6C157.8 216.5 147.8 219.9 142.8 228.2C137.8 236.5 139.6 246.9 146.4 253.2L149.6 255.6L299.8 345.8L299.8 494.5C299.8 505.5 308.8 514.5 319.8 514.5C330.8 514.5 339.8 505.5 339.8 494.5L339.8 345.8L490.1 255.6C499.6 249.9 502.7 237.6 497 228.2C491.3 218.8 479 215.7 469.6 221.3L319.9 311.1L170.2 221.3L166.5 219.6z"/>
          </svg>
        </span>
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

<Modal
  visible={showModal}
  onClose={closeModal}
  title={modalMode === 'add' ? 'Add game system' : 'Edit game system'}
  width="min(440px, 90vw)"
>
  <div class="body">
    <div class="field">
      <span class="label">Tag</span>
      <input
        id="sys-tag"
        type="text"
        class="input"
        bind:value={modalTag}
        bind:this={tagInput}
        placeholder="e.g. Cairn"
      />
    </div>

    <div class="field">
      <span class="label">Keywords</span>
      <input
        id="sys-keywords"
        type="text"
        class="input"
        bind:value={modalKeywords}
        placeholder="e.g. cairn, cairn rpg"
      />
      <p class="hint">
        Comma-separated. Detection checks the file's <strong>folder path</strong> first,
        then scans the <strong>first 2000 characters</strong> of the PDF. Path tokens
        like &ldquo;<em>{modalTag.trim() || 'Cairn'}</em>&rdquo; or its abbreviation
        match best — a folder named that way wins over content.
      </p>
      <p class="hint">
        Matching ignores case, spaces, punctuation, and accents — so
        <em>d&amp;d 5e</em>, <em>dnd-5e</em>, and <em>DnD 5E</em> all match the same
        keyword. Avoid very short keywords (e.g. two-letter abbreviations) since
        they false-positive on unrelated paths.
      </p>
    </div>

    {#if modalError}
      <div class="error-msg">{modalError}</div>
    {/if}

    <div class="footer">
      <div class="footer-left">
        {#if modalMode === 'edit' && editIsBuiltin && editIsCustomized}
          <button class="btn btn-reset" on:click={handleReset}>Reset to defaults</button>
        {/if}
        {#if modalMode === 'edit' && !editIsBuiltin}
          <button class="btn btn-delete" on:click={handleDelete}>Delete</button>
        {/if}
      </div>
      <div class="footer-right">
        <ActionButton kind="discard" label="Discard" onClick={closeModal} />
        <ActionButton kind="confirm" label={modalMode === 'add' ? 'Add' : 'Save'} onClick={handleSave} disabled={!canSave} />
      </div>
    </div>
  </div>
</Modal>

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
    color: var(--text-secondary);
    text-align: left;
    padding: 0;
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
    /* Push the tag-column header past the icon column on each row. */
    padding-left: 1rem;
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
    border-radius: var(--radius-md);
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

  .system-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    color: var(--text-accent);
  }
  .system-icon svg {
    width: 0.85rem;
    height: 0.85rem;
    display: block;
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
    border-radius: var(--radius-sm);
  }

  .builtin-label {
    color: var(--text-tertiary);
    border: 1px solid var(--border-subtle);
  }

  .custom-label {
    color: var(--text-accent);
    border: 1px solid var(--border-accent);
  }

  /* Modal body */
  .body {
    padding: 0.85rem 1rem 1rem;
    font-family: var(--font-body);
  }
  .field {
    display: flex;
    flex-direction: column;
    margin-bottom: 0.75rem;
    font-size: 0.85rem;
  }
  .label {
    font-family: var(--font-heading, var(--font-body));
    font-size: 0.7rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--text-secondary);
    margin-bottom: 0.3rem;
  }
  .input {
    padding: 0.4rem 0.6rem;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    font-family: var(--font-body);
    font-size: 0.85rem;
    background: var(--bg-focused);
    color: var(--text-primary);
  }
  .input:focus {
    outline: 1px solid var(--text-accent);
    outline-offset: -1px;
    border-color: var(--border-subtle);
  }

  .hint {
    margin: 0.4rem 0 0;
    font-family: var(--font-body);
    font-size: 0.75rem;
    color: var(--text-secondary);
    line-height: 1.4;
  }
  .hint strong {
    color: var(--text-primary);
    font-weight: 600;
  }
  .hint em {
    font-style: normal;
    color: var(--text-accent);
  }

  .error-msg {
    font-size: 0.75rem;
    color: var(--text-danger);
    margin-bottom: 0.5rem;
  }

  .footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-top: 0.5rem;
    gap: 0.5rem;
  }
  .footer-left,
  .footer-right {
    display: flex;
    gap: 0.4rem;
  }

  .btn {
    font-family: var(--font-body);
    font-size: 0.8rem;
    padding: 0.3rem 0.75rem;
    border-radius: var(--radius-md);
    cursor: pointer;
    border: 1px solid var(--border-subtle);
    background: none;
    transition: all var(--transition-fast);
  }
  .btn-delete {
    color: var(--text-danger);
    border-color: var(--text-danger);
  }
  .btn-delete:hover {
    background: var(--text-danger);
    color: var(--text-inverse);
  }
  .btn-reset {
    color: var(--text-secondary);
  }
  .btn-reset:hover {
    color: var(--text-primary);
  }
</style>
