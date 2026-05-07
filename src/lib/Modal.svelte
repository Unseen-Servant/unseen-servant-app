<script lang="ts">
  import { tick, onDestroy } from 'svelte';

  export let visible = false;
  export let onClose: () => void;
  export let title: string;
  export let width: string = 'min(480px, 90vw)';
  export let height: string = 'auto';
  export let maxHeight: string | undefined = undefined;

  let dialogEl: HTMLDialogElement | undefined;
  // Element that held focus before the modal opened — restored on close
  // so the user lands back where they were instead of falling to <body>.
  let returnTarget: HTMLElement | null = null;

  // Drive the native dialog from the `visible` prop so existing call
  // sites can stay declarative. Reactive runs once dialogEl is bound.
  $: if (dialogEl) sync(visible);

  async function sync(v: boolean) {
    if (!dialogEl) return;
    if (v && !dialogEl.open) {
      returnTarget = document.activeElement as HTMLElement | null;
      dialogEl.showModal();
      await tick();
      // Override the UA's default focus pick: prefer the first text
      // input in the slot for edit dialogs. Skip checkboxes/radios so
      // we don't paint a focus ring on a stray toggle. If there's no
      // input we leave focus on the dialog itself — Esc and Tab still
      // work, and mouse users don't see a misleading outline.
      const firstInput = dialogEl.querySelector(
        'input:not([disabled]):not([type="checkbox"]):not([type="radio"]):not([type="hidden"]), textarea:not([disabled]), [contenteditable="true"]',
      ) as HTMLElement | null;
      if (firstInput) firstInput.focus();
    } else if (!v && dialogEl.open) {
      dialogEl.close();
    }
  }

  function handleCancel(e: Event) {
    // Esc on a native <dialog> fires `cancel` first. preventDefault so
    // the close goes through onClose (which the parent uses to flip
    // its own visibility state), keeping the source of truth in sync.
    e.preventDefault();
    onClose();
  }

  function handleClose() {
    restoreFocus();
  }

  // Some callers unmount the modal directly (e.g. `{#if statsModalPath}`)
  // rather than flipping `visible` first, so the dialog's close event
  // never fires. Restore focus on destroy too — restoreFocus is
  // idempotent because returnTarget is cleared after use.
  onDestroy(() => restoreFocus());

  function restoreFocus() {
    if (returnTarget && document.contains(returnTarget)) {
      returnTarget.focus();
    }
    returnTarget = null;
  }

  function handleClick(e: MouseEvent) {
    // Clicks where target IS the dialog (not a descendant) hit the
    // backdrop area between its border and the visible content edge.
    if (e.target === dialogEl) onClose();
  }
</script>

<dialog
  bind:this={dialogEl}
  class="modal"
  style:width
  style:height
  style:max-height={maxHeight}
  aria-label={title}
  on:cancel={handleCancel}
  on:close={handleClose}
  on:click={handleClick}
>
  <div class="modal-header">
    <span class="modal-title font-heading">{title}</span>
    <button type="button" class="close-btn" on:click={onClose} aria-label="Close">&times;</button>
  </div>
  <slot />
</dialog>

<style>
  dialog.modal {
    background: var(--bg-container);
    color: var(--text-primary);
    border: 1px solid var(--border-subtle);
    border-radius: 8px;
    padding: 0;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
  }

  dialog.modal[open] {
    display: flex;
    flex-direction: column;
  }

  dialog.modal::backdrop {
    background: rgba(0, 0, 0, 0.6);
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
