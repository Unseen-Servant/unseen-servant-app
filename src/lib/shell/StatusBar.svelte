<script lang="ts">
  import { jobNotification, pendingNotification } from './notificationStore';
  import { chordHint } from './keybindings';
  import { FOLDER, FOLDER_OPEN } from '../ui/iconPaths';

  export let selectedFolder: string;
  export let sidecarConnected: boolean;
  // Embedding runtime (process answers) vs. ready (it also has the model):
  // the remedies differ — launch the runtime vs. pull the model — so the
  // lamp shows the half-way state dim rather than folding it into "off".
  export let embedderRunning: boolean = false;
  export let embedderReady: boolean = false;
  export let mcpConnected: boolean = false;
  export let mcpActive: boolean = false;
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
  export let onOpenSettings: () => void;
  export let onShowHelp: () => void;

  $: jobNote = $jobNotification;
  $: pendingNote = $pendingNotification;

  // Long titles lose their middle, not their end, so "…Handbook (2024)"
  // stays tellable from "…Handbook (2014)". The tail never shrinks.
  const BOOK_TAIL = 8;
  function splitBook(name: string): [string, string] {
    return name.length > BOOK_TAIL * 2
      ? [name.slice(0, -BOOK_TAIL), name.slice(-BOOK_TAIL)]
      : [name, ''];
  }

  $: [bookHead, bookTail] = splitBook(jobNote?.book ?? '');
  $: jobTitle = jobNote
    ? jobNote.detail ?? (jobNote.book ? `${jobNote.message} · ${jobNote.book}` : jobNote.message)
    : '';

  function handlePendingDismiss() {
    pendingNote?.onDismiss?.();
    pendingNotification.dismiss();
  }

  // lastSyncTime is stamped by every index-status check, not only by
  // syncs, and this button runs a check — so name it for what it is.
  $: syncTooltip = (lastSyncTime
    ? `Check for changes — last checked ${lastSyncTime.toLocaleTimeString()}`
    : 'Check for changes') + chordHint('sync.run');

  $: sidecarTooltip = sidecarConnected ? 'Sidecar connected' : 'Sidecar disconnected';
  $: mcpTooltip = mcpActive ? 'MCP active — agent querying' : mcpConnected ? 'MCP connected' : 'MCP not detected';

  $: embedderTooltip = embedderReady
    ? 'Embedder ready'
    : embedderRunning
      ? 'Embedder running — model missing'
      : 'Embedder not running';

  function formatSize(bytes: number): string {
    if (bytes >= 1_073_741_824) return (bytes / 1_073_741_824).toFixed(1) + ' GB';
    if (bytes >= 1_048_576) return (bytes / 1_048_576).toFixed(1) + ' MB';
    if (bytes >= 1_024) return (bytes / 1_024).toFixed(0) + ' KB';
    return bytes + ' B';
  }
</script>

