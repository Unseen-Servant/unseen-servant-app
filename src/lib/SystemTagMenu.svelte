<script lang="ts">
  import { afterUpdate, onDestroy } from 'svelte';
  import type { KnownGameSystem } from './types';
  import { claimMenuSlot, releaseMenuSlot } from './menuSlot';
  import { clampToViewport } from './menuGeometry';

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

  $: hasTag = tags.length > 0;

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
    {#each knownSystems as sys}
      <button
        class="dropdown-item"
        role="menuitemcheckbox"
        aria-checked={tags.includes(sys.tag)}
        on:click={() => onToggleSystem(sys.tag)}
      >
        <span class="menu-pip" class:on={tags.includes(sys.tag)} aria-hidden="true"></span>
        <!-- Font Awesome "dice-d6" — one fill for every system -->
        <svg class="dd-die" viewBox="0 0 640 640" fill="var(--text-secondary)" aria-hidden="true">
          <path d="M288.4 72.3C308 61.2 332 61.2 351.6 72.3L527.6 172C547.6 183.4 560 204.6 560 227.7L560 425.1C560 448.1 547.6 469.4 527.6 480.8L351.6 580.5C332 591.6 308 591.6 288.5 580.5L112.5 480.8C92.4 469.5 80 448.2 80 425.2L80 227.8C80 204.8 92.4 183.5 112.4 172.1L288.4 72.4zM166.6 219.6C157.8 216.5 147.8 219.9 142.8 228.2C137.8 236.5 139.6 246.9 146.4 253.2L149.6 255.6L299.8 345.8L299.8 494.5C299.8 505.5 308.8 514.5 319.8 514.5C330.8 514.5 339.8 505.5 339.8 494.5L339.8 345.8L490.1 255.6C499.6 249.9 502.7 237.6 497 228.2C491.3 218.8 479 215.7 469.6 221.3L319.9 311.1L170.2 221.3L166.5 219.6z"/>
        </svg>
        <span class="dropdown-tag" title={sys.tag}>{sys.tag}</span>
      </button>
    {/each}
    {#if hasTag}
      <hr class="dropdown-divider" />
      <button class="dropdown-item dropdown-clear" role="menuitem" on:click={clearSystem}>
        Clear tags
      </button>
    {/if}
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
  .dropdown-item {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    width: 100%;
    padding: 0.2rem 0.6rem;
    border: none;
    background: none;
    cursor: pointer;
    text-align: left;
    font-size: 0.8rem;
    line-height: 1.3;
    font-family: var(--font-body);
    color: var(--text-primary);
    transition: background var(--transition-fast);
  }
  .dropdown-item:hover {
    background: var(--bg-container);
  }
  .dd-die {
    width: 11px;
    height: 11px;
    flex-shrink: 0;
  }
  /* Tags are user-written and uncapped — ellipsize against --menu-max-width
     rather than stretching the menu or scrolling it sideways.
     The label stays primary ink: identity rides on the die, the same way a
     collection row carries its pigment in the ribbon and not the name. */
  .dropdown-tag {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-weight: 600;
  }
  .dropdown-divider {
    margin: 0.15rem 0;
    border: none;
    border-top: 1px solid var(--bg-category);
  }
  .dropdown-clear {
    color: var(--text-danger);
  }
</style>
