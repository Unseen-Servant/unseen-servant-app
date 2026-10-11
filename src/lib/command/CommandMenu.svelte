<script lang="ts">
  // A context menu for Command's rows. Same anatomy as Legend Lore's
  // (.menu-row / .menu-divider in app.css): measured before it shows,
  // clamped to the window, and holding the one menu slot while open.
  import { onDestroy, onMount, tick } from 'svelte';
  import { claimMenuSlot, releaseMenuSlot } from '../shell/menuSlot';
  import { clampToViewport } from '../ui/menuGeometry';
  import type { MenuItem } from './menu';

  export let x: number;
  export let y: number;
  export let items: MenuItem[];
  export let onClose: () => void;

  let el: HTMLDivElement;
  let pos = { x, y };
  let measured = false;

  function close() {
    releaseMenuSlot(close);
    onClose();
  }

  function pick(run: () => void) {
    close();
    run();
  }

  function onWindowMousedown(e: MouseEvent) {
    if (el && !el.contains(e.target as Node)) close();
  }

  function onWindowKeydown(e: KeyboardEvent) {
    if (e.key === 'Escape') {
      e.preventDefault();
      e.stopPropagation();
      close();
    }
  }

  onMount(async () => {
    claimMenuSlot(close);
    await tick();
    const box = el.getBoundingClientRect();
    pos = clampToViewport(
      { x, y },
      { width: box.width, height: box.height },
      { width: window.innerWidth, height: window.innerHeight },
    );
    measured = true;
  });

  onDestroy(() => releaseMenuSlot(close));
</script>

<svelte:window on:mousedown={onWindowMousedown} on:keydown={onWindowKeydown} on:blur={close} />

<div class="command-menu" class:measured bind:this={el} style:left="{pos.x}px" style:top="{pos.y}px" role="menu">
  {#each items as item, i (i)}
    {#if item.kind === 'divider'}
      <hr class="menu-divider" />
    {:else if item.kind === 'heading'}
      <div class="menu-heading ledger-label">{item.label}</div>
    {:else}
      {@const run = item.action}
      <button type="button" class="menu-row" class:danger={item.danger} role="menuitem" on:click={() => pick(run)}>
        {item.label}
      </button>
    {/if}
  {/each}
</div>

<style>
  .command-menu {
    position: fixed;
    z-index: 200;
    visibility: hidden;
    background: var(--bg-container);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-dropdown);
    min-width: var(--menu-width);
    max-width: var(--menu-max-width);
    max-height: var(--menu-max-height);
    overflow-y: auto;
    padding: 0.15rem 0;
  }

  .command-menu.measured {
    visibility: visible;
  }

  .menu-heading {
    padding: 0.35rem 0.6rem 0.1rem;
  }

  .menu-row {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
</style>
