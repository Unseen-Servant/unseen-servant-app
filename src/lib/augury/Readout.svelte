<script lang="ts">
  // Augury's readout (design §5): the total in seven-segment lamps, the level
  // meter standing as tall as the digits at the right edge, and each die's
  // face under both. Under advantage or disadvantage the dropped roll's dice
  // follow, dimmed. A word die's face (§7) prints where the digits stand,
  // with the meter and the breakdown dark.
  import { m } from '../paraglide/messages';
  import Breakdown from './Breakdown.svelte';
  import { level, type Roll } from './dice';
  import { DIGIT_VIEWBOX, isLit, readoutCells, SEGMENTS } from './sevenSegment';

  export let result: Roll | null;
  export let dropped: Roll | null = null;
  export let word: { face: string; pigment?: string } | null = null;
  // Bumped by every roll, so a reroll that lands the same total still
  // shows its detent.
  export let seq: number;

  const METER_CELLS = 10;

  $: cells = readoutCells(result ? result.total : null);
  $: lit = result ? level(result, METER_CELLS) : 0;
</script>

<div class="readout">
  <div class="face">
    {#key seq}
      {#if word}
        <!-- A long face steps down a size and takes two lines. -->
        <div
          class="word"
          class:long={word.face.length > 16}
          class:fresh={seq > 0}
          class:pigmented={!!word.pigment}
          style:--pigment={word.pigment ?? null}
        >
          <span>{word.face}</span>
        </div>
      {:else}
        <div class="digits" class:fresh={seq > 0} aria-hidden="true">
          {#each cells as char}
            <svg class="digit" viewBox={DIGIT_VIEWBOX}>
              {#each SEGMENTS as [segment, points] (segment)}
                <polygon {points} class:lit={isLit(char, segment)} />
              {/each}
            </svg>
          {/each}
        </div>
      {/if}
    {/key}
    <div class="meter" aria-hidden="true">
      {#each Array(METER_CELLS) as _, i}
        <span class="meter-cell" class:lit={i < lit}></span>
      {/each}
    </div>
  </div>
  <Breakdown {result} {dropped} />
  <span class="announce" role="status">{word ? word.face : result ? m.augury_rolled({ total: result.total }) : ''}</span>
</div>

<style>
  /* A display window sunk in the faceplate: the well recipe on a warm
     ground (--bg-vellum), lit from behind, where the keys' wells are dark.
     Its unlit lamps are ghosts of the lit ones, as a segment display's
     are. A set height, which the faces editor shares, so the pads below
     never move. */
  .readout {
    --ghost: color-mix(in srgb, var(--text-accent) 12%, transparent);
    height: 5.5rem;
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
    padding: 0.55rem 0.65rem 0.4rem;
    background: var(--bg-vellum);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-well);
  }

  .face {
    display: flex;
    justify-content: space-between;
    gap: 0.75rem;
  }

  .digits {
    display: flex;
    gap: 0.3rem;
  }

  .digit {
    width: 1.55rem;
    height: 2.8rem;
  }

  /* Each segment is a lamp: a ghost at rest, parchment lit — the total is
     data. No glow: a result isn't a state anyone switched on. */
  polygon {
    fill: var(--ghost);
  }

  polygon.lit {
    fill: var(--text-accent);
  }

  /* A word die's face in the readout's mono, parchment as the total is, or
     in its pad's pigment. Sized so sixteen characters fit one line at the
     panel's narrowest; a longer face steps down and takes two. */
  .word {
    flex: 1;
    min-width: 0;
    height: 2.8rem;
    display: flex;
    align-items: center;
    font-family: var(--font-readout);
    font-size: 1.3rem;
    line-height: 1.15;
    color: var(--text-accent);
  }

  .word.pigmented {
    color: var(--pigment);
  }

  .word span {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .word.long {
    font-size: 0.95rem;
    line-height: 1.3rem;
  }

  .word.long span {
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
    white-space: normal;
  }

  /* The app's detent (app.css): one bright frame as the new total lands. */
  .digits.fresh,
  .word.fresh {
    animation: detent-flat 110ms ease-out;
  }

  @media (prefers-reduced-motion: reduce) {
    .digits.fresh,
    .word.fresh {
      animation: none;
    }
  }

  /* The status bar's meter cells (StatusBar .meter-cell) turned on their
     side and stacked, filling from the bottom as a level meter does, as tall
     as the digits so the breakdown has the full width under them; unlit,
     the segments' ghost. */
  .meter {
    display: flex;
    flex-direction: column-reverse;
    justify-content: space-between;
    height: 2.8rem;
    flex-shrink: 0;
  }

  .meter-cell {
    width: 8px;
    height: 3px;
    border-radius: var(--radius-cell);
    background: var(--ghost);
  }

  .meter-cell.lit {
    background: var(--text-accent);
  }

  .announce {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
  }
</style>
