<script lang="ts">
  import GettingStartedSteps from '../../legend-lore/GettingStartedSteps.svelte';
  import CommandGuide from '../../command/CommandGuide.svelte';

  export let sidecarConnected: boolean = true;
  export let ollamaRunning: boolean = false;
  export let ollamaModelReady: boolean = false;
  export let folderSelected: boolean = false;
  export let filesIndexed: boolean = false;
  export let mcpConnected: boolean = false;
  export let onSelectFolder: () => void;
  export let onCopyMcpConfig: () => void;
</script>

<div class="pane">
  <h3 class="pane-title ledger-label">Legend Lore</h3>

  <GettingStartedSteps
    {sidecarConnected}
    {ollamaRunning}
    {ollamaModelReady}
    {folderSelected}
    {filesIndexed}
    {mcpConnected}
    {onSelectFolder}
    {onCopyMcpConfig}
  />

  <h3 class="pane-title ledger-label second">Command</h3>

  <CommandGuide />
</div>

<style>
  .pane {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .pane-title {
    margin: 0;
  }
  .pane-title.second {
    margin-top: 1rem;
  }
</style>
