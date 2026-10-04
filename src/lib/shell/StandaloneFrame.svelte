<script lang="ts">
  // A panel popped out into its own window: a title strip with the way back,
  // then the panel, always active (PANELS.md).
  import ActionButton from '../ui/ActionButton.svelte';
  import PanelView from './PanelView.svelte';
  import { panelTitle, type PanelId } from './panels';
  import { dock } from './shellState';

  export let id: PanelId;

  $: title = panelTitle(id);

  function dockBack() {
    dock(id).catch((err) => console.error(`Failed to dock ${title}:`, err));
  }
</script>

<div class="frame">
  <div class="strip">
    <span class="title">{title}</span>
    <ActionButton label="dock back" title="Return {title} to its tab in the main window" onClick={dockBack} />
  </div>
  <div class="body">
    <PanelView {id} active />
  </div>
</div>

<style>
  .frame {
    height: 100vh;
    display: flex;
    flex-direction: column;
    background: var(--bg-app);
  }

  .strip {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    padding: 0.2rem 0.75rem;
    background: var(--bg-header);
    border-bottom: 1px solid var(--border-subtle);
  }

  .title {
    font-family: var(--font-heading);
    color: var(--text-secondary);
  }

  .body {
    flex: 1;
    min-height: 0;
  }
</style>
