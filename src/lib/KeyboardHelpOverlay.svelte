<script lang="ts">
  import Modal from './Modal.svelte';
  import { KEYBINDINGS, chord, type KeyScope } from './keybindings';

  export let visible = false;
  export let onClose: () => void;

  // Order chosen to match the spec: most-used scopes first, modal-internal
  // chords last. `modal` scope intentionally omitted — those chords live
  // inside dialogs and aren't useful in a global cheat sheet.
  const SCOPE_ORDER: KeyScope[] = [
    'global',
    'fileTree',
    'systemsView',
    'collections',
    'searchInput',
    'searchResults',
    'filterPanel',
    'contextMenu',
  ];

  const SCOPE_LABELS: Record<KeyScope, string> = {
    global: 'Global',
    fileTree: 'File tree',
    systemsView: 'Systems view',
    collections: 'Collections',
    searchInput: 'Search input',
    searchResults: 'Search results',
    filterPanel: 'Filters panel',
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

<Modal
  {visible}
  {onClose}
  title="Keyboard shortcuts"
  width="min(640px, 90vw)"
  height="min(640px, 80vh)"
  autofocus={false}
>
  <div class="help-body">
    {#each grouped as group (group.scope)}
      <section class="group">
        <h3 class="group-title section-title">{group.label}</h3>
        <dl class="bindings">
          {#each group.entries as entry (entry.id)}
            <dt class="chord">{chord(entry.id)}</dt>
            <dd class="label">{entry.label}</dd>
          {/each}
        </dl>
      </section>
    {/each}
  </div>
</Modal>

<style>
  .help-body {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding: 1rem;
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
  }

  .group {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }

  .group-title {
    margin: 0;
  }

  .bindings {
    margin: 0;
    display: grid;
    grid-template-columns: 9rem 1fr;
    column-gap: 1.25rem;
    row-gap: 0.3rem;
    font-size: 0.85rem;
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
</style>
