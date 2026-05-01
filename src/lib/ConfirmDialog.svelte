<script lang="ts">
  import ActionButton from './ActionButton.svelte';

  export let title: string = 'Confirm';
  export let message: string = '';
  export let confirmLabel: string = 'Confirm';
  export let cancelLabel: string = 'Cancel';
  export let danger: boolean = false;
  export let onConfirm: () => void = () => {};
  export let onCancel: () => void = () => {};

  let confirmBtn: HTMLButtonElement | undefined;

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
      <ActionButton kind="discard" label={cancelLabel} onClick={onCancel} />
      <ActionButton
        kind="confirm"
        {danger}
        label={confirmLabel}
        onClick={onConfirm}
        bind:buttonRef={confirmBtn}
      />
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
    gap: 0.4rem;
  }
</style>
