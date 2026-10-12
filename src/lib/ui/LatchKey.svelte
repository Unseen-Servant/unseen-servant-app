<script lang="ts">
  // A hardware latch in its own well, cut like the view switch's. At rest the
  // key is flush with the well floor; open, it comes up on the raised fill
  // (a view, not a mode). The LED under the icon is the only purple.
  export let open: boolean = false;
  export let lit: boolean = false;
  // A key with nothing to report goes without the lamp (Command's shelf).
  export let lamp: boolean = true;
  export let title: string;
  export let label: string;
  export let onClick: () => void;
</script>

<div class="key-well">
  <button
    class="key"
    class:open
    on:click={onClick}
    {title}
    aria-label={label}
    aria-pressed={open}
  >
    <slot />
    {#if lamp}<span class="lamp" class:lit aria-hidden="true"></span>{/if}
  </button>
</div>

<style>
  .key-well {
    display: flex;
    padding: 2px;
    background: var(--bg-app);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-well);
  }
  .key {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 3px;
    width: 26px;
    height: 22px;
    background: transparent;
    border: none;
    border-radius: var(--radius-md);
    color: var(--text-tertiary);
    cursor: pointer;
    padding: 0;
    transition: all var(--transition-fast);
    flex-shrink: 0;
  }
  .key:hover {
    color: var(--text-primary);
  }
  .key:active {
    transform: scale(0.97);
  }
  .key.open {
    background: var(--bg-header);
    color: var(--text-primary);
  }
  .key :global(svg) {
    width: 12px;
    height: 12px;
  }
  /* The LED: a dark slot at rest, so the key reads as hardware with a lamp
     that is off rather than a key with no lamp. Lit, it takes the transport's
     purple and glow. */
  .lamp {
    width: 10px;
    height: 2px;
    border-radius: var(--radius-sm);
    background: var(--border-subtle);
    transition: background var(--transition-fast);
  }
  .key.open .lamp {
    background: var(--bg-app);
  }
  .lamp.lit,
  .key.open .lamp.lit {
    background: var(--text-active);
    filter: var(--glow-active);
  }
</style>
