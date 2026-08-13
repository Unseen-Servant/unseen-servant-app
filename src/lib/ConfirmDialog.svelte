<script lang="ts">
  import Modal from './Modal.svelte';
  import CommitSwitch from './CommitSwitch.svelte';
  import { confirmPrompt } from './confirmStore';
  import { isCommitChord } from './confirmKeys';

  // Mounted once at page level; the store decides whether it is on screen and
  // what it asks. See confirmStore.ts for the call-site shape and
  // docs/specs/ui/2026-08-12-modal-rack-units-design.md for the unit.

  const MESSAGE_ID = 'confirm-dialog-message';

  // Esc, the backdrop, and the rail's escape legend all mean the same thing.
  const cancel = () => confirmPrompt.answer(false);
  const accept = () => confirmPrompt.answer(true);

  $: danger = $confirmPrompt?.danger === true;

  // An activation prompt puts focus on its commit, so Enter activates the
  // button natively — there is deliberately no Enter handler here (F1). A
  // removal prompt focuses the dialog itself, leaving Enter inert, and
  // commits on the delete chord instead: the key that raised the deletion is
  // the key that commits it.
  //
  // That chord is matched at dialog level, so it fires wherever focus sits —
  // including when the user has tabbed to the rail's escape legend. That is
  // the same *shape* as F1 and not the same fault. F1 was Enter, and Enter is
  // the key that means "activate the thing that is focused"; handling it above
  // the focused control overrides the answer that control was sitting there to
  // give, which is how Cancel came to commit. ⌘⌫ carries no such meaning to
  // override: it is a deliberate modifier chord that means delete, nothing
  // inside a confirm claims it, and a *person* who reaches for it has stated
  // an intent that does not change with what Tab last landed on. Esc is
  // dialog-wide for the same reason — both keys are statements about the
  // prompt rather than about the focused control.
  function handleKeydown(e: KeyboardEvent) {
    if (e.isComposing) return;
    // A held key is one intent, not two — and the sentence above is only true
    // of presses a person made. ⌘⌫ on a file row raises this prompt within a
    // microtask, well inside the OS repeat delay, so the second keydown of a
    // *single* held press would arrive at the freshly focused dialog and
    // commit a deletion nobody has read yet. Auto-repeat is not someone
    // reaching for the chord. Press-release-press still commits: that is the
    // arm-then-fire the design asks for. Same guard as every other key path
    // in the app (+page.svelte:2043, CollectionsPanel.svelte:486).
    if (e.repeat) return;
    if (!$confirmPrompt) return;
    if (!isCommitChord(e, danger)) return;
    // Hygiene, both of them: ⌘⌫ has no default action outside editable
    // content and this unit contains no field, and the global handler already
    // bails while a dialog is open (+page.svelte:2127). Stopping the event
    // here is what makes that second fact structural rather than lucky —
    // accept() clears the store synchronously, so a window-level guard that
    // reads $confirmPrompt (GameSystemsSettings.svelte:88) sees null by the
    // time the answering keystroke reaches it. Today only Svelte batching the
    // close into a microtask keeps that from mattering; this retires the
    // class instead of resting on flush order.
    e.preventDefault();
    accept();
    e.stopPropagation();
  }
</script>

<Modal
  visible={$confirmPrompt !== null}
  onClose={cancel}
  title={$confirmPrompt?.title ?? ''}
  size="sm"
  autofocus={false}
  escapeWord="cancel"
  describedBy={$confirmPrompt?.message ? MESSAGE_ID : undefined}
  on:keydown={handleKeydown}
>
  <div class="modal-bays">
    {#if $confirmPrompt?.rows?.length}
      <div class="modal-bay">
        <div class="modal-well" class:removal={danger} class:activation={!danger}>
          {#each $confirmPrompt.rows as row, i (i)}
            <div class="modal-well-row">
              <span class="ledger-label">{row.label}</span>
              <span class="modal-readout">
                {row.value}{#if row.to}<span class="arrow">→</span><span
                    class="to"
                    class:unchanged={row.unchanged}>{row.to}</span>{/if}
              </span>
            </div>
          {/each}
        </div>
      </div>
    {/if}
    {#if $confirmPrompt?.message}
      <p id={MESSAGE_ID} class="message">{$confirmPrompt.message}</p>
    {/if}
  </div>

  <svelte:fragment slot="commit">
    <CommitSwitch
      label={$confirmPrompt?.confirmLabel ?? 'Confirm'}
      {danger}
      onClick={accept}
      initialFocus={!danger}
    />
  </svelte:fragment>
</Modal>

<style>
  /* The prose line, when a caller has one. Rows carry the figures; this
     carries what a figure can't — what the change means. */
  .message {
    margin: 0;
    font-size: 0.9rem;
    color: var(--text-secondary);
    line-height: 1.4;
  }
</style>
