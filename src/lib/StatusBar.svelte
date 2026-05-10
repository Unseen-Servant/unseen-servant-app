<script lang="ts">
  import { jobNotification, pendingNotification } from './notificationStore';
  import { chordHint } from './keybindings';

  export let selectedFolder: string;
  export let sidecarConnected: boolean;
  export let mcpConnected: boolean = false;
  export let mcpActive: boolean = false;
  export let selectedCount: number;
  export let indexedCount: number;
  export let gameSystemCount: number;
  export let topGameSystem: string = '';
  export let totalChunks: number = 0;
  export let storageBytes: number;
  export let reclaimableBytes: number = 0;
  export let isSyncing: boolean = false;
  export let lastSyncTime: Date | null = null;
  export let onSync: (() => void) | undefined = undefined;
  export let onOpenFolder: () => void;
  export let onShowGuide: () => void;
  export let onOpenSettings: () => void;
  export let onShowHelp: () => void;
  export let showGuideButton: boolean = true;

  $: jobNote = $jobNotification;
  $: pendingNote = $pendingNotification;

  function handlePendingDismiss() {
    pendingNote?.onDismiss?.();
    pendingNotification.dismiss();
  }

  $: syncTooltip = (lastSyncTime
    ? `Last synced ${lastSyncTime.toLocaleTimeString()}`
    : 'Sync index') + chordHint('sync.run');

  $: storageTooltip = reclaimableBytes > 0
    ? `${formatSize(reclaimableBytes)} reclaimable — compact from Settings → Library`
    : 'No reclaimable space';

  function formatSize(bytes: number): string {
    if (bytes >= 1_073_741_824) return (bytes / 1_073_741_824).toFixed(1) + ' GB';
    if (bytes >= 1_048_576) return (bytes / 1_048_576).toFixed(1) + ' MB';
    if (bytes >= 1_024) return (bytes / 1_024).toFixed(0) + ' KB';
    return bytes + ' B';
  }
</script>

