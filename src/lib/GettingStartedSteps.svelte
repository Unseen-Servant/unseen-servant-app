<script lang="ts">
  export let ollamaRunning: boolean = false;
  export let ollamaModelReady: boolean = false;
  export let folderSelected: boolean = false;
  export let filesIndexed: boolean = false;
  export let collectionsCreated: boolean = false;
  export let mcpConnected: boolean = false;
  export let onSelectFolder: () => void;
  export let onCopyMcpConfig: () => void;

  let expanded = new Set<number>();
  function toggleExpand(i: number) {
    if (expanded.has(i)) expanded.delete(i);
    else expanded.add(i);
    expanded = expanded;
  }

  $: ollamaReady = ollamaRunning && ollamaModelReady;
</script>

<div class="manual">
  <!-- 1. Ollama -->
  <section class="entry" class:done={ollamaReady}>
    <header class="entry-head">
      <span class="led" class:on={ollamaReady} aria-hidden="true"></span>
      <span class="num">1.</span>
      <h3 class="title">Ollama — local AI engine</h3>
      <span class="state">
        {#if ollamaReady}ready
        {:else if ollamaRunning}model pending
        {:else}not detected
        {/if}
      </span>
    </header>
    <p class="prose">
      Legend Lore runs entirely on your machine. Ollama is the local
      model server that turns your PDFs into vectors — numerical
      fingerprints so search can find passages by meaning, not just
      keywords. It's free, open-source, and your library never leaves
      your disk.
    </p>
    {#if !ollamaRunning}
      <p class="action">
        Download from <strong>ollama.com</strong>, install, and launch
        the app.
      </p>
    {:else if !ollamaModelReady}
      <p class="action">
        Ollama is running, but the embedding model isn't pulled yet.
        Run this once:
      </p>
      <code class="command">ollama pull bge-m3</code>
    {/if}
    <button class="expander" on:click={() => toggleExpand(0)}>
      {expanded.has(0) ? '▾' : '▸'} Why bge-m3?
    </button>
    {#if expanded.has(0)}
      <p class="prose detail">
        bge-m3 is a multilingual embedding model that performs well on
        passage retrieval — about 1 GB on disk, runs on CPU, outputs
        1,024-dimensional vectors. It handles game-system jargon and
        long-tail TTRPG vocabulary gracefully, which matters when the
        same word ("save", "check", "advantage") means different things
        across systems.
      </p>
    {/if}
  </section>

  <!-- 2. Library -->
  <section class="entry" class:done={folderSelected}>
    <header class="entry-head">
      <span class="led" class:on={folderSelected} aria-hidden="true"></span>
      <span class="num">2.</span>
      <h3 class="title">Library — your PDF folder</h3>
      <span class="state">{folderSelected ? 'selected' : 'unset'}</span>
    </header>
    <p class="prose">
      Pick a folder containing your TTRPG PDFs. Legend Lore reads from
      disk in place — no upload, no copying, no cloud sync. Subfolders
      are fine; the file tree mirrors your folder layout. Move, rename,
      or delete files anytime; the index follows along.
    </p>
    {#if !folderSelected}
      <button class="link" on:click={onSelectFolder}>Choose folder</button>
    {/if}
    <button class="expander" on:click={() => toggleExpand(1)}>
      {expanded.has(1) ? '▾' : '▸'} Where does my data live?
    </button>
    {#if expanded.has(1)}
      <p class="prose detail">
        Your PDFs stay in the folder you pick. Legend Lore stores only
        the index — extracted text, chunk boundaries, and embeddings —
        in a local ChromaDB instance under the app's data directory
        (visible from <em>Settings → Library</em>). Delete the index
        anytime; the PDFs are untouched.
      </p>
    {/if}
  </section>

  <!-- 3. Index -->
  <section class="entry" class:done={filesIndexed}>
    <header class="entry-head">
      <span class="led" class:on={filesIndexed} aria-hidden="true"></span>
      <span class="num">3.</span>
      <h3 class="title">Index — embed your books</h3>
      <span class="state">{filesIndexed ? 'indexed' : 'none yet'}</span>
    </header>
    <p class="prose">
      Indexing reads each PDF, splits it at heading boundaries into
      ~1,000-character chunks, and embeds each one via Ollama. The
      result lives locally in ChromaDB. First-time indexing takes
      roughly a minute per book; afterwards only changed PDFs are
      re-embedded.
    </p>
    <p class="action">
      Tick the boxes next to PDFs in the file tree, then hit the sync
      button in the status bar.
    </p>
    <button class="expander" on:click={() => toggleExpand(2)}>
      {expanded.has(2) ? '▾' : '▸'} Why chunks instead of whole PDFs?
    </button>
    {#if expanded.has(2)}
      <p class="prose detail">
        Embedding models have a context window. Feeding a whole rulebook
        at once would dilute the signal — every chunk would smell like
        every other chunk. Splitting at heading boundaries keeps
        semantic context intact (a rule and its caveats stay together)
        while letting each vector point sharply at one idea. Search
        retrieves matching chunks but returns the parent section, so
        results land at a useful granularity.
      </p>
    {/if}
  </section>

  <!-- 4. Collections -->
  <section class="entry" class:done={collectionsCreated}>
    <header class="entry-head">
      <span class="led" class:on={collectionsCreated} aria-hidden="true"></span>
      <span class="num">4.</span>
      <h3 class="title">Collections — scope your searches</h3>
      <span class="state">{collectionsCreated ? 'created' : 'none yet'}</span>
    </header>
    <p class="prose">
      Collections group indexed PDFs for fast scoping. A "Curse of
      Strahd" collection might be just the campaign book; "D&amp;D
      Bestiary" might pull in three monster manuals. Activate a
      collection and every search — yours and your agent's — narrows to
      it. Right-click any folder or file in the tree for one-shot
      scoping.
    </p>
    <p class="action">
      Use the <strong>+</strong> in the collections panel to create
      one, or right-click a folder and choose
      <em>Create collection from folder</em>.
    </p>
  </section>

  <!-- 5. MCP -->
  <section class="entry optional" class:done={mcpConnected}>
    <header class="entry-head">
      <span class="led" class:on={mcpConnected} aria-hidden="true"></span>
      <span class="num">5.</span>
      <h3 class="title">MCP — wire up an AI agent <span class="opt">(optional)</span></h3>
      <span class="state">{mcpConnected ? 'connected' : 'not detected'}</span>
    </header>
    <p class="prose">
      MCP (Model Context Protocol) is the bridge between Legend Lore
      and your AI agent — Claude Desktop, Claude Code, or anything else
      that speaks MCP. Once configured, your agent can search your
      library mid-session: stat blocks, spell descriptions, random
      tables, lore. Skip this if you're using Legend Lore standalone.
    </p>
    <button class="link" on:click={onCopyMcpConfig}>Copy MCP config</button>
    <button class="expander" on:click={() => toggleExpand(4)}>
      {expanded.has(4) ? '▾' : '▸'} How is this still local?
    </button>
    {#if expanded.has(4)}
      <p class="prose detail">
        Paste the config into your agent's MCP settings. The agent
        spawns <code class="inline-code">mcp_server.py</code> as a
        subprocess and talks to it over stdio. The MCP server then
        calls back to the local sidecar at
        <code class="inline-code">localhost:8420</code>, which queries
        ChromaDB and returns results. The agent sees only the search
        results — never your PDF files, never the embeddings, never
        anything outside what you asked it to look for.
      </p>
    {/if}
  </section>
</div>

<style>
  .manual {
    display: flex;
    flex-direction: column;
    gap: 1.6rem;
    width: 100%;
    max-width: 540px;
    font-family: var(--font-body);
  }

  .entry {
    display: flex;
    flex-direction: column;
    gap: 0.55rem;
  }
  .entry.done {
    opacity: 0.85;
  }

  .entry-head {
    display: grid;
    grid-template-columns: auto auto 1fr auto;
    align-items: baseline;
    column-gap: 0.5rem;
    padding-bottom: 0.4rem;
    border-bottom: 1px solid var(--border-subtle);
  }

  .led {
    align-self: center;
    width: 9px;
    height: 9px;
    border-radius: 50%;
    border: 1.5px solid var(--text-tertiary);
    background: transparent;
  }
  .led.on {
    background: var(--text-active);
    border-color: var(--text-active);
  }

  .num {
    font-family: var(--font-heading, var(--font-body));
    font-size: 0.85rem;
    color: var(--text-tertiary);
    letter-spacing: 0.08em;
  }

  .title {
    margin: 0;
    font-family: var(--font-heading, var(--font-body));
    font-size: 0.95rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--text-primary);
    font-weight: 600;
  }
  .entry.done .title {
    color: var(--text-secondary);
  }

  .opt {
    font-family: var(--font-body);
    font-size: 0.75rem;
    letter-spacing: 0;
    text-transform: none;
    color: var(--text-tertiary);
    font-weight: normal;
    margin-left: 0.4rem;
  }

  .state {
    font-family: var(--font-heading, var(--font-body));
    font-size: 0.7rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--text-tertiary);
    white-space: nowrap;
  }
  .entry.done .state {
    color: var(--text-active);
  }

  .prose {
    margin: 0;
    font-size: 0.88rem;
    color: var(--text-secondary);
    line-height: 1.55;
  }
  .prose em {
    color: var(--text-secondary);
    font-style: italic;
  }
  .prose.detail {
    color: var(--text-tertiary);
    border-left: 2px solid var(--border-subtle);
    padding-left: 0.75rem;
    margin-left: 0.1rem;
  }

  .action {
    margin: 0;
    font-size: 0.85rem;
    color: var(--text-secondary);
    line-height: 1.5;
  }
  .action strong {
    color: var(--text-primary);
    font-weight: 600;
  }
  .action em {
    color: var(--text-accent);
    font-style: normal;
  }

  .command {
    display: inline-block;
    padding: 0.25rem 0.55rem;
    background: var(--bg-app);
    border: 1px solid var(--border-subtle);
    border-radius: 3px;
    font-family: var(--font-mono, ui-monospace, monospace);
    font-size: 0.8rem;
    color: var(--text-primary);
    user-select: all;
    -webkit-user-select: all;
    width: fit-content;
  }
  .inline-code {
    font-family: var(--font-mono, ui-monospace, monospace);
    font-size: 0.85em;
    padding: 0 0.25em;
    background: var(--bg-app);
    border-radius: 2px;
    color: var(--text-primary);
  }

  .link {
    align-self: flex-start;
    background: none;
    border: none;
    color: var(--text-active);
    font-family: var(--font-body);
    font-size: 0.88rem;
    padding: 0;
    cursor: pointer;
    transition: filter var(--transition-fast);
  }
  .link::before {
    content: '[';
    color: var(--text-secondary);
    margin-right: 0.2rem;
  }
  .link::after {
    content: ']';
    color: var(--text-secondary);
    margin-left: 0.2rem;
  }
  .link:hover {
    filter: brightness(1.2);
  }
  .link:hover::before,
  .link:hover::after {
    color: var(--text-accent);
  }

  .expander {
    align-self: flex-start;
    background: none;
    border: none;
    color: var(--text-tertiary);
    font-family: var(--font-body);
    font-size: 0.78rem;
    padding: 0;
    cursor: pointer;
    transition: color var(--transition-fast);
    margin-top: 0.1rem;
  }
  .expander:hover {
    color: var(--text-secondary);
  }
</style>
