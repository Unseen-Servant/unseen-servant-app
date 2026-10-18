<script lang="ts">
  import { openUrl } from '@tauri-apps/plugin-opener';
  import ReadyTag from '../shell/help/ReadyTag.svelte';

  export let sidecarConnected: boolean = true;
  export let ollamaRunning: boolean = false;
  export let ollamaModelReady: boolean = false;
  export let folderSelected: boolean = false;
  export let filesIndexed: boolean = false;
  export let onSelectFolder: () => void;

  // What the Ollama lamp means in words (ReadyTag).
  const OLLAMA_STATE = {
    unknown: "Unknown: the sidecar isn't running",
    ready: 'Ready',
    model: 'Model missing',
    missing: 'Not detected',
  };

  // Ollama is probed through the sidecar: with the sidecar down its state is
  // unknown, and "not detected" would send a working setup to reinstall it.
  let ollamaState: keyof typeof OLLAMA_STATE;
  $: ollamaState = !sidecarConnected
    ? 'unknown'
    : ollamaRunning && ollamaModelReady
      ? 'ready'
      : ollamaRunning
        ? 'model'
        : 'missing';
</script>

<!-- Each step leads with what to do; its lamp reads the live state. -->
<div class="manual">
  <section class="field">
    <div class="field-title-row">
      <h3 class="field-title section-title">Ollama</h3>
      <ReadyTag
        lit={ollamaState === 'ready'}
        half={ollamaState === 'model'}
        state={OLLAMA_STATE[ollamaState]}
      />
    </div>
    <p class="field-desc">
      Runs the model that lets search find passages by meaning, on this
      machine.
      {#if ollamaState === 'unknown'}
        The sidecar isn't running, so Ollama can't be checked. Quit Unseen
        Servant and open it again.
      {:else if ollamaState === 'missing'}
        Install Ollama and open it.
      {:else if ollamaState === 'model'}
        Pull its model once, in a terminal:
      {/if}
    </p>
    {#if ollamaState === 'missing'}
      <button class="btn-link" on:click={() => openUrl('https://ollama.com').catch(() => {})}>ollama.com</button>
    {:else if ollamaState === 'model'}
      <code class="command">ollama pull bge-m3</code>
    {/if}
  </section>

  <section class="field">
    <div class="field-title-row">
      <h3 class="field-title section-title">Library folder</h3>
      <ReadyTag lit={folderSelected} state={folderSelected ? 'Ready' : 'No folder chosen'} />
    </div>
    <p class="field-desc">
      The folder that holds your PDFs. They are read where they are, nothing
      is uploaded or copied, and subfolders become the tree. Rename books and
      folders here (<strong>R</strong>) to keep their index; outside the app,
      a moved book or a renamed folder has to be indexed again.
    </p>
    {#if !folderSelected}
      <button class="btn-link" on:click={onSelectFolder}>choose folder</button>
    {/if}
  </section>

  <section class="field">
    <div class="field-title-row">
      <h3 class="field-title section-title">Index</h3>
      <ReadyTag lit={filesIndexed} state={filesIndexed ? 'Ready' : 'Nothing indexed yet'} />
    </div>
    <p class="field-desc">
      Tick books or folders in the tree; the status bar then offers
      <em>sync</em> (<strong>&#8984;S</strong>). Later syncs index only the
      books that changed.
    </p>
  </section>

  <section class="field">
    <div class="field-title-row">
      <h3 class="field-title section-title">
        Collections <span class="opt">(optional)</span>
      </h3>
    </div>
    <p class="field-desc">
      Named sets of books. Play one (&#9654; or <strong>P</strong>) and search
      covers only its books; play several to search them together. Without a
      collection, solo (<strong>S</strong>) or mute (<strong>M</strong>) books
      and folders in the tree.
    </p>
    <p class="field-desc">
      <strong>&#8984;N</strong> starts one, armed (&#9679;): click books in the
      tree to file them in it, then disarm it with its &#9679; or
      <strong>E</strong>. Dropping a book or folder on a collection files it
      too.
    </p>
  </section>
</div>

<style>
  /* Shape mirrors LibrarySettings: stacked .field sections at 1.25rem
     gap, .field-title in Almendra at 0.95rem, .field-desc in body at
     0.85rem. The Setup-specific bits — right-aligned ReadyTag and
     command box — extend that vocabulary rather than replace it. */
  .manual {
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
    width: 100%;
    font-family: var(--font-body);
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: 0.45rem;
  }

  .field-title-row {
    display: flex;
    align-items: baseline;
    gap: 0.75rem;
  }

  .field-title {
    flex: 1;
    min-width: 0;
    margin: 0;
  }

  .opt {
    font-family: var(--font-body);
    font-size: 0.78rem;
    color: var(--text-tertiary);
    font-weight: normal;
    margin-left: 0.3rem;
  }


  .field-desc {
    font-family: var(--font-body);
    font-size: 0.85rem;
    color: var(--text-secondary);
    line-height: 1.45;
    margin: 0;
  }
  .field-desc strong {
    color: var(--text-primary);
    font-weight: 600;
  }
  .field-desc em {
    color: var(--text-secondary);
    font-style: italic;
  }

  .command {
    align-self: flex-start;
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

  /* Bracket-link action — same pattern as LibrarySettings .btn-link.
     Mono 0.7rem, accent text, [bracketed] in secondary, hover brightens. */
  .btn-link {
    align-self: flex-start;
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
