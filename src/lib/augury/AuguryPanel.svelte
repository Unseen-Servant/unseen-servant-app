<script lang="ts">
  // Augury, the dice roller (docs/roadmap/2026-10-30-augury-design.md). The
  // loaded dice set's pads feed a formula in xdy notation, which the GM can
  // also type, and a roll lands on the readout. After a roll the formula
  // stays, so rolling again is the reroll; the first pad press after it
  // starts a new formula, as a calculator's first key after = does. A
  // right-click takes from the formula there. The ±1 pad in the corner moves
  // its number, and after a roll the total without new dice: the one pad
  // that never starts a new formula, since no roll starts with a bonus.
  import { onDestroy, onMount, type Snippet } from 'svelte';
  import { load } from '@tauri-apps/plugin-store';
  import { m } from '../paraglide/messages';
  import { focusPath } from '../shell/focus';
  import { bindKeys } from '../shell/keys';
  import { parseEnum } from '../shell/storeParsers';
  import { CARET_RIGHT, PLAY } from '../ui/iconPaths';
  import Readout from './Readout.svelte';
  import {
    bump,
    diceOf,
    formatFormula,
    numberOf,
    parseFormula,
    refigure,
    rollOutcome,
    stepDie,
    type Edge,
    type Outcome,
  } from './dice';
  import { SETS } from './sets';

  export let windowKey: Snippet | undefined = undefined;

  // Font Awesome "xmark" (src/lib/ui/icons/xmark-solid-full.svg)
  const XMARK =
    'M183.1 137.4C170.6 124.9 150.3 124.9 137.8 137.4C125.3 149.9 125.3 170.2 137.8 182.7L275.2 320L137.9 457.4C125.4 469.9 125.4 490.2 137.9 502.7C150.4 515.2 170.7 515.2 183.2 502.7L320.5 365.3L457.9 502.6C470.4 515.1 490.7 515.1 503.2 502.6C515.7 490.1 515.7 469.8 503.2 457.3L365.8 320L503.1 182.6C515.6 170.1 515.6 149.8 503.1 137.3C490.6 124.8 470.3 124.8 457.8 137.3L320.5 274.7L183.1 137.4z';

  let text = '';
  let refused = false;
  let outcome: Outcome | null = null;
  // Advantage or disadvantage, part of the formula: it stays for a reroll
  // and goes with a new formula.
  let edge: Edge | null = null;
  let seq = 0;
  // The field holds the formula on the readout, so the next press starts anew.
  let rolled = false;
  // The set on the pads, and the one on the display: ◀ ▶ move only the
  // display, and [load] brings its set onto the pads.
  let loaded = 0;
  let browsed = 0;

  $: terms = parseFormula(text);
  $: bonus = numberOf(terms ?? []);
  $: pads = SETS[loaded].pads;
  $: browsedName = SETS[browsed].name();

  // A changed formula has no result yet, so the readout goes dark.
  function unroll() {
    if (!rolled) return;
    rolled = false;
    outcome = null;
  }

  function setFormula(next: string) {
    text = next;
    refused = false;
    unroll();
  }

  // A press after a roll starts a new formula, with no edge; a right-click
  // (by -1) takes from the formula there.
  function press(size: number, by: 1 | -1) {
    const fresh = rolled && by > 0;
    const next = stepDie(fresh ? [] : (terms ?? []), size, by);
    if (!next) return;
    if (fresh) edge = null;
    setFormula(formatFormula(next));
  }

  function bumpBy(by: 1 | -1) {
    if (terms === null) {
      refused = true;
      return;
    }
    const next = bump(terms, by);
    if (!next) return;
    if (!rolled || !outcome) {
      setFormula(formatFormula(next));
      return;
    }
    // Only the number moved: the dice on the readout stay, and the total
    // moves with it.
    text = formatFormula(next);
    outcome = { kept: refigure(outcome.kept, next), dropped: outcome.dropped && refigure(outcome.dropped, next) };
  }

  function toggleEdge(to: Edge) {
    edge = edge === to ? null : to;
    unroll();
  }

  function rollNow() {
    if (terms === null) {
      refused = true;
      return;
    }
    if (terms.length === 0) return;
    outcome = rollOutcome(terms, edge);
    seq += 1;
    rolled = true;
  }

  function clear() {
    text = '';
    refused = false;
    outcome = null;
    edge = null;
    rolled = false;
  }

  function step(by: number) {
    browsed = (browsed + by + SETS.length) % SETS.length;
  }

  async function loadSet() {
    loaded = browsed;
    try {
      const store = await load('settings.json');
      await store.set('augurySet', SETS[loaded].id);
    } catch (e) {
      console.error('Failed to save the loaded dice set:', e);
    }
  }

  const unbindKeys = bindKeys(
    (event, ctx) => {
      if (ctx.menu || event.metaKey || event.ctrlKey || event.altKey) return false;
      // A focused key's Enter is its own press.
      if (event.key === 'Enter' && !(event.target instanceof HTMLButtonElement)) {
        rollNow();
        return true;
      }
      // With nothing to clear, Esc goes on down the app's ladder.
      if (event.key === 'Escape' && (text !== '' || outcome || edge)) {
        clear();
        return true;
      }
      return false;
    },
    { tool: 'augury' },
  );

  onMount(async () => {
    try {
      const store = await load('settings.json');
      const id = parseEnum(
        await store.get('augurySet'),
        SETS.map((s) => s.id),
      );
      if (id) loaded = browsed = SETS.findIndex((s) => s.id === id);
    } catch (e) {
      console.error('Failed to read the loaded dice set:', e);
    }
  });

  onDestroy(unbindKeys);
