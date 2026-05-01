<script lang="ts">
  import GettingStartedSteps from './GettingStartedSteps.svelte';

  export let ollamaRunning: boolean = false;
  export let ollamaModelReady: boolean = false;
  export let folderSelected: boolean = false;
  export let filesIndexed: boolean = false;
  export let collectionsCreated: boolean = false;
  export let mcpConnected: boolean = false;
  export let onSelectFolder: () => void;
  export let onCopyMcpConfig: () => void;
</script>

<div class="page">
  <span class="label">Initial setup</span>
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
  .page {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 2.5rem 2rem;
    gap: 0.8rem;
    overflow-y: auto;
  }

  .label {
    font-family: var(--font-heading, var(--font-body));
    font-size: 0.7rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--text-tertiary);
    width: 100%;
    max-width: 540px;
  }
</style>
