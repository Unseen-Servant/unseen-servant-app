<script lang="ts">
  // The words the app uses that a newcomer meets without a definition.
  const GLOSSARY: { group: string; terms: [term: string, meaning: string][] }[] = [
    {
      group: 'Legend Lore',
      terms: [
        ['Collection', 'A named set of books'],
        ['Play', 'Search covers only the playing collections (P)'],
        ['Mix', 'Several collections playing together'],
        ['Arm', 'While a collection or a beat is armed (●), clicks file things in or out'],
        ['Solo', 'Narrow search to a book, folder or game system (S)'],
        ['Mute', 'Leave a book, folder, game system or collection out of search (M)'],
        ['Bypass', 'Set every play, solo and mute aside without clearing them (B)'],
        ['Strong · Good · Weak', 'How closely a result matches; weak ones fade'],
        ['Sync', 'Index the ticked books (⌘S)'],
      ],
    },
    {
      group: 'Command',
      terms: [
        ['Campaign', 'A folder in the campaigns folder, holding all it uses'],
        ['Track', 'A folder in a campaign, shown as a column: NPCs, Secrets…'],
        ['Note', 'A Markdown file; [[Name]] links to one'],
        ['Shelf', 'Notes gathered but not filed on a track yet'],
        ['Beat', 'A scene: the notes it needs'],
        ['Session', 'The beats planned for one game'],
        ['Prep · Play', 'Arranging and running, switched with Tab'],
        ['Launch', 'Put a beat or a note in play (P)'],
        ['Live set', 'The notes in play right now'],
        ['Spent', 'Used up at the table, and dimmed from then on (A)'],
        ['Board', "Play's cards, one board per session"],
        ['Card tray', 'The live set as a hand of cards, under the board'],
      ],
    },
    {
      group: 'Machinery',
      terms: [
        ['Sidecar', "Indexes and searches in the background; the status bar's first lamp"],
        ['Embedder', 'Ollama with bge-m3, reading text for meaning; the second lamp'],
        ['MCP', 'How an AI agent reaches the library and campaigns; the third lamp'],
        ['Rack', "The main window's tools, laid out in views; 1–8 switch views"],
      ],
    },
  ];

  // The tools sidecar/mcp_server.py registers. Keep in step with it.
  const MCP_TOOLS: { group: string; tools: [name: string, what: string][] }[] = [
    {
      group: 'Library',
      tools: [
        ['search_library', 'Search by meaning, optionally within a source, game system or collection'],
        ['get_section', 'Read a whole section from a search result'],
        ['get_pages', 'Read up to 20 pages of a PDF as text'],
        ['list_sources', 'List the indexed PDFs'],
        ['list_collections', 'List the collections'],
        ['list_game_systems', 'List the game systems in the library'],
      ],
    },
    {
      group: 'Command · reads',
      tools: [
        ['campaign_overview', "The campaigns, then the open one's tracks, notes, beats and sessions"],
        ['current_session', "A session's plan of beats, and what's live"],
        ['live_set', 'The notes in play, in full'],
        ['read_note', 'Read one note, with the hash an edit needs'],
        ['find_notes', 'Find notes by name or text'],
      ],
    },
    {
      group: 'Command · writes',
      tools: [
        ['create_note', 'Write a new note on a track or the shelf, citing its book'],
        ['edit_note', "Replace a note's text, keeping its frontmatter"],
        ['create_track', 'Make a new track at the end of the tracks'],
        ['move_note', 'Move a note to another track or the shelf'],
        ['create_beat', 'Make a beat from notes, with its scene, optionally in a session'],
        ['add_to_beat', 'Put a note in a beat, or take it out'],
        ['create_session', 'Start the next session and open it in the app'],
        ['set_active_session', 'Open a session in the app'],
        ['plan_beat', "Put a beat in a session's plan, move it, or take it out"],
        ['add_to_live_set', 'Put a note in play, or take it out'],
        ['spend', 'Mark a note spent or unspent'],
      ],
    },
    {
      group: 'Command · board',
      tools: [
        ['arrange_board', "Frame a session's planned beats on its board, as Arrange does"],
        ['frame_cards', 'Gather notes into a named frame'],
        ['connect_cards', "Draw a line between two notes' cards, with a label"],
        ['add_text', 'Put a text card beside a note, or under the board'],
      ],
    },
  ];
</script>

<div class="pane">
  <section class="block">
    <h3 class="block-title section-title">Keyboard shortcuts</h3>
    <p class="block-desc">
      Press <code class="kbd">?</code> outside a text field, or click the
      keyboard key in the status bar, to see every shortcut.
    </p>
  </section>

  <section class="block">
    <h3 class="block-title section-title">Glossary</h3>
    {#each GLOSSARY as group (group.group)}
      <section class="tool-group">
        <h4 class="tool-group-title ledger-label">{group.group}</h4>
        <dl class="terms">
          {#each group.terms as [term, meaning] (term)}
            <dt class="term">{term}</dt>
            <dd class="what">{meaning}</dd>
          {/each}
        </dl>
      </section>
    {/each}
  </section>

  <section class="block">
    <h3 class="block-title section-title">Game system keywords</h3>
    <p class="block-desc">
      A book gets a game system when one of that system's keywords appears in
      its path (folders and filename) or, failing that, near the start of its
      text. Case, spaces, accents and punctuation don't count, and
      <em>&amp;</em> reads as <em>n</em>: <em>d&amp;d 5e</em>,
      <em>dnd-5e</em> and <em>DnD 5E</em> all match. Keep keywords to four
      characters or more; shorter ones turn up inside unrelated words.
    </p>
    <p class="block-desc">Name a system in a search and its books come first.</p>
  </section>

  <section class="block">
    <h3 class="block-title section-title">MCP tools</h3>
    <p class="block-desc">
      What an AI agent connected through MCP can do. Command tools work on the
      campaign open in the app unless the agent names another.
    </p>
    {#each MCP_TOOLS as group (group.group)}
      <section class="tool-group">
        <h4 class="tool-group-title ledger-label">{group.group}</h4>
        <dl class="tools">
          {#each group.tools as [name, what] (name)}
            <dt class="tool">{name}</dt>
            <dd class="what">{what}</dd>
          {/each}
        </dl>
      </section>
    {/each}
  </section>
</div>

<style>
  .pane {
    display: flex;
    flex-direction: column;
    gap: 1.4rem;
  }

  .block {
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
  }

  .block-title {
    margin: 0;
  }

  .block-desc {
    margin: 0;
    font-family: var(--font-body);
    font-size: 0.8rem;
    color: var(--text-secondary);
    line-height: 1.45;
  }

  .kbd {
    font-family: var(--font-mono);
    font-size: 0.85em;
    padding: 0.05em 0.3em;
    background: var(--bg-focused);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    color: var(--text-primary);
  }

  .tool-group {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
  }

  .tool-group-title {
    margin: 0;
  }

  .tools,
  .terms {
    margin: 0;
    display: grid;
    grid-template-columns: 9rem 1fr;
    column-gap: 1.25rem;
    row-gap: 0.25rem;
    align-items: baseline;
    font-size: 0.8rem;
  }

  .tool {
    margin: 0;
    font-family: var(--font-mono);
    font-size: 0.72rem;
    color: var(--text-primary);
    white-space: nowrap;
  }

  .term {
    margin: 0;
    font-weight: 600;
    color: var(--text-primary);
    white-space: nowrap;
  }

  .what {
    margin: 0;
    color: var(--text-secondary);
    line-height: 1.35;
  }
</style>
