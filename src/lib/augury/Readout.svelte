<script lang="ts">
  // Augury's readout (design §5): the total in seven-segment lamps, the level
  // meter standing as tall as the digits at the right edge, and each die's
  // face under both.
  // Under advantage or disadvantage the dropped roll's dice follow, dimmed.
  import { m } from '../paraglide/messages';
  import { level, type Roll } from './dice';
  import { DIGIT_VIEWBOX, isLit, readoutCells, SEGMENTS } from './sevenSegment';

  export let result: Roll | null;
  export let dropped: Roll | null = null;
  // Bumped by every roll, so a reroll that lands the same total still
  // shows its detent.
  export let seq: number;

  const METER_CELLS = 10;

  $: cells = readoutCells(result ? result.total : null);
  $: lit = result ? level(result, METER_CELLS) : 0;
  $: parts = result ? breakdown(result, true) : [];
  // The dropped roll's dice alone: its numbers are the kept roll's.
  $: droppedParts = dropped ? breakdown(dropped, false) : [];
  $: title = [plain(parts), droppedParts.length ? m.augury_dropped({ faces: plain(droppedParts) }) : '']
    .filter(Boolean)
    .join(' · ');

  interface Part {
    /** − before a term taken away, + before a number; an added die term has none. */
    sign: string;
    /** A dice term's faces, each in its own window; null for a number. */
    faces: number[] | null;
    value: number;
  }

  function breakdown(r: Roll, numbers: boolean): Part[] {
    return r.terms.flatMap((t, i): Part[] => {
      if (t.kind === 'number') return numbers ? [{ sign: t.sign < 0 ? '−' : '+', faces: null, value: t.value }] : [];
      return [{ sign: t.sign < 0 ? '−' : '', faces: r.faces[i], value: 0 }];
    });
  }

  // The tooltip's words for the line: faces apart by a space, terms by two.
  function plain(ps: Part[]): string {
    return ps.map((p) => p.sign + (p.faces ? p.faces.join(' ') : String(p.value))).join('  ');
  }
</script>

<div class="readout">
  <div class="face">
    {#key seq}
      <div class="digits" class:fresh={seq > 0} aria-hidden="true">
        {#each cells as char}
          <svg class="digit" viewBox={DIGIT_VIEWBOX}>
            {#each SEGMENTS as [segment, points] (segment)}
              <polygon {points} class:lit={isLit(char, segment)} />
            {/each}
          </svg>
        {/each}
      </div>
    {/key}
    <div class="meter" aria-hidden="true">
      {#each Array(METER_CELLS) as _, i}
        <span class="meter-cell" class:lit={i < lit}></span>
      {/each}
    </div>
  </div>
  <!-- One line, so the pads below never move; the tooltip holds the rest.
       Each die's face sits in its own window, like a mechanical counter's,
       so no glyph has to separate them; a gap sets the terms apart. Written
       without whitespace between tags: the margins do the spacing. -->
  <div class="breakdown" {title}>
    {#each parts as part}<span class="term">{part.sign}{#if part.faces}{#each part.faces as face}<span class="die">{face}</span>{/each}{:else}{part.value}{/if}</span>{/each}{#if droppedParts.length}<span class="dropped">{#each droppedParts as part}<span class="term">{part.sign}{#each part.faces ?? [] as face}<span class="die">{face}</span>{/each}</span>{/each}</span>{/if}
  </div>
  <span class="announce" role="status">{result ? m.augury_rolled({ total: result.total }) : ''}</span>
</div>

<style>
  /* A readout sits in the panel, not on it: the well recipe. */
  .readout {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
    padding: 0.55rem 0.65rem 0.4rem;
    background: var(--bg-app);
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

  /* Each segment is a lamp: a dark slot at rest, parchment lit — the total
     is data. No glow: a result isn't a state anyone switched on. */
  polygon {
    fill: var(--border-subtle);
  }

  polygon.lit {
    fill: var(--text-accent);
  }

  /* The app's detent (app.css): one bright frame as the new total lands. */
  .digits.fresh {
    animation: detent-flat 110ms ease-out;
  }

  @media (prefers-reduced-motion: reduce) {
    .digits.fresh {
      animation: none;
    }
  }

  /* The status bar's meter cells (StatusBar .meter-cell) turned on their
     side and stacked, filling from the bottom as a level meter does, as tall
     as the digits so the breakdown has the full width under them; unlit in
     the search gauge's grey, which shows on this ground. */
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
    background: var(--border-subtle);
  }

  .meter-cell.lit {
    background: var(--text-accent);
  }

  /* A fixed height, so a line of windows can't push the pads down. */
  .breakdown {
    height: 1.25rem;
    font-family: var(--font-body);
    font-size: 0.9rem;
    line-height: 1.25rem;
    font-variant-numeric: tabular-nums;
    color: var(--text-secondary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .term + .term {
    margin-left: 0.6rem;
  }

  /* A die's window: the readout's own edge at a small radius, recessed in
     the well, never filled. */
  .die {
    display: inline-block;
    vertical-align: middle;
    min-width: 1.15rem;
    padding: 0 0.2rem;
    line-height: 1rem;
    text-align: center;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
  }

  .die + .die {
    margin-left: 2px;
  }

  /* The dropped roll is out of the total: the app's out-of-scope dim. */
  .dropped {
    margin-left: 0.9rem;
    opacity: var(--opacity-out-of-scope);
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
