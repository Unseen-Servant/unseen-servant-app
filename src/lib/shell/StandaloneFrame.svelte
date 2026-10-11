<script lang="ts">
  // A panel popped out into its own window, always active. No chrome of its
  // own: the native title bar names it, and the way back is the dock toggle
  // in the panel's header (PANELS.md).
  import ConfirmDialog from '../ui/ConfirmDialog.svelte';
  import DockToggle from './DockToggle.svelte';
  import PanelView from './PanelView.svelte';
  import type { PanelId } from './panels';

  export let id: PanelId;
</script>

<div class="frame">
  <PanelView {id} active>
    {#snippet windowKey()}<DockToggle {id} popped />{/snippet}
  </PanelView>

  <!-- One prompt per window, for whichever panel asks (confirmStore). -->
  <ConfirmDialog />
</div>

<style>
  .frame {
    height: 100vh;
    background: var(--bg-app);
  }
</style>
