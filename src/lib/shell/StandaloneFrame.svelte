<script lang="ts">
  // A panel popped out into its own window, always active. The native title
  // bar names it, the dock toggle in the panel's header is the way back, and
  // a status bar at its foot carries the lamps and the panel's own status
  // section (PANELS.md).
  import { onDestroy } from 'svelte';
  import ConfirmDialog from '../ui/ConfirmDialog.svelte';
  import DockToggle from './DockToggle.svelte';
  import KeyboardHelpOverlay from './KeyboardHelpOverlay.svelte';
  import { setFocusedTool } from './focus';
  import { bindKeys, dispatchKey, hostKeys } from './keys';
  import PanelView from './PanelView.svelte';
  import StatusBar from './StatusBar.svelte';
  import type { PanelId } from './panels';
  import { openSettings } from './shellState';

  export let id: PanelId;

  let statusSlot: HTMLElement | null = null;
  let showHelp = false;
  // The window is all the panel's already: filling it only sets the
  // panel's header aside.
  let filled = false;

  function showSettings(tab: 'general' | 'help') {
    openSettings(tab).catch((err) => console.error('Failed to open settings:', err));
  }

  // The one tool here has the keyboard for the window's life (focus.ts).
  setFocusedTool(id);

  // The window's keys go through the shell's dispatcher (keys.ts); the
  // host answers for the shortcut sheet and settings.
  const unbindKeys = bindKeys(hostKeys({ settings: () => showSettings('general'), shortcuts: () => (showHelp = true) }));
  onDestroy(unbindKeys);
</script>

<svelte:window on:keydown={dispatchKey} />

<div class="frame">
  <div class="panel">
    <PanelView {id} active {statusSlot} {filled} onFill={(on) => (filled = on)}>
      {#snippet windowKey()}<DockToggle {id} popped />{/snippet}
    </PanelView>
  </div>

  <StatusBar
    onOpenSettings={() => showSettings('general')}
    onOpenHelp={() => showSettings('help')}
    onShowShortcuts={() => (showHelp = true)}
  >
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
