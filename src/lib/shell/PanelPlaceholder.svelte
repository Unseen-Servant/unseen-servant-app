<script lang="ts">
  // Stand-in for a tool that isn't built yet. The context readout doubles as
  // the proof that shell state reaches every window.
  import { appContext } from './shellState';

  export let title: string;
  export let purpose: string;
</script>

<section class="placeholder">
  <h1>{title}</h1>
  <p class="purpose">{purpose}</p>
  <p class="readout">
    <span class="key">campaign</span>
    <span class="value" class:none={!$appContext.campaign}>{$appContext.campaign ?? 'none'}</span>
    <span class="sep">·</span>
    <span class="key">session</span>
    <span class="value" class:none={!$appContext.session}>{$appContext.session ?? 'none'}</span>
  </p>
</section>

<style>
  .placeholder {
    height: 100%;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    background: var(--bg-app);
    color: var(--text-secondary);
  }

  h1 {
    margin: 0;
    font-family: var(--font-heading);
    font-weight: normal;
    font-size: 1.6rem;
    color: var(--text-primary);
  }

  .purpose {
    margin: 0;
    color: var(--text-tertiary);
  }

  .readout {
    margin: 0.75rem 0 0;
    display: flex;
    gap: 0.4rem;
    align-items: baseline;
  }

  .key {
    color: var(--text-tertiary);
  }

  .value {
    color: var(--text-accent);
  }

  .value.none {
    color: var(--text-tertiary);
    font-style: italic;
  }

  .sep {
    color: var(--text-tertiary);
  }
</style>
