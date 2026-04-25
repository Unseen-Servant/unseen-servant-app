<script lang="ts">
  import GettingStartedSteps from './GettingStartedSteps.svelte';

  export let ollamaRunning: boolean = false;
  export let ollamaModelReady: boolean = false;
  export let folderSelected: boolean = false;
  export let filesIndexed: boolean = false;
  export let collectionsCreated: boolean = false;
  export let onSelectFolder: () => void;
  export let onCopyMcpConfig: () => void;
</script>

<div class="getting-started-page">
  <h1 class="page-title font-display">Getting Started</h1>
  <p class="page-subtitle">Set up Legend Lore to browse, index, and search your TTRPG library.</p>
  <GettingStartedSteps
    {ollamaRunning}
    {ollamaModelReady}
    {folderSelected}
    {filesIndexed}
    {collectionsCreated}
    {onSelectFolder}
    {onCopyMcpConfig}
  />
</div>

<style>
  .getting-started-page {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 2rem;
    gap: 0.25rem;
  }

  .page-title {
    font-size: 1.6rem;
    color: var(--text-accent);
    margin: 0;
    letter-spacing: 0.04em;
  }

  .page-subtitle {
    font-size: 0.95rem;
    color: var(--text-secondary);
    margin: 0 0 1rem;
  }
</style>
