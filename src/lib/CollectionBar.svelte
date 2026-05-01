<script lang="ts">
  import type { CollectionInfo } from './types';

  export let collections: Record<string, CollectionInfo> = {};
  export let editingName: string | null = null;
  export let isCreating: boolean = false;
  export let editName: string = '';
  export let editDescription: string = '';
  export let editFileCount: number = 0;
  export let highlightedName: string | null = null;
  export let activeName: string | null = null;

  export let onStartCreate: () => void = () => {};
  export let onStartEdit: (name: string) => void = () => {};
  export let onSave: () => void = () => {};
  export let onCancel: () => void = () => {};
  export let onDelete: (name: string) => void = () => {};
  export let onHighlight: (name: string | null) => void = () => {};
  export let onToggleActive: (name: string) => void = () => {};

  let confirmingDelete: string | null = null;

  $: isEditMode = editingName !== null || isCreating;
  $: collectionList = Object.values(collections);

  function handleChipClick(name: string) {
    if (isEditMode) return;
    onHighlight(highlightedName === name ? null : name);
  }

  function handleEdit(event: MouseEvent, name: string) {
    event.stopPropagation();
    confirmingDelete = null;
    onStartEdit(name);
  }

  function handlePin(event: MouseEvent, name: string) {
    event.stopPropagation();
    confirmingDelete = null;
    onToggleActive(name);
  }

  function handleDeleteClick(event: MouseEvent, name: string) {
    event.stopPropagation();
    if (confirmingDelete === name) {
      onDelete(name);
      confirmingDelete = null;
    } else {
      confirmingDelete = name;
    }
  }

  function handleDeleteBlur() {
    confirmingDelete = null;
  }

  let nameInput: HTMLInputElement;

  $: if (isEditMode && nameInput) {
    nameInput.focus();
  }
</script>

