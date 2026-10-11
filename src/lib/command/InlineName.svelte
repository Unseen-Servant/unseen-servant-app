<script lang="ts">
  // Naming in place — a new note, track or campaign, or a rename. Enter
  // commits, Escape or leaving the field cancels: nothing gets created by a
  // stray click. Drawn in dashed parchment, the app's "prospective, not yet
  // real" idiom.
  import { onMount } from 'svelte';

  export let value: string = '';
  export let placeholder: string = '';
  export let label: string;
  export let onCommit: (name: string) => void;
  export let onCancel: () => void;

  let input: HTMLInputElement;
  let done = false;

  function finish(commit: boolean) {
    if (done) return;
    done = true;
    const name = input.value.trim();
    if (commit && name && name !== value) onCommit(name);
    else onCancel();
  }

  function onKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter') {
      e.preventDefault();
      finish(true);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      e.stopPropagation();
      finish(false);
    }
  }

  onMount(() => {
    input.focus();
    input.select();
  });
</script>

<input
  class="inline-name"
  bind:this={input}
  {value}
  {placeholder}
  aria-label={label}
  spellcheck="false"
  autocomplete="off"
  on:keydown={onKeydown}
  on:blur={() => finish(false)}
/>

<style>
  .inline-name {
    width: 100%;
    min-width: 0;
    padding: 0.15rem 0.35rem;
    font-family: var(--font-body);
    font-size: inherit;
    line-height: inherit;
    color: var(--text-primary);
    background: var(--bg-app);
    border: none;
    border-radius: var(--radius-sm);
    outline: var(--outline-drop);
    outline-offset: -1px;
  }

  .inline-name::placeholder {
    color: var(--text-tertiary);
  }
</style>
