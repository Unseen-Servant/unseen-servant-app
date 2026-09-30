<script lang="ts">
  // The launch splash window (label "splash", tauri.conf.json). Rust runs
  // the cold start and closes this window when the tools open.
  import { onMount, onDestroy, tick } from 'svelte';
  import { invoke } from '@tauri-apps/api/core';
  import { listen } from '@tauri-apps/api/event';
  import { getVersion } from '@tauri-apps/api/app';
  import { getCurrentWebviewWindow } from '@tauri-apps/api/webviewWindow';
  import LaunchSplash from '../../lib/shell/LaunchSplash.svelte';
  import { newerSnapshot, type BootSnapshot } from '../../lib/shell/bootSteps';

  let snapshot: BootSnapshot | null = null;
  let version = '';
  let unlisten: (() => void) | null = null;

  onMount(async () => {
    // Listen before pulling so no update falls between the two; seq sorts
    // out which of them is newer.
    unlisten = await listen<BootSnapshot>('boot://update', (event) => {
      snapshot = newerSnapshot(snapshot, event.payload);
    });
    try {
      snapshot = newerSnapshot(snapshot, await invoke<BootSnapshot>('get_boot_state'));
    } catch {
      // The lamps stay dark; the boot still opens the tools.
    }
    try {
      version = await getVersion();
    } catch {
      // No version line, nothing else lost.
    }

    // The window starts hidden so its blank first frame never shows. Reveal
    // it once the card has painted in its own fonts.
    await tick();
    await document.fonts.ready;
    requestAnimationFrame(() => {
      void getCurrentWebviewWindow().show();
    });
  });

  onDestroy(() => unlisten?.());
</script>

<svelte:head>
  <title>Unseen Servant</title>
</svelte:head>

<LaunchSplash {snapshot} {version} />