<div class="collection-bar">
  {#if !isEditMode}
    <div class="chips-row">
      <span class="label">Collections</span>
      {#each collectionList as col}
        <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
        <div
          class="chip"
          class:highlighted={highlightedName === col.name}
          class:active={activeName === col.name}
          on:click={() => handleChipClick(col.name)}
        >
          <span class="chip-name">{col.name}</span>
          <span class="chip-count">{col.file_count}</span>
          <button
            class="chip-action pin"
            class:on={activeName === col.name}
            on:click={(e) => handlePin(e, col.name)}
            title={activeName === col.name ? 'Clear active context' : 'Set as active context'}
          >
            &#9733;
          </button>
          <button class="chip-action edit" on:click={(e) => handleEdit(e, col.name)} title="Edit">
            &#9998;
          </button>
          <button
            class="chip-action delete"
            class:confirming={confirmingDelete === col.name}
            on:click={(e) => handleDeleteClick(e, col.name)}
            on:blur={handleDeleteBlur}
            title={confirmingDelete === col.name ? 'Click again to confirm' : 'Delete'}
          >
            {confirmingDelete === col.name ? '?' : '\u00d7'}
          </button>
        </div>
      {/each}
      <button class="chip new-chip" on:click={onStartCreate}>
        + New Collection
      </button>
    </div>
  {:else}
    <div class="edit-form">
      <div class="edit-header">
        {#if isCreating}
          New Collection
        {:else}
          Editing: {editingName}
        {/if}
      </div>
      <div class="edit-fields">
        <label class="edit-label">
          Name
          <input
            type="text"
            bind:value={editName}
            bind:this={nameInput}
            placeholder="e.g. Curse of Strahd Prep"
            class="edit-input"
          />
        </label>
        <label class="edit-label">
          Description
          <input
            type="text"
            bind:value={editDescription}
            placeholder="Optional"
            class="edit-input"
          />
        </label>
      </div>
      <div class="edit-actions">
        <span class="file-count">{editFileCount} file{editFileCount === 1 ? '' : 's'} selected</span>
        {#if editingName}
          <button class="btn btn-delete" on:click={(e) => handleDeleteClick(e, editingName ?? '')}>
            {confirmingDelete === editingName ? 'Confirm Delete' : 'Delete'}
          </button>
        {/if}
        <button class="btn btn-cancel" on:click={onCancel}>Cancel</button>
        <button class="btn btn-save" on:click={onSave} disabled={!editName.trim()}>Save</button>
      </div>
    </div>
  {/if}
</div>

<style>
  .collection-bar {
    display: contents;
  }
  .chips-row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.4rem;
  }
  .label {
    font-size: 0.85rem;
    font-family: var(--font-heading);
    color: var(--text-secondary);
    margin-right: 0.25rem;
    -webkit-user-select: none;
    user-select: none;
  }
  .chip {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    padding: 0.2rem 0.6rem;
    border-radius: 12px;
    font-size: 0.8rem;
    font-family: var(--font-body);
    background: var(--bg-focused);
    color: var(--text-primary);
    border: 1px solid var(--bg-category);
    cursor: pointer;
    transition: all var(--transition-fast);
  }
  .chip:hover {
    border-color: var(--text-accent);
  }
  .chip.highlighted {
    border-color: var(--text-accent);
    background: rgba(182, 159, 129, 0.15);
    color: var(--text-accent);
  }
  .chip.active {
    border-color: var(--text-accent);
    border-width: 2px;
    padding: calc(0.2rem - 1px) calc(0.6rem - 1px);
    background: rgba(182, 159, 129, 0.2);
    color: var(--text-accent);
    font-weight: 600;
  }
  .chip-name {
    font-weight: 500;
  }
  .chip-count {
    font-size: 0.7rem;
    opacity: 0.6;
  }
  .chip-action {
    display: none;
    padding: 0;
    margin: 0;
    border: none;
    background: none;
    cursor: pointer;
    font-size: 0.75rem;
    line-height: 1;
    opacity: 0.5;
  }
  .chip:hover .chip-action {
    display: inline;
  }
  .chip-action:hover {
    opacity: 1;
  }
  .chip-action.pin {
    color: var(--text-secondary);
  }
  .chip-action.pin.on {
    display: inline;
    opacity: 1;
    color: var(--text-accent);
  }
  .chip-action.edit {
    color: var(--text-secondary);
  }
  .chip-action.delete {
    color: var(--text-danger);
  }
  .chip-action.delete.confirming {
    color: var(--text-danger);
    opacity: 1;
    font-weight: bold;
  }
  .new-chip {
    background: transparent;
    border: 1px dashed var(--bg-category);
    color: var(--text-secondary);
  }
  .new-chip:hover {
    border-color: var(--text-accent);
    color: var(--text-accent);
  }

  /* Edit form */
  .edit-form {
    background: var(--bg-focused);
    border: 1px solid var(--bg-category);
    border-radius: 6px;
    padding: 0.75rem;
  }
  .edit-header {
    font-weight: 600;
    font-size: 0.9rem;
    font-family: var(--font-heading);
    color: var(--text-accent);
    margin-bottom: 0.5rem;
  }
  .edit-fields {
    display: flex;
    gap: 0.75rem;
    margin-bottom: 0.5rem;
  }
  .edit-label {
    display: flex;
    flex-direction: column;
    font-size: 0.75rem;
    color: var(--text-secondary);
    flex: 1;
  }
  .edit-input {
    margin-top: 0.2rem;
    padding: 0.3rem 0.5rem;
    border: 1px solid var(--bg-category);
    border-radius: 4px;
    font-size: 0.85rem;
    background: var(--bg-container);
    color: var(--text-primary);
  }
  .edit-input:focus {
    outline: none;
    border-color: var(--text-accent);
  }
  .edit-actions {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  .file-count {
    font-size: 0.8rem;
    color: var(--text-secondary);
    margin-right: auto;
  }
  .btn {
    padding: 0.3rem 0.7rem;
    border-radius: 4px;
    border: 1px solid transparent;
    font-size: 0.8rem;
    font-family: var(--font-body);
    cursor: pointer;
    transition: all var(--transition-fast);
  }
  .btn:disabled {
    opacity: 0.4;
    cursor: default;
  }
  .btn:active:not(:disabled) {
    transform: scale(0.97);
  }
  .btn-save {
    background: var(--bg-active);
    color: var(--text-primary);
  }
  .btn-save:hover:not(:disabled) {
    background: var(--bg-active-focused);
  }
  .btn-cancel {
    background: var(--bg-focused);
    color: var(--text-secondary);
    border-color: var(--bg-category);
  }
  .btn-cancel:hover {
    background: var(--bg-container);
  }
  .btn-delete {
    background: transparent;
    color: var(--text-danger);
    border-color: var(--text-danger);
  }
  .btn-delete:hover {
    background: rgba(239, 68, 68, 0.1);
  }
</style>
