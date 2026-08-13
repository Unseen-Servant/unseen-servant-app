<script lang="ts">
  import Modal from './Modal.svelte';
  import { KEYBINDINGS, chord, isBareKeyChord, type KeyScope } from './keybindings';

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
  size="lg"
  height="min(640px, 80vh)"
  autofocus={false}
  escapeWord="close"
>
  <div class="legend-body">
    <div class="legend-cols">
      {#each grouped as group (group.scope)}
        <section class="lgroup">
          <h3 class="ledger-label">{group.label}</h3>
          <dl class="bindings">
            {#each group.entries as entry (entry.id)}
              <dt class="keys">
                {#if isBareKeyChord(entry.id)}
                  <span class="keycap" class:switch-key={entry.switch}>{chord(entry.id)}</span>
                {:else}
                  <span class="mono">{chord(entry.id)}</span>
                {/if}
              </dt>
              <dd class="desc">{entry.label}</dd>
            {/each}
          </dl>
        </section>
      {/each}
    </div>
  </div>
</Modal>

<style>
  /* The scroller and the columns are deliberately two elements. A multicol box
     with a *definite* block size does not push its overflow downward — it
     spills into extra columns to the right (CSS Multicol §7.2 "overflow
     columns"), and since `overflow-y: auto` makes overflow-x compute to `auto`,
     putting column-count on the flex-sized scroller itself would turn a tall
     sheet into a sideways one. The inner box has auto height, so the two
     columns balance to the content and the scroller does its usual job. */
  .legend-body {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding: var(--modal-pad);
  }
  .legend-cols {
    column-count: 2;
    column-gap: 1.5rem;
    column-rule: 1px solid var(--border-subtle);
  }

  /* Scopes are independent blocks, so multi-column does the whole job — the
     groups flow and stay intact, halving a sheet that ran five screens. */
  .lgroup {
    break-inside: avoid;
    margin: 0 0 1rem;
  }
  /* Still an <h3>: the sheet carried a heading per scope before this redesign,
     and dropping to the nameplate voice is a change of dress, not of outline. */
  .lgroup > .ledger-label {
    margin: 0 0 0.4rem;
  }

  /* The <dl> *is* the grid: a shortcut sheet is the one screen whose whole job
     is conveying term/definition pairs, so the pairing stays programmatic and
     the two-column layout costs no wrapper. `auto` rather than the old fixed
     9rem, right-aligned against a shared gap: a fixed column sized itself for
     the longest chord in the whole sheet and floated every short one away from
     its label — and anything longer than it (`hold S / M / P / B`,
     `Shift+F10 / Menu`) spilled out of its cell. `auto` is per-group, so it
     cannot overflow and only the group holding a long chord pays for it. */
  .bindings {
    margin: 0;
    display: grid;
    grid-template-columns: auto 1fr;
    column-gap: 0.65rem;
    row-gap: 0.1rem;
    align-items: center;
  }
  .keys {
    margin: 0;
    display: flex;
    justify-content: flex-end;
    gap: 3px;
    align-items: center;
  }
  .mono {
    font-family: var(--font-mono);
    font-size: 0.76rem;
    color: var(--text-primary);
    white-space: nowrap;
  }
  .desc {
    margin: 0;
    font-size: 0.82rem;
    color: var(--text-secondary);
    line-height: 1.3;
  }

  /* A cap means "there is a square in the window for this key". The purple
     edge marks the ones that light purple when engaged. */
  .keycap {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 17px;
    height: 17px;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    background: var(--bg-app);
    font-family: var(--font-body);
    font-size: 0.62rem;
    font-weight: 700;
    color: var(--text-primary);
    flex-shrink: 0;
  }
  .keycap.switch-key {
    border-color: color-mix(in srgb, var(--text-active) 40%, transparent);
    color: var(--text-active);
  }
</style>
