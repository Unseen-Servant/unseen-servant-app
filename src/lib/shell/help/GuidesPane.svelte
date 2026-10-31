<script lang="ts">
  import GettingStartedSteps from '../../legend-lore/GettingStartedSteps.svelte';
  import CommandGuide from '../../command/CommandGuide.svelte';
  import AuguryGuide from '../../augury/AuguryGuide.svelte';
  import ServantGuide from '../../servant/ServantGuide.svelte';

  export let folderSelected: boolean = false;
  export let filesIndexed: boolean = false;
  export let mcpConnected: boolean = false;
  export let onSelectFolder: () => void;
  export let onCopyMcpConfig: () => void;
</script>

<div class="pane">
  <h3 class="pane-title ledger-label">Legend Lore</h3>

  <GettingStartedSteps
    {folderSelected}
    {filesIndexed}
    {onSelectFolder}
  />

  <h3 class="pane-title ledger-label second">Command</h3>

  <CommandGuide />

  <h3 class="pane-title ledger-label second">Augury</h3>

  <AuguryGuide />

  <!-- MCP reaches both tools, so its step is the Servant's, not one tool's. -->
  <h3 class="pane-title ledger-label second">Servant</h3>

  <ServantGuide {mcpConnected} {onCopyMcpConfig} />
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
