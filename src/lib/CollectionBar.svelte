<script lang="ts">
  import type { CollectionInfo } from './types';

  export let collections: Record<string, CollectionInfo> = {};
  export let editingName: string | null = null;
  export let isCreating: boolean = false;
  export let editName: string = '';
  export let editDescription: string = '';
  export let editFileCount: number = 0;
  export let highlightedName: string | null = null;

  export let onStartCreate: () => void = () => {};
  export let onStartEdit: (name: string) => void = () => {};
  export let onSave: () => void = () => {};
  export let onCancel: () => void = () => {};
  export let onDelete: (name: string) => void = () => {};
  export let onHighlight: (name: string | null) => void = () => {};

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
          on:click={() => handleChipClick(col.name)}
        >
          <span class="chip-name">{col.name}</span>
          <span class="chip-count">{col.file_count}</span>
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
    margin-top: 0.5rem;
  }
  .chips-row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.4rem;
  }
  .label {
    font-size: 0.85rem;
    color: #666;
    margin-right: 0.25rem;
  }
  .chip {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    padding: 0.2rem 0.5rem;
    border-radius: 12px;
    font-size: 0.8rem;
    background: #ede7f6;
    color: #5e35b1;
    border: 1px solid transparent;
    cursor: pointer;
    transition: border-color 0.15s;
  }
  .chip:hover {
    border-color: #b39ddb;
  }
  .chip.highlighted {
    border-color: #7c4dff;
    background: #d1c4e9;
  }
  .chip-name {
    font-weight: 500;
  }
  .chip-count {
    font-size: 0.7rem;
    opacity: 0.7;
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
  .chip-action.edit {
    color: #5e35b1;
  }
  .chip-action.delete {
    color: #c62828;
  }
  .chip-action.delete.confirming {
    color: #c62828;
    opacity: 1;
    font-weight: bold;
  }
  .new-chip {
    background: transparent;
    border: 1px dashed #b39ddb;
    color: #7c4dff;
  }
  .new-chip:hover {
    background: #ede7f6;
    border-color: #7c4dff;
  }

  /* Edit form */
  .edit-form {
    background: #f5f0ff;
    border: 1px solid #d1c4e9;
    border-radius: 6px;
    padding: 0.75rem;
  }
  .edit-header {
    font-weight: 600;
    font-size: 0.9rem;
    color: #4a148c;
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
    color: #666;
    flex: 1;
  }
  .edit-input {
    margin-top: 0.2rem;
    padding: 0.3rem 0.5rem;
    border: 1px solid #d1c4e9;
    border-radius: 4px;
    font-size: 0.85rem;
  }
  .edit-input:focus {
    outline: none;
    border-color: #7c4dff;
  }
  .edit-actions {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  .file-count {
    font-size: 0.8rem;
    color: #666;
    margin-right: auto;
  }
  .btn {
    padding: 0.3rem 0.7rem;
    border-radius: 4px;
    border: 1px solid transparent;
    font-size: 0.8rem;
    cursor: pointer;
  }
  .btn:disabled {
    opacity: 0.4;
    cursor: default;
  }
  .btn-save {
    background: #7c4dff;
    color: white;
  }
  .btn-save:hover:not(:disabled) {
    background: #651fff;
  }
  .btn-cancel {
    background: #f5f5f5;
    color: #666;
    border-color: #ccc;
  }
  .btn-cancel:hover {
    background: #eee;
  }
  .btn-delete {
    background: transparent;
    color: #c62828;
    border-color: #c62828;
  }
  .btn-delete:hover {
    background: #fce4ec;
  }
</style>
