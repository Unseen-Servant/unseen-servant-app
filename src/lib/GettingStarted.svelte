<script lang="ts">
  export let mode: 'page' | 'modal' = 'page';
  export let onClose: (() => void) | null = null;

  // Step completion status
  export let ollamaRunning: boolean = false;
  export let ollamaModelReady: boolean = false;
  export let folderSelected: boolean = false;
  export let filesIndexed: boolean = false;
  export let collectionsCreated: boolean = false;

  // Action callbacks
  export let onSelectFolder: () => void;
  export let onCopyMcpConfig: () => void;

  function handleBackdrop(e: MouseEvent) {
    if (e.target === e.currentTarget && onClose) onClose();
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Escape' && onClose) onClose();
  }

  interface Step {
    title: string;
    description: string;
    done: boolean;
  }

  $: steps = [
    {
      title: 'Install Ollama',
      description: 'Local AI embeddings for semantic search.',
      done: ollamaRunning && ollamaModelReady,
    },
    {
      title: 'Connect Your AI Agent',
      description: 'Give your AI agent access to your indexed library via MCP.',
      done: false,
    },
    {
      title: 'Add Your PDFs',
      description: 'Point Legend Lore at a folder of TTRPG rulebooks, supplements, and adventures.',
      done: folderSelected,
    },
    {
      title: 'Index & Tag',
      description: 'Select PDFs in the file tree and sync to create searchable embeddings. Add game system tags to stay organized.',
      done: filesIndexed,
    },
    {
      title: 'Create Collections',
      description: 'Group indexed PDFs by campaign, game system, or topic for quick access.',
      done: collectionsCreated,
    },
  ] as Step[];
</script>

