<script lang="ts">
  import { KEYBINDINGS, chord, type KeyScope } from '../keybindings';

  const SCOPE_ORDER: KeyScope[] = [
    'global',
    'fileTree',
    'systemsView',
    'collections',
    'searchInput',
    'searchResults',
    'filterMenu',
    'contextMenu',
  ];

  const SCOPE_LABELS: Record<KeyScope, string> = {
    global: 'Global',
    fileTree: 'File tree',
    systemsView: 'Systems view',
    collections: 'Collections',
    searchInput: 'Search input',
    searchResults: 'Search results',
    filterMenu: 'Filter console',
    contextMenu: 'Context menu',
    modal: 'Modal',
  };

  $: grouped = SCOPE_ORDER
    .map(scope => ({
      scope,
      label: SCOPE_LABELS[scope],
      entries: KEYBINDINGS.filter(k => k.scope === scope),
    }))
    .filter(g => g.entries.length > 0);
</script>

<div class="pane">
  <section class="block">
    <header class="block-head">
      <h3 class="block-title font-heading">Keyboard shortcuts</h3>
      <p class="block-desc">
        Press <code class="kbd">?</code> anywhere in the app to show these as
        an overlay.
      </p>
    </header>

    <div class="kb-groups">
      {#each grouped as group (group.scope)}
        <section class="kb-group">
          <h4 class="kb-group-title font-heading">{group.label}</h4>
          <dl class="bindings">
            {#each group.entries as entry (entry.id)}
              <dt class="chord">{chord(entry.id)}</dt>
              <dd class="label">{entry.label}</dd>
            {/each}
          </dl>
        </section>
      {/each}
    </div>
  </section>

  <section class="block">
    <header class="block-head">
      <h3 class="block-title font-heading">MCP tools</h3>
      <p class="block-desc">
        What an AI agent connected via MCP (Claude Desktop, Claude Code, or
        anything else that speaks the Model Context Protocol) can do with your
        library.
      </p>
    </header>

    <ul class="tools-list">
      <li>
        <strong>Search the library</strong> by meaning — scoped by source,
        game system, or collection. Results come back with page numbers and
        section headings, ready to cite.
      </li>
      <li>
        <strong>List indexed PDFs</strong> — what's actually queryable.
      </li>
      <li>
        <strong>List collections</strong> — your curated subsets, with the
        active one marked.
      </li>
      <li>
        <strong>List game systems</strong> — which systems are present, so
        the agent doesn't guess names.
      </li>
    </ul>
    <p class="tools-footnote">
      Set an active collection and search and listings auto-scope to it —
      your agent stays focused on tonight's session.
    </p>
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

  .block-head {
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
  }

  .block-title {
    margin: 0;
    font-size: 0.95rem;
    color: var(--text-primary);
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

  .kb-groups {
    display: flex;
    flex-direction: column;
    gap: 0.9rem;
  }

  .kb-group {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
  }

  .kb-group-title {
    margin: 0;
    font-size: 0.78rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--text-tertiary);
  }

  .bindings {
    margin: 0;
    display: grid;
    grid-template-columns: 9rem 1fr;
    column-gap: 1.25rem;
    row-gap: 0.25rem;
    font-size: 0.8rem;
  }

  .chord {
    margin: 0;
    font-family: var(--font-mono);
    color: var(--text-primary);
    white-space: nowrap;
  }

  .label {
    margin: 0;
    color: var(--text-secondary);
    line-height: 1.35;
  }

  .tools-list {
    margin: 0;
    padding-left: 1.1rem;
    list-style: disc;
    font-family: var(--font-body);
    font-size: 0.85rem;
    color: var(--text-secondary);
    line-height: 1.45;
  }
  .tools-list li {
    margin-bottom: 0.4rem;
  }
  .tools-list li:last-child {
    margin-bottom: 0;
  }
  .tools-list strong {
    color: var(--text-primary);
    font-weight: 600;
  }

  .tools-footnote {
    margin: 0.2rem 0 0;
    font-family: var(--font-body);
    font-size: 0.8rem;
    color: var(--text-tertiary);
    line-height: 1.45;
  }
</style>
