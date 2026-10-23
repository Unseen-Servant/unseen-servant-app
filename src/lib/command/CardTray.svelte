<script lang="ts">
  // The card tray (design §5.2): the live set's notes as a hand of cards,
  // docked under the board as a deckbuilder's hand sits under its table.
  // Each card keeps its reading width; past what fits they overlap evenly,
  // so every one stays in view. Pointing at a card brings it to the front,
  // whole, and outlines its card on the board. Clicking cards picks them,
  // raised in the hand; [select] lays the picked side by side to read
  // together, the rest on their side as spines. A new live set clears the
  // picks. Folded, the tray is its plate, the hand as nameplates that
  // bring their card up when pointed at.
  import { onDestroy, onMount } from 'svelte';
  import { CARET_RIGHT } from '../ui/iconPaths';
  import CardFace from './CardFace.svelte';
  import { handStep, type Card, type CardData } from './board';
  import { m } from '../paraglide/messages';

  /** The hand: the board's cards for the live set (handOf). */
  export let cards: Card[];
  export let dataOf: (card: Card) => CardData;
  /** The live beat's name; null for a set played note by note. */
  export let beat: string | null;
  /** The tray unfolded. CommandPanel keeps it across Tab. */
  export let open: boolean;
  /** The note pointed at, or null: the board outlines its card. */
  export let onPoint: (path: string | null) => void;
  export let onMenu: (card: Card, e: MouseEvent) => void;

  $: held = cards.map(dataOf);

  // -- picks and the spread -------------------------------------------------

  let picked: string[] = [];
  /** The picked cards laid side by side, the rest as spines. */
  let selecting = false;
  let setKey: string | null = null;
  $: {
    const key = [beat ?? '', ...cards.map((c) => c.path)].join('\n');
    if (key !== setKey) {
      setKey = key;
      picked = [];
    }
  }
  $: spread = selecting && picked.length > 0;
  // With nothing left picked, the spread goes back into the hand.
  $: if (!picked.length) selecting = false;

  /** A click picks a card or puts it back; a double-click's second click
   *  is the card's, which opens the note. A link or a key keeps its own. */
  function toggle(path: string, e: MouseEvent) {
    if (e.detail > 1 || (e.target as HTMLElement).closest('a, button')) return;
    picked = picked.includes(path) ? picked.filter((p) => p !== path) : [...picked, path];
  }

  /** A nameplate on the folded plate opens the tray with its card picked. */
  function unfold(path: string) {
    open = true;
    picked = [path];
  }

  // -- pointing -------------------------------------------------------------

  let pointed: string | null = null;
  function point(path: string | null) {
    if (path === pointed) return;
    pointed = path;
    onPoint(path);
  }
  $: if (pointed && !cards.some((c) => c.path === pointed)) point(null);
  onDestroy(() => onPoint(null));

  // -- the hand's layout ----------------------------------------------------

  /** A card's reading width, in rem: five fit across a 1280px window. */
  const CARD_REM = 14.6;
  let rem = 16;
  onMount(() => (rem = parseFloat(getComputedStyle(document.documentElement).fontSize) || rem));
  let room = 0;
  $: step = handStep(cards.length, room, CARD_REM * rem, 0.5 * rem);

  /** The card whose strip is under the pointer, not the one on top there:
   *  a card brought to the front covers its neighbours' strips, and moving
   *  along the hand should still step through them in turn. Past the last
   *  card's edge is the empty tray, no card's. Spread, the cards don't
   *  overlap and the one under the pointer is the one. */
  function track(e: PointerEvent & { currentTarget: HTMLElement }) {
    if (spread) {
      const slot = (e.target as HTMLElement).closest<HTMLElement>('[data-path]');
      point(slot?.dataset.path ?? null);
      return;
    }
    const x = e.clientX - e.currentTarget.getBoundingClientRect().left;
    if (x > (cards.length - 1) * step + CARD_REM * rem) {
      point(null);
      return;
    }
    const at = step > 0 ? Math.min(Math.floor(x / step), cards.length - 1) : cards.length - 1;
    point(cards[Math.max(at, 0)]?.path ?? null);
  }
</script>

