<script lang="ts">
  // Foresight, the turn tracker (docs/roadmap/2026-11-03-foresight-design.md).
  // A step sequencer: one step per row, the playhead is the turn, each loop
  // a round. The encounter is a note of the campaign open in Command; its
  // table is the tracker (encounter.ts), and every change is written to it
  // at once, a write at a time, the latest state winning. A change made to
  // the note elsewhere comes back through the vault watcher; when it lands
  // under a write of Foresight's, the note's version wins.
  //
  // Empty, Foresight is the bare instrument: the first row named in its
  // empty row makes `Encounter N` in the Encounters track. Clearing spends
  // the note, which stays in the campaign. The open encounter is kept per
  // campaign (`foresightOpen`), and Foresight follows the campaign open in
  // Command, as Augury's Tracks set does.
  //
  // The columns are the GM's, edited on the plate with the idioms of
  // Command's tracks: + names one in place, a double-click renames, a drag
  // moves, right-click has Rename and Remove. The last encounter's columns
  // are kept (`foresightColumns`) for the next one, and edited there while
  // Foresight is empty. A click on a cell opens it; a number cell takes −7
  // or +3 (encounter.ts enterCell). Rows drag to reorder, and the clicked
  // row takes the keys: ↓/J ↑/K, M, R, ⌘D.
  import { onDestroy, tick, type Snippet } from 'svelte';
  import { load } from '@tauri-apps/plugin-store';
  import { DIGIT_VIEWBOX, SEGMENTS, isLit, readoutCells } from '../augury/sevenSegment';
  import { commandApi, onVaultChange } from '../command/api';
  import CommandMenu from '../command/CommandMenu.svelte';
  import InlineName from '../command/InlineName.svelte';
  import { action, type OpenMenu } from '../command/menu';
  import { m } from '../paraglide/messages';
  import { confirmPrompt } from '../shell/confirmStore';
  import { focusPath } from '../shell/focus';
  import { hoist } from '../shell/hoist';
  import { eventMatchKey } from '../shell/keybindings';
  import { bindKeys } from '../shell/keys';
  import { appContext } from '../shell/shellState';
  import { parseRecord, parseStringArray } from '../shell/storeParsers';
  import { grab } from '../ui/grab';
  import { CARET_RIGHT } from '../ui/iconPaths';
  import RenameField from '../ui/RenameField.svelte';
  import {
    addColumn,
    addRow,
    duplicateRow,
    encounterApi,
    enterCell,
    isFigures,
    moveColumn,
    moveRow,
    removeColumn,
    removeRow,
    renameColumn,
    renameRow,
    setCell,
    step,
    toggleOut,
    type Encounter,
    type EncounterRow,
  } from './encounter';

  export let windowKey: Snippet | undefined = undefined;
  export let statusSlot: HTMLElement | null = null;

  type Table = Pick<Encounter, 'columns' | 'rows'>;

  // The campaign whose encounter shows; undefined until the first follows.
  let shown: string | null | undefined = undefined;
  let enc: Encounter | null = null;
  // Open encounters by campaign, and the last one's columns, as the
  // settings store keeps them.
  let opened: Record<string, string> = {};
  let carried: string[] | null = null;
  let selected: string | null = null;
  // The empty row's field, opened again after each name for the next.
  let naming = false;
  let named = 0;
  // What's open in place: a cell, a row's name, a column's name, a new
  // column's field.
  let editing: { row: string; col: number } | null = null;
  let renamingRow: string | null = null;
  let renamingColumn: number | null = null;
  let namingColumn = false;
  let menu: OpenMenu | null = null;
  // A row or a column carried by hand, and where it would land: before the
  // row or column at that index, the length for the end.
  let draggingRow: string | null = null;
  let rowDrop: number | null = null;
  let draggingColumn: number | null = null;
  let columnDrop: number | null = null;
  let rowEls: Record<string, HTMLElement> = {};
  // The first row is making the encounter; names given meanwhile wait.
  let creating = false;
  let waiting: string[] = [];
  // One write at a time: `dirty` while the state on screen isn't on disk
  // yet, `stale` when the note changed under a write and is read again.
  // `version` counts the states shown, so a read begun before one of them
  // is dropped.
  let writing = false;
  let dirty = false;
  let stale = false;
  let version = 0;
  let flushed: Promise<void> = Promise.resolve();
  let refreshTimer: ReturnType<typeof setTimeout> | undefined;

  /** The columns the very first encounter starts with. */
  const defaultColumns = () => [m.foresight_column_combatant(), m.foresight_column_hp(), m.foresight_column_remarks()];

  $: columns = enc?.columns.length ? enc.columns : (carried ?? defaultColumns());
  $: rows = enc?.rows ?? [];
  // What a column holds decides how it reads, never its name.
  $: figures = columns.map((_, c) => c > 0 && isFigures(rows, c));
  // The step number, the name (never squeezed past a short name), a cell
  // per column (figures narrow), a new column's field while it's named, the
  // M key's slot. Content never sizes a track: each row is a grid of its
  // own, and they must line up.
  $: grid = [
    '1.1rem',
    'minmax(4.5rem, 1.2fr)',
    ...columns.slice(1).map((_, i) => (figures[i + 1] ? '2.9rem' : 'minmax(0, 1fr)')),
    ...(namingColumn ? ['minmax(0, 1fr)'] : []),
    '18px',
  ].join(' ');
  $: cells = readoutCells(enc?.round ?? null, 1);
  $: turnRow = rows.find((r) => r.name === enc?.turn) ?? null;
  // The open encounter's columns are the next one's.
  $: if (enc && enc.columns.length && enc.columns.join('\n') !== carried?.join('\n')) void keepColumns(enc.columns);

  const ready = (async () => {
    try {
      const store = await load('settings.json');
      const saved = parseRecord(await store.get('foresightOpen')) ?? {};
      opened = Object.fromEntries(Object.entries(saved).filter(([, v]) => typeof v === 'string')) as Record<string, string>;
      const kept = parseStringArray(await store.get('foresightColumns'));
      if (kept?.length) carried = kept;
    } catch (e) {
      console.error('Failed to read the open encounters:', e);
    }
  })();

  async function save(key: 'foresightOpen' | 'foresightColumns', value: unknown) {
    try {
      const store = await load('settings.json');
      await store.set(key, value);
    } catch (e) {
      console.error(`Failed to save ${key}:`, e);
    }
  }

  function keepOpened(next: Record<string, string>) {
    opened = next;
    void save('foresightOpen', next);
  }

  function keepColumns(next: string[]) {
    carried = next;
    void save('foresightColumns', next);
  }

  function forget(campaign: string) {
    const { [campaign]: _gone, ...rest } = opened;
    keepOpened(rest);
  }

  // An encounter with no table yet takes the carried columns.
  function shape(got: Encounter): Encounter {
    return got.columns.length ? got : { ...got, columns };
  }

  function closeAll() {
    selected = null;
    naming = false;
    editing = null;
    renamingRow = null;
    renamingColumn = null;
    namingColumn = false;
    menu = null;
  }

  // Foresight follows Command's campaign.
  $: void follow($appContext.campaign ?? null);

  async function follow(campaign: string | null) {
    if (campaign === shown) return;
    shown = campaign;
    enc = null;
    closeAll();
    waiting = [];
    await ready;
    const path = campaign ? opened[campaign] : undefined;
    if (!campaign || !path) return;
    try {
      const got = await encounterApi.read(campaign, path);
      if (shown !== campaign) return;
      // Spent is cleared, whoever spent it.
      if (got.spent) forget(campaign);
      else enc = shape(got);
    } catch (e) {
      console.error('Failed to read the encounter:', e);
    }
  }

  /** Read the open encounter again after a change on disk. Foresight's own
   *  writes come back with the hash it holds, and change nothing. */
  async function refresh() {
    const campaign = shown;
    const path = enc?.path;
    const at = version;
    if (!campaign || !path) return;
    if (writing) {
      stale = true;
      return;
    }
    try {
      const got = await encounterApi.read(campaign, path);
      if (shown !== campaign || enc?.path !== path || writing || version !== at) return;
      if (got.spent) {
        enc = null;
        closeAll();
        forget(campaign);
      } else if (got.hash !== enc.hash) {
        enc = shape(got);
        if (selected && !enc.rows.some((r) => r.name === selected)) selected = null;
      }
    } catch (e) {
      // Moved, renamed, deleted, or no longer an encounter: Foresight is
      // empty, and finds it again if it comes back.
      console.error('Failed to read the encounter again:', e);
      if (shown === campaign && enc?.path === path && !writing) {
        enc = null;
        closeAll();
      }
    }
  }

  const unlistenVault = onVaultChange((event) => {
    if (!enc || (event.campaign !== null && (event.campaign !== shown || !event.paths.includes(enc.path)))) return;
    clearTimeout(refreshTimer);
    refreshTimer = setTimeout(() => void refresh(), 150);
  });

  /** Show `next` and write it. */
  function change(next: Encounter) {
    enc = next;
    version += 1;
    dirty = true;
    if (!writing) flushed = write();
  }

  async function write() {
    const campaign = shown;
    writing = true;
    try {
      while (dirty && enc && campaign && shown === campaign) {
        dirty = false;
        const sent = enc;
        const outcome = await encounterApi.save(campaign, sent);
        if (shown !== campaign || enc?.path !== sent.path) break;
        if (outcome.status === 'conflict') {
          stale = true;
          break;
        }
        enc = { ...enc, hash: outcome.hash };
        version += 1;
      }
    } catch (e) {
      console.error('Failed to save the encounter:', e);
      stale = true;
    } finally {
      writing = false;
    }
    // The note changed under the write, or the write failed: the note's
    // version replaces what wasn't written.
    if (stale) {
      stale = false;
      dirty = false;
      await refresh();
    }
  }

  /** A change to the columns: the open encounter's, or with none open the
   *  ones the next encounter takes. */
  function editColumns(edit: <T extends Table>(t: T) => T) {
    if (enc) change(edit(enc));
    else keepColumns(edit({ columns, rows: [] as EncounterRow[] }).columns);
  }

  // ---- turns and rows --------------------------------------------------------

  function pass(by: 1 | -1) {
    if (!enc) return;
    const next = step(enc, by);
    if (next.turn !== enc.turn || next.round !== enc.round) change({ ...enc, ...next });
  }

  function toggle(name: string) {
    if (enc) change(toggleOut(enc, name));
  }

  function duplicate(name: string) {
    if (!enc) return;
    const next = duplicateRow(enc, name);
    change(next);
    void reveal(next.rows[next.rows.findIndex((r) => r.name === name) + 1]?.name ?? name);
  }

  function remove(name: string) {
    if (!enc) return;
    change(removeRow(enc, name));
    if (selected === name) selected = null;
  }

  function commitRename(name: string, wanted: string) {
    renamingRow = null;
    if (!enc) return;
    const at = enc.rows.findIndex((r) => r.name === name);
    const next = renameRow(enc, name, wanted);
    change(next);
    if (selected === name) selected = next.rows[at]?.name ?? null;
  }

  function commitCell(name: string, col: number, before: string, typed: string) {
    editing = null;
    if (enc) change(setCell(enc, name, col, enterCell(before, typed)));
  }

  function clearCell(name: string, col: number) {
    editing = null;
    if (enc) change(setCell(enc, name, col, ''));
  }

  /** Select a row and bring it into view. */
  async function reveal(name: string) {
    selected = name;
    await tick();
    rowEls[name]?.scrollIntoView({ block: 'nearest' });
  }

  /** ↓/J and ↑/K: the next or previous row, from the turn's when none is
   *  selected. */
  function moveSelection(by: 1 | -1): boolean {
    if (!rows.length) return false;
    const at = rows.findIndex((r) => r.name === selected);
    const from = at >= 0 ? at + by : Math.max(0, rows.findIndex((r) => r.name === enc?.turn));
    void reveal(rows[Math.min(rows.length - 1, Math.max(0, from))].name);
    return true;
  }

  async function addNamed(name: string) {
    const campaign = shown;
    if (!campaign) return;
    if (enc) {
      change(addRow(enc, name));
      return;
    }
    if (creating) {
      waiting = [...waiting, name];
      return;
    }
    creating = true;
    try {
      const made = await encounterApi.create(campaign, columns, [{ name, link: null, out: false, cells: [] }]);
      if (shown !== campaign) return;
      keepOpened({ ...opened, [campaign]: made.path });
      enc = shape(made);
      if (waiting.length) change(waiting.reduce(addRow, enc));
    } catch (e) {
      console.error('Failed to start an encounter:', e);
    } finally {
      creating = false;
      waiting = [];
    }
  }

  /** Clearing is spending: the note is spent and stays in the campaign. */
  async function clear() {
    const campaign = shown;
    const path = enc?.path;
    if (!campaign || !path) return;
    await flushed;
    try {
      await commandApi.setSpent(campaign, path, true);
      if (shown === campaign && enc?.path === path) {
        enc = null;
        closeAll();
      }
      forget(campaign);
    } catch (e) {
      console.error('Failed to clear the encounter:', e);
    }
  }

  function rowMenu(e: MouseEvent, row: EncounterRow) {
    selected = row.name;
    menu = {
      x: e.clientX,
      y: e.clientY,
      items: [
        action(m.foresight_rename(), () => (renamingRow = row.name)),
        action(m.foresight_duplicate(), () => duplicate(row.name)),
        action(m.foresight_remove(), () => remove(row.name), true),
      ],
    };
  }

  // ---- columns ---------------------------------------------------------------

  function columnMenu(e: MouseEvent, c: number) {
    menu = {
      x: e.clientX,
      y: e.clientY,
      items: [
        action(m.foresight_rename(), () => (renamingColumn = c)),
        ...(c > 0 ? [action(m.foresight_remove(), () => void dropColumn(c), true)] : []),
      ],
    };
  }

  /** A column holding cells goes only once the GM says so. */
  async function dropColumn(c: number) {
    if (rows.some((r) => (r.cells[c - 1] ?? '').trim() !== '')) {
      const confirmed = await confirmPrompt.request({
        title: m.foresight_remove_column_title({ column: columns[c] }),
        message: m.foresight_remove_column_message(),
        confirmLabel: m.foresight_remove(),
        danger: true,
      });
      if (!confirmed) return;
    }
    editColumns((t) => removeColumn(t, c));
  }

  // ---- carrying by hand ------------------------------------------------------

  function startRowDrag(e: DragEvent, name: string) {
    draggingRow = name;
    if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move';
  }

  /** A row over row `i` (the empty row is the rows' length) points between
   *  rows, by which half of the row the pointer is in. */
  function overRow(e: DragEvent, i: number) {
    if (draggingRow === null) return;
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
    const box = (e.currentTarget as HTMLElement).getBoundingClientRect();
    rowDrop = i < rows.length && e.clientY >= box.top + box.height / 2 ? i + 1 : i;
  }

  function dropRow(e: DragEvent) {
    e.preventDefault();
    if (enc && draggingRow !== null && rowDrop !== null) change(moveRow(enc, draggingRow, rowDrop));
    endDrag();
  }

  function startColumnDrag(e: DragEvent, c: number) {
    draggingColumn = c;
    if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move';
  }

  /** A column over column `c`'s name points between columns; over the
   *  names' column, it lands first after it. */
  function overColumn(e: DragEvent, c: number) {
    if (draggingColumn === null) return;
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
    const box = (e.currentTarget as HTMLElement).getBoundingClientRect();
    columnDrop = c === 0 ? 1 : e.clientX >= box.left + box.width / 2 ? c + 1 : c;
  }

  function dropColumnAt(e: DragEvent) {
    e.preventDefault();
    if (draggingColumn !== null && columnDrop !== null) {
      const [from, to] = [draggingColumn, columnDrop];
      editColumns((t) => moveColumn(t, from, to));
    }
    endDrag();
  }

  // A drag delivers no pointerleave: unlatch on its end, dropped or not.
  function endDrag() {
    draggingRow = null;
    rowDrop = null;
    draggingColumn = null;
    columnDrop = null;
  }

  function leave(e: DragEvent) {
    if (!(e.currentTarget as HTMLElement).contains(e.relatedTarget as Node | null)) {
      rowDrop = null;
      columnDrop = null;
    }
  }

  // ---- keys ------------------------------------------------------------------

  const unbindKeys = bindKeys(
    (event, ctx) => {
      if (event.defaultPrevented || event.isComposing || ctx.typing || ctx.menu || event.altKey) return false;
      if (eventMatchKey(event) === 'meta+d') {
        if (!selected || !enc) return false;
        duplicate(selected);
        return true;
      }
      if (event.metaKey || event.ctrlKey) return false;
      if (event.key === ' ' && event.shiftKey) {
        pass(1);
        return !!enc;
      }
      if (event.shiftKey) return false;
      const key = event.key.length === 1 ? event.key.toLowerCase() : event.key;
      if (key === 'ArrowDown' || key === 'j') return moveSelection(1);
      if (key === 'ArrowUp' || key === 'k') return moveSelection(-1);
      if (!selected || !enc) return false;
      if (key === 'm') {
        toggle(selected);
        return true;
      }
      if (key === 'r') {
        renamingRow = selected;
        return true;
      }
      if (key === 'Escape') {
        selected = null;
        return true;
      }
      return false;
    },
    { tool: 'foresight' },
  );

  onDestroy(() => {
    unbindKeys();
    clearTimeout(refreshTimer);
    void unlistenVault.then((stop) => stop());
  });
