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
  // The rail's dismiss slot names the escape rather than drawing an ×: the
  // word differs because backing out of a question is not the same act as
  // closing a panel. See the design's "Cancel is a legend in the top rail".
  export let escapeWord: 'cancel' | 'close' = 'close';
  $: escapeName = escapeWord === 'cancel' ? 'Cancel' : 'Close';

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
      // descendant — that's the escape legend in our rail, which paints
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
  on:keydown
>
  <div class="modal-rail">
    <span class="dialog-nameplate ledger-label" id={titleId}>{title}</span>
    <slot name="rail" />
    <span class="rail-grow"></span>
    <!-- The chord is a hint, not part of the name: hidden, as every chord in
         the app already is (ContextMenu's .menu-chord). That leaves `close` as
         the visible label, which `aria-label` matches — WCAG 2.5.3 wants the
         name to contain the visible text, and "esc close" would not.
         aria-keyshortcuts is right here but wrong on the commit switch, and the
         two are correctly different: it names shortcuts *an author has
         implemented*. Esc is ours — handleCancel below preventDefaults the
         native `cancel` and routes through onClose. The switch's Enter is the
         browser's own <button> activation, so it stays undeclared. -->
    <button
      type="button"
      class="modal-escape"
      on:click={onClose}
      aria-label={escapeName}
      aria-keyshortcuts="Escape"
    >
      <span class="k" aria-hidden="true">esc</span>{escapeWord}
    </button>
  </div>
  <slot />
  {#if $$slots.commit}
    <div class="modal-commit-strip">
      <slot name="commit" />
    </div>
  {/if}
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

  /* --bg-header, not --bg-container: the Header and StatusBar wear this plate
     and "bracket the workspace as one piece of chrome" (StatusBar.svelte:168).
     A unit that brackets its own bays the same way reads as a small instance
     of the instrument rather than a card floating over it. */
  .modal-rail {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    height: var(--statusbar-height);
    padding: 0 0.6rem;
    background: var(--bg-header);
    border-bottom: 1px solid var(--border-subtle);
    border-top-left-radius: var(--radius-lg);
    border-top-right-radius: var(--radius-lg);
    flex-shrink: 0;
  }

  .rail-grow {
    flex: 1;
    min-width: 0;
  }

  /* Layout only — the voice stays in app.css. A title carrying a user-supplied
     name has no length limit and would otherwise push the rail's dismiss off
     the plate. */
  .modal-rail .dialog-nameplate {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    flex-shrink: 0;
  }

  /* The dismissal is ambient — it belongs with the unit's identity, not with
     the decision — so it sits here and nowhere else. A real button, drawn as
     the legend it reads as. */
  .modal-escape {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    background: none;
    border: none;
    padding: 0.15rem 0.2rem;
    border-radius: var(--radius-sm);
    cursor: pointer;
    font-family: var(--font-mono);
    font-size: 0.68rem;
    color: var(--text-tertiary);
    opacity: 0.8;
    transition: color var(--transition-fast), opacity var(--transition-fast);
  }
  .modal-escape .k {
    opacity: 0.55;
  }
  .modal-escape:hover {
    color: var(--text-secondary);
    opacity: 1;
  }
  .modal-escape:focus-visible {
    outline: 1px solid var(--text-accent);
    outline-offset: 1px;
  }

  /* The commit rail. Rendered only when a caller fills the slot: a unit that
     ends at its last bay is one you cannot operate, and that absence is the
     signal (Document info relies on it). A caller placing a note instead of a
     commit pushes it left with margin-right: auto. */
  .modal-commit-strip {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 1rem;
    min-height: var(--statusbar-height);
    padding: 0.3rem 0.6rem;
    background: var(--bg-header);
    border-top: 1px solid var(--border-subtle);
    border-bottom-left-radius: var(--radius-lg);
    border-bottom-right-radius: var(--radius-lg);
    flex-shrink: 0;
  }
</style>
