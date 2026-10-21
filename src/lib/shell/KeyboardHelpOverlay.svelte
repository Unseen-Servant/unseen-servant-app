<script lang="ts">
  import Modal from './Modal.svelte';
  import { focusPath } from './focus';
  import {
    KEYBINDINGS,
    chord,
    liveScopes,
    type KeybindingEntry,
    type KeyScope,
  } from './keybindings';

  export let visible = false;
  export let onClose: () => void;

  // The sheet is laid out by place, not by the dispatcher's scopes: the
  // window and the transport, the search bar, then the lists — what every
  // list answers, what Legend Lore's lists share, and only then each view
  // with what is its own — and the menus last. The order is fixed so the
  // sheet reads the same every time. `modal` is omitted: those chords live
  // inside dialogs and aren't useful in a global cheat sheet.
  type SectionKey = 'window' | 'transport' | 'anyList' | 'llLists' | 'board' | KeyScope;
  const SECTIONS: { key: SectionKey; label: string }[] = [
    { key: 'window', label: 'Window' },
    { key: 'transport', label: 'Transport, from anywhere' },
    { key: 'searchInput', label: 'Search bar' },
    { key: 'anyList', label: 'Any list' },
    { key: 'llLists', label: 'Legend Lore lists' },
    { key: 'fileTree', label: 'File tree' },
    { key: 'systemsView', label: 'Systems view' },
    { key: 'collections', label: 'Collections' },
    { key: 'filterPanel', label: 'Filters' },
    { key: 'searchResults', label: 'Search results' },
    { key: 'command', label: 'Command' },
    { key: 'commandPrep', label: 'Prep' },
    { key: 'commandPlay', label: 'Play' },
    { key: 'board', label: 'Board' },
    { key: 'contextMenu', label: 'Menus' },
  ];

  // Legend Lore's transport works from anywhere, so it is registered
  // global; on the sheet it is its own block, apart from the window's keys.
  const TRANSPORT = new Set([
    'collections.slot', 'collections.slotMix', 'collections.new',
    'sync.run', 'sync.commit', 'search.focus', 'filter.toggle',
    'filter.toggleHidden', 'library.reveal', 'scope.bypass', 'scope.peek',
  ]);

  const LISTS = new Set<KeyScope>([
    'fileTree', 'systemsView', 'collections', 'filterPanel', 'searchResults',
    'commandPrep', 'commandPlay', 'contextMenu',
  ]);
  const COMMAND_LISTS = new Set<KeyScope>(['commandPrep', 'commandPlay']);

  // A chord that reads the same in two lists is one row, filed under the
  // lists it spans: "Any list" when Command's are among them, "Legend Lore
  // lists" otherwise. The merge is by chord and label, so a list that words
  // a key differently keeps its own row — the registry's wording is what
  // decides whether a key is shared, and the sheet shows that decision.
  interface Row {
    entry: KeybindingEntry;
    scopes: KeyScope[];
  }
  const rows: Row[] = [];
  const merged = new Map<string, Row>();
  for (const entry of KEYBINDINGS) {
    if (!LISTS.has(entry.scope)) {
      rows.push({ entry, scopes: [entry.scope] });
      continue;
    }
    const key = `${entry.keys.mac}|${entry.keys.other}|${entry.label}`;
    const row = merged.get(key);
    if (row) {
      row.scopes.push(entry.scope);
    } else {
      const fresh = { entry, scopes: [entry.scope] };
      merged.set(key, fresh);
      rows.push(fresh);
    }
  }

  function sectionOf({ entry, scopes }: Row): SectionKey | null {
    if (entry.scope === 'modal') return null;
    if (entry.scope === 'global') return TRANSPORT.has(entry.id) ? 'transport' : 'window';
    if (entry.scope === 'tool') return 'window';
    if (entry.id.startsWith('command.board')) return 'board';
    if (scopes.length > 1) return scopes.some(s => COMMAND_LISTS.has(s)) ? 'anyList' : 'llLists';
    return entry.scope;
  }

  const grouped = SECTIONS
    .map(section => ({ ...section, rows: rows.filter(r => sectionOf(r) === section.key) }))
    .filter(section => section.rows.length > 0);

  // The rows the keyboard can reach from where it is (focus.ts) keep their
  // rank; the others step down the text ramp, in their usual place, so the
  // sheet says which part is live. A merged row is live from any list it
  // spans; a section's heading steps down only when every row has.
  $: live = liveScopes($focusPath);
  $: isLive = (row: Row) => row.scopes.some(s => live.has(s));

  // One cap per alternative (`↓ / J` is two keys, not one), with the peek
  // line's leading "hold" kept as a word rather than capped; its `S/M/P/B`
  // is one cap, any of four keys, so the row stays one line.
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
      {#each grouped as section (section.key)}
        <section class="lgroup" class:away={!section.rows.some(isLive)}>
          <h3 class="ledger-label">{section.label}</h3>
          <dl class="bindings">
            {#each section.rows as row (row.entry.id)}
              {@const c = caps(row.entry.id)}
              {@const away = !isLive(row)}
              <dt class="keys" class:away>
                <!-- Each cap carries its trailing slash (and the first, the
                     "hold"), so a wrapped chord breaks after a slash. -->
                {#each c.keys as key, i}
                  <span class="alt">
                    {#if i === 0 && c.prefix}<span class="word">{c.prefix}</span>{/if}
                    <span class="keycap" class:switch-key={row.entry.switch}>{key}</span>
                    {#if i < c.keys.length - 1}<span class="word">/</span>{/if}
                  </span>
                {/each}
              </dt>
              <dd class="desc" class:away>{row.entry.label}</dd>
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

  /* Sections are independent blocks, so multi-column does the whole job — the
     groups flow and stay intact. The gap below a group is padding, not margin:
     WebKit carries a trailing margin across a column break, so the group that
     ended column one pushed the top of column two down by exactly that much.
     Padding sits inside the unbreakable box and stays with it. */
  .lgroup {
    break-inside: avoid;
    margin: 0;
    padding-bottom: 1rem;
  }
  /* Still an <h3>: the sheet carried a heading per scope before this redesign,
     and dropping to the nameplate voice is a change of dress, not of outline. */
  .lgroup > .ledger-label {
    margin: 0 0 0.4rem;
  }
  /* A row the keyboard can't reach from where it is: one step down the
     ramp, label and caps alike, never faded. The heading follows when the
     whole section is out of reach. */
  .lgroup.away > .ledger-label,
  .desc.away {
    color: var(--text-tertiary);
  }
  .keys.away .keycap {
    color: var(--text-secondary);
  }
  .keys.away .keycap.switch-key {
    color: var(--text-secondary);
    border-color: color-mix(in srgb, var(--text-active) 20%, transparent);
  }

  /* The <dl> *is* the grid: a shortcut sheet is the one screen whose whole job
     is conveying term/definition pairs, so the pairing stays programmatic and
     the two-column layout costs no wrapper. The label leads and the chord
     sits at the row's end, as a menu lays its accelerators out — you look
     for what you want to do, then read the key — so the <dt> is placed in
     the second column and the <dd> in the first. Dense packing is what puts
     a term and its definition on the same row: sparse auto-placement would
     drop the <dd> a row down, since its column is left of the cursor. The
     key column is fit-content: sized per section to its widest chord, up
     to a cap that keeps a long chord from squeezing every label beside it
     (minmax would take the cap outright whenever there is room). */
  .bindings {
    margin: 0;
    display: grid;
    grid-template-columns: 1fr fit-content(6rem);
    grid-auto-flow: dense;
    column-gap: 0.65rem;
    row-gap: 0.1rem;
    align-items: center;
  }
  .keys {
    grid-column: 2;
    margin: 0;
    display: flex;
    flex-wrap: wrap;
    justify-content: flex-end;
    gap: 2px 3px;
    align-items: center;
  }
  .desc {
    grid-column: 1;
    margin: 0;
    font-size: 0.82rem;
    color: var(--text-secondary);
    line-height: 1.3;
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
