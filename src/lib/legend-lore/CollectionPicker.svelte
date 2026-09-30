<script lang="ts">
  // ⌘P: play a collection from anywhere without walking focus to the panel.
  // Type to narrow, ↵ plays the row alone (again stops it), ⇧↵ adds it to
  // the mix or takes it out and keeps the picker open for the next one.
  // The input keeps focus the whole time — rows swallow mousedown — so a
  // blur means the user went elsewhere, and the picker closes quietly.
  import { onDestroy, onMount, tick } from 'svelte';
  import type { CollectionInfo } from './types';
  import { RIBBON_OUTLINE } from '../ui/iconPaths';
  import { claimMenuSlot, releaseMenuSlot } from '../shell/menuSlot';
  import { slotChord } from '../shell/keybindings';
  import { filterByQuery } from './collectionOrder';

  /** Transport-carrying names in panel order; index N−1 is slot N. */
  export let names: string[] = [];
  export let collections: Record<string, CollectionInfo> = {};
  export let playingNames: Set<string> = new Set();
  export let mutedNames: Set<string> = new Set();
  export let onPlayOnly: (name: string) => void = () => {};
  export let onToggleMix: (name: string) => void = () => {};
  /** `restore` is true when the picker ends on its own terms (Esc, ↵) and
   *  focus should go back where it came from; false when focus already left. */
  export let onClose: (restore: boolean) => void = () => {};

  let input: HTMLInputElement;
  let listEl: HTMLUListElement;
  let query = '';
  let cursor = 0;
  let top = 0;
  let left = 0;

  $: matches = filterByQuery(names, query);
  // A new query re-aims at the best match; the list itself can also shrink
  // under the cursor (a track archived or deleted while open).
  $: query, (cursor = 0);
  $: if (cursor > matches.length - 1) cursor = Math.max(0, matches.length - 1);

  const close = () => onClose(false);

  onMount(() => {
    claimMenuSlot(close);
    // Over the file pane's top edge, centered — the scope bar just below
    // it is where the mix it changes is read back.
    const area = document.querySelector('.file-tree-area')?.getBoundingClientRect();
    top = (area?.top ?? 48) + 6;
    left = area ? area.left + area.width / 2 : window.innerWidth / 2;
    input.focus();
  });
  onDestroy(() => releaseMenuSlot(close));

  async function scrollCursorIntoView() {
    await tick();
    listEl?.querySelector('.kb-focused')?.scrollIntoView({ block: 'nearest' });
  }

  function choose(name: string, mix: boolean) {
    if (mix) {
      onToggleMix(name);
    } else {
      onPlayOnly(name);
      onClose(true);
    }
  }

  function handleKeydown(event: KeyboardEvent) {
    // Cmd/Ctrl chords go on to the window: ⌘1–9 still select tracks with
    // the picker open, and ⌘P closes it.
    if (event.metaKey || event.ctrlKey) return;
    // Everything else is ours — bare letters are the query, not the tree's
    // or the panel's single-key commands.
    event.stopPropagation();
    if (event.isComposing) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      onClose(true);
    } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      if (matches.length === 0) return;
      const delta = event.key === 'ArrowDown' ? 1 : -1;
      cursor = Math.min(matches.length - 1, Math.max(0, cursor + delta));
      void scrollCursorIntoView();
    } else if (event.key === 'Enter') {
      event.preventDefault();
      const name = matches[cursor];
      if (name) choose(name, event.shiftKey);
    } else if (event.key === 'Tab') {
      event.preventDefault();
    }
  }
</script>

<div class="collection-picker hover-dark" style="top: {top}px; left: {left}px">
  <input
    bind:this={input}
    bind:value={query}
    class="picker-input"
    type="text"
    placeholder={names.length ? 'Play collection…' : 'No collections to play'}
    spellcheck="false"
    autocomplete="off"
    role="combobox"
    aria-expanded="true"
    aria-controls="collection-picker-list"
    aria-activedescendant={matches.length ? `collection-picker-${cursor}` : undefined}
    on:keydown={handleKeydown}
    on:blur={close}
  />
  {#if names.length > 0}
    <ul class="picker-list" id="collection-picker-list" role="listbox" bind:this={listEl}>
      {#each matches as name, i (name)}
        {@const col = collections[name]}
        {@const slot = names.indexOf(name) + 1}
        <!-- svelte-ignore a11y-click-events-have-key-events -->
        <li
          id="collection-picker-{i}"
          class="menu-row"
          class:kb-focused={i === cursor}
          role="option"
          aria-selected={i === cursor}
          on:mousedown|preventDefault
          on:pointermove={() => (cursor = i)}
          on:click={(e) => choose(name, e.shiftKey)}
        >
          <span class="menu-pip" class:on={playingNames.has(name)} aria-hidden="true"></span>
          <svg class="ribbon" viewBox="0 0 24 24" fill="none" stroke={col?.color ?? 'var(--text-tertiary)'} stroke-width="2.2" stroke-linejoin="round" aria-hidden="true">
            <path d={RIBBON_OUTLINE}/>
          </svg>
          <span class="name" class:muted={mutedNames.has(name)}>{name}</span>
          {#if mutedNames.has(name)}<span class="muted-tag">muted</span>{/if}
          {#if slot <= 9}<span class="menu-chord">{slotChord(slot)}</span>{/if}
        </li>
      {:else}
        <li class="empty">No collection matches</li>
      {/each}
    </ul>
  {/if}
</div>

<style>
  .collection-picker {
    position: fixed;
    z-index: 200;
    transform: translateX(-50%);
    width: var(--menu-max-width);
    background: var(--bg-focused);
    border: 1px solid var(--bg-category);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-dropdown);
    padding-bottom: 0.15rem;
  }
  .picker-input {
    width: 100%;
    box-sizing: border-box;
    padding: 0.4rem 0.6rem;
    background: transparent;
    border: none;
    border-bottom: 1px solid var(--bg-category);
    outline: none;
    color: var(--text-primary);
    font-family: var(--font-body);
    font-size: 0.9rem;
  }
  .picker-input::placeholder {
    color: var(--text-secondary);
    font-style: italic;
  }
  .picker-list {
    list-style: none;
    margin: 0;
    padding: 0.15rem 0 0;
    max-height: 18rem;
    overflow-y: auto;
  }
  .ribbon {
    width: 0.85rem;
    height: 0.85rem;
    flex-shrink: 0;
  }
  .name {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .name.muted {
    color: var(--text-tertiary);
  }
  .muted-tag {
    font-size: 0.7rem;
    color: var(--text-danger);
  }
  .empty {
    padding: 0.2rem 0.6rem;
    font-size: 0.8rem;
    font-style: italic;
    color: var(--text-secondary);
  }
</style>