<section class="tray" aria-label={m.command_tray_label()}>
  <div class="nameplate">
    <!-- The plate's label is the fold's key, as the session player's is. -->
    <button type="button" class="fold" aria-expanded={open} on:click={() => (open = !open)}>
      <svg class="caret" class:open viewBox="96 64 512 512" fill="currentColor" aria-hidden="true"><path d={CARET_RIGHT} /></svg>
      <span class="ledger-label">{m.command_tray_title()}</span>
    </button>
    <span class="row-count">{cards.length}</span>
    {#if open}
      {#if beat}<span class="beat" title={beat}>{beat}</span>{/if}
      <!-- Names what it does, as the inspector's [read]/[edit] does. -->
      <button
        type="button"
        class="plate-btn"
        disabled={!picked.length}
        title={spread ? m.command_tray_deselect_title() : m.command_tray_select_title()}
        on:click={() => (selecting = !spread)}
      >{spread ? m.command_tray_deselect() : m.command_tray_select()}</button>
    {:else}
      <!-- Folded: a nameplate per card in its track's pigment, as Prep's
           track plates wear it. -->
      <div class="plates">
        {#each held as d, i (d.card.id)}
          {@const path = d.card.path ?? ''}
          <div class="plate-slot" role="presentation" on:pointerenter={() => point(path)} on:pointerleave={() => point(null)}>
            {#if pointed === path}
              <div class="peek" class:end={i >= held.length / 2}><CardFace data={d} held /></div>
            {/if}
            <!-- svelte-ignore a11y_click_events_have_key_events -->
            <div
              class="note-plate"
              role="button"
              tabindex="-1"
              data-path={path}
              class:pigmented={!!d.pigment}
              class:spent={!!d.spent}
              class:pointed={pointed === path}
              style:--pigment={d.pigment}
              title={d.name}
              on:click={() => unfold(path)}
              on:contextmenu|preventDefault={(e) => onMenu(d.card, e)}
            >
              {d.name}
            </div>
          </div>
        {/each}
      </div>
    {/if}
  </div>

  {#if open}
    <div class="hand">
      <div
        class="cards"
        class:spread
        role="presentation"
        bind:clientWidth={room}
        on:pointermove={track}
        on:pointerleave={() => point(null)}
      >
        {#each held as d, i (d.card.id)}
          {@const path = d.card.path ?? ''}
          {@const isPicked = picked.includes(path)}
          {#if spread && !isPicked}
            <!-- svelte-ignore a11y_click_events_have_key_events -->
            <div
              class="spine"
              role="button"
              tabindex="-1"
              aria-pressed="false"
              data-path={path}
              class:spent={!!d.spent}
              class:pointed={pointed === path}
              style:--pigment={d.pigment}
              title={d.name}
              on:click={(e) => toggle(path, e)}
              on:contextmenu|preventDefault={(e) => onMenu(d.card, e)}
            >
              <span>{d.name}</span>
            </div>
          {:else}
            <!-- svelte-ignore a11y_click_events_have_key_events -->
            <div
              class="slot"
              role="button"
              tabindex="-1"
              aria-pressed={isPicked}
              data-path={path}
              class:picked={isPicked}
              class:look={pointed === path}
              style:left={spread ? null : `${i * step}px`}
              style:width={spread ? null : `${CARD_REM}rem`}
              style:z-index={spread ? null : pointed === path ? held.length : i}
              on:click={(e) => toggle(path, e)}
              on:contextmenu|preventDefault={(e) => onMenu(d.card, e)}
            >
              <div class="lift"><CardFace data={d} held /></div>
            </div>
          {/if}
        {/each}
      </div>
    </div>
  {/if}
</section>

<style>
  /* Docked under the board, above it in the stack: a card looked at grows
     up over the board. */
  .tray {
    position: relative;
    z-index: 6;
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    background: var(--bg-app);
    border-top: 1px solid var(--border-subtle);
  }

  /* The app's plate: a row's height, the label in the rail voice. */
  .nameplate {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    gap: 0.4rem;
    min-height: 1.65rem;
    box-sizing: border-box;
    padding: 0.2rem 0.6rem 0.15rem;
    background: var(--bg-container);
  }

  /* The session player's fold key (Arrangement .nameplate): its caret and
     hover, on the label alone, as the folded plate holds keys of its own. */
  .fold {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    gap: 0.3rem;
    padding: 0;
    background: none;
    border: none;
    font: inherit;
    cursor: pointer;
  }

  .caret {
    width: 0.7rem;
    height: 0.7rem;
    color: var(--text-tertiary);
    transition: transform var(--transition-fast);
  }

  .caret.open {
    transform: rotate(90deg);
  }

  .fold .ledger-label {
    transition: color var(--transition-fast);
  }

  .fold:hover .ledger-label,
  .fold:hover .caret {
    color: var(--text-secondary);
  }

  .fold:focus-visible {
    outline: 1px solid var(--text-accent);
    outline-offset: 2px;
  }

  /* Legend Lore's LED count readout (CollectionsPanel .row-count). */
  .row-count {
    flex-shrink: 0;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    height: 18px;
    min-width: 18px;
    padding: 0 0.3rem;
    box-sizing: border-box;
    border-radius: var(--radius-sm);
    background: color-mix(in srgb, var(--text-tertiary) 18%, transparent);
    color: var(--text-secondary);
    font-size: 0.65rem;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    line-height: 1;
  }

  .beat {
    flex: 0 1 auto;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 0.85rem;
    font-style: italic;
    color: var(--text-secondary);
  }

  .plate-btn {
    flex-shrink: 0;
    margin-left: auto;
    white-space: nowrap;
  }

  /* -- folded ------------------------------------------------------------ */

  .plates {
    flex: 1;
    min-width: 0;
    display: flex;
    gap: 0.25rem;
    margin-left: 0.35rem;
  }

  /* Nameplates give way, ellipsed, before they'd wrap. */
  .plate-slot {
    position: relative;
    flex: 0 1 auto;
    min-width: 0;
    display: flex;
  }

  .note-plate {
    min-width: 0;
    max-width: 10rem;
    box-sizing: border-box;
    height: calc(1.65rem - 0.4rem - 2px);
    padding: 0 0.5rem;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    background: var(--bg-container);
    font-family: var(--font-heading);
    font-size: 0.85rem;
    line-height: calc(1.65rem - 0.4rem - 4px);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    color: var(--text-primary);
    cursor: pointer;
    -webkit-user-select: none;
    user-select: none;
  }

  /* A track's pigment fills its nameplate, the name in bold ink, as on
     Prep's plates (TrackGrid .nameplate.pigmented). */
  .note-plate.pigmented {
    background: var(--pigment);
    color: var(--text-inverse);
    font-weight: 700;
  }

  .note-plate.spent {
    opacity: var(--opacity-out-of-scope);
  }

  .note-plate.pointed {
    box-shadow: 0 0 0 1px var(--bg-container), 0 0 0 2px var(--text-accent);
  }

  .note-plate:active {
    transform: scale(0.97);
  }

  /* The pointed nameplate's card, standing on it; the padding bridges the
     gap, so the pointer can go up onto the card. The second half of the
     plate's cards stand to the left of theirs, clear of the tray's end. */
  .peek {
    position: absolute;
    left: 0;
    bottom: 100%;
    width: 16rem;
    max-height: 26rem;
    box-sizing: border-box;
    padding-bottom: 0.6rem;
    display: flex;
    flex-direction: column;
  }

  .peek.end {
    left: auto;
    right: 0;
  }

  .peek :global(.card) {
    flex: 1 1 auto;
  }

  /* -- open -------------------------------------------------------------- */

  .hand {
    height: 11.85rem;
    box-sizing: border-box;
    padding: 0.5rem;
    border-top: 1px solid var(--border-subtle);
  }

  .cards {
    position: relative;
    height: 100%;
  }

  .cards.spread {
    display: flex;
    gap: 0.5rem;
  }

  .slot {
    position: absolute;
    top: 0;
    bottom: 0;
  }

  .cards.spread .slot {
    position: relative;
    flex: 1 1 0;
    min-width: 0;
  }

  .lift {
    position: absolute;
    left: 0;
    right: 0;
    bottom: 0;
    height: 100%;
    display: flex;
    flex-direction: column;
  }

  .lift :global(.card) {
    flex: 1 1 auto;
  }

  /* Looked at: a note longer than the tray grows up over the board until
     all of it shows, or the board's height would. */
  .slot.look .lift {
    height: auto;
    min-height: 100%;
    max-height: 28rem;
  }

  /* Picked: the board's selected card's accent rule, and in the hand
     raised a step, as a card readied to play. */
  .slot.picked :global(.card) {
    border-color: var(--text-accent);
  }

  .cards:not(.spread) .slot.picked .lift {
    transform: translateY(-0.4rem);
  }

  /* A card on its side, the pigment its spine, the name read upward. */
  .spine {
    flex: 0 0 1.9rem;
    box-sizing: border-box;
    display: flex;
    align-items: center;
    padding: 0.5rem 0;
    overflow: hidden;
    background: var(--pigment, var(--bg-container));
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    cursor: pointer;
  }

  .spine span {
    max-height: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    writing-mode: vertical-rl;
    transform: rotate(180deg);
    font-family: var(--font-heading);
    font-size: 0.95rem;
    font-weight: 700;
    color: var(--text-inverse);
  }

  /* A track without a pigment: the plain plate's ink. */
  .spine:not([style*='--pigment']) span {
    font-weight: 400;
    color: var(--text-secondary);
  }

  .spine.spent span {
    opacity: var(--opacity-out-of-scope);
  }

  .spine.pointed {
    border-color: var(--text-accent);
  }

  .spine:active {
    transform: scale(0.97);
  }
</style>
