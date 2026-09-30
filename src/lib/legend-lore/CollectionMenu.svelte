<script lang="ts">
  // The search bar's `@` completion: collections to play, filtered by what
  // follows the @. The bar keeps focus and forwards its keys here — ↑/↓
  // move the cursor, ↵ plays the row alone (again stops it), ⇧↵ adds it to
  // the mix or takes it out. Rows swallow mousedown so a click never pulls
  // focus out of the bar.
  import { tick } from 'svelte';
  import type { CollectionInfo } from './types';
  import { RIBBON_OUTLINE } from '../ui/iconPaths';
  import { slotChord } from '../shell/keybindings';
  import { filterByQuery } from './collectionOrder';

  /** Transport-carrying names in panel order; index N−1 is slot N. */
  export let names: string[] = [];
  export let collections: Record<string, CollectionInfo> = {};
  export let playingNames: Set<string> = new Set();
  export let mutedNames: Set<string> = new Set();
  export let query = '';
  export let onChoose: (name: string, mix: boolean) => void = () => {};

  let listEl: HTMLUListElement;
  let cursor = 0;

  $: matches = filterByQuery(names, query);
  // A new query re-aims at the best match; the list itself can also shrink
  // under the cursor (a track archived or deleted while open).
  $: query, (cursor = 0);
  $: if (cursor > matches.length - 1) cursor = Math.max(0, matches.length - 1);

  async function scrollCursorIntoView() {
    await tick();
    listEl?.querySelector('.kb-focused')?.scrollIntoView({ block: 'nearest' });
  }

  /** A key from the search bar. True when the menu consumed it. */
  export function handleKey(event: KeyboardEvent): boolean {
    if (event.metaKey || event.ctrlKey || event.altKey) return false;
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      if (matches.length > 0) {
        const delta = event.key === 'ArrowDown' ? 1 : -1;
        cursor = Math.min(matches.length - 1, Math.max(0, cursor + delta));
        void scrollCursorIntoView();
      }
      return true;
    }
    if (event.key === 'Enter') {
      const name = matches[cursor];
      if (name) onChoose(name, event.shiftKey);
      return true;
    }
    return false;
  }
</script>

<div class="collection-menu hover-dark">
  {#if names.length === 0}
    <p class="empty">No collections to play</p>
  {:else}
    <ul class="menu-list" role="listbox" aria-label="Collections" bind:this={listEl}>
      {#each matches as name, i (name)}
        {@const col = collections[name]}
        {@const slot = names.indexOf(name) + 1}
        <!-- svelte-ignore a11y-click-events-have-key-events -->
        <li
          class="menu-row"
          class:kb-focused={i === cursor}
          role="option"
          aria-selected={i === cursor}
          on:mousedown|preventDefault
          on:pointermove={() => (cursor = i)}
          on:click={(e) => onChoose(name, e.shiftKey)}
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
  .collection-menu {
    width: var(--menu-max-width);
    background: var(--bg-focused);
    border: 1px solid var(--bg-category);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-dropdown);
    padding: 0.15rem 0;
  }
  .menu-list {
    list-style: none;
    margin: 0;
    padding: 0;
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
    margin: 0;
    padding: 0.2rem 0.6rem;
    font-size: 0.8rem;
    font-style: italic;
    color: var(--text-secondary);
  }
</style>
