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

<!-- The filename leaves the title: as a rail nameplate it would truncate at
     ~48 characters, and as the first readout row it gets the full 560px in the
     same mono column as everything else about the file. -->
<Modal visible={true} {onClose} title="Document" size="md" escapeWord="close">
  <svelte:fragment slot="rail">
    <span class="rail-rule" aria-hidden="true"></span>
    <span class="lamp" class:live={!!stats?.indexed_at} aria-hidden="true"></span>
    <span class="rail-note">{stats?.indexed_at ? 'indexed' : 'not indexed'}</span>
  </svelte:fragment>

  <div class="modal-bays">
    {#if error}
      <p class="error">Could not load stats: {error}</p>
    {:else if !stats}
      <p class="loading">Loading…</p>
    {:else}
      <div class="modal-bay">
        <div class="modal-well">
          <div class="modal-well-row">
            <span class="ledger-label">File</span>
            <span class="modal-readout" title={stats.filename}>{stats.filename}</span>
          </div>
          <div class="modal-well-row">
            <span class="ledger-label">Path</span>
            <span class="modal-readout" title={stats.source}>{stats.source}</span>
          </div>
          <!-- Wrapped, not ellipsised: a multi-system file joins its tags into
               a string with no length limit, and the tail is as much the answer
               as the head. -->
          <div class="modal-well-row">
            <span class="ledger-label">System</span>
            <span class="modal-readout wrap">{(stats.game_systems && stats.game_systems.length > 0) ? stats.game_systems.join(', ') : displaySystem(stats.game_system || 'unknown')}</span>
          </div>
        </div>
      </div>

      <div class="modal-bay">
        <span class="ledger-label">Index</span>
        <div class="modal-well">
          <div class="modal-well-row">
            <span class="ledger-label">Chunks</span>
            <span class="modal-readout">{stats.chunks.toLocaleString()}</span>
          </div>
          <div class="modal-well-row">
            <span class="ledger-label">Pages</span>
            <span class="modal-readout">{stats.pages > 0 ? stats.pages.toLocaleString() : '—'}</span>
          </div>
          <div class="modal-well-row">
            <span class="ledger-label">Size</span>
            <span class="modal-readout">{formatBytes(stats.file_size_bytes)}</span>
          </div>
          <div class="modal-well-row">
            <span class="ledger-label">Indexed</span>
            <span class="modal-readout">{formatRelative(stats.indexed_at)}<span class="stamp">{indexedAbsolute}</span></span>
          </div>
        </div>
      </div>
    {/if}
  </div>
</Modal>
<!-- There is no `slot="commit"`: nothing here is operable, and the missing
     rail is the signal. -->

<style>
  .loading,
  .error {
    color: var(--text-secondary);
    font-size: 0.85rem;
    padding: 0.5rem 0;
    margin: 0;
  }
  .error {
    color: var(--text-danger);
  }

  /* `.rail-rule` is global (Task 3) — three surfaces need it. */

  /* Amber is connectivity in this system, and "live in the index" is exactly
     that. Dark when the file has never been indexed. */
  .lamp {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--text-tertiary);
    opacity: 0.4;
    flex-shrink: 0;
  }
  .lamp.live {
    background: var(--text-connected);
    opacity: 1;
  }

  .rail-note {
    font-family: var(--font-body);
    font-size: 0.75rem;
    color: var(--text-tertiary);
  }

  /* The exact stamp used to exist only as a title attribute — invisible on an
     instrument panel and unreachable by touch or keyboard. The well has room. */
  .stamp {
    color: var(--text-tertiary);
    opacity: 0.8;
    margin-left: 0.5rem;
  }
</style>