<footer class="statusbar">
  <div class="statusbar-left">
    {#if selectedFolder}
      <span class="indicator" class:connected={sidecarConnected} title={sidecarConnected ? 'Sidecar connected' : 'Sidecar disconnected'}>
        <!-- Font Awesome "server" icon (static/icons/server-solid-full.svg) -->
        <svg class="indicator-icon" viewBox="0 0 640 640" fill="currentColor">
          <path d="M160 96C124.7 96 96 124.7 96 160L96 224C96 259.3 124.7 288 160 288L480 288C515.3 288 544 259.3 544 224L544 160C544 124.7 515.3 96 480 96L160 96zM376 168C389.3 168 400 178.7 400 192C400 205.3 389.3 216 376 216C362.7 216 352 205.3 352 192C352 178.7 362.7 168 376 168zM432 192C432 178.7 442.7 168 456 168C469.3 168 480 178.7 480 192C480 205.3 469.3 216 456 216C442.7 216 432 205.3 432 192zM160 352C124.7 352 96 380.7 96 416L96 480C96 515.3 124.7 544 160 544L480 544C515.3 544 544 515.3 544 480L544 416C544 380.7 515.3 352 480 352L160 352zM376 424C389.3 424 400 434.7 400 448C400 461.3 389.3 472 376 472C362.7 472 352 461.3 352 448C352 434.7 362.7 424 376 424zM432 448C432 434.7 442.7 424 456 424C469.3 424 480 434.7 480 448C480 461.3 469.3 472 456 472C442.7 472 432 461.3 432 448z"/>
        </svg>
      </span>
      <span
        class="indicator mcp"
        class:connected={mcpConnected}
        class:active={mcpActive}
        title={mcpActive ? 'MCP active — agent querying' : mcpConnected ? 'MCP connected' : 'MCP not detected'}
      >
        <!-- MCP logo (static/icons/mcp.svg) -->
        <svg class="indicator-icon" viewBox="0 0 180 180" fill="none" stroke="currentColor" stroke-width="12" stroke-linecap="round">
          <path d="M18 84.8528L85.8822 16.9706C95.2548 7.59798 110.451 7.59798 119.823 16.9706V16.9706C129.196 26.3431 129.196 41.5391 119.823 50.9117L68.5581 102.177"/>
          <path d="M69.2652 101.47L119.823 50.9117C129.196 41.5391 144.392 41.5391 153.765 50.9117L154.118 51.2652C163.491 60.6378 163.491 75.8338 154.118 85.2063L92.7248 146.6C89.6006 149.724 89.6006 154.789 92.7248 157.913L105.331 170.52"/>
          <path d="M102.853 33.9411L52.6482 84.1457C43.2756 93.5183 43.2756 108.714 52.6482 118.087V118.087C62.0208 127.459 77.2167 127.459 86.5893 118.087L136.794 67.8822"/>
        </svg>
      </span>
      {#if indexedCount > 0}
        <span title="{indexedCount} PDF{indexedCount === 1 ? '' : 's'}, {totalChunks.toLocaleString()} searchable chunks">{indexedCount} PDF{indexedCount === 1 ? '' : 's'} indexed</span>
        {#if gameSystemCount > 0}
          <span class="separator">&middot;</span>
          <span title={topGameSystem}>{gameSystemCount} system{gameSystemCount === 1 ? '' : 's'}</span>
        {/if}
        {#if storageBytes > 0}
          <span class="separator">&middot;</span>
          <span title={storageTooltip}>{formatSize(storageBytes)}</span>
        {/if}
      {:else}
        <span>{selectedCount} selected</span>
      {/if}
      <span class="separator">&middot;</span>
      <button class="sync-btn" on:click={onOpenFolder} title={`Reveal library folder${chordHint('library.reveal')}`}>
        <!-- Font Awesome "folder-open" icon -->
        <svg class="sync-icon" viewBox="0 0 576 512" fill="currentColor">
          <path d="M88.7 223.8L0 375.8L0 96C0 60.7 28.7 32 64 32L181.5 32C198.5 32 214.8 38.7 226.7 50.7L269.3 93.3C281.3 105.3 297.6 112 314.5 112L448 112C483.3 112 512 140.7 512 176L512 208L144 208C121.4 208 100.6 220 88.7 223.8zM144 240L560 240C572.1 240 583.3 246.8 588.9 257.6C594.5 268.4 593.5 281.4 586.4 291.2L501.9 467.2C495.3 480.6 481.6 488 467.2 488L48 488C36 488 24.8 481.2 19.2 470.4C13.6 459.6 14.6 446.6 21.7 436.8L106.2 260.8C112.8 247.4 126.5 240 144 240z"/>
        </svg>
      </button>
      {#if onSync}
        <button class="sync-btn" class:spinning={isSyncing} on:click={onSync} title={syncTooltip} disabled={isSyncing}>
          <!-- Font Awesome "arrows-rotate" icon (static/icons/arrows-rotate-solid-full.svg) -->
          <svg class="sync-icon" viewBox="0 0 640 640" fill="currentColor">
            <path d="M129.9 292.5C143.2 199.5 223.3 128 320 128C373 128 421 149.5 455.8 184.2C456 184.4 456.2 184.6 456.4 184.8L464 192L416.1 192C398.4 192 384.1 206.3 384.1 224C384.1 241.7 398.4 256 416.1 256L544.1 256C561.8 256 576.1 241.7 576.1 224L576.1 96C576.1 78.3 561.8 64 544.1 64C526.4 64 512.1 78.3 512.1 96L512.1 149.4L500.8 138.7C454.5 92.6 390.5 64 320 64C191 64 84.3 159.4 66.6 283.5C64.1 301 76.2 317.2 93.7 319.7C111.2 322.2 127.4 310 129.9 292.6zM573.4 356.5C575.9 339 563.7 322.8 546.3 320.3C528.9 317.8 512.6 330 510.1 347.4C496.8 440.4 416.7 511.9 320 511.9C267 511.9 219 490.4 184.2 455.7C184 455.5 183.8 455.3 183.6 455.1L176 447.9L223.9 447.9C241.6 447.9 255.9 433.6 255.9 415.9C255.9 398.2 241.6 383.9 223.9 383.9L96 384C87.5 384 79.3 387.4 73.3 393.5C67.3 399.6 63.9 407.7 64 416.3L65 543.3C65.1 561 79.6 575.2 97.3 575C115 574.8 129.2 560.4 129 542.7L128.6 491.2L139.3 501.3C185.6 547.4 249.5 576 320 576C449 576 555.7 480.6 573.4 356.5z"/>
          </svg>
        </button>
      {/if}
    {/if}
    {#if jobNote}
      {#if selectedFolder}<span class="separator">&middot;</span>{/if}
      <div class="status-note" class:status-error={jobNote.type === 'error'}>
        {#if jobNote.type === 'progress'}
          <span class="status-note-msg">
            {jobNote.filesCompleted ?? 0}/{jobNote.filesTotal ?? 0} files &middot; {(jobNote.chunksProcessed ?? 0).toLocaleString()} chunks
          </span>
        {:else}
          <span class="status-note-msg">{jobNote.message}</span>
        {/if}
      </div>
    {/if}
    {#if pendingNote}
      {#if selectedFolder || jobNote}<span class="separator">&middot;</span>{/if}
      <div class="status-note">
        <span class="status-note-msg">{pendingNote.message}</span>
        {#if pendingNote.actionLabel}
          <button
            class="note-action"
            on:click={pendingNote.onAction}
            disabled={pendingNote.actionDisabled || !pendingNote.onAction}
          >{pendingNote.actionLabel}</button>
        {/if}
        {#if pendingNote.onDismiss}
          <button class="note-dismiss" on:click={handlePendingDismiss} aria-label="Dismiss">&times;</button>
        {/if}
      </div>
    {/if}
  </div>
  <div class="statusbar-right">
    <button class="license-link" on:click={onOpenSettings} title={`Settings${chordHint('settings.open')}`}>
      <!-- Font Awesome "gear" icon -->
      <svg class="license-icon" viewBox="0 0 512 512" fill="currentColor">
        <path d="M495.9 166.6c3.2 8.7 .5 18.4-6.4 24.6l-43.3 39.4c1.1 8.3 1.7 16.8 1.7 25.4s-.6 17.1-1.7 25.4l43.3 39.4c6.9 6.2 9.6 15.9 6.4 24.6c-4.4 11.9-9.7 23.3-15.8 34.3l-4.7 8.1c-6.6 11-14 21.4-22.1 31.2c-5.9 7.2-15.7 9.6-24.5 6.8l-55.7-17.7c-13.4 10.3-28.2 18.9-44 25.4l-12.5 57.1c-2 9.1-9 16.3-18.2 17.8c-13.8 2.3-28 3.5-42.5 3.5s-28.7-1.2-42.5-3.5c-9.2-1.5-16.2-8.7-18.2-17.8l-12.5-57.1c-15.8-6.5-30.6-15.1-44-25.4L83.1 425.9c-8.8 2.8-18.6 .3-24.5-6.8c-8.1-9.8-15.5-20.2-22.1-31.2l-4.7-8.1c-6.1-11-11.4-22.4-15.8-34.3c-3.2-8.7-.5-18.4 6.4-24.6l43.3-39.4C64.6 273.1 64 264.6 64 256s.6-17.1 1.7-25.4L22.4 191.2c-6.9-6.2-9.6-15.9-6.4-24.6c4.4-11.9 9.7-23.3 15.8-34.3l4.7-8.1c6.6-11 14-21.4 22.1-31.2c5.9-7.2 15.7-9.6 24.5-6.8l55.7 17.7c13.4-10.3 28.2-18.9 44-25.4l12.5-57.1c2-9.1 9-16.3 18.2-17.8C227.3 1.2 241.5 0 256 0s28.7 1.2 42.5 3.5c9.2 1.5 16.2 8.7 18.2 17.8l12.5 57.1c15.8 6.5 30.6 15.1 44 25.4l55.7-17.7c8.8-2.8 18.6-.3 24.5 6.8c8.1 9.8 15.5 20.2 22.1 31.2l4.7 8.1c6.1 11 11.4 22.4 15.8 34.3zM256 336a80 80 0 1 0 0-160 80 80 0 1 0 0 160z"/>
      </svg>
    </button>
    <button class="license-link" on:click={onShowHelp} title={`Keyboard shortcuts${chordHint('help.overlay')}`}>
      <!-- Font Awesome "circle-question" icon (static/icons/circle-question-solid-full.svg) -->
      <svg class="license-icon" viewBox="0 0 640 640" fill="currentColor">
        <path d="M320 576C461.4 576 576 461.4 576 320C576 178.6 461.4 64 320 64C178.6 64 64 178.6 64 320C64 461.4 178.6 576 320 576zM320 240C302.3 240 288 254.3 288 272C288 285.3 277.3 296 264 296C250.7 296 240 285.3 240 272C240 227.8 275.8 192 320 192C364.2 192 400 227.8 400 272C400 319.2 364 339.2 344 346.5L344 350.3C344 363.6 333.3 374.3 320 374.3C306.7 374.3 296 363.6 296 350.3L296 342.2C296 321.7 310.8 307 326.1 302C332.5 299.9 339.3 296.5 344.3 291.7C348.6 287.5 352 281.7 352 272.1C352 254.4 337.7 240.1 320 240.1zM288 432C288 414.3 302.3 400 320 400C337.7 400 352 414.3 352 432C352 449.7 337.7 464 320 464C302.3 464 288 449.7 288 432z"/>
      </svg>
    </button>
    {#if showGuideButton}
      <button class="license-link" on:click={onShowGuide} title="Help">
        <!-- Font Awesome "circle-info" icon (static/icons/circle-info-solid-full.svg) -->
        <svg class="license-icon" viewBox="0 0 640 640" fill="currentColor">
          <path d="M320 576C461.4 576 576 461.4 576 320C576 178.6 461.4 64 320 64C178.6 64 64 178.6 64 320C64 461.4 178.6 576 320 576zM288 224C288 206.3 302.3 192 320 192C337.7 192 352 206.3 352 224C352 241.7 337.7 256 320 256C302.3 256 288 241.7 288 224zM280 288L328 288C341.3 288 352 298.7 352 312L352 400L360 400C373.3 400 384 410.7 384 424C384 437.3 373.3 448 360 448L280 448C266.7 448 256 437.3 256 424C256 410.7 266.7 400 280 400L304 400L304 336L280 336C266.7 336 256 325.3 256 312C256 298.7 266.7 288 280 288z"/>
        </svg>
      </button>
    {/if}
  </div>
</footer>

<style>
  .statusbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: var(--statusbar-height);
    padding: 0 0.75rem;
    background: var(--bg-container);
    border-top: 1px solid var(--border-subtle);
    flex-shrink: 0;
    font-size: 0.75rem;
    color: var(--text-secondary);
    user-select: none;
    -webkit-user-select: none;
  }

  .statusbar-left {
    display: flex;
    align-items: center;
    gap: 0.4rem;
  }

  .statusbar-right {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    min-width: 0;
  }

  .indicator {
    display: inline-flex;
    align-items: center;
    color: var(--text-tertiary);
    line-height: 0;
  }
  .indicator.connected {
    color: var(--text-connected);
  }
  .indicator.mcp.connected {
    color: var(--text-connected);
  }
  .indicator.mcp.active {
    animation: mcp-pulse 0.9s ease-in-out;
  }
  /* Resting state is the warm pilot-lamp amber, like the sidecar LED.
     Activity blinks briefly to active-purple with a glow — amber = lamp
     on, purple beat = agent querying right now. Tightened so amber
     dominates and the purple reads like a hardware MIDI-activity LED. */
  @keyframes mcp-pulse {
    0%, 100% { color: var(--text-connected); filter: brightness(1); }
    20%, 80% { color: var(--text-connected); filter: brightness(1); }
    50% { color: var(--text-active); filter: var(--glow-active) brightness(1.3); }
  }
  .indicator-icon {
    width: 12px;
    height: 12px;
  }

  .status-note {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    color: var(--text-secondary);
    font-variant-numeric: tabular-nums;
    min-width: 0;
  }
  .status-note.status-error {
    color: var(--text-danger);
  }
  .status-note-msg {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 40ch;
  }
  .note-action {
    background: none;
    border: none;
    color: var(--text-active);
    font-family: var(--font-body);
    font-size: inherit;
    padding: 0;
    cursor: pointer;
    white-space: nowrap;
    transition: filter var(--transition-fast);
  }
  .note-action::before {
    content: '[';
    color: var(--text-secondary);
    margin-right: 0.15rem;
  }
  .note-action::after {
    content: ']';
    color: var(--text-secondary);
    margin-left: 0.15rem;
  }
  .note-action:hover:not(:disabled) {
    filter: brightness(1.25);
  }
  .note-action:hover:not(:disabled)::before,
  .note-action:hover:not(:disabled)::after {
    color: var(--text-accent);
  }
  .note-action:disabled {
    cursor: default;
    color: var(--text-tertiary);
  }
  .note-dismiss {
    background: none;
    border: none;
    color: var(--text-tertiary);
    cursor: pointer;
    padding: 0 0.15rem;
    font-size: 0.85rem;
    line-height: 1;
  }
  .note-dismiss:hover {
    color: var(--text-secondary);
  }

  .sync-btn {
    background: none;
    border: none;
    color: var(--text-secondary);
    padding: 0;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    transition: color var(--transition-fast);
    line-height: 0;
  }
  .sync-btn + .sync-btn {
    margin-left: 0.2rem;
  }
  .sync-btn:hover:not(:disabled) {
    color: var(--text-accent);
  }
  .sync-btn:disabled {
    cursor: default;
    color: var(--text-tertiary);
  }
  .sync-btn.spinning,
  .sync-btn.spinning:disabled {
    color: var(--text-accent);
  }
  .sync-icon {
    width: 12px;
    height: 12px;
  }
  .sync-btn.spinning .sync-icon {
    animation: spin 1s linear infinite;
    filter: var(--glow-accent);
  }
  @keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }

  .separator {
    opacity: 0.5;
  }

  .license-link {
    background: none;
    border: none;
    color: var(--text-secondary);
    font-size: inherit;
    font-family: inherit;
    padding: 0;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
    transition: color var(--transition-fast);
  }
  .license-icon {
    width: 12px;
    height: 12px;
  }
  .license-link:hover {
    color: var(--text-accent);
  }

</style>
