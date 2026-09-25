<script lang="ts">
  export let ollamaRunning: boolean = false;
  export let ollamaModelReady: boolean = false;
  export let onSelectFolder: () => void;
  export let onOpenHelp: () => void = () => {};

  $: ollamaState = ollamaRunning && ollamaModelReady
    ? 'ready'
    : ollamaRunning
      ? 'pending'
      : 'missing';

  $: ollamaLabel = ollamaState === 'ready'
    ? 'READY'
    : ollamaState === 'pending'
      ? 'MODEL PENDING'
      : 'NOT DETECTED';
</script>

<div class="page">
  <div class="frame">
    <header class="frame-strip frame-strip-top">
      <span class="brand">LEGEND LORE</span>
      <span
        class="ollama-pill"
        class:ok={ollamaState === 'ready'}
        class:partial={ollamaState === 'pending'}
      >
        OLLAMA · {ollamaLabel}
      </span>
    </header>

    <div class="frame-body">
      <h1 class="hero-title font-heading">Set up your library</h1>
      <p class="hero-desc">
        Legend Lore reads PDFs from a folder you choose.<br />
        Nothing leaves your machine.
      </p>

      <button class="primary-cta font-heading" type="button" on:click={onSelectFolder}>
        [ Choose library folder ]
      </button>

      {#if ollamaState === 'missing'}
        <p class="ollama-hint">
          Ollama not detected — install from <strong>ollama.com</strong>,
          then launch the app.
        </p>
      {:else if ollamaState === 'pending'}
        <p class="ollama-hint">
          Ollama running, embedding model pending. Run:
        </p>
        <code class="command">ollama pull bge-m3</code>
      {/if}
    </div>

    <footer class="frame-strip frame-strip-bottom">
      <button type="button" class="btn-link" on:click={onOpenHelp}>
        More setup info in Help → Guides
      </button>
    </footer>
  </div>
</div>

<style>
  .page {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 2rem;
    overflow-y: auto;
  }

  /* The frame is the visual anchor. Centered card with thin border, top
     and bottom status strips, content body. Mirrors the old-school
     control-panel feel: status at the edges, action in the center. */
  .frame {
    width: 100%;
    max-width: 460px;
    background: var(--bg-container);
    border: 1px solid var(--border-subtle);
    border-radius: 6px;
    overflow: hidden;
  }

  .frame-strip {
    padding: 0.5rem 0.85rem;
    font-family: var(--font-heading, var(--font-body));
    font-size: 0.65rem;
    letter-spacing: 0.12em;
    color: var(--text-tertiary);
  }

  .frame-strip-top {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    border-bottom: 1px solid var(--border-subtle);
  }

  .frame-strip-bottom {
    border-top: 1px solid var(--border-subtle);
    text-align: center;
  }

  .brand {
    color: var(--text-secondary);
  }

  .ollama-pill {
    color: var(--text-tertiary);
    font-variant-numeric: tabular-nums;
  }
  .ollama-pill.ok {
    color: var(--text-active);
  }
  .ollama-pill.partial {
    color: var(--text-accent);
  }

  .frame-body {
    padding: 1.8rem 1.4rem 1.6rem;
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    gap: 0.8rem;
  }

  .hero-title {
    margin: 0;
    font-size: 1.25rem;
    color: var(--text-primary);
    letter-spacing: 0.01em;
  }

  .hero-desc {
    margin: 0;
    font-family: var(--font-body);
    font-size: 0.85rem;
    color: var(--text-secondary);
    line-height: 1.55;
  }

  /* Bracket-button: text-only, no background, accent-colored, generous
     padding so it has presence. The brackets are part of the rendered
     text (not pseudo-elements) so the spacing inside reads as a single
     framed phrase. */
  .primary-cta {
    margin-top: 0.5rem;
    padding: 0.55rem 1rem;
    font-size: 0.95rem;
    color: var(--text-accent);
    background: transparent;
    border: none;
    cursor: pointer;
    letter-spacing: 0.02em;
    transition: filter var(--transition-fast);
  }
  .primary-cta:hover {
    filter: brightness(1.2);
  }

  .ollama-hint {
    margin: 0.6rem 0 0;
    font-family: var(--font-body);
    font-size: 0.8rem;
    color: var(--text-secondary);
    line-height: 1.5;
  }
  .ollama-hint strong {
    color: var(--text-primary);
    font-weight: 600;
  }

  .command {
    display: inline-block;
    padding: 0.3rem 0.55rem;
    background: var(--bg-focused);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    font-family: var(--font-mono);
    font-size: 0.75rem;
    color: var(--text-primary);
    user-select: all;
    -webkit-user-select: all;
  }

  /* Bracketed terminal-style action — matches LibrarySettings/AboutPane */
  .btn-link {
    background: transparent;
    border: none;
    padding: 0;
    font-family: var(--font-mono);
    font-size: 0.7rem;
    color: var(--text-accent);
    cursor: pointer;
    transition: filter var(--transition-fast);
  }
  .btn-link::before,
  .btn-link::after {
    color: var(--text-secondary);
    transition: color var(--transition-fast);
  }
  .btn-link::before {
    content: '[';
    margin-right: 0.15rem;
  }
  .btn-link::after {
    content: ']';
    margin-left: 0.15rem;
  }
  .btn-link:hover {
    filter: brightness(1.25);
  }
  .btn-link:hover::before,
  .btn-link:hover::after {
    color: var(--text-accent);
  }
</style>