{#if mode === 'modal'}
  <!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
  <div class="backdrop" role="dialog" aria-modal="true" aria-label="Getting Started" tabindex="-1" on:click={handleBackdrop} on:keydown={handleKeydown}>
    <div class="modal">
      <div class="modal-header">
        <span class="modal-title font-display">Getting Started</span>
        <button class="close-btn" on:click={onClose} aria-label="Close">&times;</button>
      </div>
      <div class="modal-body">
        <div class="steps">
          {#each steps as step, i}
            <div class="step" class:done={step.done}>
              <span class="step-status" class:complete={step.done}>
                {#if step.done}
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                {:else}
                  <span class="step-number">{i + 1}</span>
                {/if}
              </span>
              <div class="step-content">
                <span class="step-title font-heading">{step.title}</span>
                <span class="step-desc">{step.description}</span>
                {#if i === 0}
                  <div class="step-detail">
                    {#if ollamaRunning && ollamaModelReady}
                      <span class="status-ok">Ready</span>
                    {:else if ollamaRunning}
                      <span class="status-partial">Ollama running — pull the embedding model:</span>
                      <code class="command">ollama pull nomic-embed-text</code>
                    {:else}
                      <span class="status-pending">Not detected — download from <strong>ollama.com</strong></span>
                    {/if}
                  </div>
                {/if}
                {#if i === 1}
                  <button class="action-btn" on:click={onCopyMcpConfig}>
                    <svg class="action-icon" viewBox="0 0 180 180" fill="none" stroke="currentColor" stroke-width="12" stroke-linecap="round">
                      <path d="M18 84.8528L85.8822 16.9706C95.2548 7.59798 110.451 7.59798 119.823 16.9706V16.9706C129.196 26.3431 129.196 41.5391 119.823 50.9117L68.5581 102.177"/>
                      <path d="M69.2652 101.47L119.823 50.9117C129.196 41.5391 144.392 41.5391 153.765 50.9117L154.118 51.2652C163.491 60.6378 163.491 75.8338 154.118 85.2063L92.7248 146.6C89.6006 149.724 89.6006 154.789 92.7248 157.913L105.331 170.52"/>
                      <path d="M102.853 33.9411L52.6482 84.1457C43.2756 93.5183 43.2756 108.714 52.6482 118.087V118.087C62.0208 127.459 77.2167 127.459 86.5893 118.087L136.794 67.8822"/>
                    </svg>
                    Copy MCP Config
                  </button>
                {/if}
                {#if i === 2 && !folderSelected}
                  <button class="action-btn" on:click={onSelectFolder}>Choose Library Folder</button>
                {/if}
              </div>
            </div>
          {/each}
        </div>
        <p class="reaccess-hint">
          You can reopen this guide anytime from the
          <svg class="hint-icon" viewBox="0 0 640 640" fill="currentColor"><path d="M320 576C461.4 576 576 461.4 576 320C576 178.6 461.4 64 320 64C178.6 64 64 178.6 64 320C64 461.4 178.6 576 320 576zM288 224C288 206.3 302.3 192 320 192C337.7 192 352 206.3 352 224C352 241.7 337.7 256 320 256C302.3 256 288 241.7 288 224zM280 288L328 288C341.3 288 352 298.7 352 312L352 400L360 400C373.3 400 384 410.7 384 424C384 437.3 373.3 448 360 448L280 448C266.7 448 256 437.3 256 424C256 410.7 266.7 400 280 400L304 400L304 336L280 336C266.7 336 256 325.3 256 312C256 298.7 266.7 288 280 288z"/></svg>
          button in the status bar.
        </p>
      </div>
    </div>
  </div>
{:else}
  <div class="getting-started-page">
    <h1 class="page-title font-display">Getting Started</h1>
    <p class="page-subtitle">Set up Legend Lore to browse, index, and search your TTRPG library.</p>
    <div class="steps">
      {#each steps as step, i}
        <div class="step" class:done={step.done}>
          <span class="step-status" class:complete={step.done}>
            {#if step.done}
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
            {:else}
              <span class="step-number">{i + 1}</span>
            {/if}
          </span>
          <div class="step-content">
            <span class="step-title font-heading">{step.title}</span>
            <span class="step-desc">{step.description}</span>
            {#if i === 0}
              <div class="step-detail">
                {#if ollamaRunning && ollamaModelReady}
                  <span class="status-ok">Ready</span>
                {:else if ollamaRunning}
                  <span class="status-partial">Ollama running — pull the embedding model:</span>
                  <code class="command">ollama pull nomic-embed-text</code>
                {:else}
                  <span class="status-pending">Not detected — download from <strong>ollama.com</strong></span>
                {/if}
              </div>
            {/if}
            {#if i === 1}
              <button class="action-btn" on:click={onCopyMcpConfig}>
                <svg class="action-icon" viewBox="0 0 180 180" fill="none" stroke="currentColor" stroke-width="12" stroke-linecap="round">
                  <path d="M18 84.8528L85.8822 16.9706C95.2548 7.59798 110.451 7.59798 119.823 16.9706V16.9706C129.196 26.3431 129.196 41.5391 119.823 50.9117L68.5581 102.177"/>
                  <path d="M69.2652 101.47L119.823 50.9117C129.196 41.5391 144.392 41.5391 153.765 50.9117L154.118 51.2652C163.491 60.6378 163.491 75.8338 154.118 85.2063L92.7248 146.6C89.6006 149.724 89.6006 154.789 92.7248 157.913L105.331 170.52"/>
                  <path d="M102.853 33.9411L52.6482 84.1457C43.2756 93.5183 43.2756 108.714 52.6482 118.087V118.087C62.0208 127.459 77.2167 127.459 86.5893 118.087L136.794 67.8822"/>
                </svg>
                Copy MCP Config
              </button>
            {/if}
            {#if i === 2}
              <button class="action-btn" on:click={onSelectFolder}>Choose Library Folder</button>
            {/if}
          </div>
        </div>
      {/each}
    </div>
  </div>
{/if}

<style>
  /* --- Page mode (empty state replacement) --- */
  .getting-started-page {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 2rem;
    gap: 0.25rem;
  }

  .page-title {
    font-size: 1.6rem;
    color: var(--text-accent);
    margin: 0;
    letter-spacing: 0.04em;
  }

  .page-subtitle {
    font-size: 0.95rem;
    color: var(--text-secondary);
    margin: 0 0 1rem;
  }

  /* --- Modal mode --- */
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
    width: min(520px, 90vw);
    max-height: 80vh;
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
    overflow-y: auto;
    padding: 1rem;
  }

  /* --- Shared step layout --- */
  .steps {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    width: 100%;
    max-width: 460px;
  }

  .step {
    display: flex;
    gap: 0.75rem;
    padding: 0.75rem;
    background: var(--bg-app);
    border: 1px solid var(--border-subtle);
    border-radius: 6px;
    transition: border-color var(--transition-fast);
  }

  .step.done {
    border-color: var(--text-active);
    opacity: 0.75;
  }

  .step-status {
    flex-shrink: 0;
    width: 24px;
    height: 24px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: var(--font-heading);
    font-size: 0.8rem;
    color: var(--text-tertiary);
    border: 1.5px solid var(--text-tertiary);
    margin-top: 1px;
  }

  .step-status.complete {
    color: var(--text-active);
    border-color: var(--text-active);
  }

  .step-status svg {
    width: 14px;
    height: 14px;
  }

  .step-number {
    line-height: 1;
  }

  .step-content {
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
    min-width: 0;
  }

  .step-title {
    font-size: 1rem;
    color: var(--text-primary);
    font-weight: 700;
  }

  .step-desc {
    font-size: 0.85rem;
    color: var(--text-secondary);
    line-height: 1.4;
  }

  .step-detail {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    margin-top: 0.25rem;
    font-size: 0.8rem;
  }

  .status-ok {
    color: var(--text-active);
    font-weight: 600;
  }

  .status-partial {
    color: var(--text-accent);
  }

  .status-pending {
    color: var(--text-tertiary);
  }
  .status-pending strong {
    color: var(--text-secondary);
  }

  .command {
    background: rgba(0, 0, 0, 0.3);
    border: 1px solid var(--border-subtle);
    border-radius: 4px;
    padding: 0.25rem 0.5rem;
    font-family: monospace;
    font-size: 0.8rem;
    color: var(--text-primary);
    user-select: all;
    -webkit-user-select: all;
    width: fit-content;
  }

  .action-btn {
    margin-top: 0.35rem;
    padding: 0.3rem 0.75rem;
    border-radius: 4px;
    border: 1px solid var(--border-accent);
    background: transparent;
    color: var(--text-accent);
    font-family: var(--font-heading);
    font-size: 0.85rem;
    transition: all var(--transition-fast);
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    width: fit-content;
  }
  .action-btn:hover {
    background: rgba(182, 159, 129, 0.1);
  }
  .action-btn:active {
    transform: scale(0.97);
  }

  .action-icon {
    width: 14px;
    height: 14px;
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
