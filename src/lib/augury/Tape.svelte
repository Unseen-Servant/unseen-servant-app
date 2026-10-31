<script lang="ts">
  // The tape (design §13), under the pads: the readout shows the roll, the
  // tape the ones before it. Down, its slot shows the last line; its key
  // raises the rest out of the slot over the pads, as a printing
  // calculator's paper rises, the newest line by the slot and the older
  // above it. The panel's box never changes size. A click on a line puts
  // its formula back in the field, to roll again.
  import { m } from '../paraglide/messages';
  import LatchKey from '../ui/LatchKey.svelte';
  import Breakdown from './Breakdown.svelte';
  import { formatFormula } from './dice';
  import type { TapeLine } from './tape';

  export let lines: TapeLine[];
  export let open: boolean;
  export let onToggle: () => void;
  export let onRecall: (line: TapeLine) => void;

  // Font Awesome "receipt" (src/lib/ui/icons/receipt-solid-full.svg)
  const RECEIPT =
    'M142 66.2C150.5 62.3 160.5 63.7 167.6 69.8L208 104.4L248.4 69.8C257.4 62.1 270.7 62.1 279.6 69.8L320 104.4L360.4 69.8C369.4 62.1 382.6 62.1 391.6 69.8L432 104.4L472.4 69.8C479.5 63.7 489.5 62.3 498 66.2C506.5 70.1 512 78.6 512 88L512 552C512 561.4 506.5 569.9 498 573.8C489.5 577.7 479.5 576.3 472.4 570.2L432 535.6L391.6 570.2C382.6 577.9 369.4 577.9 360.4 570.2L320 535.6L279.6 570.2C270.6 577.9 257.3 577.9 248.4 570.2L208 535.6L167.6 570.2C160.5 576.3 150.5 577.7 142 573.8C133.5 569.9 128 561.4 128 552L128 88C128 78.6 133.5 70.1 142 66.2zM232 200C218.7 200 208 210.7 208 224C208 237.3 218.7 248 232 248L408 248C421.3 248 432 237.3 432 224C432 210.7 421.3 200 408 200L232 200zM208 416C208 429.3 218.7 440 232 440L408 440C421.3 440 432 429.3 432 416C432 402.7 421.3 392 408 392L232 392C218.7 392 208 402.7 208 416zM232 296C218.7 296 208 306.7 208 320C208 333.3 218.7 344 232 344L408 344C421.3 344 432 333.3 432 320C432 306.7 421.3 296 408 296L232 296z';

  $: shown = open ? lines : lines.slice(0, 1);

  function formulaOf(line: TapeLine): string {
    if (line.kind === 'word') return line.die.name;
    const edge = line.edge === 'advantage' ? m.augury_advantage() : line.edge === 'disadvantage' ? m.augury_disadvantage() : '';
    return [formatFormula(line.outcome.kept.terms), edge].filter(Boolean).join(' ');
  }
</script>

<div class="tape" class:open>
  <LatchKey
    {open}
    lamp={false}
    title={open ? m.augury_tape_close() : m.augury_tape_open()}
    label={open ? m.augury_tape_close() : m.augury_tape_open()}
    onClick={onToggle}
  >
    <svg viewBox="0 0 640 640" fill="currentColor" aria-hidden="true"><path d={RECEIPT} /></svg>
  </LatchKey>
  <div class="paper" role="group" aria-label={m.augury_tape_label()}>
    {#each shown as line (line.id)}
      {@const formula = formulaOf(line)}
      <button
        type="button"
        class="line"
        class:word={line.kind === 'word'}
        title={m.augury_tape_line_title({ formula })}
        on:click={() => onRecall(line)}
      >
        <span class="formula">{formula}</span>
        {#if line.kind === 'dice'}
          <Breakdown result={line.outcome.kept} dropped={line.outcome.dropped} />
          <span class="total">{line.outcome.kept.total}</span>
        {:else}
          <span class="face" class:pigmented={!!line.die.pigment} style:--pigment={line.die.pigment ?? null}>{line.face}</span>
        {/if}
      </button>
    {/each}
  </div>
</div>

<style>
  /* The key beside the slot, at the foot: raised, the paper fills the
     pads' place above it and the key stays where it was. */
  .tape {
    flex-shrink: 0;
    display: flex;
    align-items: flex-end;
    gap: 0.4rem;
  }

  .tape.open {
    flex: 1;
    min-height: 0;
    align-items: stretch;
  }

  .tape.open :global(.key-well) {
    align-self: flex-end;
  }

  /* Paper: a reading surface like the display (--bg-vellum), where the
     keys' wells are dark. Its lines stack up from the slot, newest at the
     bottom, so it opens scrolled to the newest. */
  .paper {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column-reverse;
    min-height: calc(1.65rem + 2px);
    background: var(--bg-vellum);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-well);
    overflow-y: auto;
  }

  /* One row height (1.65rem), as every clickable row. The formula as typed,
     the dice in their windows, the total as data on the right. */
  .line {
    flex-shrink: 0;
    display: grid;
    grid-template-columns: minmax(0, max-content) minmax(0, 1fr) auto;
    align-items: center;
    gap: 0.5rem;
    height: 1.65rem;
    padding: 0 0.45rem;
    background: transparent;
    border: none;
    border-radius: var(--radius-md);
    color: var(--text-secondary);
    text-align: left;
    cursor: pointer;
    transition: background var(--transition-fast);
  }

  .line:hover {
    background: var(--bg-focused);
  }

  .line:active {
    transform: scale(0.97);
  }

  .line.word {
    grid-template-columns: minmax(0, max-content) minmax(0, 1fr);
  }

  .formula,
  .face {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .formula {
    font-family: var(--font-mono);
    font-size: 0.7rem;
    color: var(--text-tertiary);
  }

  .line :global(.breakdown) {
    font-size: 0.75rem;
  }

  /* The total and the face are what the roll said: parchment, in the
     readout's mono. */
  .total,
  .face {
    font-family: var(--font-readout);
    font-size: 0.85rem;
    font-variant-numeric: tabular-nums;
    color: var(--text-accent);
  }

  .face {
    text-align: right;
  }

  .face.pigmented {
    color: var(--pigment);
  }
</style>
