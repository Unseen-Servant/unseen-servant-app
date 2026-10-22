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
  import { openDialogs } from './dialogStack';
  import { m } from '../paraglide/messages';

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

  const titleId = `modal-title-${++seq}`;

  $: width = `min(${WIDTH[size]}, 90vw)`;

  let dialogEl: HTMLDialogElement | undefined;
  // Element that held focus before the modal opened — restored on close
  // so the user lands back where they were instead of falling to <body>.
  let returnTarget: HTMLElement | null = null;
  // Set from the count at showModal() time: a dialog that opens while
  // another is already open scrims lighter, so it does not extinguish the
  // modal it is asking about.
  let stacked = false;
  // Guards the release: `visible` and unmount are independent paths into
  // closing, and DocumentStatsModal takes the second one.
  let registered = false;

  // Drive the native dialog from the `visible` prop so existing call
  // sites can stay declarative. Reactive runs once dialogEl is bound.
  $: if (dialogEl) sync(visible);

  async function sync(v: boolean) {
    if (!dialogEl) return;
    if (v && !dialogEl.open) {
      returnTarget = document.activeElement as HTMLElement | null;
      // Guarded so register and release stay symmetric. `close` fires its
      // event as a queued task rather than synchronously, so a caller that
      // flipped `visible` false→true inside one task would re-enter here
      // with `dialogEl.open` already false and register twice against a
      // single release — net +1, and the chrome dims for the rest of the
      // session. No call site does that today; the guard costs a line and
      // the failure mode is invisible until someone wonders why the app
      // looks wrong.
      if (!registered) {
        stacked = openDialogs.register();
        registered = true;
      }
      dialogEl.showModal();
      await tick();
      // showModal() auto-focuses the first sequentially-focusable
      // descendant — that's the first control in our rail, which paints
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
    releaseDialog();
    restoreFocus();
  }

  // Some callers unmount the modal directly (e.g. `{#if statsModalPath}`)
  // rather than flipping `visible` first, so the dialog's close event
  // never fires. Restore focus on destroy too — restoreFocus is
  // idempotent because returnTarget is cleared after use.
  onDestroy(() => {
    releaseDialog();
    restoreFocus();
  });

  // Idempotent for the same reason restoreFocus is: `close` and `destroy`
  // are both reachable for one open, and DocumentStatsModal exercises the
  // destroy path because {#if statsModalPath} unmounts it outright.
  function releaseDialog() {
    if (!registered) return;
    registered = false;
    openDialogs.release();
  }

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
  class:stacked
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
    <!-- No aria-label: the name comes from content, so hiding the chord is what
         keeps it out — the button announces "close"/"cancel". That is the same
         shape as ContextMenu's .menu-row, which also names itself from its text
         and hides its .menu-chord; an aria-label here would win outright and
         make the aria-hidden inert.
         This rests on a judgement: WCAG 2.5.3 asks the name to contain the
         *visible label*, and we read the mono `esc` as a shortcut badge rather
         than label text — how menus and platform chrome have always treated
         chords — with aria-keyshortcuts carrying the key properly for AT. The
         weak point, stated plainly: our badge *leads* the word, where
         .menu-chord trails its label, and a leading badge reads more like part
         of the label. Disagreeing means naming this "esc close", which then
         announces the chord on every single dismissal.
         aria-keyshortcuts is right here but wrong on an *activation* commit
         switch, and the two are correctly different: it names shortcuts *an
         author has implemented*. Esc is ours — handleCancel above preventDefaults
         the native `cancel` and routes through onClose, as a removal switch's
         ⌘⌫ is its prompt's. An activation switch's Enter is the browser's own
         <button> activation, so that one stays undeclared. -->
    <button type="button" class="modal-escape" on:click={onClose} aria-keyshortcuts="Escape">
      <span class="k" aria-hidden="true">esc</span>{escapeWord === 'cancel' ? m.modal_cancel() : m.modal_close()}
    </button>
  </div>
  <slot />
  <!-- $$slots is compile-time: a caller writing `<svelte:fragment slot="commit">`
       registers the slot whatever its contents evaluate to, so wrapping the
       switch in an `{#if}` inside the fragment yields a bare band claiming the
       unit is operable when it offers nothing. Gate the fragment, not its body. -->
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
    /* min-height, not height, as on the commit strip: whatever a caller puts in
       the rail slot fits inside 28px today, but a fixed height would overflow
       rather than grow the first time something doesn't. */
    min-height: var(--statusbar-height);
    padding: 0 0.6rem;
    background: var(--bg-header);
    border-bottom: 1px solid var(--border-subtle);
    border-top-left-radius: var(--radius-lg);
    border-top-right-radius: var(--radius-lg);
    flex-shrink: 0;
  }

  /* Layout, plus one surface correction. A title carrying a user-supplied name
     has no length limit — DocumentStatsModal passes a raw PDF filename from a
     library of thousands — so the nameplate has to be the item that gives, and
     these four properties are what let it ellipsise instead of shoving the
     escape past the dialog's border. It must NOT carry flex-shrink: 0: with no
     flex-basis the item's base size is max-content, so refusing to shrink means
     the overflow never happens and the ellipsis never fires. (The scope bar's
     .nameplate can afford that property because it holds the fixed string
     `Scope`.) The escape is what stays whole; flex-shrink: 0 lives there.

     The colour is not a new voice. .ledger-label is --text-tertiary, which is
     4.71:1 on the --bg-app the scope bar sits on but only 3.64:1 here on the
     --bg-header plate — same pair, darker surface, and the ramp has to be read
     against the surface it actually meets. One step up to --text-secondary is
     4.42:1: still a hair under AA rather than clearing it, and the honest trade
     for chrome. --text-primary would clear it and make the module's name shout
     louder than the content below. Every other .ledger-label sits on a darker
     well, so this correction stays local to this surface. */
  .modal-rail .dialog-nameplate {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--text-secondary);
  }

  /* The dismissal is ambient — it belongs with the unit's identity, not with
     the decision — so it sits here and nowhere else. A real button, drawn as
     the legend it reads as. `margin-left: auto` rides it to the trailing edge
     the way .menu-chord rides to the end of a menu row, which is one fewer
     element than a spacer div; flex-shrink: 0 keeps this fixed two-word string
     whole and hands the shrinking to the nameplate, where it belongs.

     Colour follows .menu-chord (app.css:641) — mono, --text-secondary, and no
     opacity, because opacity was the bug. 0.8 on the button multiplied by 0.55
     on the chord composited the chord to 1.79:1 against --bg-header, under even
     the 3:1 non-text floor, on the one element whose entire job is teaching the
     Esc key. Now: word 4.42:1, chord one ramp step below at 3.64:1 — where the
     × this replaced was 3.44:1. Keeping them one step apart rather than two is
     what makes the chord read as a badge instead of a smudge. */
  .modal-escape {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    margin-left: auto;
    flex-shrink: 0;
    background: none;
    border: none;
    padding: 0.15rem 0.2rem;
    border-radius: var(--radius-sm);
    cursor: pointer;
    font-family: var(--font-mono);
    font-size: 0.68rem;
    color: var(--text-secondary);
    transition: color var(--transition-fast);
  }
  .modal-escape .k {
    color: var(--text-tertiary);
  }
  /* One grey step for both halves, so hover brightens the legend without
     widening the gap between the chord and the word it labels. */
  .modal-escape:hover {
    color: var(--text-primary);
  }
  .modal-escape:hover .k {
    color: var(--text-secondary);
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
