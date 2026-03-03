<script lang="ts">
  export let selectedFolder: string;
  export let onSelectFolder: () => void;
  export let onCopyMcpConfig: () => void;
</script>

<header class="header">
  <div class="header-left">
    <span class="app-title">Unseen Servant</span>
  </div>

  <div class="header-center"></div>

  <div class="header-right">
    <button
      class="icon-btn"
      on:click={onSelectFolder}
      data-tooltip={selectedFolder ? 'Change library folder' : 'Select TTRPG library folder'}
    >
      <svg class="btn-icon" viewBox="0 0 640 640" fill="currentColor">
        <path d="M480 576L192 576C139 576 96 533 96 480L96 160C96 107 139 64 192 64L496 64C522.5 64 544 85.5 544 112L544 400C544 420.9 530.6 438.7 512 445.3L512 512C529.7 512 544 526.3 544 544C544 561.7 529.7 576 512 576L480 576zM192 448C174.3 448 160 462.3 160 480C160 497.7 174.3 512 192 512L448 512L448 448L192 448zM224 216C224 229.3 234.7 240 248 240L424 240C437.3 240 448 229.3 448 216C448 202.7 437.3 192 424 192L248 192C234.7 192 224 202.7 224 216zM248 288C234.7 288 224 298.7 224 312C224 325.3 234.7 336 248 336L424 336C437.3 336 448 325.3 448 312C448 298.7 437.3 288 424 288L248 288z"/>
      </svg>
    </button>

    <button
      class="icon-btn"
      on:click={onCopyMcpConfig}
      data-tooltip="Copy MCP config"
    >
      <svg class="btn-icon" viewBox="0 0 180 180" fill="none" stroke="currentColor" stroke-width="12" stroke-linecap="round">
        <path d="M18 84.8528L85.8822 16.9706C95.2548 7.59798 110.451 7.59798 119.823 16.9706V16.9706C129.196 26.3431 129.196 41.5391 119.823 50.9117L68.5581 102.177"/>
        <path d="M69.2652 101.47L119.823 50.9117C129.196 41.5391 144.392 41.5391 153.765 50.9117L154.118 51.2652C163.491 60.6378 163.491 75.8338 154.118 85.2063L92.7248 146.6C89.6006 149.724 89.6006 154.789 92.7248 157.913L105.331 170.52"/>
        <path d="M102.853 33.9411L52.6482 84.1457C43.2756 93.5183 43.2756 108.714 52.6482 118.087V118.087C62.0208 127.459 77.2167 127.459 86.5893 118.087L136.794 67.8822"/>
      </svg>
    </button>

  </div>
</header>

<style>
  .header {
    display: flex;
    align-items: center;
    height: var(--header-height);
    padding: 0 1rem;
    background: var(--bg-header);
    border-bottom: 1px solid var(--border-subtle);
    flex-shrink: 0;
    gap: 1rem;
  }

  .header-left {
    flex-shrink: 0;
  }

  .app-title {
    font-family: var(--font-heading);
    font-size: 1.25rem;
    font-weight: 700;
    color: var(--text-accent);
    letter-spacing: 0.02em;
  }

  .header-center {
    flex: 1;
  }

  .header-right {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-shrink: 0;
  }

  .icon-btn {
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0.25rem 0.5rem;
    background: none;
    border: 1px solid transparent;
    border-radius: 4px;
    color: var(--text-secondary);
    font-size: 0.85rem;
    transition: all var(--transition-fast);
  }
  .icon-btn:hover {
    color: var(--text-accent);
    border-color: var(--border-subtle);
    background: var(--bg-focused);
  }
  .icon-btn:active {
    transform: scale(0.97);
  }

  .btn-icon {
    width: 1.1rem;
    height: 1.1rem;
  }
  .icon-btn[data-tooltip]::after {
    content: attr(data-tooltip);
    position: absolute;
    top: 100%;
    right: 0;
    margin-top: 6px;
    padding: 0.3rem 0.6rem;
    background: var(--bg-container);
    color: var(--text-primary);
    border: 1px solid var(--bg-category);
    border-radius: 4px;
    font-size: 0.7rem;
    font-family: var(--font-body);
    white-space: nowrap;
    pointer-events: none;
    opacity: 0;
    transform: translateY(-2px);
    transition: opacity var(--transition-fast), transform var(--transition-fast);
    box-shadow: var(--shadow-dropdown);
    z-index: 50;
  }
  .icon-btn[data-tooltip]:hover::after {
    opacity: 1;
    transform: translateY(0);
  }

</style>
