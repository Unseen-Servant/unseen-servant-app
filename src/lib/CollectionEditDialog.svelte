<script lang="ts">
  import type { CollectionInfo } from './types';
  import Modal from './Modal.svelte';
  import ActionButton from './ActionButton.svelte';

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
  let colorBtn: HTMLButtonElement;
  let colorMenuEl: HTMLDivElement;
  let colorMenuOpen = false;

  $: if (nameInput) nameInput.focus();

  $: dirty =
    name !== collection.name ||
    description !== collection.description ||
    (color || '') !== (collection.color ?? '') ||
    archived !== collection.archived;
  $: canSave = name.trim().length > 0 && dirty;

  function handleKey(event: KeyboardEvent) {
    if (event.key === 'Escape' && colorMenuOpen) {
      colorMenuOpen = false;
      return;
    }
    if (event.key === 'Enter' && canSave && (event.metaKey || event.ctrlKey)) {
      submit();
    }
  }

  function handleWindowClick(event: MouseEvent) {
    if (!colorMenuOpen) return;
    const target = event.target as Node;
    if (colorBtn && (colorBtn === target || colorBtn.contains(target))) return;
    if (colorMenuEl && colorMenuEl.contains(target)) return;
    colorMenuOpen = false;
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
    color = c;
    colorMenuOpen = false;
  }
</script>

<svelte:window on:keydown={handleKey} on:click={handleWindowClick} />

