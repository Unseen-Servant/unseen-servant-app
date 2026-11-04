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
  import { onDestroy, type Snippet } from 'svelte';
  import { load } from '@tauri-apps/plugin-store';
  import { DIGIT_VIEWBOX, SEGMENTS, isLit, readoutCells } from '../augury/sevenSegment';
  import { commandApi, onVaultChange } from '../command/api';
  import InlineName from '../command/InlineName.svelte';
  import { m } from '../paraglide/messages';
  import { focusPath } from '../shell/focus';
  import { hoist } from '../shell/hoist';
  import { bindKeys } from '../shell/keys';
  import { appContext } from '../shell/shellState';
  import { parseRecord } from '../shell/storeParsers';
  import { CARET_RIGHT } from '../ui/iconPaths';
  import { addRow, encounterApi, step, toggleOut, type Encounter } from './encounter';

  export let windowKey: Snippet | undefined = undefined;
  export let statusSlot: HTMLElement | null = null;

  // The campaign whose encounter shows; undefined until the first follows.
  let shown: string | null | undefined = undefined;
  let enc: Encounter | null = null;
  // Open encounters by campaign, as the settings store keeps them.
  let opened: Record<string, string> = {};
  let selected: string | null = null;
  // The empty row's field, opened again after each name for the next.
  let naming = false;
  let named = 0;
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

  /** The columns a new encounter starts with. */
  const defaultColumns = () => [m.foresight_column_combatant(), m.foresight_column_hp(), m.foresight_column_remarks()];

  $: columns = enc?.columns.length ? enc.columns : defaultColumns();
  // The step number, the name, a cell per column, the M key's slot.
  $: grid = ['1.1rem', 'minmax(0, 1fr)', ...columns.slice(1).map(() => 'minmax(0, 0.75fr)'), '18px'].join(' ');
  $: cells = readoutCells(enc?.round ?? null, 1);
  $: turnRow = enc?.rows.find((r) => r.name === enc?.turn) ?? null;

  const ready = (async () => {
    try {
      const store = await load('settings.json');
      const saved = parseRecord(await store.get('foresightOpen')) ?? {};
      opened = Object.fromEntries(Object.entries(saved).filter(([, v]) => typeof v === 'string')) as Record<string, string>;
    } catch (e) {
      console.error('Failed to read the open encounters:', e);
    }
  })();

  async function keepOpened(next: Record<string, string>) {
    opened = next;
    try {
      const store = await load('settings.json');
      await store.set('foresightOpen', next);
    } catch (e) {
      console.error('Failed to save the open encounters:', e);
    }
  }

  function forget(campaign: string) {
    const { [campaign]: _gone, ...rest } = opened;
    void keepOpened(rest);
  }

  // An encounter with no table yet takes the default columns for its first.
  function shape(got: Encounter): Encounter {
    return got.columns.length ? got : { ...got, columns: defaultColumns() };
  }

  // Foresight follows Command's campaign.
  $: void follow($appContext.campaign ?? null);

  async function follow(campaign: string | null) {
    if (campaign === shown) return;
    shown = campaign;
    enc = null;
    selected = null;
    naming = false;
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
        forget(campaign);
      } else if (got.hash !== enc.hash) {
        enc = shape(got);
        if (selected && !enc.rows.some((r) => r.name === selected)) selected = null;
      }
    } catch (e) {
      // Moved, renamed, deleted, or no longer an encounter: Foresight is
      // empty, and finds it again if it comes back.
      console.error('Failed to read the encounter again:', e);
      if (shown === campaign && enc?.path === path && !writing) enc = null;
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

  function pass(by: 1 | -1) {
    if (!enc) return;
    const next = step(enc, by);
    if (next.turn !== enc.turn || next.round !== enc.round) change({ ...enc, ...next });
  }

  function toggle(name: string) {
    if (enc) change(toggleOut(enc, name));
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
      const made = await encounterApi.create(campaign, defaultColumns(), [{ name, link: null, out: false, cells: [] }]);
      if (shown !== campaign) return;
      void keepOpened({ ...opened, [campaign]: made.path });
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
        selected = null;
      }
      forget(campaign);
    } catch (e) {
      console.error('Failed to clear the encounter:', e);
    }
  }

  const unbindKeys = bindKeys(
    (event, ctx) => {
      if (event.defaultPrevented || ctx.typing || ctx.menu || event.metaKey || event.ctrlKey || event.altKey) return false;
      if (event.key === ' ' && event.shiftKey) {
        pass(1);
        return !!enc;
      }
      if (event.shiftKey) return false;
      if (event.key.toLowerCase() === 'm' && selected && enc) {
        toggle(selected);
        return true;
      }
      if (event.key === 'Escape' && selected) {
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

  <!-- The plate names the columns, the rows' names first. -->
  <div class="plate nameplate">
    <span aria-hidden="true"></span>
    {#each columns as column, c (c)}
      <span class="ledger-label" class:cell-head={c > 0} title={column}>{column}</span>
    {/each}
  </div>

  <ol class="rows" aria-label={m.foresight_rows_label()}>
    {#if enc}
      {#each enc.rows as row, i (row.name)}
        {@const playing = row.name === enc.turn}
        <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_noninteractive_element_interactions -->
        <li
          class="row"
          class:playing
          class:out={row.out}
          class:selected={row.name === selected}
          aria-current={playing ? 'step' : undefined}
          on:click={() => (selected = row.name)}
        >
          <span class="num">{String(i + 1).padStart(2, '0')}</span>
          <span class="name" title={row.name}>{row.name}</span>
          {#each row.cells as cell, c (c)}
            <span class="cell" title={cell || undefined}>{cell}</span>
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
    {/if}
    <!-- The empty row: a new row is named in place, the next one after it. -->
    <li class="row empty" class:naming>
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

  .plate .ledger-label {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .cell-head,
  .cell {
    padding-left: 0.35rem;
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

  .cell {
    font-size: 0.8rem;
    color: var(--text-secondary);
  }

  /* Out of the fight: down the ramp, not faded; the mute key stays lit. */
  .row.out .name,
  .row.out .cell,
  .row.out .num {
    color: var(--text-tertiary);
  }

  /* The M key shows while lit, on the turn's row and under the pointer, as
     Command's spend key shows on a row; its slot is always kept. */
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
