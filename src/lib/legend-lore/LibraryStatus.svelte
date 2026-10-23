<script lang="ts">
  // Legend Lore's section of the status bar: the scope bypass, the library's
  // readouts, and the folder and sync keys. The panel hoists it into the
  // slot its host keeps in the bar (PANELS.md); the bar's own styles dress
  // the shared parts (.rule, .stats, .icon-btn).
  import { chordHint } from '../shell/keybindings';
  import { FOLDER, FOLDER_OPEN } from '../ui/iconPaths';
  import { m } from '../paraglide/messages';

  export let selectedFolder: string;
  export let selectedCount: number;
  export let indexedCount: number;
  export let gameSystemCount: number;
  export let topGameSystem: string = '';
  export let totalChunks: number = 0;
  export let storageBytes: number;
  export let isSyncing: boolean = false;
  // Master bypass is lit, not persisted — the lamp is the only thing
  // telling you the console you can see isn't currently doing anything.
  export let scopeBypassed: boolean = false;
  export let lastSyncTime: Date | null = null;
  export let onSync: (() => void) | undefined = undefined;
  export let onOpenFolder: () => void;

  // lastSyncTime is stamped by every index-status check, not only by
  // syncs, and this button runs a check — so name it for what it is.
  $: syncTooltip = (lastSyncTime
    ? m.lore_status_check_last({ time: lastSyncTime.toLocaleTimeString() })
    : m.lore_status_check()) + chordHint('sync.run');

  function formatSize(bytes: number): string {
    if (bytes >= 1_073_741_824) return m.lore_status_size_gb({ size: (bytes / 1_073_741_824).toFixed(1) });
    if (bytes >= 1_048_576) return m.lore_status_size_mb({ size: (bytes / 1_048_576).toFixed(1) });
    if (bytes >= 1_024) return m.lore_status_size_kb({ size: (bytes / 1_024).toFixed(0) });
    return m.lore_status_size_b({ size: bytes });
  }
</script>

{#if selectedFolder}
  {#if scopeBypassed}
    <span class="rule" aria-hidden="true"></span>
    <span
      class="bypass-lamp readout-label"
      title={m.lore_status_bypass_title()}
    >{m.lore_status_bypass()}</span>
  {/if}
  <span class="rule" aria-hidden="true"></span>
  {#if indexedCount > 0}
    <!-- Rules divide groups; readouts within a group sit apart on
         spacing alone, so the two levels never look alike. -->
    <span class="stats">
      <span title={m.lore_status_indexed_title({ count: indexedCount, chunks: totalChunks.toLocaleString() })}>{m.lore_status_books({ count: indexedCount })}</span>
      {#if gameSystemCount > 0}
        <span title={topGameSystem}>{m.lore_status_systems({ count: gameSystemCount })}</span>
      {/if}
      {#if storageBytes > 0}
        <span>{formatSize(storageBytes)}</span>
      {/if}
    </span>
  {:else}
    <span>{m.lore_status_selected({ count: selectedCount })}</span>
  {/if}
  <span class="rule" aria-hidden="true"></span>
  <button class="icon-btn" on:click={onOpenFolder} aria-label={m.lore_status_reveal()} title={m.lore_status_reveal()}>
    <svg class="btn-icon" viewBox="0 0 640 640" fill="currentColor" aria-hidden="true">
      <path class="folder-shut" d={FOLDER}/>
      <path class="folder-opened" d={FOLDER_OPEN}/>
    </svg>
  </button>
  {#if onSync}
    <button class="icon-btn" class:spinning={isSyncing} on:click={onSync} aria-label={isSyncing ? m.lore_status_syncing() : m.lore_status_check()} title={syncTooltip} disabled={isSyncing}>
      <!-- Font Awesome "arrows-rotate" icon (src/lib/ui/icons/arrows-rotate-solid-full.svg) -->
      <svg class="btn-icon" viewBox="0 0 640 640" fill="currentColor" aria-hidden="true">
        <path d="M129.9 292.5C143.2 199.5 223.3 128 320 128C373 128 421 149.5 455.8 184.2C456 184.4 456.2 184.6 456.4 184.8L464 192L416.1 192C398.4 192 384.1 206.3 384.1 224C384.1 241.7 398.4 256 416.1 256L544.1 256C561.8 256 576.1 241.7 576.1 224L576.1 96C576.1 78.3 561.8 64 544.1 64C526.4 64 512.1 78.3 512.1 96L512.1 149.4L500.8 138.7C454.5 92.6 390.5 64 320 64C191 64 84.3 159.4 66.6 283.5C64.1 301 76.2 317.2 93.7 319.7C111.2 322.2 127.4 310 129.9 292.6zM573.4 356.5C575.9 339 563.7 322.8 546.3 320.3C528.9 317.8 512.6 330 510.1 347.4C496.8 440.4 416.7 511.9 320 511.9C267 511.9 219 490.4 184.2 455.7C184 455.5 183.8 455.3 183.6 455.1L176 447.9L223.9 447.9C241.6 447.9 255.9 433.6 255.9 415.9C255.9 398.2 241.6 383.9 223.9 383.9L96 384C87.5 384 79.3 387.4 73.3 393.5C67.3 399.6 63.9 407.7 64 416.3L65 543.3C65.1 561 79.6 575.2 97.3 575C115 574.8 129.2 560.4 129 542.7L128.6 491.2L139.3 501.3C185.6 547.4 249.5 576 320 576C449 576 555.7 480.6 573.4 356.5z"/>
      </svg>
    </button>
  {/if}
{/if}

<style>
  .icon-btn.spinning,
  .icon-btn.spinning:disabled {
    color: var(--text-accent);
  }
  .icon-btn.spinning .btn-icon {
    animation: spin 1s linear infinite;
    filter: var(--glow-accent);
  }
  @keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }

  /* Purple + glow: bypass is a mode you switched on, which is what the
     colour semantics reserve purple for. Not amber — that is connectivity
     — and not danger, since nothing is being destroyed. */
  .bypass-lamp {
    color: var(--text-active);
    filter: var(--glow-active);
  }
</style>
