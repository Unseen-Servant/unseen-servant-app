<script lang="ts">
  import { onMount } from 'svelte';
  import { invoke } from '@tauri-apps/api/core';
  import Modal from './Modal.svelte';

  export let path: string;
  export let onClose: () => void;

  type DocumentStats = {
    filename: string;
    source: string;
    chunks: number;
    game_system: string;
    pages: number;
    indexed_at: string | null;
    file_size_bytes: number | null;
  };

  let stats: DocumentStats | null = null;
  let error: string | null = null;

  onMount(async () => {
    try {
      stats = await invoke<DocumentStats>('get_document_stats', { path });
    } catch (e) {
      error = String(e);
    }
  });

  function formatBytes(bytes: number | null): string {
    if (bytes == null) return '—';
    if (bytes < 1024) return `${bytes} B`;
    const kb = bytes / 1024;
    if (kb < 1024) return `${kb.toFixed(1)} KB`;
    const mb = kb / 1024;
    if (mb < 1024) return `${mb.toFixed(1)} MB`;
    return `${(mb / 1024).toFixed(2)} GB`;
  }

  function formatRelative(iso: string | null): string {
    if (!iso) return 'Unknown';
    const date = new Date(iso);
    const seconds = Math.floor((Date.now() - date.getTime()) / 1000);
    if (seconds < 30) return 'just now';
    if (seconds < 60) return `${seconds}s ago`;
    const minutes = Math.floor(seconds / 60);
    if (minutes === 1) return '1 minute ago';
    if (minutes < 60) return `${minutes} minutes ago`;
    const hours = Math.floor(minutes / 60);
    if (hours === 1) return '1 hour ago';
    if (hours < 24) return `${hours} hours ago`;
    const days = Math.floor(hours / 24);
    if (days === 1) return '1 day ago';
    return `${days} days ago`;
  }

  $: indexedAbsolute = stats?.indexed_at ? new Date(stats.indexed_at).toLocaleString() : '';
</script>

<Modal visible={true} {onClose} title="Info" width="min(560px, 90vw)">
  <div class="body">
    {#if error}
      <p class="error">Could not load stats: {error}</p>
    {:else if !stats}
      <p class="loading">Loading…</p>
    {:else}
      <div class="filename" title={stats.source}>{stats.filename}</div>

      <div class="stat-block" role="group" aria-label="Document stats">
        <div class="stat-cell">
          <div class="stat-label">CHUNKS</div>
          <div class="stat-value">{stats.chunks.toLocaleString()}</div>
        </div>
        <div class="stat-cell">
          <div class="stat-label">PAGES</div>
          <div class="stat-value">{stats.pages > 0 ? stats.pages.toLocaleString() : '—'}</div>
        </div>
        <div class="stat-cell">
          <div class="stat-label">SIZE</div>
          <div class="stat-value">{formatBytes(stats.file_size_bytes)}</div>
        </div>
        <div class="stat-cell">
          <div class="stat-label">INDEXED</div>
          <div class="stat-value" title={indexedAbsolute}>{formatRelative(stats.indexed_at)}</div>
        </div>
        <div class="stat-cell">
          <div class="stat-label">SYSTEM</div>
          <div class="stat-value">{stats.game_system || 'unknown'}</div>
        </div>
      </div>
    {/if}
  </div>
</Modal>

<style>
  .body {
    padding: 1rem 1.25rem 1.25rem;
  }
  .filename {
    font-family: var(--font-body);
    font-size: 0.95rem;
    color: var(--text-primary);
    margin-bottom: 0.75rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .loading,
  .error {
    color: var(--text-secondary);
    font-size: 0.85rem;
    padding: 0.5rem 0;
  }
  .error {
    color: var(--text-danger);
  }
  .stat-block {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 0.5rem;
    padding: 0.75rem 0.25rem;
    border-top: 1px solid var(--border-subtle);
    border-bottom: 1px solid var(--border-subtle);
  }
  .stat-cell {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.15rem;
  }
  .stat-label {
    font-family: var(--font-heading, var(--font-body));
    font-size: 0.7rem;
    letter-spacing: 0.08em;
    color: var(--text-secondary);
    text-transform: uppercase;
  }
  .stat-value {
    font-family: var(--font-mono, ui-monospace, monospace);
    font-size: 0.75rem;
    color: var(--text-primary);
    font-variant-numeric: tabular-nums;
    text-align: center;
  }
</style>
