<script lang="ts">
  // A word die's faces, edited in the readout's well (design §7): one face
  // a line, a face written twice twice as likely. Esc or a click away keeps
  // the edit, and so does the editor going away (another pad, edit mode
  // ended): there's nothing to cancel back to that the GM would want.
  import { onDestroy, onMount } from 'svelte';
  import { m } from '../paraglide/messages';

  export let name: string;
  export let faces: string[];
  export let onDone: (faces: string[]) => void;

  let area: HTMLTextAreaElement;
  let done = false;

  function finish() {
    if (done) return;
    done = true;
    onDone(
      area.value
        .split('\n')
        .map((f) => f.trim())
        .filter(Boolean),
    );
  }

  // The field's own keys: Enter breaks the line rather than rolling, and
  // Esc keeps the edit rather than clearing the formula.
  function onKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter') e.stopPropagation();
    if (e.key === 'Escape') {
      e.preventDefault();
      e.stopPropagation();
      finish();
    }
  }

  onMount(() => area.focus({ preventScroll: true }));
  onDestroy(finish);
</script>

<div class="faces">
  <span class="readout-label">{m.augury_faces_label({ name })}</span>
  <textarea
    bind:this={area}
    value={faces.join('\n')}
    aria-label={m.augury_faces_label({ name })}
    spellcheck="false"
    on:keydown={onKeydown}
    on:blur={finish}
  ></textarea>
</div>

<style>
  /* The readout's well and height (Readout .readout), ringed while its
     text has the caret. */
  .faces {
    height: 5.5rem;
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
    padding: 0.4rem 0.65rem;
    background: var(--bg-app);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-well);
    box-shadow: var(--ring-focus);
  }

  .readout-label {
    flex-shrink: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  textarea {
    flex: 1;
    min-height: 0;
    padding: 0;
    resize: none;
    font-family: var(--font-body);
    font-size: 0.9rem;
    line-height: 1.25;
    color: var(--text-primary);
    caret-color: var(--text-accent);
    background: transparent;
    border: none;
    outline: none;
  }
</style>
