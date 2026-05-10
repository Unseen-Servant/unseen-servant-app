<script lang="ts">
  import OllamaStatus from './OllamaStatus.svelte';

  export let ollamaRunning: boolean = false;
  export let ollamaModelReady: boolean = false;
  export let onSelectFolder: () => void;
  export let onOpenHelp: () => void = () => {};
</script>

<div class="page">
  <div class="page-inner">
    <header class="hero">
      <h1 class="title font-heading">Legend Lore</h1>
      <p class="tagline">A local-first reference for your TTRPG library.</p>
    </header>

    <section class="block">
      <h2 class="block-title font-heading">Pick your library folder</h2>
      <p class="block-desc">
        Legend Lore reads PDFs from this folder. Nothing leaves your machine.
      </p>
      <button class="primary-cta" type="button" on:click={onSelectFolder}>
        Choose folder
      </button>
    </section>

    <section class="block">
      <h2 class="block-title font-heading">Ollama — local AI engine</h2>
      <p class="block-desc">
        The local model server that turns your PDFs into searchable
        vectors. Free, open-source, runs alongside the app.
      </p>
      <OllamaStatus {ollamaRunning} {ollamaModelReady} />
    </section>

    <p class="more-link">
      <button type="button" class="btn-link" on:click={onOpenHelp}>
        More setup info in Help → Guides
      </button>
    </p>
  </div>
</div>

<style>
  .page {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 3rem 2rem;
    overflow-y: auto;
  }

  .page-inner {
    width: 100%;
    max-width: 540px;
    display: flex;
    flex-direction: column;
    gap: 1.75rem;
  }

  .hero {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
    align-items: center;
    text-align: center;
    margin-bottom: 0.5rem;
  }

  .title {
    margin: 0;
    font-size: 1.6rem;
    color: var(--text-primary);
    letter-spacing: 0.02em;
  }

  .tagline {
    margin: 0;
    font-family: var(--font-body);
    font-size: 0.9rem;
    color: var(--text-secondary);
  }

  .block {
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
  }

  .block-title {
    margin: 0;
    font-size: 1rem;
    color: var(--text-primary);
  }

  .block-desc {
    margin: 0;
    font-family: var(--font-body);
    font-size: 0.85rem;
    color: var(--text-secondary);
    line-height: 1.45;
  }

  .primary-cta {
    align-self: flex-start;
    padding: 0.55rem 1rem;
    font-family: var(--font-heading, var(--font-body));
    font-size: 0.9rem;
    color: var(--bg-container);
    background: var(--text-accent);
    border: 1px solid var(--text-accent);
    border-radius: 4px;
    cursor: pointer;
    transition: filter var(--transition-fast);
  }
  .primary-cta:hover {
    filter: brightness(1.1);
  }

  .more-link {
    margin: 0.4rem 0 0;
    text-align: center;
  }

  /* Bracketed terminal-style action — matches LibrarySettings/AboutPane */
  .btn-link {
    background: transparent;
    border: none;
    padding: 0;
    font-family: var(--font-mono, ui-monospace, monospace);
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
