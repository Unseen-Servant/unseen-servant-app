<script lang="ts">
  // The empty row's field. It names a new row as InlineName does (Enter
  // commits, Esc or leaving the field cancels, no field of its own), and an
  // open `[[` offers the campaign's notes, as Command's editor does: drops
  // don't cross windows, so this is how a row links to a note while either
  // tool is popped out. ↑↓ move through the offer; Enter or Tab takes one.
  import { onMount } from 'svelte';
  import type { NoteEntry } from '../command/types';
  import { openTarget } from '../command/wikilinks';
  import { completions } from './encounter';

  export let placeholder: string;
  export let label: string;
  export let notes: NoteEntry[];
  /** The text typed, and the note taken from the offer, if one was. */
  export let onCommit: (text: string, note: NoteEntry | null) => void;
  export let onCancel: () => void;

  let input: HTMLInputElement;
  let text = '';
  let at = 0;
  let spot = '';
  let done = false;

  $: target = openTarget(text);
  $: offered = target ? completions(notes, target.typed) : [];
  $: if (at >= offered.length) at = 0;
  $: if (offered.length) place();

  // Fixed, so the rows' scroll can't clip it, on the side with more room.
  function place() {
    const r = input.getBoundingClientRect();
    const up = r.top > window.innerHeight - r.bottom;
    spot = `left: ${r.left}px; min-width: ${r.width}px; ` + (up ? `bottom: ${window.innerHeight - r.top + 2}px` : `top: ${r.bottom + 2}px`);
  }

  function finish(commit: boolean, note: NoteEntry | null = null) {
    if (done) return;
    done = true;
    const typed = text.trim();
    if (commit && (typed || note)) onCommit(typed, note);
    else onCancel();
  }

  function onKeydown(e: KeyboardEvent) {
    if (e.isComposing) return;
    const offering = offered.length > 0;
    if (e.key === 'Enter' || (e.key === 'Tab' && offering)) {
      e.preventDefault();
      finish(true, offered[at] ?? null);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      e.stopPropagation();
      finish(false);
    } else if (offering && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
      e.preventDefault();
      at = (at + (e.key === 'ArrowDown' ? 1 : offered.length - 1)) % offered.length;
    }
  }

  onMount(() => input.focus());
</script>

<input
  class="name-field"
  bind:this={input}
  bind:value={text}
  {placeholder}
  aria-label={label}
  spellcheck="false"
  autocomplete="off"
  on:keydown={onKeydown}
  on:blur={() => finish(false)}
/>
{#if offered.length}
  <!-- The press would take the caret from the field, and end it. -->
  <div class="offer" role="listbox" tabindex="-1" aria-label={label} style={spot} on:mousedown|preventDefault>
    {#each offered as note, i (note.path)}
      <button
        type="button"
        class="menu-row"
        class:kb-focused={i === at}
        role="option"
        aria-selected={i === at}
        tabindex="-1"
        title={note.path}
        on:click={() => finish(true, note)}
      >
        {note.name}
      </button>
    {/each}
  </div>
{/if}

<style>
  .name-field {
    width: 100%;
    min-width: 0;
    padding: 0;
    font-family: var(--font-body);
    font-size: inherit;
    line-height: inherit;
    color: var(--text-primary);
    background: transparent;
    border: none;
    outline: none;
  }

  .name-field::placeholder {
    font-style: italic;
    color: var(--text-tertiary);
  }

  /* CommandMenu's box, its rows app.css's. */
  .offer {
    position: fixed;
    z-index: 200;
    max-width: var(--menu-max-width);
    max-height: var(--menu-max-height);
    overflow-y: auto;
    padding: 0.15rem 0;
    background: var(--bg-container);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-dropdown);
  }

  .menu-row {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
</style>
