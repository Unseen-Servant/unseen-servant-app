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
    if (event.key !== 'Enter' || !canSave) return;
    // Plain Enter saves when the user is in any of the dialog's text
    // inputs — matches "I typed a name, I press Enter, it commits."
    // Cmd/Ctrl+Enter saves regardless so the chord still works from
    // the checkbox or button focus state.
    const target = event.target as HTMLElement | null;
    const inTextInput = target instanceof HTMLInputElement && target.type === 'text';
    if (event.metaKey || event.ctrlKey || inTextInput) {
      event.preventDefault();
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
            {#if color}
              <span class="color-swatch" style="background: {color}" aria-hidden="true"></span>
            {:else}
              <span class="color-swatch none" aria-hidden="true">&times;</span>
            {/if}
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
                  style="background: {c}"
                  on:click={() => pickColor(c)}
                  title={c}
                  aria-label={`Color ${c}`}
                ></button>
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
    border-radius: var(--radius-md);
    cursor: pointer;
    transition: border-color var(--transition-fast);
  }
  .color-trigger:hover,
  .color-trigger.open {
    border-color: var(--text-accent);
  }
  .color-swatch {
    width: 14px;
    height: 14px;
    border-radius: var(--radius-sm);
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }
  .color-swatch.none {
    background: transparent;
    border: 1px dashed var(--text-tertiary);
    color: var(--text-tertiary);
    font-size: 0.85rem;
    line-height: 1;
  }
  .color-menu {
    position: absolute;
    top: calc(100% + 4px);
    right: 0;
    background: var(--bg-focused);
    border: 1px solid var(--bg-category);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-dropdown);
    padding: 0.5rem;
    display: grid;
    grid-template-columns: repeat(3, auto);
    gap: 0.4rem;
    z-index: 50;
  }

  .swatch {
    width: 22px;
    height: 22px;
    border-radius: var(--radius-md);
    cursor: pointer;
    padding: 0;
    border: 1px solid transparent;
    transition: transform var(--transition-fast), border-color var(--transition-fast);
  }
  .swatch:hover {
    transform: scale(1.08);
  }
  .swatch.selected {
    border-color: var(--text-primary);
  }
  .swatch.none {
    background: transparent;
    border: 1px dashed var(--text-secondary);
    color: var(--text-secondary);
    font-size: 1rem;
    line-height: 1;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .swatch.none.selected {
    border-color: var(--text-primary);
    border-style: solid;
    color: var(--text-primary);
  }
  .actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.4rem;
    margin-top: 0.5rem;
  }
</style>
