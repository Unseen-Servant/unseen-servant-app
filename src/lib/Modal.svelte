<script lang="ts">
  import { tick } from 'svelte';

  export let visible = false;
  export let onClose: () => void;
  export let title: string;
  export let width: string = 'min(480px, 90vw)';
  export let height: string = 'auto';
  export let maxHeight: string | undefined = undefined;

  let backdropEl: HTMLElement | undefined;
  // Element that had focus when the modal opened — restored on close so
  // the user lands back where they were (typically the button or row
  // that triggered the modal). Skipped if the trigger is gone by the
  // time we close (re-rendered, removed from DOM, etc.).
  let returnTarget: HTMLElement | null = null;

  function handleBackdrop(e: MouseEvent) {
    if (e.target === e.currentTarget) onClose();
  }

  function handleKeydown(e: KeyboardEvent) {
    if (visible && e.key === 'Escape') onClose();
  }

  // Auto-focus on open / restore on close. Picks the first text input
  // when the modal has one (the common case for edit dialogs); falls
  // back to the backdrop so Esc / Tab work without a mouse click first.
  $: handleVisibilityChange(visible);
  async function handleVisibilityChange(v: boolean) {
    if (v) {
      returnTarget = document.activeElement as HTMLElement | null;
      await tick();
      if (!backdropEl) return;
      const firstInput = backdropEl.querySelector(
        'input:not([disabled]), textarea:not([disabled]), [contenteditable="true"]',
      ) as HTMLElement | null;
      (firstInput ?? backdropEl).focus();
    } else if (returnTarget && document.contains(returnTarget)) {
      returnTarget.focus();
      returnTarget = null;
    }
  }
</script>

<svelte:window on:keydown={handleKeydown} />

{#if visible}
  <!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
  <!-- svelte-ignore a11y-click-events-have-key-events -->
  <div class="backdrop" role="dialog" aria-modal="true" aria-label={title} tabindex="-1" bind:this={backdropEl} on:click={handleBackdrop}>
    <div class="modal" style:width style:height style:max-height={maxHeight}>
      <div class="modal-header">
        <span class="modal-title font-heading">{title}</span>
        <button class="close-btn" on:click={onClose} aria-label="Close">&times;</button>
      </div>
      <slot />
    </div>
  </div>
{/if}

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.6);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 100;
  }

  .modal {
    background: var(--bg-container);
    border: 1px solid var(--border-subtle);
    border-radius: 8px;
    display: flex;
    flex-direction: column;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
  }

  .modal-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.4rem 1rem;
    background: var(--bg-focused);
    border-bottom: 1px solid var(--border-subtle);
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    flex-shrink: 0;
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
</style>
