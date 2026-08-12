<script context="module" lang="ts">
  // Per-instance ids for aria-labelledby. Several modals are mounted at
  // once (Settings, the shortcut sheet, the confirm prompt all sit in the
  // tree permanently), so a fixed id would duplicate.
  let seq = 0;

  const WIDTH = {
    sm: 'var(--modal-width-sm)',
    md: 'var(--modal-width-md)',
    lg: 'var(--modal-width-lg)',
  } as const;
</script>

<script lang="ts">
  import { tick, onDestroy } from 'svelte';

  export let visible = false;
  export let onClose: () => void;
  export let title: string;
  export let size: keyof typeof WIDTH = 'md';
  // Undefined by default so the dialog sizes to its content. The old
  // implementation (overlay div + child div) made `height: auto` mean
  // "shrink-wrap content"; on a native <dialog> the user-agent inset
  // rules make `auto` stretch instead, so callers who want intrinsic
  // height should leave this unset (the default).
  export let height: string | undefined = undefined;
  export let maxHeight: string | undefined = undefined;
  // Opt-out for modals where auto-focusing the first text input is
  // wrong — e.g., Settings opens on a readonly path field that we
  // don't want highlighted as if it were inviting an edit.
  export let autofocus: boolean = true;
  // id of the element stating what the dialog is asking, for modals whose
  // body is a statement rather than a form (the confirm prompt).
  export let describedBy: string | undefined = undefined;

  const titleId = `modal-title-${++seq}`;

  $: width = `min(${WIDTH[size]}, 90vw)`;

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
      // showModal() auto-focuses the first sequentially-focusable
      // descendant — that's the × button in our header, which paints
      // a focus ring on what should be inert chrome. Override it.
      // An explicit [data-autofocus] outranks both the text-input
      // heuristic and the `autofocus` prop — a child naming its own
      // target is stating intent. It lands here rather than in the child
      // so there is one focus call, made after showModal(), instead of
      // two racing across a reactive flush.
      const declared = dialogEl.querySelector('[data-autofocus]') as HTMLElement | null;
      const firstInput = autofocus
        ? (dialogEl.querySelector(
            'input:not([disabled]):not([type="checkbox"]):not([type="radio"]):not([type="hidden"]), textarea:not([disabled]), [contenteditable="true"]',
          ) as HTMLElement | null)
        : null;
      // Falling back to the dialog itself keeps Esc/Tab working without
      // any visible focus ring (the dialog has tabindex="-1").
      (declared ?? firstInput ?? dialogEl).focus();
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
  tabindex="-1"
  style:width
  style:height
  style:max-height={maxHeight}
  aria-labelledby={titleId}
  aria-describedby={describedBy}
  on:cancel={handleCancel}
  on:close={handleClose}
  on:click={handleClick}
>
  <div class="modal-header">
    <span class="dialog-title" id={titleId}>{title}</span>
    <button type="button" class="close-btn" on:click={onClose} aria-label="Close">
      <!-- Hand-drawn ×, as with the checkbox tick in app.css: Font Awesome
           vendors circle-xmark but no bare xmark, and a circled glyph is
           too heavy for inert chrome. -->
      <svg viewBox="0 0 16 16" aria-hidden="true">
        <path d="M4 4 L12 12 M12 4 L4 12" />
      </svg>
    </button>
  </div>
  <slot />
</dialog>

<style>
  dialog.modal {
    background: var(--bg-container);
    color: var(--text-primary);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-lg);
    padding: 0;
    box-shadow: var(--shadow-modal);
    /* Override the UA default that stretches a dialog to fill its
       inset region — without this, modals without an explicit height
       prop balloon to the viewport height. */
    height: max-content;
    max-height: calc(100vh - 2rem);
  }

  dialog.modal[open] {
    display: flex;
    flex-direction: column;
  }

  /* When focus lands on the dialog itself (autofocus={false} or no
     input found), don't paint a focus ring on the chrome — Esc and
     Tab still work, but the user shouldn't see a "selected" frame. */
  dialog.modal:focus,
  dialog.modal:focus-visible {
    outline: none;
  }

  .modal-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.4rem 1rem;
    background: var(--bg-focused);
    border-bottom: 1px solid var(--border-subtle);
    border-top-left-radius: var(--radius-lg);
    border-top-right-radius: var(--radius-lg);
    flex-shrink: 0;
  }

  .close-btn {
    background: none;
    border: none;
    color: var(--text-tertiary);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0.2rem;
    border-radius: var(--radius-md);
    cursor: pointer;
    transition: color var(--transition-fast);
  }
  .close-btn svg {
    width: 14px;
    height: 14px;
    display: block;
    fill: none;
    stroke: currentColor;
    stroke-width: 1.5;
    stroke-linecap: round;
  }
  /* One step, like the rest of the chrome — the old glyph jumped to
     primary, brighter than anything else in the header plate. */
  .close-btn:hover {
    color: var(--text-secondary);
  }
</style>
