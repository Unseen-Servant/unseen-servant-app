<script lang="ts">
  import { afterUpdate, onDestroy } from 'svelte';
  import type { KnownGameSystem } from './types';
  import { claimMenuSlot, releaseMenuSlot } from '../shell/menuSlot';
  import { clampToViewport } from '../ui/menuGeometry';
  import SystemTagRows from './SystemTagRows.svelte';

  export let knownSystems: KnownGameSystem[] = [];
  export let tags: string[] = [];
  // Which edge of the trigger the menu hangs from: the file tree's badge
  // cluster sits at the row's right edge so the menu grows leftward from
  // it; the inspector's badge sits mid-panel and reads left-to-right.
  export let align: 'left' | 'right' = 'left';
  export let onToggleSystem: (tag: string) => void = () => {};
  export let onClear: () => void = () => {};

  // The .dropdown class is load-bearing beyond this file: the page-level
  // Escape ladder queries for it to yield while any menu is open.
  let showDropdown: boolean = false;
  let dropdownX: number = 0;
  let dropdownY: number = 0;
  // Anchored in viewport coords so the surrounding layout's shifts can't drag
  // the menu around. Held from the click until the menu has rendered and can
  // be measured — where it fits depends on how tall it actually is, which is
  // a question only the mounted element can answer.
  let triggerRect: DOMRect | null = null;
  let positioned = false;
  let dropdownEl: HTMLDivElement | null = null;

  export function toggle(event: MouseEvent) {
    event.stopPropagation();
    if (showDropdown) {
      closeDropdown();
      return;
    }
    triggerRect = (event.currentTarget as HTMLElement).getBoundingClientRect();
    positioned = false;
    showDropdown = true;
    claimMenuSlot(closeDropdown);
  }

  // First pass runs while the menu is still hidden: measure, place, reveal.
  // Later passes catch the menu growing under its own feet — toggling the
  // first tag adds a "Clear tags" row, which can push it past the bottom
  // edge. Placement is idempotent while it fits, so a menu with room to
  // spare never drifts out from under the pointer.
  afterUpdate(() => {
    if (!showDropdown || !dropdownEl || !triggerRect) return;
    const width = dropdownEl.offsetWidth;
    ({ x: dropdownX, y: dropdownY } = clampToViewport(
      {
        x: align === 'right' ? triggerRect.right - width : triggerRect.left,
        y: triggerRect.bottom + 2,
      },
      { width, height: dropdownEl.offsetHeight },
      { width: window.innerWidth, height: window.innerHeight },
    ));
    positioned = true;
  });

  function clearSystem() {
    onClear();
    closeDropdown();
  }

  function closeDropdown() {
    showDropdown = false;
    releaseMenuSlot(closeDropdown);
  }

  // A tree row can be unmounted (folder collapsed, filter changed) with its
  // dropdown still open — don't leave a dead menu holding the slot.
  onDestroy(() => releaseMenuSlot(closeDropdown));

  function handleWindowKeydown(event: KeyboardEvent) {
    if (showDropdown && event.key === 'Escape') {
      closeDropdown();
    }
  }
</script>

<svelte:window on:click={closeDropdown} on:keydown={handleWindowKeydown} />

{#if showDropdown}
  <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
  <div
    class="dropdown"
    role="menu"
    tabindex="-1"
    bind:this={dropdownEl}
    style="left: {dropdownX}px; top: {dropdownY}px; visibility: {positioned ? 'visible' : 'hidden'}"
    on:click|stopPropagation
    on:mousedown|stopPropagation
  >
    <SystemTagRows {knownSystems} {tags} onToggle={onToggleSystem} onClear={clearSystem} />
  </div>
{/if}

<style>
  .dropdown {
    position: fixed;
    z-index: 200;
    background: var(--bg-focused);
    border: 1px solid var(--bg-category);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-dropdown);
    min-width: var(--menu-width);
    max-width: var(--menu-max-width);
    max-height: var(--menu-max-height);
    overflow-y: auto;
    padding: 0.15rem 0;
  }
</style>