<footer class="statusbar">
  <div class="statusbar-left">
    <!-- Lamps stay lit with no folder chosen: whether the machinery is up
         is worth knowing before there's a library to point it at. -->
    <span class="indicator" class:connected={sidecarConnected} role="img" aria-label={sidecarTooltip} title={sidecarTooltip}>
      <!-- Font Awesome "server" icon (src/lib/ui/icons/server-solid-full.svg) -->
      <svg class="indicator-icon" viewBox="0 0 640 640" fill="currentColor" aria-hidden="true">
        <path d="M160 96C124.7 96 96 124.7 96 160L96 224C96 259.3 124.7 288 160 288L480 288C515.3 288 544 259.3 544 224L544 160C544 124.7 515.3 96 480 96L160 96zM376 168C389.3 168 400 178.7 400 192C400 205.3 389.3 216 376 216C362.7 216 352 205.3 352 192C352 178.7 362.7 168 376 168zM432 192C432 178.7 442.7 168 456 168C469.3 168 480 178.7 480 192C480 205.3 469.3 216 456 216C442.7 216 432 205.3 432 192zM160 352C124.7 352 96 380.7 96 416L96 480C96 515.3 124.7 544 160 544L480 544C515.3 544 544 515.3 544 480L544 416C544 380.7 515.3 352 480 352L160 352zM376 424C389.3 424 400 434.7 400 448C400 461.3 389.3 472 376 472C362.7 472 352 461.3 352 448C352 434.7 362.7 424 376 424zM432 448C432 434.7 442.7 424 456 424C469.3 424 480 434.7 480 448C480 461.3 469.3 472 456 472C442.7 472 432 461.3 432 448z"/>
      </svg>
    </span>
    <span
      class="indicator"
      class:connected={embedderReady}
      class:partial={embedderRunning && !embedderReady}
      role="img"
      aria-label={embedderTooltip}
      title={embedderTooltip}
    >
      <!-- Font Awesome "microchip" icon (src/lib/ui/icons/microchip-solid-full.svg) -->
      <svg class="indicator-icon" viewBox="0 0 640 640" fill="currentColor" aria-hidden="true">
        <path d="M240 88C240 74.7 229.3 64 216 64C202.7 64 192 74.7 192 88L192 128C156.7 128 128 156.7 128 192L88 192C74.7 192 64 202.7 64 216C64 229.3 74.7 240 88 240L128 240L128 296L88 296C74.7 296 64 306.7 64 320C64 333.3 74.7 344 88 344L128 344L128 400L88 400C74.7 400 64 410.7 64 424C64 437.3 74.7 448 88 448L128 448C128 483.3 156.7 512 192 512L192 552C192 565.3 202.7 576 216 576C229.3 576 240 565.3 240 552L240 512L296 512L296 552C296 565.3 306.7 576 320 576C333.3 576 344 565.3 344 552L344 512L400 512L400 552C400 565.3 410.7 576 424 576C437.3 576 448 565.3 448 552L448 512C483.3 512 512 483.3 512 448L552 448C565.3 448 576 437.3 576 424C576 410.7 565.3 400 552 400L512 400L512 344L552 344C565.3 344 576 333.3 576 320C576 306.7 565.3 296 552 296L512 296L512 240L552 240C565.3 240 576 229.3 576 216C576 202.7 565.3 192 552 192L512 192C512 156.7 483.3 128 448 128L448 88C448 74.7 437.3 64 424 64C410.7 64 400 74.7 400 88L400 128L344 128L344 88C344 74.7 333.3 64 320 64C306.7 64 296 74.7 296 88L296 128L240 128L240 88zM224 192L416 192C433.7 192 448 206.3 448 224L448 416C448 433.7 433.7 448 416 448L224 448C206.3 448 192 433.7 192 416L192 224C192 206.3 206.3 192 224 192zM240 240L240 400L400 400L400 240L240 240z"/>
      </svg>
    </span>
    <span
      class="indicator mcp"
      class:connected={mcpConnected}
      class:active={mcpActive}
      role="img"
      aria-label={mcpTooltip}
      title={mcpTooltip}
    >
      <!-- MCP logo (src/lib/ui/icons/mcp.svg). The viewBox is padded out from the
           mark's native 0 0 180 180 so its ink renders 8.4px tall — the same
           optical size as the Font Awesome server icon beside it, which
           carries built-in padding the bare logo doesn't. stroke-width scales
           with the box, so it's bumped 12 -> 17 to keep the same 0.8px stroke. -->
      <svg class="indicator-icon" viewBox="-37 -37 254 254" fill="none" stroke="currentColor" stroke-width="17" stroke-linecap="round" aria-hidden="true">
        <path d="M18 84.8528L85.8822 16.9706C95.2548 7.59798 110.451 7.59798 119.823 16.9706V16.9706C129.196 26.3431 129.196 41.5391 119.823 50.9117L68.5581 102.177"/>
        <path d="M69.2652 101.47L119.823 50.9117C129.196 41.5391 144.392 41.5391 153.765 50.9117L154.118 51.2652C163.491 60.6378 163.491 75.8338 154.118 85.2063L92.7248 146.6C89.6006 149.724 89.6006 154.789 92.7248 157.913L105.331 170.52"/>
        <path d="M102.853 33.9411L52.6482 84.1457C43.2756 93.5183 43.2756 108.714 52.6482 118.087V118.087C62.0208 127.459 77.2167 127.459 86.5893 118.087L136.794 67.8822"/>
      </svg>
    </span>
    {#if selectedFolder}
      {#if scopeBypassed}
        <span class="rule" aria-hidden="true"></span>
        <span
          class="bypass-lamp readout-label"
          title="Scope bypassed — every indexed file is in scope. B restores it."
        >BYPASS</span>
      {/if}
      <span class="rule" aria-hidden="true"></span>
      {#if indexedCount > 0}
        <!-- Rules divide groups; readouts within a group sit apart on
             spacing alone, so the two levels never look alike. -->
        <span class="stats">
          <span title="{indexedCount} book{indexedCount === 1 ? '' : 's'} indexed, {totalChunks.toLocaleString()} searchable chunks">{indexedCount} book{indexedCount === 1 ? '' : 's'}</span>
          {#if gameSystemCount > 0}
            <span title={topGameSystem}>{gameSystemCount} system{gameSystemCount === 1 ? '' : 's'}</span>
          {/if}
          {#if storageBytes > 0}
            <span>{formatSize(storageBytes)}</span>
          {/if}
        </span>
      {:else}
        <span>{selectedCount} book{selectedCount === 1 ? '' : 's'} selected</span>
      {/if}
      <span class="rule" aria-hidden="true"></span>
      <button class="icon-btn" on:click={onOpenFolder} aria-label="Reveal library folder" title={`Reveal library folder${chordHint('library.reveal')}`}>
        <svg class="btn-icon" viewBox="0 0 640 640" fill="currentColor" aria-hidden="true">
          <path class="folder-shut" d={FOLDER}/>
          <path class="folder-opened" d={FOLDER_OPEN}/>
        </svg>
      </button>
      {#if onSync}
        <button class="icon-btn" class:spinning={isSyncing} on:click={onSync} aria-label={isSyncing ? 'Syncing' : 'Check for changes'} title={syncTooltip} disabled={isSyncing}>
          <!-- Font Awesome "arrows-rotate" icon (src/lib/ui/icons/arrows-rotate-solid-full.svg) -->
          <svg class="btn-icon" viewBox="0 0 640 640" fill="currentColor" aria-hidden="true">
            <path d="M129.9 292.5C143.2 199.5 223.3 128 320 128C373 128 421 149.5 455.8 184.2C456 184.4 456.2 184.6 456.4 184.8L464 192L416.1 192C398.4 192 384.1 206.3 384.1 224C384.1 241.7 398.4 256 416.1 256L544.1 256C561.8 256 576.1 241.7 576.1 224L576.1 96C576.1 78.3 561.8 64 544.1 64C526.4 64 512.1 78.3 512.1 96L512.1 149.4L500.8 138.7C454.5 92.6 390.5 64 320 64C191 64 84.3 159.4 66.6 283.5C64.1 301 76.2 317.2 93.7 319.7C111.2 322.2 127.4 310 129.9 292.6zM573.4 356.5C575.9 339 563.7 322.8 546.3 320.3C528.9 317.8 512.6 330 510.1 347.4C496.8 440.4 416.7 511.9 320 511.9C267 511.9 219 490.4 184.2 455.7C184 455.5 183.8 455.3 183.6 455.1L176 447.9L223.9 447.9C241.6 447.9 255.9 433.6 255.9 415.9C255.9 398.2 241.6 383.9 223.9 383.9L96 384C87.5 384 79.3 387.4 73.3 393.5C67.3 399.6 63.9 407.7 64 416.3L65 543.3C65.1 561 79.6 575.2 97.3 575C115 574.8 129.2 560.4 129 542.7L128.6 491.2L139.3 501.3C185.6 547.4 249.5 576 320 576C449 576 555.7 480.6 573.4 356.5z"/>
          </svg>
        </button>
      {/if}
    {/if}
    {#if jobNote}
      <span class="rule" aria-hidden="true"></span>
      <div class="status-note" class:status-error={jobNote.type === 'error'} title={jobTitle}>
        <span class="status-note-msg" class:keep={jobNote.book}>{jobNote.message}</span>
        {#if jobNote.book}
          <span class="note-sep" aria-hidden="true">&middot;</span>
          <span class="note-book"><span class="note-book-head">{bookHead}</span><span class="note-book-tail">{bookTail}</span></span>
        {/if}
        {#if jobNote.dismissible}
          <button class="note-dismiss" on:click={() => jobNotification.dismiss()} aria-label="Dismiss">&times;</button>
        {/if}
      </div>
    {/if}
    {#if pendingNote}
      <span class="rule" aria-hidden="true"></span>
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
    <button class="icon-btn" on:click={onShowHelp} aria-label="Keyboard shortcuts" title={`Keyboard shortcuts${chordHint('help.overlay')}`}>
      <!-- Font Awesome "keyboard" icon (src/lib/ui/icons/keyboard-solid-full.svg) -->
      <svg class="btn-icon" viewBox="0 0 640 640" fill="currentColor" aria-hidden="true">
        <path d="M96 128C60.7 128 32 156.7 32 192L32 448C32 483.3 60.7 512 96 512L544 512C579.3 512 608 483.3 608 448L608 192C608 156.7 579.3 128 544 128L96 128zM112 192L144 192C152.8 192 160 199.2 160 208L160 240C160 248.8 152.8 256 144 256L112 256C103.2 256 96 248.8 96 240L96 208C96 199.2 103.2 192 112 192zM96 304C96 295.2 103.2 288 112 288L144 288C152.8 288 160 295.2 160 304L160 336C160 344.8 152.8 352 144 352L112 352C103.2 352 96 344.8 96 336L96 304zM208 192L240 192C248.8 192 256 199.2 256 208L256 240C256 248.8 248.8 256 240 256L208 256C199.2 256 192 248.8 192 240L192 208C192 199.2 199.2 192 208 192zM192 304C192 295.2 199.2 288 208 288L240 288C248.8 288 256 295.2 256 304L256 336C256 344.8 248.8 352 240 352L208 352C199.2 352 192 344.8 192 336L192 304zM208 384L432 384C440.8 384 448 391.2 448 400L448 432C448 440.8 440.8 448 432 448L208 448C199.2 448 192 440.8 192 432L192 400C192 391.2 199.2 384 208 384zM288 208C288 199.2 295.2 192 304 192L336 192C344.8 192 352 199.2 352 208L352 240C352 248.8 344.8 256 336 256L304 256C295.2 256 288 248.8 288 240L288 208zM304 288L336 288C344.8 288 352 295.2 352 304L352 336C352 344.8 344.8 352 336 352L304 352C295.2 352 288 344.8 288 336L288 304C288 295.2 295.2 288 304 288zM384 208C384 199.2 391.2 192 400 192L432 192C440.8 192 448 199.2 448 208L448 240C448 248.8 440.8 256 432 256L400 256C391.2 256 384 248.8 384 240L384 208zM400 288L432 288C440.8 288 448 295.2 448 304L448 336C448 344.8 440.8 352 432 352L400 352C391.2 352 384 344.8 384 336L384 304C384 295.2 391.2 288 400 288zM480 208C480 199.2 487.2 192 496 192L528 192C536.8 192 544 199.2 544 208L544 240C544 248.8 536.8 256 528 256L496 256C487.2 256 480 248.8 480 240L480 208zM496 288L528 288C536.8 288 544 295.2 544 304L544 336C544 344.8 536.8 352 528 352L496 352C487.2 352 480 344.8 480 336L480 304C480 295.2 487.2 288 496 288z"/>
      </svg>
    </button>
    <button class="icon-btn" on:click={onOpenSettings} aria-label="Settings" title={`Settings${chordHint('settings.open')}`}>
      <!-- Font Awesome "sliders" icon (src/lib/ui/icons/sliders-solid-full.svg) -->
      <svg class="btn-icon" viewBox="0 0 640 640" fill="currentColor" aria-hidden="true">
        <path d="M96 128C78.3 128 64 142.3 64 160C64 177.7 78.3 192 96 192L182.7 192C195 220.3 223.2 240 256 240C288.8 240 317 220.3 329.3 192L544 192C561.7 192 576 177.7 576 160C576 142.3 561.7 128 544 128L329.3 128C317 99.7 288.8 80 256 80C223.2 80 195 99.7 182.7 128L96 128zM96 288C78.3 288 64 302.3 64 320C64 337.7 78.3 352 96 352L342.7 352C355 380.3 383.2 400 416 400C448.8 400 477 380.3 489.3 352L544 352C561.7 352 576 337.7 576 320C576 302.3 561.7 288 544 288L489.3 288C477 259.7 448.8 240 416 240C383.2 240 355 259.7 342.7 288L96 288zM96 448C78.3 448 64 462.3 64 480C64 497.7 78.3 512 96 512L150.7 512C163 540.3 191.2 560 224 560C256.8 560 285 540.3 297.3 512L544 512C561.7 512 576 497.7 576 480C576 462.3 561.7 448 544 448L297.3 448C285 419.7 256.8 400 224 400C191.2 400 163 419.7 150.7 448L96 448z"/>
      </svg>
    </button>
  </div>
</footer>

<style>
  .statusbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: var(--statusbar-height);
    padding: 0 0.75rem;
    /* Same plate as the header — the two bars bracket the workspace as one
       piece of chrome. --bg-container is the generic raised surface (panels,
       modals, popovers), which is what this used to sit on. */
    background: var(--bg-header);
    border-top: 1px solid var(--border-subtle);
    flex-shrink: 0;
    font-size: 0.75rem;
    color: var(--text-secondary);
    /* Every number down here is a readout; fixed-width figures keep them
       from jittering while indexing ticks them over. */
    font-variant-numeric: tabular-nums;
    user-select: none;
    -webkit-user-select: none;
  }

  .statusbar-left {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    min-width: 0;
    white-space: nowrap;
  }
  /* Only the notes give way when the row runs long (they ellipsize);
     lamps, counts and buttons keep their width. No overflow: hidden
     here — it would clip the lamps' glows. */
  .statusbar-left > :not(.status-note) {
    flex-shrink: 0;
  }

  .statusbar-right {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    flex-shrink: 0;
    margin-left: 0.75rem;
  }

  .indicator {
    display: inline-flex;
    align-items: center;
    color: var(--text-tertiary);
    line-height: 0;
  }
  .indicator + .indicator {
    margin-left: 0.2rem;
  }
  .indicator.connected {
    color: var(--text-connected);
  }
  /* Lamp half-lit: the runtime answers but lacks the model. */
  .indicator.partial {
    color: color-mix(in srgb, var(--text-connected) 45%, transparent);
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
    min-width: 0;
  }
  .status-note.status-error {
    color: var(--text-danger);
  }
  .status-note-msg {
    min-width: 0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 40ch;
  }
  /* The verb and count ("Indexing 4 of 12") hold; the book name gives. */
  .status-note-msg.keep {
    flex-shrink: 0;
  }
  .note-sep {
    color: var(--text-tertiary);
  }
  /* Parchment: the book is content, not chrome. */
  .note-book {
    display: inline-flex;
    min-width: 0;
    max-width: 32ch;
    color: var(--text-accent);
  }
  /* pre, not nowrap: a space at the split must survive on either side. */
  .note-book-head {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: pre;
  }
  .note-book-tail {
    flex-shrink: 0;
    white-space: pre;
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

  .icon-btn {
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
  .statusbar-left .icon-btn + .icon-btn {
    margin-left: 0.2rem;
  }
  .icon-btn:hover:not(:disabled) {
    color: var(--text-primary);
  }
  .icon-btn:active:not(:disabled) {
    transform: scale(0.97);
  }
  .icon-btn:disabled {
    cursor: default;
    color: var(--text-tertiary);
  }
  .icon-btn.spinning,
  .icon-btn.spinning:disabled {
    color: var(--text-accent);
  }
  .btn-icon {
    width: 12px;
    height: 12px;
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

  /* Group divider — the scope bar's master rule, same size and tone. A
     box has no font metrics, so it centres on the icon row unaided. */
  .rule {
    width: 1px;
    height: 12px;
    margin: 0 0.15rem;
    background: var(--bg-category);
  }

  .stats {
    display: inline-flex;
    align-items: center;
    gap: 0.6rem;
  }

</style>
