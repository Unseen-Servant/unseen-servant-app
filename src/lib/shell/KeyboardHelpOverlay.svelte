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

  // One cap per alternative (`↓ / J` is two keys, not one), with the peek
  // line's leading "hold" kept as a word rather than capped.
  function caps(id: string): { prefix: string; keys: string[] } {
    const c = chord(id);
    const prefix = c.startsWith('hold ') ? 'hold' : '';
    return { prefix, keys: (prefix ? c.slice(5) : c).split(' / ') };
  }
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
              {@const c = caps(entry.id)}
              <dt class="keys">
                <!-- Each cap carries its trailing slash (and the first, the
                     "hold"), so a wrapped chord breaks after a slash. -->
                {#each c.keys as key, i}
                  <span class="alt">
                    {#if i === 0 && c.prefix}<span class="word">{c.prefix}</span>{/if}
                    <span class="keycap" class:switch-key={entry.switch}>{key}</span>
                    {#if i < c.keys.length - 1}<span class="word">/</span>{/if}
                  </span>
                {/each}
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
     the two-column layout costs no wrapper. The key column is one fixed width
     across every group, so each section's labels start at the same indent;
     sized for the common chords, with the rare long one (`hold S / M / P / B`,
     `Shift+F10 / Menu`) wrapping onto a second line inside its cell rather
     than spilling out of it, as the old unwrapped 9rem column did. */
  .bindings {
    margin: 0;
    display: grid;
    grid-template-columns: 5.5rem 1fr;
    column-gap: 0.65rem;
    row-gap: 0.1rem;
    align-items: center;
  }
  .keys {
    margin: 0;
    display: flex;
    flex-wrap: wrap;
    justify-content: flex-end;
    gap: 2px 3px;
    align-items: center;
  }
  .alt {
    display: inline-flex;
    gap: 3px;
    align-items: center;
  }
  .word {
    font-size: 0.76rem;
    color: var(--text-tertiary);
    white-space: nowrap;
  }
  .desc {
    margin: 0;
    font-size: 0.82rem;
    color: var(--text-secondary);
    line-height: 1.3;
  }

  /* Every key reads as a cap; a single letter stays square, a chord grows
     wider. The purple edge marks keys that throw a switch in the window —
     the ones that light purple when engaged. */
  .keycap {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 17px;
    height: 17px;
    padding: 0 4px;
    box-sizing: border-box;
    white-space: nowrap;
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
