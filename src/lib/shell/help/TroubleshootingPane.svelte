<script lang="ts">
  import { openUrl } from '@tauri-apps/plugin-opener';

  export let onOpenDataDir: () => void = () => {};

  const SUPPORT_EMAIL = 'guild@unseenservant.games';
</script>

<!-- One entry per problem, found by the messages the app shows for it
     (quoted as the code words them), then what to do. -->
<div class="pane">
  <section class="entry">
    <h3 class="entry-title section-title">Search says Ollama isn't running</h3>
    <p class="shows">
      &ldquo;Ollama isn&rsquo;t running. Start it to search.&rdquo; &middot;
      &ldquo;Embedder isn&rsquo;t running. Search waits for it&rdquo; &middot;
      &ldquo;Embedder is running without bge-m3&rdquo;
    </p>
    <p class="fix">
      Ollama has to be running to search or index. Install it from ollama.com
      and open it; if it runs without its model, run
      <code class="inline-code">ollama pull bge-m3</code> once in a terminal.
      Help &rarr; Guides shows which part is missing.
    </p>
  </section>

  <section class="entry">
    <h3 class="entry-title section-title">Books failed to index</h3>
    <p class="shows">&ldquo;2 books failed&rdquo; &middot; &ldquo;Added 3 books &middot; 1 failed&rdquo;</p>
    <p class="fix">
      Hover that line in the status bar for each book's reason.
      <em>Empty or scanned PDF</em> means its pages are pictures with no text:
      run it through an OCR tool, then tick it again. A locked or damaged PDF
      fails the same way. If every book failed at once, Ollama is likely down
      (above).
    </p>
  </section>

  <section class="entry">
    <h3 class="entry-title section-title">Search finds nothing, or only weak matches</h3>
    <p class="shows">
      &ldquo;Everything is muted.&rdquo; &middot; &ldquo;Nothing indexed is
      playing.&rdquo; &middot; &ldquo;Nothing under the soloed items.&rdquo;
      &middot; &ldquo;No strong matches &mdash; the content may be outside the
      current scope.&rdquo;
    </p>
    <p class="fix">
      A playing collection, a solo or a mute is narrowing the search. The
      <strong>B</strong> switch on the scope bar (<strong>B</strong> outside a
      text field) sets them all aside until you throw it back. Faded rows are
      weak matches; <em>Settings &rarr; General &rarr; Dim weak matches</em>
      turns the fading off.
    </p>
  </section>

  <section class="entry">
    <h3 class="entry-title section-title">The AI agent can't reach the library</h3>
    <p class="shows">
      &ldquo;MCP not detected&rdquo; on the status bar lamp &middot; the agent
      says &ldquo;Cannot connect to Legend Lore app&rdquo;
    </p>
    <p class="fix">
      Unseen Servant has to be running: closing its window doesn't quit it,
      quitting does. Check the config is in the agent's MCP settings (Help
      &rarr; Guides &rarr; Servant) and restart the agent after any edit. If
      the app moved since you copied the config, copy it again: the config
      holds the app's location.
    </p>
  </section>

  <section class="entry">
    <h3 class="entry-title section-title">Search and indexing are offline</h3>
    <p class="shows">
      &ldquo;Sidecar didn&rsquo;t start. Search and indexing are offline&rdquo;
      &middot; &ldquo;Library store didn&rsquo;t open&rdquo; &middot;
      &ldquo;Indexer failed to start. See log: &hellip;&rdquo;
    </p>
    <p class="fix">
      Quit Unseen Servant and open it again; a first launch after installing
      can be slow. If it fails again, copy <em>sidecar.log</em> out of the data
      folder before reopening, as every launch starts a new one, and send it
      with your report (below).
    </p>
    <button class="btn-link" on:click={onOpenDataDir}>reveal data folder</button>
  </section>

  <section class="entry">
    <h3 class="entry-title section-title">The library folder can't be reached</h3>
    <p class="shows">
      &ldquo;Library folder isn&rsquo;t reachable: &hellip;&rdquo; &middot;
      &ldquo;Library folder is no longer accessible: &hellip;&rdquo; &middot;
      &ldquo;Library folder isn&rsquo;t responding: &hellip;&rdquo;
    </p>
    <p class="fix">
      Connect the drive or network share it lives on. If the folder moved,
      choose it again in <em>Settings &rarr; Library</em>. On macOS, also check
      that <em>System Settings &rarr; Privacy &amp; Security &rarr; Files and
      Folders</em> lets Unseen Servant in.
    </p>
  </section>

  <section class="entry">
    <h3 class="entry-title section-title">Command can't find its campaigns</h3>
    <p class="shows">&ldquo;The campaign folder &hellip; is missing&rdquo;</p>
    <p class="fix">
      Connect the drive it lives on, or pick the folder again in
      <em>Settings &rarr; Command</em> (on macOS, also
      <em>File &rarr; Change Campaigns Folder&hellip;</em>).
    </p>
  </section>

  <section class="entry">
    <h3 class="entry-title section-title">Still stuck</h3>
    <p class="fix">
      Write with what you see, and <em>sidecar.log</em> if search or indexing
      is involved.
    </p>
    <button class="btn-link" on:click={() => openUrl(`mailto:${SUPPORT_EMAIL}`).catch(() => {})}>{SUPPORT_EMAIL}</button>
  </section>
</div>

<style>
  /* Same vocabulary as the Guides steps (GettingStartedSteps.svelte):
     Almendra titles, body text at 0.85rem, bracketed actions. The quoted
     messages sit a step quieter, so the eye lands on the fix. */
  .pane {
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
    font-family: var(--font-body);
  }

  .entry {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
  }

  .entry-title {
    margin: 0;
  }

  .shows {
    margin: 0;
    font-size: 0.78rem;
    font-style: italic;
    color: var(--text-tertiary);
    line-height: 1.4;
  }

  .fix {
    margin: 0;
    font-size: 0.85rem;
    color: var(--text-secondary);
    line-height: 1.45;
  }
  .fix strong {
    color: var(--text-primary);
    font-weight: 600;
  }
  .fix em {
    font-style: italic;
  }

  .inline-code {
    font-family: var(--font-mono);
    font-size: 0.85em;
    padding: 0 0.25em;
    background: var(--bg-focused);
    border-radius: var(--radius-sm);
    color: var(--text-primary);
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
