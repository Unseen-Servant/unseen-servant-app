<script lang="ts">
  import Modal from './Modal.svelte';
  import GettingStartedSteps from './GettingStartedSteps.svelte';

  export let visible: boolean;
  export let onClose: () => void;
  export let ollamaRunning: boolean = false;
  export let ollamaModelReady: boolean = false;
  export let folderSelected: boolean = false;
  export let filesIndexed: boolean = false;
  export let collectionsCreated: boolean = false;
  export let onSelectFolder: () => void;
  export let onCopyMcpConfig: () => void;
</script>

<Modal {visible} {onClose} title="Getting Started" width="min(520px, 90vw)" maxHeight="80vh">
  <div class="modal-body">
    <GettingStartedSteps
      {ollamaRunning}
      {ollamaModelReady}
      {folderSelected}
      {filesIndexed}
      {collectionsCreated}
      {onSelectFolder}
      {onCopyMcpConfig}
    />
    <p class="reaccess-hint">
      You can reopen this guide anytime from the
      <svg class="hint-icon" viewBox="0 0 640 640" fill="currentColor"><path d="M320 576C461.4 576 576 461.4 576 320C576 178.6 461.4 64 320 64C178.6 64 64 178.6 64 320C64 461.4 178.6 576 320 576zM288 224C288 206.3 302.3 192 320 192C337.7 192 352 206.3 352 224C352 241.7 337.7 256 320 256C302.3 256 288 241.7 288 224zM280 288L328 288C341.3 288 352 298.7 352 312L352 400L360 400C373.3 400 384 410.7 384 424C384 437.3 373.3 448 360 448L280 448C266.7 448 256 437.3 256 424C256 410.7 266.7 400 280 400L304 400L304 336L280 336C266.7 336 256 325.3 256 312C256 298.7 266.7 288 280 288z"/></svg>
      button in the status bar.
    </p>
  </div>
</Modal>

<style>
  .modal-body {
    overflow-y: auto;
    padding: 1rem;
  }

  .reaccess-hint {
    margin: 1rem 0 0;
    font-size: 0.75rem;
    color: var(--text-tertiary);
    text-align: center;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.25rem;
  }

  .hint-icon {
    width: 12px;
    height: 12px;
    vertical-align: middle;
    opacity: 0.7;
  }
</style>
