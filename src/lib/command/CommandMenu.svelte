<script lang="ts">
  // A context menu for Command's rows. Same anatomy as Legend Lore's
  // (.menu-row / .menu-divider in app.css): measured before it shows,
  // clamped to the window, and holding the one menu slot while open.
  import { onDestroy, onMount, tick } from 'svelte';
  import { chord, isBareKeyChord } from '../shell/keybindings';
  import { claimMenuSlot, releaseMenuSlot } from '../shell/menuSlot';
  import { CARET_RIGHT } from '../ui/iconPaths';
  import { clampToViewport } from '../ui/menuGeometry';
  import type { MenuItem } from './menu';

  export let x: number;
  export let y: number;
  export let items: MenuItem[];
  export let onClose: () => void;

  let el: HTMLDivElement;
  let pos = { x, y };
  let measured = false;

  // The open submenu: its row's index, and the flyout, fixed beside the
  // menu rather than inside it, which scrolls and would clip it.
  let openSub: number | null = null;
  let subEl: HTMLDivElement;
  let subPos = { x: 0, y: 0 };
  let subMeasured = false;

  // In a menu with choice rows, every row keeps the pip's width, so the
  // labels line up.
  $: lamps = items.some((item) => item.kind === 'action' && item.lamp !== undefined);

  function close() {
    releaseMenuSlot(close);
    onClose();
  }

  function pick(run: () => void) {
    close();
    run();
  }

  function onWindowMousedown(e: MouseEvent) {
    const target = e.target as Node;
    if (el && !el.contains(target) && !subEl?.contains(target)) close();
  }

  // Legend Lore's placement (ContextMenu clampOpenSubmenuToViewport): right
  // of the menu with its first row level with the trigger, on the left when
  // only that side has room, and kept inside the window.
  async function openSubmenu(i: number, trigger: HTMLElement) {
    if (openSub === i) return;
    openSub = i;
    subMeasured = false;
    await tick();
    const row = trigger.getBoundingClientRect();
    const box = subEl.getBoundingClientRect();
    const padding = 8;
    const spaceRight = window.innerWidth - row.right - padding;
    const spaceLeft = row.left - padding;
    const left = box.width > spaceRight && spaceLeft > spaceRight;
    const rem = parseFloat(getComputedStyle(document.documentElement).fontSize);
    subPos = clampToViewport(
      { x: left ? row.left - box.width : row.right, y: row.top - 0.15 * rem },
      { width: box.width, height: box.height },
      { width: window.innerWidth, height: window.innerHeight },
    );
    subMeasured = true;
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
    {:else if item.kind === 'submenu'}
      <button
        type="button"
        class="menu-row"
        class:open={openSub === i}
        role="menuitem"
        aria-haspopup="menu"
        aria-expanded={openSub === i}
        on:pointerenter={(e) => openSubmenu(i, e.currentTarget)}
        on:click={(e) => openSubmenu(i, e.currentTarget)}
      >
        {#if lamps}<span class="menu-pip" aria-hidden="true"></span>{/if}
        <span class="menu-label">{item.label}</span>
        <svg class="caret submenu-caret" viewBox="96 64 512 512" fill="currentColor" aria-hidden="true"><path d={CARET_RIGHT} /></svg>
      </button>
    {:else if item.kind === 'heading'}
      <div class="menu-heading ledger-label">{item.label}</div>
    {:else if item.kind === 'picks'}
      <div class="menu-picks" role="group" aria-label={item.label}>
        {#each item.picks as p (p.label)}
          {@const run = p.action}
          <button type="button" class="menu-pick" role="menuitemradio" aria-checked={p.on} aria-label={p.label} title={p.label} on:click={() => pick(run)}>
            <span class="menu-swatch" class:none={!p.swatch} style:background={p.swatch} aria-hidden="true"></span>
            <span class="menu-pip" class:on={p.on} aria-hidden="true"></span>
          </button>
        {/each}
      </div>
    {:else}
      {@const run = item.action}
      {#if item.lamp !== undefined}
        <button type="button" class="menu-row" role="menuitemradio" aria-checked={item.lamp} on:pointerenter={() => (openSub = null)} on:click={() => pick(run)}>
          <span class="menu-pip" class:on={item.lamp} aria-hidden="true"></span>
          <span class="menu-label">{item.label}</span>
        </button>
      {:else}
        <button type="button" class="menu-row" class:danger={item.danger} role="menuitem" on:pointerenter={() => (openSub = null)} on:click={() => pick(run)}>
          {#if lamps}<span class="menu-pip" aria-hidden="true"></span>{/if}
          <span class="menu-label">{item.label}</span>
          {#if item.chord}
            <span class="menu-chord" class:bare={isBareKeyChord(item.chord)} aria-hidden="true">{chord(item.chord)}</span>
          {/if}
        </button>
      {/if}
    {/if}
  {/each}
</div>

{#if openSub !== null}
  {@const open = items[openSub]}
  {#if open.kind === 'submenu'}
    <div class="command-menu" class:measured={subMeasured} bind:this={subEl} style:left="{subPos.x}px" style:top="{subPos.y}px" role="menu" aria-label={open.label}>
      {#each open.items as item, j (j)}
        {#if item.kind === 'divider'}
          <hr class="menu-divider" />
        {:else if item.kind === 'action'}
          {@const run = item.action}
          <button type="button" class="menu-row" class:danger={item.danger} role="menuitem" title={item.label} on:click={() => pick(run)}>
            <span class="menu-label">{item.label}</span>
          </button>
        {/if}
      {/each}
    </div>
  {/if}
{/if}

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
  }

  /* Legend Lore's submenu row (ContextMenu .submenu-trigger): lit while its
     flyout is open, the caret at the far end. */
  .menu-row.open {
    background: var(--bg-focused);
  }

  .submenu-caret {
    font-size: 0.7rem;
    opacity: 0.6;
    margin-left: auto;
  }

  .menu-label {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
  }
</style>
