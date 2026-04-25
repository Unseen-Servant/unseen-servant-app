<script lang="ts">
  export let visible = false;
  export let onClose: () => void;
  export let title: string;
  export let width: string = 'min(480px, 90vw)';
  export let height: string = 'auto';
  export let maxHeight: string | undefined = undefined;

  function handleBackdrop(e: MouseEvent) {
    if (e.target === e.currentTarget) onClose();
  }

  function handleKeydown(e: KeyboardEvent) {
    if (visible && e.key === 'Escape') onClose();
  }
</script>

<svelte:window on:keydown={handleKeydown} />

{#if visible}
  <!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
  <!-- svelte-ignore a11y-click-events-have-key-events -->
  <div class="backdrop" role="dialog" aria-modal="true" aria-label={title} tabindex="-1" on:click={handleBackdrop}>
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