</script>

<section class="foresight" class:dormant={$focusPath.tool !== 'foresight'} style:--grid={grid}>
  <header class="bar">
    <span class="title readout-label" title={enc?.name}>{enc?.name ?? ''}</span>
    <div class="well" role="group" aria-label={m.foresight_turn_label()}>
      <button
        type="button"
        class="key"
        disabled={!enc}
        title={m.foresight_turn_previous()}
        aria-label={m.foresight_turn_previous()}
        on:click={() => pass(-1)}
      >
        <svg class="back" viewBox="96 64 512 512" fill="currentColor" aria-hidden="true"><path d={CARET_RIGHT} /></svg>
      </button>
      <!-- Augury's readout lamps, small: the round, as a sequencer counts
           its bars. -->
      <span class="round" title={enc ? m.foresight_round_title({ round: enc.round }) : undefined}>
        {#each cells as char, i (i)}
          <svg class="digit" viewBox={DIGIT_VIEWBOX} aria-hidden="true">
            {#each SEGMENTS as [segment, points] (segment)}
              <polygon {points} class:lit={isLit(char, segment)} />
            {/each}
          </svg>
        {/each}
      </span>
      <button
        type="button"
        class="key"
        disabled={!enc}
        title={m.foresight_turn_next()}
        aria-label={m.foresight_turn_next()}
        on:click={() => pass(1)}
      >
        <svg viewBox="96 64 512 512" fill="currentColor" aria-hidden="true"><path d={CARET_RIGHT} /></svg>
      </button>
      <span class="rule" aria-hidden="true"></span>
      <!-- Command's spend key: clearing spends the encounter's note. -->
      <button
        type="button"
        class="key"
        disabled={!enc}
        title={enc ? m.foresight_clear_title({ name: enc.name }) : m.foresight_clear_label()}
        aria-label={m.foresight_clear_label()}
        on:click={() => void clear()}
      >
        <!-- Font Awesome "box-archive" icon (src/lib/ui/icons/box-archive-solid-full.svg),
             its viewBox cropped to the glyph. -->
        <svg class="spend" viewBox="64 96 512 448" fill="currentColor" aria-hidden="true">
          <path
            d="M64 128C64 110.3 78.3 96 96 96L544 96C561.7 96 576 110.3 576 128L576 160C576 177.7 561.7 192 544 192L96 192C78.3 192 64 177.7 64 160L64 128zM96 240L544 240L544 480C544 515.3 515.3 544 480 544L160 544C124.7 544 96 515.3 96 480L96 240zM248 304C234.7 304 224 314.7 224 328C224 341.3 234.7 352 248 352L392 352C405.3 352 416 341.3 416 328C416 314.7 405.3 304 392 304L248 304z"
          />
        </svg>
      </button>
    </div>
    {@render windowKey?.()}
  </header>

  <!-- The plate names the columns, the rows' names first; Command's track
       plates are edited the same way. -->
  <div class="plate nameplate" role="presentation" on:dragleave={leave}>
    <span aria-hidden="true"></span>
    {#each columns as column, c (c)}
      {#if renamingColumn === c}
        <span class="col-field" class:figures={figures[c]}>
          <RenameField
            value={column}
            label={m.foresight_column_rename_label({ column })}
            onCommit={(name) => {
              renamingColumn = null;
              editColumns((t) => renameColumn(t, c, name));
            }}
            onCancel={() => (renamingColumn = null)}
          />
        </span>
      {:else}
        <span
          class="ledger-label col"
          class:cell-head={c > 0}
          class:figures={figures[c]}
          class:dragging={draggingColumn === c}
          class:drop-before={c > 0 && columnDrop === c}
          class:drop-after={c === columns.length - 1 && columnDrop === columns.length}
          role="columnheader"
          tabindex="-1"
          title={column}
          use:grab={c > 0}
          on:dragstart={(e) => startColumnDrag(e, c)}
          on:dragend={endDrag}
          on:dragover={(e) => overColumn(e, c)}
          on:drop={dropColumnAt}
          on:dblclick={() => (renamingColumn = c)}
          on:contextmenu|preventDefault={(e) => columnMenu(e, c)}>{column}</span
        >
      {/if}
    {/each}
    {#if namingColumn}
      <span class="col-field">
        <InlineName
          bare
          placeholder={m.foresight_column_placeholder()}
          label={m.foresight_column_new_label()}
          onCommit={(name) => {
            namingColumn = false;
            editColumns((t) => addColumn(t, name));
          }}
          onCancel={() => (namingColumn = false)}
        />
      </span>
    {/if}
    <button
      type="button"
      class="add"
      class:hidden={namingColumn}
      title={m.foresight_column_add_title()}
      aria-label={m.foresight_column_add_title()}
      on:click={() => (namingColumn = true)}>+</button
    >
  </div>

  <ol class="rows" aria-label={m.foresight_rows_label()} on:dragleave={leave}>
    {#each rows as row, i (row.name)}
      {@const playing = row.name === enc?.turn}
      {@const open = renamingRow === row.name || editing?.row === row.name}
      <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_noninteractive_element_interactions -->
      <li
        class="row"
        class:playing
        class:out={row.out}
        class:selected={row.name === selected}
        class:dragging={draggingRow === row.name}
        class:drop-before={rowDrop === i}
        aria-current={playing ? 'step' : undefined}
        bind:this={rowEls[row.name]}
        use:grab={!open}
        on:dragstart={(e) => startRowDrag(e, row.name)}
        on:dragend={endDrag}
        on:dragover={(e) => overRow(e, i)}
        on:drop={dropRow}
        on:click={() => (selected = row.name)}
        on:contextmenu|preventDefault={(e) => rowMenu(e, row)}
      >
        <span class="num">{String(i + 1).padStart(2, '0')}</span>
        {#if renamingRow === row.name}
          <span class="name editing">
            <RenameField
              value={row.name}
              label={m.foresight_row_rename_label({ name: row.name })}
              onCommit={(name) => commitRename(row.name, name)}
              onCancel={() => (renamingRow = null)}
            />
          </span>
        {:else}
          <span class="name" title={row.name}>{row.name}</span>
        {/if}
        {#each row.cells as cell, c (c)}
          {#if editing?.row === row.name && editing.col === c + 1}
            <span class="cell editing" class:figures={figures[c + 1]}>
              <RenameField
                value={cell}
                label={m.foresight_cell_label({ name: row.name, column: columns[c + 1] ?? '' })}
                onCommit={(typed) => commitCell(row.name, c + 1, cell, typed)}
                onCancel={() => (editing = null)}
                onEmpty={() => clearCell(row.name, c + 1)}
              />
            </span>
          {:else}
            <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
            <span
              class="cell"
              class:figures={figures[c + 1]}
              title={cell || undefined}
              on:click={() => {
                selected = row.name;
                editing = { row: row.name, col: c + 1 };
              }}>{cell}</span
            >
          {/if}
        {/each}
        <!-- Legend Lore's mute: out of the fight, the GM's call. -->
        <button
          type="button"
          class="sm-btn"
          class:mute-on={row.out}
          aria-pressed={row.out}
          aria-label={m.foresight_out_label()}
          title={row.out ? m.foresight_in_title({ name: row.name }) : m.foresight_out_title({ name: row.name })}
          on:click|stopPropagation={() => toggle(row.name)}>M</button
        >
      </li>
    {/each}
    <!-- The empty row: a new row is named in place, the next one after it. -->
    <li
      class="row empty"
      class:naming
      class:drop-before={rowDrop === rows.length}
      on:dragover={(e) => overRow(e, rows.length)}
      on:drop={dropRow}
    >
      <span class="num" aria-hidden="true"></span>
      {#if naming}
        {#key named}
          <span class="field">
            <InlineName
              bare
              placeholder={m.foresight_name_placeholder()}
              label={m.foresight_name_label()}
              onCommit={(name) => {
                named += 1;
                void addNamed(name);
              }}
              onCancel={() => (naming = false)}
            />
          </span>
        {/key}
      {:else}
        <button
          type="button"
          class="ghost"
          disabled={!shown}
          title={shown ? m.foresight_new_row_title() : m.foresight_no_campaign()}
          on:click={() => (naming = true)}
        >
          {m.foresight_name_placeholder()}
        </button>
      {/if}
    </li>
  </ol>
</section>

{#if menu}
  <CommandMenu x={menu.x} y={menu.y} items={menu.items} onClose={() => (menu = null)} />
{/if}

{#if statusSlot && enc && turnRow}
  <div class="status-section" use:hoist={statusSlot}>
    <span class="rule" aria-hidden="true"></span>
    <span class="where" title={m.foresight_status_title({ round: enc.round, name: turnRow.name })}>
      <span>{m.foresight_status_round({ round: enc.round })}</span>
      <span class="sep" aria-hidden="true">·</span>
      <span class="who">{turnRow.name}</span>
    </span>
  </div>
{/if}

<style>
  .foresight.dormant {
    --ring-focus: var(--ring-dormant);
  }

  .foresight {
    height: 100%;
    display: flex;
    flex-direction: column;
    background: var(--bg-app);
    color: var(--text-primary);
  }

  /* Augury's bar: the same height, inset and rule. */
  .bar {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    gap: 0.4rem;
    height: var(--header-height);
    padding: 1px 0.5rem 0;
    background: var(--bg-header);
    border-bottom: 1px solid var(--border-subtle);
  }

  .title {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--text-accent);
  }

  /* Augury's set strip (AuguryPanel .well, .key). */
  .well {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    gap: 2px;
    padding: 2px;
    background: var(--bg-app);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-well);
  }

  .key {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 26px;
    height: 22px;
    padding: 0;
    background: transparent;
    border: none;
    border-radius: var(--radius-md);
    color: var(--text-tertiary);
    cursor: pointer;
  }

  .key:hover:not(:disabled) {
    color: var(--text-primary);
  }

  .key:active:not(:disabled) {
    transform: scale(0.97);
  }

  .key:disabled {
    cursor: default;
  }

  .key svg {
    width: 12px;
    height: 12px;
  }

  .key svg.spend {
    width: 11px;
    height: 11px;
  }

  .back {
    transform: scaleX(-1);
  }

  .well .rule {
    width: 1px;
    height: 14px;
    margin: 0 1px;
    background: var(--border-subtle);
  }

  /* Augury's readout lamps, small. No ghost digit ahead of the round:
     beside the name, an unlit 8 reads as part of it. */
  .round {
    --ghost: color-mix(in srgb, var(--text-accent) 12%, transparent);
    flex-shrink: 0;
    display: flex;
    justify-content: center;
    gap: 2px;
    min-width: 1.1rem;
    padding: 0 0.15rem;
  }

  .digit {
    width: 0.62rem;
    height: 1.12rem;
  }

  polygon {
    fill: var(--ghost);
  }

  polygon.lit {
    fill: var(--text-accent);
  }

  /* The plate and every row share one set of columns. */
  .plate,
  .row {
    display: grid;
    grid-template-columns: var(--grid);
    align-items: center;
    column-gap: 0.35rem;
    min-height: 1.65rem;
    padding: 0 0.5rem 0 calc(0.5rem - 2px);
    border-left: 2px solid transparent;
  }

  .plate {
    flex-shrink: 0;
    border-bottom: 1px solid var(--border-subtle);
  }

  .plate .col {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    cursor: default;
  }

  .cell-head,
  .cell {
    padding-left: 0.35rem;
  }

  /* Figures: right-aligned, the header with them. */
  .col.figures,
  .cell.figures {
    padding-left: 0;
    text-align: right;
  }

  .col-field {
    min-width: 0;
    font-size: 0.8rem;
  }

  .col-field.figures :global(.rename-field) {
    text-align: right;
  }

  .col-field :global(.inline-name::placeholder) {
    font-style: italic;
  }

  .add {
    grid-column: -2;
    width: 18px;
    height: 18px;
    padding: 0;
    background: none;
    border: none;
    color: var(--text-tertiary);
    font-family: var(--font-readout);
    font-size: 0.8rem;
    cursor: pointer;
  }

  .add:hover {
    color: var(--text-primary);
  }

  .add.hidden {
    visibility: hidden;
  }

  /* A column carried by hand: an accent rule marks where it would land. */
  .col.dragging {
    opacity: 0.4;
  }

  .col.drop-before {
    box-shadow: inset 2px 0 0 var(--text-accent);
  }

  .col.drop-after {
    box-shadow: inset -2px 0 0 var(--text-accent);
  }

  .rows {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  /* Command's ledger lines: a hairline at each row's foot. */
  .row {
    box-shadow: inset 0 -1px 0 var(--border-subtle);
    cursor: default;
  }

  .row:hover:not(.empty) {
    background: var(--bg-focused);
  }

  .row.selected {
    box-shadow: var(--ring-focus);
  }

  /* Legend Lore's playing highlight (CollectionsPanel .row-container.playing),
     as Command's live beat wears it: whose turn it is. */
  .row.playing,
  .row.playing:hover {
    background: color-mix(in srgb, var(--text-accent) 8%, transparent);
    border-left-color: var(--text-active);
  }

  /* A row carried by hand, as Command's beats: it fades, and an accent rule
     marks where it would land. */
  .row.dragging {
    opacity: 0.4;
  }

  .row.drop-before {
    box-shadow: inset 0 2px 0 var(--text-accent);
  }

  .num {
    font-family: var(--font-readout);
    font-size: 0.65rem;
    font-variant-numeric: tabular-nums;
    color: var(--text-tertiary);
  }

  .name,
  .cell {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .name {
    font-size: 0.9rem;
  }

  /* The whole height of the row takes the click that opens a cell. */
  .cell {
    align-self: stretch;
    line-height: 1.65rem;
    font-size: 0.8rem;
    color: var(--text-secondary);
    cursor: text;
  }

  /* Figures: tabular readout digits in parchment, as data. */
  .cell.figures {
    font-family: var(--font-readout);
    font-size: 0.7rem;
    font-variant-numeric: tabular-nums;
    color: var(--text-accent);
  }

  .cell.figures :global(.rename-field) {
    text-align: right;
  }

  /* A field open in a cell or a name: room for its ring. */
  .cell.editing,
  .name.editing {
    display: flex;
    align-items: center;
    overflow: visible;
  }

  /* Out of the fight: down the ramp, not faded; the mute key stays lit. */
  .row.out .name,
  .row.out .cell,
  .row.out .num {
    color: var(--text-tertiary);
  }

  /* The M key shows while lit, on the turn's row, the selected one and
     under the pointer, as Command's spend key shows on a row; its slot is
     always kept, the last. */
  .row .sm-btn {
    grid-column: -2;
  }

  .row .sm-btn:not(.mute-on) {
    visibility: hidden;
  }

  .row:hover .sm-btn,
  .row.playing .sm-btn,
  .row.selected .sm-btn {
    visibility: visible;
  }

  /* The empty row: the next line of the ledger, naming in place. */
  .ghost,
  .field {
    grid-column: 2 / -1;
    min-width: 0;
  }

  .ghost {
    padding: 0;
    background: none;
    border: none;
    text-align: left;
    font-family: var(--font-body);
    font-size: 0.9rem;
    font-style: italic;
    color: var(--text-tertiary);
    cursor: text;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .ghost:disabled {
    cursor: default;
  }

  .row.empty:hover .ghost:not(:disabled) {
    color: var(--text-secondary);
  }

  .field {
    font-size: 0.9rem;
  }

  .field :global(.inline-name::placeholder) {
    font-style: italic;
  }

  /* Status bar section (Command's SessionStatus). */
  .where {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
  }

  .sep {
    color: var(--text-tertiary);
  }

  .who {
    max-width: 24ch;
    overflow: hidden;
    text-overflow: ellipsis;
    color: var(--text-accent);
  }
</style>