<Modal visible={true} onClose={onCancel} title="Edit collection" width="min(440px, 90vw)">
  <div class="body">
    <div class="field">
      <span class="label">Name</span>
      <div class="name-row">
        <input
          type="text"
          bind:value={name}
          bind:this={nameInput}
          class="input"
          placeholder="Collection name"
        />
        <div class="color-wrapper">
          <button
            type="button"
            class="color-trigger"
            class:open={colorMenuOpen}
            on:click|stopPropagation={() => { colorMenuOpen = !colorMenuOpen; }}
            bind:this={colorBtn}
            title={color || 'No color'}
            aria-label="Collection color"
            aria-haspopup="menu"
            aria-expanded={colorMenuOpen}
          >
            <span
              class="color-icon"
              class:none={!color}
              style={color ? `color: ${color}` : ''}
              aria-hidden="true"
            >
              <!-- Font Awesome "book" -->
              <svg viewBox="0 0 640 640" fill="currentColor">
                <path d="M480 576L192 576C139 576 96 533 96 480L96 160C96 107 139 64 192 64L496 64C522.5 64 544 85.5 544 112L544 400C544 420.9 530.6 438.7 512 445.3L512 512C529.7 512 544 526.3 544 544C544 561.7 529.7 576 512 576L480 576zM192 448C174.3 448 160 462.3 160 480C160 497.7 174.3 512 192 512L448 512L448 448L192 448zM224 216C224 229.3 234.7 240 248 240L424 240C437.3 240 448 229.3 448 216C448 202.7 437.3 192 424 192L248 192C234.7 192 224 202.7 224 216zM248 288C234.7 288 224 298.7 224 312C224 325.3 234.7 336 248 336L424 336C437.3 336 448 325.3 448 312C448 298.7 437.3 288 424 288L248 288z"/>
              </svg>
            </span>
          </button>
          {#if colorMenuOpen}
            <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
            <div
              class="color-menu"
              bind:this={colorMenuEl}
              on:click|stopPropagation
            >
              <button
                type="button"
                class="swatch none"
                class:selected={!color}
                on:click={() => pickColor('')}
                title="No color"
                aria-label="No color"
              >&times;</button>
              {#each PALETTE as c}
                <button
                  type="button"
                  class="swatch"
                  class:selected={color === c}
                  style="color: {c}"
                  on:click={() => pickColor(c)}
                  title={c}
                  aria-label={`Color ${c}`}
                >
                  <!-- "books" — collection-of-books glyph -->
                  <svg viewBox="0 0 640 640" fill="currentColor">
                    <path d="M96 96 C96 78.3 110.3 64 128 64L192 64 C209.7 64 224 78.3 224 96L224 544 C224 561.7 209.7 576 192 576L128 576 C110.3 576 96 561.7 96 544L96 96zM256 96 C256 78.3 270.3 64 288 64L352 64 C369.7 64 384 78.3 384 96L384 544 C384 561.7 369.7 576 352 576L288 576 C270.3 576 256 561.7 256 544L256 96zM416 96 C416 78.3 430.3 64 448 64L512 64 C529.7 64 544 78.3 544 96L544 544 C544 561.7 529.7 576 512 576L448 576 C430.3 576 416 561.7 416 544L416 96z"/>
                  </svg>
                </button>
              {/each}
            </div>
          {/if}
        </div>
      </div>
    </div>

    <label class="field">
      <span class="label">Description</span>
      <input
        type="text"
        bind:value={description}
        class="input"
        placeholder="Optional"
      />
    </label>

    <label class="field row">
      <span class="row-label">
        <span class="label inline">Archived</span>
        <span class="hint">Hidden from the chip bar; visible in the panel via "Show archived"</span>
      </span>
      <input class="app-checkbox" type="checkbox" bind:checked={archived} />
    </label>

    <div class="actions">
      <ActionButton kind="discard" label="Discard" onClick={onCancel} />
      <ActionButton kind="confirm" label="Save" onClick={submit} disabled={!canSave} />
    </div>
  </div>
</Modal>

<style>
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
  .field.row {
    flex-direction: row;
    align-items: flex-start;
    justify-content: space-between;
    gap: 0.75rem;
    cursor: pointer;
  }
  .row-label {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 0.1rem;
  }
  .label {
    font-family: var(--font-heading, var(--font-body));
    font-size: 0.7rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--text-secondary);
    margin-bottom: 0.3rem;
  }
  .label.inline {
    font-family: var(--font-heading, var(--font-body));
    font-size: 0.8rem;
    letter-spacing: 0;
    text-transform: none;
    color: var(--text-primary);
    margin-bottom: 0;
  }
  .hint {
    font-family: var(--font-body);
    font-size: 0.75rem;
    color: var(--text-secondary);
    line-height: 1.35;
  }
  .input {
    padding: 0.4rem 0.6rem;
    border: 1px solid var(--border-subtle);
    border-radius: 4px;
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

  .name-row {
    display: flex;
    align-items: stretch;
    gap: 0.4rem;
  }
  .name-row .input {
    flex: 1;
    min-width: 0;
  }
  .color-wrapper {
    position: relative;
    flex-shrink: 0;
  }
  .color-trigger {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 100%;
    padding: 0;
    background: var(--bg-focused);
    border: 1px solid var(--border-subtle);
    border-radius: 4px;
    cursor: pointer;
    transition: border-color var(--transition-fast);
  }
  .color-trigger:hover,
  .color-trigger.open {
    border-color: var(--text-accent);
  }
  .color-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    color: var(--text-accent);
  }
  .color-icon.none {
    color: var(--text-tertiary);
  }
  .color-icon svg {
    width: 14px;
    height: 14px;
    display: block;
  }
  .color-menu {
    position: absolute;
    top: calc(100% + 4px);
    right: 0;
    background: var(--bg-focused);
    border: 1px solid var(--bg-category);
    border-radius: 4px;
    box-shadow: var(--shadow-dropdown);
    padding: 0.5rem;
    display: grid;
    grid-template-columns: repeat(3, auto);
    gap: 0.4rem;
    z-index: 50;
  }

  .swatch {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 4px;
    cursor: pointer;
    padding: 0;
    transition: transform var(--transition-fast), border-color var(--transition-fast);
  }
  .swatch:hover {
    transform: scale(1.08);
  }
  .swatch.selected {
    border-color: var(--text-primary);
  }
  .swatch svg {
    width: 18px;
    height: 18px;
    display: block;
  }
  .swatch.none {
    color: var(--text-secondary);
    border: 1px dashed var(--text-secondary);
    font-size: 1rem;
    line-height: 1;
  }
  .swatch.none.selected {
    border-color: var(--text-primary);
    border-style: solid;
  }
  .actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.4rem;
    margin-top: 0.5rem;
  }
</style>
