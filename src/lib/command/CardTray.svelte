<script lang="ts">
  // The card tray (design §5.2): the live set's notes as a hand of cards,
  // docked under the board as a deckbuilder's hand sits under its table.
  // Each card keeps its reading width; past what fits they overlap evenly,
  // so every one stays in view. Pointing at a card brings it to the front,
  // whole, and outlines its card on the board. A double-click opens its
  // note. A right-click stands the card up in the middle of the dimmed
  // board, or puts it back; the tray stays as it was. A card drags along
  // the hand to put the live set in another order. Folded, the tray is its
  // plate, the hand as nameplates that bring their card up when pointed at.
  import { onDestroy, onMount } from 'svelte';
  import { CARET_RIGHT } from '../ui/iconPaths';
  import { grab } from '../ui/grab';
  import CardFace from './CardFace.svelte';
  import { handPlace, handShift, handStep, type Card, type CardData } from './board';
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
  /** The hand dragged into a new order: the live set's notes in it.
   *  Settles once the live set has answered. */
  export let onOrder: (notes: string[]) => Promise<void>;
  /** A right-click stands a card in the middle of the board, or puts it
   *  back. */
  export let onStand: (card: Card) => void;

  $: held = cards.map(dataOf);

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
   *  card's edge is the empty tray, no card's. */
  function track(e: PointerEvent & { currentTarget: HTMLElement }) {
    if (moving) return;
    const x = e.clientX - e.currentTarget.getBoundingClientRect().left;
    if (x > (cards.length - 1) * step + CARD_REM * rem) {
      point(null);
      return;
    }
    const at = step > 0 ? Math.min(Math.floor(x / step), cards.length - 1) : cards.length - 1;
    point(cards[Math.max(at, 0)]?.path ?? null);
  }

  // -- reordering -----------------------------------------------------------
  //
  // A card drags along the hand, and the hand makes room for it as it
  // goes: the cards between slide a place aside, and the card shows, dimmed
  // as a carried row is, in the place nearest where it rides. Nothing is
  // pointed at meanwhile, so no card grows up over the board. Off the
  // hand, it shows back in its own place, where a drop leaves it.
  const CARD_MIME = 'application/x-command-tray-card';
  const isCardDrag = (e: DragEvent) =>
    Array.from(e.dataTransfer?.types ?? []).some((t) => t.toLowerCase() === CARD_MIME);

  /** The card carried and the place it shows at: while it's carried and,
   *  once dropped, until the live set answers in its new order. */
  let moving: { path: string; to: number } | null = null;
  let carrying = false;
  /** How far into the card it was taken, so its place follows the card
   *  rather than the pointer. */
  let grabX = 0;
  $: from = moving ? cards.findIndex((c) => c.path === moving?.path) : -1;

  function startDrag(e: DragEvent & { currentTarget: HTMLElement }, path: string) {
    point(null);
    grabX = e.clientX - e.currentTarget.getBoundingClientRect().left;
    moving = { path, to: cards.findIndex((c) => c.path === path) };
    carrying = true;
    if (!e.dataTransfer) return;
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData(CARD_MIME, path);
  }

  // The drag's end reaches the window, from a card a new live set took
  // out of the hand too. After a drop, the hand keeps the card's new place
  // for the live set's answer.
  function endDrag() {
    if (!carrying) return;
    carrying = false;
    moving = null;
  }

  function placeAt(e: DragEvent & { currentTarget: HTMLElement }, path: string) {
    const left = e.clientX - e.currentTarget.getBoundingClientRect().left - grabX;
    const to = handPlace(left, cards.length, step);
    if (moving?.to !== to) moving = { path, to };
  }

  function overHand(e: DragEvent & { currentTarget: HTMLElement }) {
    if (!carrying || !moving || !isCardDrag(e)) return;
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
    placeAt(e, moving.path);
  }

  // WebKit sends a dragleave between the hand's own elements, so leaving
  // is judged by where the pointer is (TrackGrid leaveGrid).
  function leaveHand(e: DragEvent & { currentTarget: HTMLElement }) {
    const box = e.currentTarget.getBoundingClientRect();
    if (e.clientX > box.left && e.clientX < box.right && e.clientY > box.top && e.clientY < box.bottom) return;
    if (carrying && moving && from >= 0) moving = { path: moving.path, to: from };
  }

  function dropOnHand(e: DragEvent & { currentTarget: HTMLElement }) {
    if (!carrying || !moving || !isCardDrag(e)) return;
    e.preventDefault();
    carrying = false;
    placeAt(e, moving.path);
    const move = moving;
    const order = cards.map((c) => c.path ?? '');
    const at = order.indexOf(move.path);
    if (at < 0 || at === move.to) {
      moving = null;
      return;
    }
    order.splice(move.to, 0, ...order.splice(at, 1));
    void onOrder(order).then(() => {
      if (moving === move) moving = null;
    });
  }
</script>

<svelte:window on:dragend={endDrag} />

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
    {:else}
      <!-- Folded: a nameplate per card in its track's pigment, as Prep's
           track plates wear it. -->
      <div class="plates">
        {#each held as d, i (d.card.id)}
          {@const path = d.card.path ?? ''}
          <div class="plate-slot" role="presentation" on:pointerenter={() => point(path)} on:pointerleave={() => point(null)}>
            {#if pointed === path}
              <div class="peek" class:end={i >= held.length / 2}>
                <CardFace data={d} held />
              </div>
            {/if}
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
              on:contextmenu|preventDefault={() => onStand(d.card)}
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
        role="presentation"
        bind:clientWidth={room}
        class:sorting={!!moving}
        on:pointermove={track}
        on:pointerleave={() => point(null)}
        on:dragenter={overHand}
        on:dragover={overHand}
        on:dragleave={leaveHand}
        on:drop={dropOnHand}
      >
        {#each held as d, i (d.card.id)}
          {@const path = d.card.path ?? ''}
          {@const at = moving && from >= 0 ? handShift(i, from, moving.to) : i}
          <div
            class="slot"
            role="button"
            tabindex="-1"
            data-path={path}
            class:look={pointed === path}
            class:carried={carrying && moving?.path === path}
            style:left="{at * step}px"
            style:width="{CARD_REM}rem"
            style:z-index={pointed === path ? held.length : at}
            on:contextmenu|preventDefault={() => onStand(d.card)}
            use:grab
            on:dragstart={(e) => startDrag(e, path)}
          >
            <div class="lift"><CardFace data={d} held /></div>
          </div>
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
     plate's cards stand to the left of theirs, clear of the tray's end,
     and over the cards standing on the board. */
  .peek {
    position: absolute;
    z-index: 1;
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

  .slot {
    position: absolute;
    top: 0;
    bottom: 0;
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

  /* A card carried along the hand: the cards slide aside for it, and it
     shows where it lands at a carried row's 0.4 (CollectionsPanel
     .dragging). */
  .cards.sorting .slot {
    transition: left var(--transition-fast);
  }

  .slot.carried {
    opacity: 0.4;
  }
</style>
