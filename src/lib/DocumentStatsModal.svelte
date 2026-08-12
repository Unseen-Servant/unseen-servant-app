<script lang="ts">
  import { onMount } from 'svelte';
  import { invoke } from '@tauri-apps/api/core';
  import Modal from './Modal.svelte';
  import { displaySystem } from './searchScope';

  export let path: string;
  export let onClose: () => void;

  type DocumentStats = {
    filename: string;
    source: string;
    chunks: number;
    game_system: string;
    game_systems?: string[];
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

<Modal visible={true} {onClose} title={stats?.filename ?? 'Document info'} size="md">
  <div class="body">
    {#if error}
      <p class="error">Could not load stats: {error}</p>
    {:else if !stats}
      <p class="loading">Loading…</p>
    {:else}
      <!-- The title carries the filename; this carries what it can't — the
           path the file sits at. -->
      <div class="source" title={stats.source}>{stats.source}</div>

      <div class="stat-block" role="group" aria-label="Document stats">
        <div class="stat-cell">
          <div class="readout-label">CHUNKS</div>
          <div class="stat-value">{stats.chunks.toLocaleString()}</div>
        </div>
        <div class="stat-cell">
          <div class="readout-label">PAGES</div>
          <div class="stat-value">{stats.pages > 0 ? stats.pages.toLocaleString() : '—'}</div>
        </div>
        <div class="stat-cell">
          <div class="readout-label">SIZE</div>
          <div class="stat-value">{formatBytes(stats.file_size_bytes)}</div>
        </div>
        <div class="stat-cell">
          <div class="readout-label">INDEXED</div>
          <div class="stat-value" title={indexedAbsolute}>{formatRelative(stats.indexed_at)}</div>
        </div>
      </div>

      <!-- Out of the numeric grid: a multi-system file joins its tags into
           a string with no length limit, which a fifth of 560px could not
           hold without wrapping raggedly against the tabular readouts. -->
      <div class="system-row">
        <span class="readout-label">SYSTEM</span>
        <span class="system-value">{(stats.game_systems && stats.game_systems.length > 0) ? stats.game_systems.join(', ') : displaySystem(stats.game_system || 'unknown')}</span>
      </div>
    {/if}
  </div>
</Modal>

<style>
  .body {
    padding: var(--modal-pad);
  }
  .source {
    font-family: var(--font-mono);
    font-size: 0.7rem;
    color: var(--text-tertiary);
    margin-bottom: 0.75rem;
    /* Plain tail truncation is right here, not the direction:rtl trick for
       keeping the end visible: the end of the path is the filename, which
       the title already carries, so what gets cut is the redundant part.
       (That trick also moves a leading "/" to the visual end, since a
       neutral character at the edge takes the paragraph direction.) */
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
    grid-template-columns: repeat(4, 1fr);
    gap: 0.5rem;
    padding: 0.75rem 0.25rem;
    border-top: 1px solid var(--border-subtle);
  }
  /* Shares the block's rules to read as one bordered region with an
     internal divider, rather than two stacked panels. */
  .system-row {
    display: flex;
    align-items: baseline;
    gap: 0.6rem;
    padding: 0.5rem 0.25rem;
    border-top: 1px solid var(--border-subtle);
    border-bottom: 1px solid var(--border-subtle);
  }
  .system-value {
    font-family: var(--font-mono);
    font-size: 0.75rem;
    color: var(--text-primary);
    min-width: 0;
    overflow-wrap: anywhere;
  }
  .stat-cell {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.15rem;
  }
  .stat-value {
    font-family: var(--font-mono);
    font-size: 0.75rem;
    color: var(--text-primary);
    font-variant-numeric: tabular-nums;
    text-align: center;
  }
</style>
