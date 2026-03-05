<script lang="ts">
  import { fly } from 'svelte/transition';
  import { notification } from './notificationStore';

  $: n = $notification;
</script>

{#if n}
  <div
    class="notification-banner {n.type}"
    transition:fly={{ y: 20, duration: 200 }}
  >
    {#if n.type === 'progress'}
      <span class="notification-spinner">&#9881;</span>
      <span class="notification-message">
        Syncing: {n.filesCompleted ?? 0}/{n.filesTotal ?? 0} files
      </span>
      {#if (n.chunksProcessed ?? 0) > 0}
        <span class="notification-detail">
          &middot; {(n.chunksProcessed ?? 0).toLocaleString()} chunks
        </span>
      {/if}
    {:else}
      <span class="notification-message">{n.message}</span>
      {#if n.actionLabel && n.onAction}
        <button class="notification-action" on:click={n.onAction}>
          {n.actionLabel}
        </button>
      {/if}
      <button class="notification-dismiss" on:click={() => { n.onDismiss?.(); notification.dismiss(); }}>
        &times;
      </button>
    {/if}
  </div>
{/if}

<style>
  .notification-banner {
    position: fixed;
    bottom: calc(var(--statusbar-height) + 0.5rem);
    right: 0.75rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 0.75rem;
    border-radius: 6px;
    font-size: 0.85rem;
    font-family: var(--font-body);
    background: var(--bg-container);
    border: 1px solid var(--border-subtle);
    box-shadow: var(--shadow-dropdown);
    z-index: 200;
    max-width: 90%;
    pointer-events: auto;
  }

  .notification-banner.success {
    border-left: 3px solid var(--text-active);
  }
  .notification-banner.info {
    border-left: 3px solid var(--text-accent);
  }
  .notification-banner.error {
    border-left: 3px solid var(--text-danger);
  }
  .notification-banner.action {
    border-left: 3px solid var(--text-accent);
  }
  .notification-banner.progress {
    border-left: 3px solid var(--text-accent);
  }

  .notification-message {
    color: var(--text-primary);
  }

  .notification-action {
    padding: 0.2rem 0.6rem;
    border-radius: 4px;
    border: none;
    font-size: 0.8rem;
    font-family: var(--font-body);
    background: var(--bg-active);
    color: var(--text-primary);
    cursor: pointer;
    white-space: nowrap;
    transition: background var(--transition-fast);
  }
  .notification-action:hover {
    background: var(--bg-active-focused);
  }
  .notification-action:active {
    transform: scale(0.97);
  }

  .notification-dismiss {
    background: none;
    border: none;
    color: var(--text-tertiary);
    cursor: pointer;
    font-size: 1rem;
    padding: 0 0.25rem;
    line-height: 1;
  }
  .notification-dismiss:hover {
    color: var(--text-secondary);
  }

  .notification-detail {
    color: var(--text-secondary);
    font-size: 0.8rem;
    white-space: nowrap;
  }

  .notification-spinner {
    display: inline-block;
    animation: spin 2s linear infinite;
  }

  @keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }
</style>
