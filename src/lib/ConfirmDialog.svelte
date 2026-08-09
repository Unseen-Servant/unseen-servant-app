<script lang="ts">
  import { onMount, onDestroy, tick } from 'svelte';
  import ActionButton from './ActionButton.svelte';

  export let title: string = 'Confirm';
  export let message: string = '';
  export let confirmLabel: string = 'Confirm';
  export let cancelLabel: string = 'Cancel';
  export let danger: boolean = false;
  export let onConfirm: () => void = () => {};
  export let onCancel: () => void = () => {};

  let dialogEl: HTMLDialogElement | undefined;
  let confirmBtn: HTMLButtonElement | undefined;
  let cancelBtn: HTMLButtonElement | undefined;
  let returnTarget: HTMLElement | null = null;

  onMount(async () => {
    returnTarget = document.activeElement as HTMLElement | null;
    dialogEl?.showModal();
    await tick();
    // Destructive prompts auto-focus Cancel — pressing Enter on muscle
    // memory shouldn't commit a permanent action. Safe prompts focus
    // Confirm so power users can rip through them.
    (danger ? cancelBtn : confirmBtn)?.focus();
  });

  onDestroy(() => {
    if (returnTarget && document.contains(returnTarget)) {
      returnTarget.focus();
    }
  });

  function handleKey(event: KeyboardEvent) {
    // Esc is handled via the native cancel event below. Enter still
    // commits regardless of which button is auto-focused — danger only
    // changes the auto-focus target, not the chord semantics.
    if (event.key === 'Enter') {
      event.preventDefault();
      onConfirm();
    }
  }

  function handleCancel(e: Event) {
    e.preventDefault();
    onCancel();
  }

  function handleClick(e: MouseEvent) {
    if (e.target === dialogEl) onCancel();
  }
</script>

<dialog
  bind:this={dialogEl}
  class="confirm-dialog"
  on:cancel={handleCancel}
  on:keydown={handleKey}
  on:click={handleClick}
>
  <div class="title dialog-title">{title}</div>
  {#if message}
    <div class="message">{message}</div>
  {/if}
  <div class="actions">
    <ActionButton kind="discard" label={cancelLabel} onClick={onCancel} bind:buttonRef={cancelBtn} />
    <ActionButton
      kind="confirm"
      {danger}
      label={confirmLabel}
      onClick={onConfirm}
      bind:buttonRef={confirmBtn}
    />
  </div>
</dialog>

<style>
  dialog.confirm-dialog {
    background: var(--bg-focused);
    border: 1px solid var(--bg-category);
    border-radius: 6px;
    box-shadow: var(--shadow-dropdown);
    padding: 1rem 1.25rem;
    min-width: 320px;
    max-width: 480px;
    font-family: var(--font-body);
    color: var(--text-primary);
  }
  dialog.confirm-dialog::backdrop {
    /* stylelint-disable-next-line declaration-property-value-allowed-list -- pure-black scrim; ::backdrop can't see :root tokens */
    background: rgba(0, 0, 0, 0.5);
  }
  .title {
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
