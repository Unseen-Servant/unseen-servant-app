<script lang="ts">
  import GettingStartedSteps from '../GettingStartedSteps.svelte';

  export let ollamaRunning: boolean = false;
  export let ollamaModelReady: boolean = false;
  export let folderSelected: boolean = false;
  export let filesIndexed: boolean = false;
  export let collectionsCreated: boolean = false;
  export let mcpConnected: boolean = false;
  export let onSelectFolder: () => void;
  export let onCopyMcpConfig: () => void;
</script>

<div class="pane">
  <header class="pane-head">
    <h3 class="pane-title section-title">Setting up Legend Lore</h3>
    <p class="pane-desc">
      The five pieces that make Legend Lore tick. Status badges reflect your
      current state — refer back here whenever you need to redo a step.
    </p>
  </header>

  <GettingStartedSteps
    {ollamaRunning}
    {ollamaModelReady}
    {folderSelected}
    {filesIndexed}
    {collectionsCreated}
    {mcpConnected}
    {onSelectFolder}
    {onCopyMcpConfig}
  />
</div>

<style>
  .pane {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .pane-head {
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
  }

  .pane-title {
    margin: 0;
  }

  .pane-desc {
    margin: 0;
    font-family: var(--font-body);
    font-size: 0.8rem;
    color: var(--text-secondary);
    line-height: 1.45;
  }
</style>
