<script lang="ts">
  // A roll's dice in one line (design §5), under the readout's digits and on
  // each line of the tape: each die's face in its own window, the numbers
  // after, and under advantage or disadvantage the dropped roll's dice,
  // dimmed. One line, so nothing below it moves; the tooltip holds the rest.
  import { m } from '../paraglide/messages';
  import type { Roll } from './dice';

  export let result: Roll | null;
  export let dropped: Roll | null = null;

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
    /** A pigmented pad's term: its windows take the pigment on their edge. */
    pigment?: string;
  }

  function breakdown(r: Roll, numbers: boolean): Part[] {
    return r.terms.flatMap((t, i): Part[] => {
      if (t.kind === 'number') return numbers ? [{ sign: t.sign < 0 ? '−' : '+', faces: null, value: t.value }] : [];
      return [{ sign: t.sign < 0 ? '−' : '', faces: r.faces[i], value: 0, pigment: t.pigment }];
    });
  }

  // The tooltip's words for the line: faces apart by a space, terms by two.
  function plain(ps: Part[]): string {
    return ps.map((p) => p.sign + (p.faces ? p.faces.join(' ') : String(p.value))).join('  ');
  }
</script>

<!-- Each die's face sits in its own window, like a mechanical counter's, so
     no glyph has to separate them; a gap sets the terms apart. Written
     without whitespace between tags: the margins do the spacing. -->
<div class="breakdown" {title}>
  {#each parts as part}<span class="term">{part.sign}{#if part.faces}{#each part.faces as face}<span class="die" class:pigmented={!!part.pigment} style:--pigment={part.pigment ?? null}>{face}</span>{/each}{:else}{part.value}{/if}</span>{/each}{#if droppedParts.length}<span class="dropped">{#each droppedParts as part}<span class="term">{part.sign}{#each part.faces ?? [] as face}<span class="die" class:pigmented={!!part.pigment} style:--pigment={part.pigment ?? null}>{face}</span>{/each}</span>{/each}</span>{/if}
</div>

<style>
  /* A fixed height, so a line of windows can't push what's below down. */
  .breakdown {
    min-width: 0;
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

  .die.pigmented {
    border-color: var(--pigment);
  }

  /* The dropped roll is out of the total: the app's out-of-scope dim. */
  .dropped {
    margin-left: 0.9rem;
    opacity: var(--opacity-out-of-scope);
  }
</style>
