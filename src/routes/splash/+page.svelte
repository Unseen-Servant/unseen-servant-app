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

    // The window starts hidden and shows itself once the card is in the DOM
    // in its own fonts: macOS shapes the shadow of a transparent window from
    // what it holds when it appears. Nothing here may wait on a frame — a
    // hidden webview never runs requestAnimationFrame — and the font wait is
    // capped, since a stall would keep the splash from ever appearing.
    await tick();
    await Promise.race([document.fonts.ready, new Promise((resolve) => setTimeout(resolve, 500))]);
    try {
      await getCurrentWebviewWindow().show();
    } catch (e) {
      console.error('Splash could not show itself:', e);
    }
  });

  onDestroy(() => unlisten?.());
</script>

<svelte:head>
  <title>Unseen Servant</title>
</svelte:head>

<LaunchSplash {snapshot} {version} />

<style>
  /* app.css paints the page; here only the card may, or the transparent
     window's corners come out square again. */
  :global(html),
  :global(body) {
    background: transparent;
  }
</style>
