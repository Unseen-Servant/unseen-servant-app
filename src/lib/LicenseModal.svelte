<script lang="ts">
  import { onMount } from 'svelte';
  import { getVersion } from '@tauri-apps/api/app';
  import { openUrl } from '@tauri-apps/plugin-opener';

  export let visible = false;
  export let onClose: () => void;

  let appVersion = '';

  onMount(async () => {
    try {
      appVersion = await getVersion();
    } catch {
      appVersion = '';
    }
  });

  function handleBackdrop(e: MouseEvent) {
    if (e.target === e.currentTarget) onClose();
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Escape') onClose();
  }

  function handleLicenseLink() {
    openUrl('https://unseenservant.games/license');
  }
</script>

{#if visible}
  <!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
  <div class="backdrop" role="dialog" aria-modal="true" aria-label="License" tabindex="-1" on:click={handleBackdrop} on:keydown={handleKeydown}>
    <div class="modal">
      <div class="modal-header">
        <span class="modal-title font-heading">About</span>
        <button class="close-btn" on:click={onClose} aria-label="Close">&times;</button>
      </div>
      <div class="modal-body">
        {#if appVersion}
          <span class="version">Legend Lore v{appVersion}</span>
        {/if}
        <p class="license-notice">
          This software is licensed under the
          <button class="license-url" on:click={handleLicenseLink}>
            Unseen Servant Games Software License</button>.
        </p>
      </div>
    </div>
  </div>
{/if}

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.6);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 100;
  }

  .modal {
    background: var(--bg-container);
    border: 1px solid var(--border-subtle);
    border-radius: 8px;
    width: min(360px, 90vw);
    display: flex;
    flex-direction: column;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
  }

  .modal-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.75rem 1rem;
    border-bottom: 1px solid var(--border-subtle);
    flex-shrink: 0;
  }

  .modal-title {
    font-size: 1.1rem;
    color: var(--text-accent);
  }

  .close-btn {
    background: none;
    border: none;
    color: var(--text-secondary);
    font-size: 1.4rem;
    line-height: 1;
    padding: 0.1rem 0.4rem;
    border-radius: 4px;
    cursor: pointer;
    transition: color var(--transition-fast);
  }
  .close-btn:hover {
    color: var(--text-primary);
  }

  .modal-body {
    padding: 1rem;
  }

  .version {
    font-family: var(--font-heading);
    font-size: 0.95rem;
    color: var(--text-accent);
  }

  .license-notice {
    margin: 0.5rem 0 0;
    font-family: var(--font-body);
    font-size: 0.85rem;
    line-height: 1.5;
    color: var(--text-primary);
  }

  .license-url {
    background: none;
    border: none;
    color: var(--text-secondary);
    font-family: inherit;
    font-size: inherit;
    padding: 0;
    cursor: pointer;
    text-decoration: underline;
    text-decoration-style: dotted;
    text-underline-offset: 2px;
    transition: color var(--transition-fast);
  }
  .license-url:hover {
    color: var(--text-accent);
  }
</style>
