<script lang="ts">
  import type { FileItem } from './types';

  export let x: number;
  export let y: number;
  export let item: FileItem;
  export let isIndexed: boolean = false;
  export let onOpen: () => void = () => {};
  export let onReveal: () => void = () => {};
  export let onRename: () => void = () => {};
  export let onDelete: () => void = () => {};
  export let onReindex: () => void = () => {};
  export let onShowStats: () => void = () => {};
  export let onClose: () => void = () => {};

  let menuEl: HTMLDivElement;

  function handleOutsideMouseDown(event: MouseEvent) {
    if (event.button === 2 && menuEl && !menuEl.contains(event.target as Node)) {
      onClose();
    }
  }

  // Clamp position so the menu stays within the viewport
  $: clampedX = Math.min(x, window.innerWidth - 200);
  $: clampedY = Math.min(y, window.innerHeight - (item.is_dir ? 160 : 160));
</script>

<svelte:window on:click={onClose} on:mousedown={handleOutsideMouseDown} />

<!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
<div
  class="context-menu"
  bind:this={menuEl}
  style="left: {clampedX}px; top: {clampedY}px"
  on:click|stopPropagation
  on:mousedown|stopPropagation
>
  {#if !item.is_dir}
    <button class="context-item" on:click={onOpen}>Open file</button>
  {/if}
  <button class="context-item" on:click={onReveal}>Reveal in folder</button>
  {#if !item.is_dir && isIndexed}
    <hr class="context-divider" />
    <button class="context-item" on:click={onReindex}>Re-index file</button>
    <button class="context-item" on:click={onShowStats}>Get info</button>
  {/if}
  <hr class="context-divider" />
  <button class="context-item" on:click={onRename}>Rename {item.is_dir ? 'folder' : 'file'}</button>
  <button class="context-item danger" on:click={onDelete}>Delete {item.is_dir ? 'folder' : 'file'}</button>
</div>

<style>
  .context-menu {
    position: fixed;
    z-index: 200;
    background: var(--bg-focused);
    border: 1px solid var(--bg-category);
    border-radius: 4px;
    box-shadow: var(--shadow-dropdown);
    min-width: 170px;
    padding: 0.25rem 0;
  }
  .context-item {
    display: block;
    width: 100%;
    padding: 0.4rem 0.75rem;
    border: none;
    background: none;
    cursor: pointer;
    text-align: left;
    font-size: 0.85rem;
    font-family: var(--font-body);
    color: var(--text-primary);
    transition: background var(--transition-fast);
  }
  .context-item:hover {
    background: var(--bg-container);
  }
  .context-item.danger {
    color: var(--text-danger);
  }
  .context-divider {
    margin: 0.25rem 0;
    border: none;
    border-top: 1px solid var(--bg-category);
  }
</style>
