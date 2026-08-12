<script lang="ts">
  import Modal from './Modal.svelte';
  import ActionButton from './ActionButton.svelte';
  import { confirmPrompt } from './confirmStore';

  // Mounted once at page level; the store decides whether it is on screen
  // and what it asks. No props — see confirmStore.ts for the call-site
  // shape and docs/specs/ui/2026-08-11-modal-audit-design.md for why this
  // stopped being one dialog per caller.

  const MESSAGE_ID = 'confirm-dialog-message';

  // Esc, the backdrop, and the shell's × all mean the same thing here.
  const cancel = () => confirmPrompt.answer(false);
  const accept = () => confirmPrompt.answer(true);

  // Destructive prompts put initial focus on Cancel — Enter on muscle
  // memory then cancels rather than committing. Nothing intercepts Enter
  // at dialog level: the focused button handles it natively, so where
  // focus sits is the whole of the chord's meaning.
  $: danger = $confirmPrompt?.danger === true;
</script>

<Modal
  visible={$confirmPrompt !== null}
  onClose={cancel}
  title={$confirmPrompt?.title ?? ''}
  width="min(420px, 90vw)"
  autofocus={false}
  describedBy={$confirmPrompt?.message ? MESSAGE_ID : undefined}
>
  <div class="body">
    {#if $confirmPrompt?.message}
      <p id={MESSAGE_ID} class="message">{$confirmPrompt.message}</p>
    {/if}
    <div class="actions">
      <ActionButton
        kind="discard"
        label={$confirmPrompt?.cancelLabel ?? 'Cancel'}
        onClick={cancel}
        initialFocus={danger}
      />
      <ActionButton
        kind="confirm"
        {danger}
        label={$confirmPrompt?.confirmLabel ?? 'Confirm'}
        onClick={accept}
        initialFocus={!danger}
      />
    </div>
  </div>
</Modal>

<style>
  .body {
    padding: 1rem 1.25rem 1.25rem;
  }

  .message {
    margin: 0 0 1rem;
    font-size: 0.9rem;
    color: var(--text-primary);
    line-height: 1.4;
  }

  .actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.4rem;
  }

  /* A programmatic .focus() does not trigger :focus-visible in Chromium
     when the preceding interaction was a mouse click — which is how a
     context-menu delete arrives. Without this the danger prompt's Cancel
     is focused but doesn't look focused, and auto-focusing it protects
     nobody. Plain :focus is right here: both buttons are decision
     targets, and there is nothing else in the dialog to confuse it with. */
  .actions :global(.action-btn:focus) {
    outline: 2px solid var(--text-accent);
    outline-offset: 2px;
  }
</style>
