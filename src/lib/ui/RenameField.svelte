<script lang="ts">
  // The one rename field: Legend Lore's books, folders and collections,
  // Command's notes, tracks, beats and campaigns. A rename ends as Finder's
  // does: Enter or clicking away commits a changed name, Escape backs out,
  // and an unchanged or emptied name just closes. A refused name keeps the
  // field and the typed text, with a red edge and the reason under it, back
  // in the field to fix; clicking away from a name just refused gives up.
  // While the rename runs the field holds the new name, so the old one
  // never flashes back. Clicks in the field are editing, never the row's: a
  // double-click selects a word rather than opening the book. Naming
  // something new is InlineName's (Command): there a stray click creates
  // nothing.
  import { onDestroy, onMount } from 'svelte';

  /** The name as it is. Read once: the field keeps the text it opened
   *  with even if the name behind it changes while the rename runs. */
  export let value: string;
  export let label: string;
  export let placeholder = '';
  /** Called with a changed, trimmed name. Resolves the reason it was
   *  refused, or nothing when it took; the owner then closes the field. */
  export let onCommit: (name: string) => Promise<string | null | void> | string | null | void;
  export let onCancel: () => void;
  /** Where emptying means removing (Augury's pads): called when a field
   *  that held a name is emptied and committed. Without it, an emptied name
   *  just closes. */
  export let onEmpty: (() => void) | undefined = undefined;

  const original = value;
  let input: HTMLInputElement;
  let scroller: HTMLElement | null = null;
  let pending = false;
  let refusal: string | null = null;
  let refusedName: string | null = null;
  let notePos = '';

  async function commit() {
    if (pending) return;
    const name = input.value.trim();
    if (!name && original && onEmpty) {
      onEmpty();
      return;
    }
    if (!name || name === original) {
      onCancel();
      return;
    }
    pending = true;
    refusal = null;
    let reason: string | null | void;
    try {
      reason = await onCommit(name);
    } catch (e) {
      reason = String(e);
    }
    pending = false;
    if (!reason) return;
    refusal = reason;
    refusedName = name;
    // Fixed, under the field: a row's overflow can't clip it.
    const r = input.getBoundingClientRect();
    notePos = `left: ${r.left}px; top: ${r.bottom + 3}px; max-width: ${Math.max(r.width, 240)}px`;
    input.focus({ preventScroll: true });
    input.select();
  }

  function onKeydown(e: KeyboardEvent) {
    if (e.isComposing) return;
    if (e.key === 'Enter') {
      e.preventDefault();
      commit();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      e.stopPropagation();
      if (!pending) onCancel();
    }
  }

  // Clicking away commits. Switching to another window isn't clicking
  // away: the field keeps its text for when the window comes back.
  function onBlur() {
    if (pending || !document.hasFocus()) return;
    if (input.value.trim() === refusedName) onCancel();
    else commit();
  }

  onMount(() => {
    for (let el = input.parentElement; el; el = el.parentElement) {
      if (/(auto|scroll)/.test(getComputedStyle(el).overflowY)) {
        scroller = el;
        break;
      }
    }
    // preventScroll: a rename starts on a row in view, and focus()'s own
    // scroll-into-view nudges the list, which reads as drift.
    input.focus({ preventScroll: true });
    input.select();
  });

  // WebKit resets the list's scroll about two frames after a focused field
  // leaves the page; one frame is too early to undo it, so restore across
  // both.
  onDestroy(() => {
    const list = scroller;
    if (!list) return;
    const saved = list.scrollTop;
    const restore = () => (list.scrollTop = saved);
    requestAnimationFrame(restore);
    requestAnimationFrame(() => requestAnimationFrame(restore));
  });
</script>

<input
  class="rename-field"
  class:refused={refusal !== null}
  bind:this={input}
  value={original}
  {placeholder}
  readonly={pending}
  aria-label={label}
  aria-busy={pending}
  aria-invalid={refusal !== null}
  spellcheck="false"
  autocomplete="off"
  on:keydown={onKeydown}
  on:blur={onBlur}
  on:input={() => (refusal = null)}
  on:click|stopPropagation
  on:dblclick|stopPropagation
  on:mousedown|stopPropagation
  on:contextmenu|stopPropagation
/>
{#if refusal}
  <span class="refusal" role="alert" style={notePos}>{refusal}</span>
{/if}

<style>
  /* The field's own look is app.css's .rename-field. */
  .refusal {
    position: fixed;
    z-index: 200;
    padding: 0.2rem 0.45rem;
    font-family: var(--font-body);
    font-size: 0.8rem;
    font-weight: normal;
    font-style: normal;
    letter-spacing: normal;
    text-transform: none;
    line-height: 1.35;
    white-space: normal;
    color: var(--text-danger);
    background: var(--bg-container);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    box-shadow: var(--shadow-dropdown);
    pointer-events: none;
  }
</style>
