<script lang="ts">
  import type { CollectionInfo } from './types';

  export let collection: CollectionInfo;
  export let onSave: (changes: {
    name: string;
    description: string;
    color: string;
    archived: boolean;
  }) => void = () => {};
  export let onCancel: () => void = () => {};

  let name = collection.name;
  let description = collection.description;
  let color = collection.color ?? '';
  let archived = collection.archived;

  const PALETTE: string[] = [
    '#c75450', // red
    '#d49449', // orange
    '#caa84b', // amber
    '#5fb068', // green
    '#4fa896', // teal
    '#5a8dc4', // blue
    '#9b6cb6', // purple
    '#b69f81', // tan (matches accent)
  ];

  let nameInput: HTMLInputElement;
  $: if (nameInput) nameInput.focus();

  $: dirty =
    name !== collection.name ||
    description !== collection.description ||
    (color || '') !== (collection.color ?? '') ||
    archived !== collection.archived;
  $: canSave = name.trim().length > 0 && dirty;

  function handleKey(event: KeyboardEvent) {
    if (event.key === 'Escape') onCancel();
    else if (event.key === 'Enter' && canSave && (event.metaKey || event.ctrlKey)) {
      submit();
    }
  }

  function submit() {
    if (!canSave) return;
    onSave({
      name: name.trim(),
      description: description.trim(),
      color,
      archived,
    });
  }

  function pickColor(c: string) {
    color = color === c ? '' : c;
  }
</script>

<svelte:window on:keydown={handleKey} />

<!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
<div class="backdrop" on:click={onCancel}>
  <div class="dialog" on:click|stopPropagation>
    <div class="title">Edit collection</div>

    <label class="field">
      <span class="label">Name</span>
      <input
        type="text"
        bind:value={name}
        bind:this={nameInput}
        class="input"
        placeholder="Collection name"
      />
    </label>

    <label class="field">
      <span class="label">Description</span>
      <input
        type="text"
        bind:value={description}
        class="input"
        placeholder="Optional"
      />
    </label>

    <div class="field">
      <span class="label">Color</span>
      <div class="palette">
        <button
          class="swatch none"
          class:selected={!color}
          on:click={() => { color = ''; }}
          title="No color"
          aria-label="No color"
        >
          &times;
        </button>
        {#each PALETTE as c}
          <button
            class="swatch"
            class:selected={color === c}
            style="background: {c}"
            on:click={() => pickColor(c)}
            title={c}
            aria-label={`Color ${c}`}
          ></button>
        {/each}
      </div>
    </div>

    <label class="field row">
      <input type="checkbox" bind:checked={archived} />
      <span class="row-label">
        <span class="label inline">Archived</span>
        <span class="hint">Hidden from the chip bar; visible in the panel via "Show archived"</span>
      </span>
    </label>

    <div class="actions">
      <button class="btn cancel" on:click={onCancel}>Cancel</button>
      <button class="btn save" on:click={submit} disabled={!canSave}>Save</button>
    </div>
  </div>
</div>

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 310;
  }
  .dialog {
    background: var(--bg-focused);
    border: 1px solid var(--bg-category);
    border-radius: 6px;
    box-shadow: var(--shadow-dropdown);
    padding: 1rem 1.25rem;
    min-width: 380px;
    max-width: 480px;
    font-family: var(--font-body);
  }
  .title {
    font-family: var(--font-heading);
    font-size: 1rem;
    font-weight: 600;
    color: var(--text-accent);
    margin-bottom: 0.75rem;
  }
  .field {
    display: flex;
    flex-direction: column;
    margin-bottom: 0.75rem;
    font-size: 0.85rem;
  }
  .field.row {
    flex-direction: row;
    align-items: flex-start;
    gap: 0.5rem;
    cursor: pointer;
  }
  .row-label {
    display: flex;
    flex-direction: column;
    gap: 0.1rem;
  }
  .label {
    color: var(--text-secondary);
    font-size: 0.75rem;
    margin-bottom: 0.2rem;
  }
  .label.inline {
    font-size: 0.85rem;
    color: var(--text-primary);
    margin-bottom: 0;
  }
  .hint {
    font-size: 0.75rem;
    color: var(--text-secondary);
  }
  .input {
    padding: 0.4rem 0.55rem;
    border: 1px solid var(--bg-category);
    border-radius: 4px;
    font-size: 0.9rem;
    background: var(--bg-container);
    color: var(--text-primary);
  }
  .input:focus {
    outline: none;
    border-color: var(--text-accent);
  }
  .palette {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
  }
  .swatch {
    width: 22px;
    height: 22px;
    border-radius: 50%;
    border: 2px solid transparent;
    cursor: pointer;
    padding: 0;
    transition: transform var(--transition-fast);
  }
  .swatch:hover {
    transform: scale(1.1);
  }
  .swatch.selected {
    border-color: var(--text-primary);
  }
  .swatch.none {
    background: transparent;
    border: 1px dashed var(--text-secondary);
    color: var(--text-secondary);
    font-size: 0.85rem;
    line-height: 1;
  }
  .swatch.none.selected {
    border-color: var(--text-primary);
    border-style: solid;
  }
  .actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.5rem;
    margin-top: 0.5rem;
  }
  .btn {
    padding: 0.4rem 0.9rem;
    border-radius: 4px;
    border: 1px solid transparent;
    font-size: 0.85rem;
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
  .cancel {
    background: var(--bg-focused);
    color: var(--text-secondary);
    border-color: var(--bg-category);
  }
  .cancel:hover {
    background: var(--bg-container);
  }
  .save {
    background: var(--bg-active);
    color: var(--text-primary);
  }
  .save:hover:not(:disabled) {
    background: var(--bg-active-focused);
  }
</style>
