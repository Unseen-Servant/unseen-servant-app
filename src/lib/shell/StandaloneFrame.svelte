<script lang="ts">
  // A panel popped out into its own window, always active. The native title
  // bar names it, the dock toggle in the panel's header is the way back, and
  // a status bar at its foot carries the lamps and the panel's own status
  // section (PANELS.md).
  import ConfirmDialog from '../ui/ConfirmDialog.svelte';
  import DockToggle from './DockToggle.svelte';
  import KeyboardHelpOverlay from './KeyboardHelpOverlay.svelte';
  import PanelView from './PanelView.svelte';
  import StatusBar from './StatusBar.svelte';
  import type { PanelId } from './panels';
  import { openSettings } from './shellState';

  export let id: PanelId;

  let statusSlot: HTMLElement | null = null;
  let showHelp = false;

  function showSettings() {
    openSettings().catch((err) => console.error('Failed to open settings:', err));
  }
</script>

<div class="frame">
  <div class="panel">
    <PanelView {id} active {statusSlot}>
      {#snippet windowKey()}<DockToggle {id} popped />{/snippet}
    </PanelView>
  </div>

  <StatusBar onOpenSettings={showSettings} onShowHelp={() => (showHelp = true)}>
    <div class="status-section" bind:this={statusSlot}></div>
  </StatusBar>

  <KeyboardHelpOverlay visible={showHelp} onClose={() => (showHelp = false)} />
  <!-- One prompt per window, for whichever panel asks (confirmStore). -->
  <ConfirmDialog />
</div>

<style>
  .frame {
    height: 100vh;
    display: flex;
    flex-direction: column;
    background: var(--bg-app);
  }

  .panel {
    flex: 1;
    min-height: 0;
  }
</style>