</script>

<section class="augury" class:dormant={$focusPath.tool !== 'augury'}>
  <!-- The set browser sits in the header, where a pad controller has its
       program display. -->
  <header class="bar">
    <div class="well browser" role="group" aria-label={m.augury_sets_label()}>
      <button
        type="button"
        class="key"
        title={m.augury_set_previous()}
        aria-label={m.augury_set_previous()}
        on:click={() => step(-1)}
      >
        <svg class="back" viewBox="96 64 512 512" fill="currentColor" aria-hidden="true"><path d={CARET_RIGHT} /></svg>
      </button>
      <!-- The rack's tool lamp (RackBar .cell): lit while the set on the
           display is the one on the pads. -->
      <span
        class="display"
        title={browsed === loaded
          ? m.augury_set_on_pads({ set: browsedName })
          : m.augury_set_off_pads({ set: browsedName })}
      >
        <span class="cell" class:lit={browsed === loaded} aria-hidden="true"></span>
        <span class="set-name readout-label">{browsedName}</span>
      </span>
      <button
        type="button"
        class="key"
        title={m.augury_set_next()}
        aria-label={m.augury_set_next()}
        on:click={() => step(1)}
      >
        <svg viewBox="96 64 512 512" fill="currentColor" aria-hidden="true"><path d={CARET_RIGHT} /></svg>
      </button>
    </div>
    <button
      type="button"
      class="plate-btn"
      disabled={browsed === loaded}
      title={m.augury_load_title({ set: browsedName })}
      on:click={loadSet}
    >
      {m.augury_load()}
    </button>
    <span class="spacer"></span>
    {@render windowKey?.()}
  </header>

  <div class="body">
    <Readout result={outcome?.kept ?? null} dropped={outcome?.dropped ?? null} {seq} />

    <div class="formula-row">
      <input
        class="formula"
        class:refused
        value={text}
        aria-label={m.augury_formula_label()}
        aria-invalid={refused}
        title={refused ? m.augury_formula_refused() : undefined}
        spellcheck="false"
        autocomplete="off"
        autocapitalize="off"
        on:input={(e) => setFormula(e.currentTarget.value)}
      />
      <!-- Latches: a mode on the formula, so the lamp lights purple. -->
      <div class="well" role="group" aria-label={m.augury_edge_label()}>
        <button
          type="button"
          class="key text-key"
          aria-pressed={edge === 'advantage'}
          title={m.augury_advantage_title()}
          on:click={() => toggleEdge('advantage')}
        >
          <span>{m.augury_advantage()}</span>
          <span class="lamp mode" class:lit={edge === 'advantage'} aria-hidden="true"></span>
        </button>
        <button
          type="button"
          class="key text-key"
          aria-pressed={edge === 'disadvantage'}
          title={m.augury_disadvantage_title()}
          on:click={() => toggleEdge('disadvantage')}
        >
          <span>{m.augury_disadvantage()}</span>
          <span class="lamp mode" class:lit={edge === 'disadvantage'} aria-hidden="true"></span>
        </button>
      </div>
      <!-- Transport keys: neither moves when the dice set changes. -->
      <div class="well">
        <button
          type="button"
          class="key"
          disabled={text === '' && !outcome && !edge}
          title={m.augury_clear()}
          aria-label={m.augury_clear()}
          on:click={clear}
        >
          <svg viewBox="0 0 640 640" fill="currentColor" aria-hidden="true"><path d={XMARK} /></svg>
        </button>
        <button
          type="button"
          class="key"
          disabled={text.trim() === ''}
          title={m.augury_roll()}
          aria-label={m.augury_roll()}
          on:click={rollNow}
        >
          <svg viewBox="0 0 640 640" fill="currentColor" aria-hidden="true"><path d={PLAY} /></svg>
        </button>
      </div>
    </div>

    <div class="pads" role="group" aria-label={m.augury_pads_label()}>
      {#each pads as size, i (i)}
        <div class="pad-well">
          {#if size !== null}
            {@const count = diceOf(terms ?? [], size)}
            <button
              type="button"
              class="pad"
              class:loaded={count !== 0}
              title={m.augury_pad_title({ size })}
              on:click={() => press(size, 1)}
              on:contextmenu|preventDefault={() => press(size, -1)}
            >
              <span>{count === 0 ? `d${size}` : `${count}d${size}`}</span>
              <span class="lamp" class:lit={count !== 0} aria-hidden="true"></span>
            </button>
          {/if}
        </div>
      {/each}
      <!-- The ±1 pad, in the same corner of every number set. -->
      <div class="pad-well">
        <button
          type="button"
          class="pad"
          class:loaded={bonus !== 0}
          title={m.augury_bonus_title()}
          on:click={() => bumpBy(1)}
          on:contextmenu|preventDefault={() => bumpBy(-1)}
        >
          <span>{bonus === 0 ? '+1' : bonus > 0 ? `+${bonus}` : `${bonus}`}</span>
          <span class="lamp" class:lit={bonus !== 0} aria-hidden="true"></span>
        </button>
      </div>
    </div>
  </div>
</section>

<style>
  .augury.dormant {
    --ring-focus: var(--ring-dormant);
  }

  .augury {
    height: 100%;
    display: flex;
    flex-direction: column;
    background: var(--bg-app);
    color: var(--text-primary);
  }

  /* Command's bar (CommandPanel .bar): the same height, inset and rule, so
     the keys centre where the neighbours' do. */
  .bar {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    height: var(--header-height);
    padding: 1px 0.5rem 0;
    background: var(--bg-header);
    border-bottom: 1px solid var(--border-subtle);
  }

  .spacer {
    flex: 1;
  }

  .plate-btn {
    flex-shrink: 0;
  }

  /* The board tools' wells and keys (BoardTools .well, .key). */
  .well {
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
    background: transparent;
    border: none;
    border-radius: var(--radius-md);
    color: var(--text-tertiary);
    cursor: pointer;
    padding: 0;
    transition: color var(--transition-fast), transform var(--transition-fast);
  }

  .key:hover:not(:disabled) {
    color: var(--text-primary);
  }

  .key:active:not(:disabled) {
    transform: scale(0.97);
  }

  .key:disabled {
    opacity: 0.35;
    cursor: default;
  }

  .key svg {
    width: 12px;
    height: 12px;
  }

  .back {
    transform: scaleX(-1);
  }

  /* A key with a word or a number on its face: the icon keys' height, as
     wide as its label needs. */
  .text-key {
    flex-direction: column;
    gap: 3px;
    width: auto;
    min-width: 26px;
    padding: 0 0.3rem;
    font-family: var(--font-mono);
    font-size: 0.65rem;
    line-height: 1;
  }

  /* At the rack's narrowest the set's name gives way, not the keys. */
  .browser {
    min-width: 0;
  }

  .display {
    display: flex;
    align-items: center;
    gap: 0.3rem;
    width: 6.5rem;
    min-width: 0;
    flex-shrink: 1;
    height: 22px;
    padding: 0 0.2rem;
  }

  .set-name {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  /* RackBar .cell, verbatim. */
  .cell {
    flex-shrink: 0;
    width: 6px;
    height: 6px;
    border-radius: var(--radius-cell);
    background: var(--border-subtle);
    transition: background var(--transition-fast);
  }

  .cell.lit {
    background: var(--text-active);
    filter: var(--glow-active);
  }

  .body {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
    padding: 0.5rem;
  }

  .formula-row {
    display: flex;
    align-items: center;
    gap: 0.4rem;
  }

  /* Mono: notation is a code-flavoured affordance. The edge is the focus
     ring, or the refused ring once a roll can't read it. */
  .formula {
    flex: 1;
    min-width: 0;
    height: 28px;
    padding: 0 0.5rem;
    font-family: var(--font-mono);
    font-size: 0.8rem;
    color: var(--text-primary);
    background: var(--bg-app);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    outline: none;
  }

  .formula:focus {
    box-shadow: var(--ring-focus);
  }

  .formula.refused {
    box-shadow: var(--ring-refused);
  }

  .pads {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 4px;
  }

  /* Each pad is a key in its own well, so the matrix reads as sixteen pads;
     one with no die is the bare well. */
  .pad-well {
    display: flex;
    height: 2.4rem;
    padding: 2px;
    background: var(--bg-app);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-well);
  }

  .pad {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 4px;
    background: transparent;
    border: none;
    border-radius: var(--radius-md);
    color: var(--text-tertiary);
    font-family: var(--font-mono);
    font-size: 0.75rem;
    cursor: pointer;
    padding: 0;
    transition: color var(--transition-fast), transform var(--transition-fast);
  }

  .pad:hover {
    color: var(--text-primary);
  }

  .pad:active {
    transform: scale(0.97);
  }

  /* Loaded dice are content: parchment, where a mode's key would light
     purple. */
  .pad.loaded {
    color: var(--text-accent);
  }

  .pad.loaded:hover {
    filter: brightness(1.2);
  }

  .lamp {
    width: 10px;
    height: 2px;
    border-radius: var(--radius-sm);
    background: var(--border-subtle);
    transition: background var(--transition-fast);
  }

  .lamp.lit {
    background: var(--text-accent);
    filter: var(--glow-accent);
  }

  /* LatchKey's lamp: a mode switched on lights the transport's purple. */
  .lamp.mode.lit {
    background: var(--text-active);
    filter: var(--glow-active);
  }
</style>
