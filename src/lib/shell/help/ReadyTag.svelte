<script lang="ts">
  // A Guides step's state: a readout in a well that always reads READY, its
  // pilot lamp (the splash's LED, LaunchSplash.svelte) saying whether it is:
  // dark or amber. `state` says it in words, for the tooltip and screen
  // readers.
  import { m } from '../../paraglide/messages';

  export let lit: boolean = false;
  export let state: string;
</script>

<span
  class="tag readout-label"
  class:lit
  role="img"
  aria-label={state}
  title={state}
><span class="led"></span>{m.guides_ready()}</span>

<style>
  .tag {
    flex-shrink: 0;
    align-self: center;
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.15rem 0.5rem 0.15rem 0.4rem;
    background: var(--bg-app);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    font-size: 0.62rem;
    color: var(--text-tertiary);
  }
  .tag.lit {
    color: var(--text-secondary);
  }
  .led {
    width: 12px;
    height: 5px;
    border-radius: var(--radius-cell);
    background: var(--bg-category);
  }
  .tag.lit .led {
    background: var(--text-connected);
  }
</style>
