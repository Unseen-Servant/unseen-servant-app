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
  <section class="field">
    <div class="field-head">
      <div class="field-title-row">
        <h3 class="field-title font-heading">Ollama — local AI engine</h3>
        <span
          class="field-status"
          class:ok={ollamaReady}
          class:partial={ollamaRunning && !ollamaModelReady}
        >
          {#if ollamaReady}Ready
          {:else if ollamaRunning}Model pending
          {:else}Not detected{/if}
        </span>
      </div>
      <p class="field-desc">
        Legend Lore runs entirely on your machine. Ollama is the local
        model server that turns your PDFs into vectors — numerical
        fingerprints so search can find passages by meaning, not just
        keywords. It's free, open-source, and your library never leaves
        your disk.
      </p>
    </div>
    {#if !ollamaRunning}
      <p class="field-desc">
        Download from <strong>ollama.com</strong>, install, and launch
        the app.
      </p>
    {:else if !ollamaModelReady}
      <p class="field-desc">Pull the embedding model (one-time):</p>
      <code class="command">ollama pull bge-m3</code>
    {/if}
    <button class="expander" on:click={() => toggleExpand(0)}>
      {expanded.has(0) ? '▾' : '▸'} Why bge-m3?
    </button>
    {#if expanded.has(0)}
      <p class="field-desc detail">
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
  <section class="field">
    <div class="field-head">
      <div class="field-title-row">
        <h3 class="field-title font-heading">Library — your PDF folder</h3>
        <span class="field-status" class:ok={folderSelected}>
          {folderSelected ? 'Selected' : 'Unset'}
        </span>
      </div>
      <p class="field-desc">
        Pick a folder containing your TTRPG PDFs. Legend Lore reads from
        disk in place — no upload, no copying, no cloud sync. Subfolders
        are fine; the file tree mirrors your folder layout. Move,
        rename, or delete files anytime; the index follows along.
      </p>
    </div>
    {#if !folderSelected}
      <button class="btn-link" on:click={onSelectFolder}>Choose folder</button>
    {/if}
    <button class="expander" on:click={() => toggleExpand(1)}>
      {expanded.has(1) ? '▾' : '▸'} Where does my data live?
    </button>
    {#if expanded.has(1)}
      <p class="field-desc detail">
        Your PDFs stay in the folder you pick. Legend Lore stores only
        the index — extracted text, chunk boundaries, and embeddings —
        in a local ChromaDB instance under the app's data directory
        (visible from <em>Settings → Library → Database</em>). Delete
        the index anytime; the PDFs are untouched.
      </p>
    {/if}
  </section>

  <!-- 3. Index -->
  <section class="field">
    <div class="field-head">
      <div class="field-title-row">
        <h3 class="field-title font-heading">Index — embed your books</h3>
        <span class="field-status" class:ok={filesIndexed}>
          {filesIndexed ? 'Indexed' : 'None yet'}
        </span>
      </div>
      <p class="field-desc">
        Indexing reads each PDF, splits it at heading boundaries into
        ~1,000-character chunks, and embeds each one via Ollama. The
        result lives locally in ChromaDB. First-time indexing takes
        roughly a minute per book; afterwards only changed PDFs are
        re-embedded.
      </p>
    </div>
    <p class="field-desc">
      Tick the boxes next to PDFs in the file tree, then hit the sync
      button in the status bar.
    </p>
    <button class="expander" on:click={() => toggleExpand(2)}>
      {expanded.has(2) ? '▾' : '▸'} Why chunks instead of whole PDFs?
    </button>
    {#if expanded.has(2)}
      <p class="field-desc detail">
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
  <section class="field">
    <div class="field-head">
      <div class="field-title-row">
        <h3 class="field-title font-heading">Collections — scope your searches</h3>
        <span class="field-status" class:ok={collectionsCreated}>
          {collectionsCreated ? 'Created' : 'None yet'}
        </span>
      </div>
      <p class="field-desc">
        Collections group indexed PDFs for fast scoping. A "Curse of
        Strahd" collection might be just the campaign book; "D&amp;D
        Bestiary" might pull in three monster manuals. Activate a
        collection and every search — yours and your agent's — narrows
        to it. Right-click any folder or file in the tree for one-shot
        scoping.
      </p>
    </div>
    <p class="field-desc">
      Use the <strong>+</strong> in the collections panel to create
      one, or right-click a folder and choose
      <em>Create collection from folder</em>.
    </p>
  </section>

  <!-- 5. MCP -->
  <section class="field">
    <div class="field-head">
      <div class="field-title-row">
        <h3 class="field-title font-heading">
          MCP — wire up an AI agent <span class="opt">(optional)</span>
        </h3>
        <span class="field-status" class:ok={mcpConnected}>
          {mcpConnected ? 'Connected' : 'Not detected'}
        </span>
      </div>
      <p class="field-desc">
        MCP (Model Context Protocol) is the bridge between Legend Lore
        and your AI agent — Claude Desktop, Claude Code, or anything
        else that speaks MCP. Once configured, your agent can search
        your library mid-session: stat blocks, spell descriptions,
        random tables, lore. Skip this if you're using Legend Lore
        standalone.
      </p>
    </div>
    <button class="btn-link" on:click={onCopyMcpConfig}>Copy MCP config</button>
    <button class="expander" on:click={() => toggleExpand(4)}>
      {expanded.has(4) ? '▾' : '▸'} How is this still local?
    </button>
    {#if expanded.has(4)}
      <p class="field-desc detail">
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
    <button class="expander" on:click={() => toggleExpand(5)}>
      {expanded.has(5) ? '▾' : '▸'} What can my agent do?
    </button>
    {#if expanded.has(5)}
      <div class="field-desc detail">
        <ul class="tools-list">
          <li>
            <strong>Search the library</strong> by meaning — scoped by
            source, game system, or collection. Results come back with
            page numbers and section headings, ready to cite.
          </li>
          <li>
            <strong>List indexed PDFs</strong> — what's actually
            queryable.
          </li>
          <li>
            <strong>List collections</strong> — your curated subsets,
            with the active one marked.
          </li>
          <li>
            <strong>List game systems</strong> — which systems are
            present, so the agent doesn't guess names.
          </li>
        </ul>
        <p class="tools-footnote">
          Set an active collection and search and listings auto-scope to
          it — your agent stays focused on tonight's session.
        </p>
      </div>
    {/if}
  </section>
</div>

<style>
  /* Shape mirrors LibrarySettings: stacked .field sections at 1.25rem
     gap, .field-title in Almendra at 0.95rem, .field-desc in body at
     0.85rem. The Setup-specific bits — right-aligned status badge,
     expanders, command box — extend that vocabulary rather than
     replace it. */
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
    gap: 0.6rem;
  }

  .field-head {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
  }

  .field-title-row {
    display: flex;
    align-items: baseline;
    gap: 0.75rem;
  }

  .field-title {
    flex: 1;
    min-width: 0;
    font-size: 0.95rem;
    color: var(--text-primary);
    margin: 0;
  }

  .opt {
    font-family: var(--font-body);
    font-size: 0.78rem;
    color: var(--text-tertiary);
    font-weight: normal;
    margin-left: 0.3rem;
  }

  .field-status {
    flex-shrink: 0;
    font-family: var(--font-heading, var(--font-body));
    font-size: 0.7rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--text-tertiary);
  }
  .field-status.ok {
    color: var(--text-active);
  }
  .field-status.partial {
    color: var(--text-accent);
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
  .field-desc.detail {
    color: var(--text-tertiary);
    padding-left: 0.75rem;
    border-left: 1px solid var(--border-subtle);
  }

  .command {
    display: inline-block;
    padding: 0.3rem 0.55rem;
    background: var(--bg-focused);
    border: 1px solid var(--border-subtle);
    border-radius: 4px;
    font-family: var(--font-mono, ui-monospace, monospace);
    font-size: 0.75rem;
    color: var(--text-primary);
    user-select: all;
    -webkit-user-select: all;
    width: fit-content;
  }
  .inline-code {
    font-family: var(--font-mono, ui-monospace, monospace);
    font-size: 0.85em;
    padding: 0 0.25em;
    background: var(--bg-focused);
    border-radius: 2px;
    color: var(--text-primary);
  }

  /* Bracket-link action — same pattern as LibrarySettings .btn-link.
     Mono 0.7rem, accent text, [bracketed] in secondary, hover brightens. */
  .btn-link {
    align-self: flex-start;
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

  /* Tool list inside the MCP "What can my agent do?" expander. Lives
     inside .field-desc.detail, so it inherits font, color, and the
     left border. Compact list with strong-tagged tool names. */
  .tools-list {
    margin: 0;
    padding-left: 1.1rem;
    list-style: disc;
  }
  .tools-list li {
    margin-bottom: 0.4rem;
  }
  .tools-list li:last-child {
    margin-bottom: 0;
  }
  .tools-footnote {
    margin: 0.6rem 0 0 0;
  }

  /* Expander — disclosure widget, distinct from .btn-link. No brackets,
     just an arrow and tertiary text. Sits below the description, marks
     the optional "deep dive" content. */
  .expander {
    align-self: flex-start;
    background: none;
    border: none;
    color: var(--text-tertiary);
    font-family: var(--font-body);
    font-size: 0.75rem;
    padding: 0;
    cursor: pointer;
    transition: color var(--transition-fast);
  }
  .expander:hover {
    color: var(--text-secondary);
  }
</style>
