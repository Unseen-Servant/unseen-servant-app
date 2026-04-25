<script lang="ts">
  import { onMount } from 'svelte';
  import { getVersion } from '@tauri-apps/api/app';
  import { openUrl } from '@tauri-apps/plugin-opener';
  import Modal from './Modal.svelte';

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

  function handleLicenseLink() {
    openUrl('https://unseenservant.games/license');
  }
</script>

<Modal {visible} {onClose} title="About" width="min(360px, 90vw)">
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
</Modal>

<style>
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
