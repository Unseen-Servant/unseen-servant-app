<script lang="ts">
  import { onMount } from 'svelte';
  import Modal from './Modal.svelte';
  import ActionButton from './ActionButton.svelte';
  import { confirmPrompt } from './confirmStore';
  import { trackInputModality, type InputModality } from './inputModality';

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
  // focus sits is the whole of the chord's meaning. Which is also why
  // only a keyboard-raised prompt places it: see viaKeyboard below.
  $: danger = $confirmPrompt?.danger === true;

  let modality: InputModality | null = null;
  onMount(() => {
    modality = trackInputModality(document);
    return () => modality?.stop();
  });

  // Snapshotted as the prompt opens rather than read at render time: the
  // question is which hand raised it, and a click on the dialog's own
  // buttons must not revise the answer. Only $confirmPrompt is a
  // dependency here, so an interaction inside an open prompt can't
  // re-run it.
  let viaKeyboard = false;
  $: if ($confirmPrompt) viaKeyboard = modality?.lastWasKeyboard() ?? false;
</script>

<Modal
  visible={$confirmPrompt !== null}
  onClose={cancel}
  title={$confirmPrompt?.title ?? ''}
  size="sm"
  autofocus={false}
  describedBy={$confirmPrompt?.message ? MESSAGE_ID : undefined}
>
  <div class="body">
    {#if $confirmPrompt?.message}
      <p id={MESSAGE_ID} class="message">{$confirmPrompt.message}</p>
    {/if}
    <div class="actions" class:ringed={viaKeyboard}>
      <ActionButton
        kind="discard"
        label={$confirmPrompt?.cancelLabel ?? 'Cancel'}
        onClick={cancel}
        initialFocus={viaKeyboard && danger}
      />
      <ActionButton
        kind="confirm"
        {danger}
        label={$confirmPrompt?.confirmLabel ?? 'Confirm'}
        onClick={accept}
        initialFocus={viaKeyboard && !danger}
      />
    </div>
  </div>
</Modal>

<style>
  .body {
    padding: var(--modal-pad);
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

  /* A programmatic .focus() does not trigger :focus-visible when the
     preceding interaction was a click, so a keyboard-raised prompt has to
     paint its own ring. Gated on .ringed, which is only set for those:
     a mouse-raised prompt auto-focuses nothing, and without the gate this
     rule would light up whichever button the pointer presses. Plain :focus
     inside it is right — both buttons are decision targets, and there is
     nothing else in the dialog to confuse it with. */
  .actions.ringed :global(.action-btn:focus) {
    outline: 2px solid var(--text-accent);
    outline-offset: 2px;
  }
</style>
