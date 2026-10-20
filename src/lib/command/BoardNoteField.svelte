<script lang="ts">
  // The Note tool's field (board toolbar design §3.2): a note's name typed
  // where the board was clicked, the campaign's notes offered under it as
  // the editor's [[ completion offers them. Enter or a click places the
  // marked note; Escape puts the tool down, and a click away lets the
  // field go. Drawn as InlineName is, in dashed parchment: not on the
  // board yet.
  import { onMount, tick } from 'svelte';
  import { placeableNotes } from './columns';
  import type { CampaignIndex } from './types';

  export let index: CampaignIndex;
  /** Where the field opens, in px from the board's corner. */
  export let left: number;
  export let top: number;
  /** The list opens above the field, near the board's foot. */
  export let up: boolean;
  export let onPick: (path: string) => void;
  /** `putDown`: Escape, back to Select; a click away keeps the tool. */
  export let onCancel: (putDown: boolean) => void;

  let input: HTMLInputElement;
  let list: HTMLElement | undefined;
  let typed = '';
  let marked = 0;
  let done = false;

  $: offered = placeableNotes(index, typed);
  $: q = typed.trim().toLowerCase();

  function finish(path: string | null, putDown = false) {
    if (done) return;
    done = true;
    if (path) onPick(path);
    else onCancel(putDown);
  }

  async function mark(i: number) {
    marked = i;
    await tick();
    list?.children[i]?.scrollIntoView({ block: 'nearest' });
  }

  function key(e: KeyboardEvent) {
    if (e.isComposing) return;
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      const n = offered.length;
      if (n) void mark((marked + (e.key === 'ArrowDown' ? 1 : n - 1)) % n);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const note = offered[marked];
      if (note) finish(note.path);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      e.stopPropagation();
      finish(null, true);
    }
  }

  onMount(() => input.focus());
</script>

<div class="note-field" class:up style:left="{left}px" style:top="{top}px">
  <input
    class="name"
    bind:this={input}
    placeholder="Note name…"
    aria-label="The note to place"
    spellcheck="false"
    autocomplete="off"
    on:input={(e) => {
      typed = e.currentTarget.value;
      marked = 0;
    }}
    on:keydown={key}
    on:blur={() => finish(null)}
  />
  {#if offered.length}
    <ul class="offers" role="listbox" aria-label="Notes" bind:this={list}>
      {#each offered as n, i (n.path)}
        {@const at = n.name.toLowerCase().indexOf(q)}
        <!-- The field keeps the keyboard: a row takes the pointer only. -->
        <!-- svelte-ignore a11y_click_events_have_key_events -->
        <li
          role="option"
          aria-selected={i === marked}
          class:marked={i === marked}
          title={n.path}
          on:pointerdown|preventDefault
          on:pointerenter={() => (marked = i)}
          on:click={() => finish(n.path)}
        >
          {n.name.slice(0, at)}<span class="matched">{n.name.slice(at, at + q.length)}</span>{n.name.slice(at + q.length)}
        </li>
      {/each}
    </ul>
  {/if}
</div>

<style>
  .note-field {
    position: absolute;
    z-index: 5;
    width: 14rem;
  }

  /* InlineName's field, a row high. */
  .name {
    width: 100%;
    height: 1.65rem;
    box-sizing: border-box;
    padding: 0 0.45rem;
    font-family: var(--font-body);
    font-size: 0.85rem;
    color: var(--text-primary);
    background: var(--bg-app);
    border: none;
    border-radius: var(--radius-sm);
    outline: var(--outline-drop);
    outline-offset: -1px;
  }

  .name::placeholder {
    color: var(--text-tertiary);
  }

  /* The editor's completion list (editorTheme .cm-tooltip-autocomplete). */
  .offers {
    position: absolute;
    left: 0;
    top: 100%;
    min-width: 100%;
    max-height: var(--menu-max-height);
    overflow-y: auto;
    margin: 2px 0 0;
    padding: 0;
    list-style: none;
    background: var(--bg-container);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-dropdown);
    font-family: var(--font-body);
    font-size: 0.85rem;
  }

  .up .offers {
    top: auto;
    bottom: 100%;
    margin: 0 0 2px;
  }

  .offers li {
    padding: 0.15rem 0.6rem;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    color: var(--text-primary);
    cursor: pointer;
  }

  .offers li.marked {
    background: var(--bg-focused);
  }

  .matched {
    color: var(--text-accent);
  }
</style>
