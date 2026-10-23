<script lang="ts">
  // The selection bar (board toolbar design §3.3): a slim box over what's
  // selected, for what needs a swatch. Every pigment and none, as the track
  // menu's row offers them, each pip lit for the one in effect; on a line,
  // its ends as three more picks and a key that opens its label. A text
  // card given a pigment becomes a sticky, and a sticky given none a text
  // card.
  import { PIGMENTS } from '../legend-lore/palette';
  import type { End } from './types';
  import { m } from '../paraglide/messages';

  /** The colour the selection shares, as drawn (board.ts paint): null for
   *  none, undefined when its cards differ. */
  export let color: string | null | undefined;
  export let onColor: (color: string | null) => void;
  /** A line's ends; null for cards, which have none. */
  export let ends: { fromEnd: End; toEnd: End } | null = null;
  export let onEnds: (ends: { fromEnd: End; toEnd: End }) => void = () => {};
  export let onLabel: () => void = () => {};

  // Font Awesome Free 7.3.1 glyphs, viewBox 0 0 640 640; each from the
  // file named beside it in src/lib/ui/icons/.
  const ENDS: { name: () => string; fromEnd: End; toEnd: End; path: string }[] = [
    {
      name: m.command_boardbar_no_arrowheads,
      fromEnd: 'none',
      toEnd: 'none',
      // minus-solid-full.svg
      path: 'M96 320C96 302.3 110.3 288 128 288L512 288C529.7 288 544 302.3 544 320C544 337.7 529.7 352 512 352L128 352C110.3 352 96 337.7 96 320z',
    },
    {
      name: m.command_boardbar_arrow_end,
      fromEnd: 'none',
      toEnd: 'arrow',
      // arrow-right-long-solid-full.svg
      path: 'M598.6 342.6C611.1 330.1 611.1 309.8 598.6 297.3L470.6 169.3C458.1 156.8 437.8 156.8 425.3 169.3C412.8 181.8 412.8 202.1 425.3 214.6L498.7 288L64 288C46.3 288 32 302.3 32 320C32 337.7 46.3 352 64 352L498.7 352L425.3 425.4C412.8 437.9 412.8 458.2 425.3 470.7C437.8 483.2 458.1 483.2 470.6 470.7L598.6 342.7z',
    },
    {
      name: m.command_boardbar_arrow_both,
      fromEnd: 'arrow',
      toEnd: 'arrow',
      // arrows-left-right-solid-full.svg
      path: 'M502.6 438.6L598.6 342.6C611.1 330.1 611.1 309.8 598.6 297.3L502.6 201.3C490.1 188.8 469.8 188.8 457.3 201.3C444.8 213.8 444.8 234.1 457.3 246.6L498.7 288L141.2 288L182.6 246.6C195.1 234.1 195.1 213.8 182.6 201.3C170.1 188.8 149.8 188.8 137.3 201.3L41.3 297.3C35.3 303.3 31.9 311.4 31.9 319.9C31.9 328.4 35.3 336.5 41.3 342.5L137.3 438.5C149.8 451 170.1 451 182.6 438.5C195.1 426 195.1 405.7 182.6 393.2L141.2 351.8L498.7 351.8L457.3 393.2C444.8 405.7 444.8 426 457.3 438.5C469.8 451 490.1 451 502.6 438.5z',
    },
  ];
  // tag-solid-full.svg
  const TAG =
    'M96.5 160L96.5 309.5C96.5 326.5 103.2 342.8 115.2 354.8L307.2 546.8C332.2 571.8 372.7 571.8 397.7 546.8L547.2 397.3C572.2 372.3 572.2 331.8 547.2 306.8L355.2 114.8C343.2 102.7 327 96 310 96L160.5 96C125.2 96 96.5 124.7 96.5 160zM208.5 176C226.2 176 240.5 190.3 240.5 208C240.5 225.7 226.2 240 208.5 240C190.8 240 176.5 225.7 176.5 208C176.5 190.3 190.8 176 208.5 176z';
</script>

<div class="bar nodrag nopan nowheel" role="toolbar" aria-label={ends ? m.command_boardbar_the_line() : m.command_boardbar_selected_cards()}>
  <div class="menu-picks" role="radiogroup" aria-label={m.command_boardbar_colour()}>
    {#each PIGMENTS as p (p.name)}
      <button type="button" class="menu-pick" role="radio" aria-checked={color === p.hex} aria-label={p.name} title={p.name} on:click={() => onColor(p.hex)}>
        <span class="menu-swatch" style:background={p.hex} aria-hidden="true"></span>
        <span class="menu-pip" class:on={color === p.hex} aria-hidden="true"></span>
      </button>
    {/each}
    <button type="button" class="menu-pick" role="radio" aria-checked={color === null} aria-label={m.command_boardbar_none()} title={m.command_boardbar_none()} on:click={() => onColor(null)}>
      <span class="menu-swatch none" aria-hidden="true"></span>
      <span class="menu-pip" class:on={color === null} aria-hidden="true"></span>
    </button>
  </div>
  {#if ends}
    {@const now = ends}
    <span class="rule" aria-hidden="true"></span>
    <div class="menu-picks" role="radiogroup" aria-label={m.command_boardbar_ends()}>
      {#each ENDS as e (e.name)}
        {@const on = now.fromEnd === e.fromEnd && now.toEnd === e.toEnd}
        <button
          type="button"
          class="menu-pick"
          role="radio"
          aria-checked={on}
          aria-label={e.name()}
          title={e.name()}
          on:click={() => onEnds({ fromEnd: e.fromEnd, toEnd: e.toEnd })}
        >
          <svg class="glyph" viewBox="0 0 640 640" fill="currentColor" aria-hidden="true"><path d={e.path} /></svg>
          <span class="menu-pip" class:on aria-hidden="true"></span>
        </button>
      {/each}
    </div>
    <span class="rule" aria-hidden="true"></span>
    <div class="menu-picks">
      <button type="button" class="menu-pick" aria-label={m.command_boardbar_label_line()} title={m.command_boardbar_label_line()} on:click={onLabel}>
        <svg class="glyph" viewBox="0 0 640 640" fill="currentColor" aria-hidden="true"><path d={TAG} /></svg>
        <!-- An action, not a choice: its pip's place, empty, keeps the row level. -->
        <span class="menu-pip unlit" aria-hidden="true"></span>
      </button>
    </div>
  {/if}
</div>

<style>
  /* Edged and lifted as a menu is (CommandMenu), as the session player's
     box is over the board. */
  .bar {
    display: flex;
    align-items: stretch;
    background: var(--bg-container);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-dropdown);
    cursor: default;
  }

  /* A swatch's box, holding a glyph in the label's ink. */
  .glyph {
    width: 1rem;
    height: 0.7rem;
    color: var(--text-secondary);
  }

  .menu-pick:hover .glyph {
    color: var(--text-primary);
  }

  .unlit {
    visibility: hidden;
  }

  /* The menu's divider, stood up between the groups. */
  .rule {
    width: 1px;
    margin: 0.3rem 0.1rem;
    background: var(--border-subtle);
  }
</style>
