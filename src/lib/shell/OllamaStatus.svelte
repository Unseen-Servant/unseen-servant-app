<script lang="ts">
  export let ollamaRunning: boolean = false;
  export let ollamaModelReady: boolean = false;

  $: ready = ollamaRunning && ollamaModelReady;
</script>

<div class="ollama-status">
  <span
    class="badge readout-label"
    class:ok={ready}
    class:partial={ollamaRunning && !ollamaModelReady}
  >
    {#if ready}Ready
    {:else if ollamaRunning}Model pending
    {:else}Not detected{/if}
  </span>

  {#if !ollamaRunning}
    <p class="hint">
      Download from <strong>ollama.com</strong>, install, and launch the app.
    </p>
  {:else if !ollamaModelReady}
    <p class="hint">Pull the embedding model (one-time):</p>
    <code class="command">ollama pull bge-m3</code>
  {/if}
</div>

<style>
  .ollama-status {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 0.5rem;
  }

  .badge {
    color: var(--text-tertiary);
  }
  .badge.ok {
    color: var(--text-active);
  }
  .badge.partial {
    color: var(--text-accent);
  }

  .hint {
    margin: 0;
    font-family: var(--font-body);
    font-size: 0.85rem;
    color: var(--text-secondary);
    line-height: 1.45;
  }
  .hint strong {
    color: var(--text-primary);
    font-weight: 600;
  }

  .command {
    display: inline-block;
    padding: 0.3rem 0.55rem;
    background: var(--bg-focused);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    font-family: var(--font-mono);
    font-size: 0.75rem;
    color: var(--text-primary);
    user-select: all;
    -webkit-user-select: all;
  }
</style>
