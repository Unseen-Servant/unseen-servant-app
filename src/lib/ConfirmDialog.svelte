<script lang="ts">
  export let title: string = 'Confirm';
  export let message: string = '';
  export let confirmLabel: string = 'Confirm';
  export let cancelLabel: string = 'Cancel';
  export let danger: boolean = false;
  export let onConfirm: () => void = () => {};
  export let onCancel: () => void = () => {};

  let confirmBtn: HTMLButtonElement;

  function handleKey(event: KeyboardEvent) {
    if (event.key === 'Escape') onCancel();
    else if (event.key === 'Enter') onConfirm();
  }

  $: if (confirmBtn) confirmBtn.focus();
</script>

<svelte:window on:keydown={handleKey} />

<!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
<div class="backdrop" on:click={onCancel}>
  <div class="dialog" on:click|stopPropagation>
    <div class="title">{title}</div>
    {#if message}
      <div class="message">{message}</div>
    {/if}
    <div class="actions">
      <button class="btn cancel" on:click={onCancel}>{cancelLabel}</button>
      <button
        class="btn confirm"
        class:danger
        bind:this={confirmBtn}
        on:click={onConfirm}
      >
        {confirmLabel}
      </button>
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
    z-index: 300;
  }
  .dialog {
    background: var(--bg-focused);
    border: 1px solid var(--bg-category);
    border-radius: 6px;
    box-shadow: var(--shadow-dropdown);
    padding: 1rem 1.25rem;
    min-width: 320px;
    max-width: 480px;
    font-family: var(--font-body);
  }
  .title {
    font-family: var(--font-heading);
    font-size: 1rem;
    font-weight: 600;
    color: var(--text-accent);
    margin-bottom: 0.5rem;
  }
  .message {
    font-size: 0.9rem;
    color: var(--text-primary);
    margin-bottom: 1rem;
    line-height: 1.4;
  }
  .actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.5rem;
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
  .btn:active {
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
  .confirm {
    background: var(--bg-active);
    color: var(--text-primary);
  }
  .confirm:hover {
    background: var(--bg-active-focused);
  }
  .confirm.danger {
    background: transparent;
    color: var(--text-danger);
    border-color: var(--text-danger);
  }
  .confirm.danger:hover {
    background: rgba(239, 68, 68, 0.1);
  }
</style>
