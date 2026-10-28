<script lang="ts">
  // The card tray (design §5.2): the live set's notes as a hand of cards,
  // docked under the board as a deckbuilder's hand sits under its table.
  // Each card keeps its reading width; past what fits they overlap evenly,
  // so every one stays in view. Pointing at a card brings it to the front,
  // whole, and outlines its card on the board. A click selects a card, one
  // at a time: it stays up, whole and raised, with its menu over it, and
  // a double-click opens its note. A right-click stands the card up over
  // the dimmed board, the board's height, and folds the tray to its
  // nameplates, where a right-click stands up more; a right-click on a
  // standing card puts it back. A click on the board, Esc or a new live set
  // puts them all back, and the hand comes back. Folded, the tray is its
  // plate, the hand as nameplates that bring their card up when pointed at.
  import { onDestroy, onMount } from 'svelte';
  import { CARET_RIGHT } from '../ui/iconPaths';
  import CardFace from './CardFace.svelte';
  import { handStep, type Card, type CardData } from './board';
  import type { OpenMenu } from './menu';
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
  export let onMenu: (card: Card, e: MouseEvent, from: Pick<OpenMenu, 'anchor' | 'onPlace' | 'onClose'>) => void;
  /** The board over the tray, in px: its height, and how far the session
   *  player or the jot bar, and the rail, reach in from its sides. The
   *  spread stands between them. */
  export let stand: { height: number; left: number; right: number };
  /** Cards stand over the board, or none do: Play dims the board. */
  export let onStand: (standing: boolean) => void;

  $: held = cards.map(dataOf);

  // -- standing cards -------------------------------------------------------

  /** The cards standing over the board. */
  let picked: string[] = [];
  let setKey: string | null = null;
  $: {
    const key = [beat ?? '', ...cards.map((c) => c.path)].join('\n');
    if (key !== setKey) {
      setKey = key;
      picked = [];
    }
  }
  // While cards stand the tray shows folded, whatever `open` says, and the
  // hand comes back with them.
  $: spread = picked.length > 0;
  $: showHand = open && !spread;
  $: onStand(spread);
  onDestroy(() => onStand(false));

  /** Esc, or a click on the dimmed board, puts every card back. False
   *  with none standing. */
  export function putBack(): boolean {
    if (!spread) return false;
    picked = [];
    return true;
  }

  /** A right-click stands a card up, or puts it back. */
  function flip(path: string) {
    deselect();
    picked = picked.includes(path) ? picked.filter((p) => p !== path) : [...picked, path];
  }

  /** The fold key; with cards standing, it puts them back and shows the
   *  hand. */
  function fold() {
    if (putBack()) open = true;
    else open = !open;
  }

  // -- the selected card and its menu ---------------------------------------

  /** The card clicked, one at a time: it stays up, whole, raised and in
   *  the accent rule, with its menu under it at its width, until the menu
   *  closes. */
  let selected: string | null = null;
  /** How far the selected card rises clear of its menu, in px: the window
   *  has no room under a card in the tray, so the menu takes its foot and
   *  the card stands on the menu. */
  let lift = 0;
  /** Selected at the press: the click closes its menu, as a second click
   *  on a menu's key does, rather than opening it again. */
  let wasSelected = false;

  // The menu opens once the double-click time has passed with no second
  // click, as a click on Legend Lore's selected collection waits
  // (CollectionsPanel): a double-click opens the note instead.
  const DOUBLE_CLICK_MS = 350;
  let pendingMenu: ReturnType<typeof setTimeout> | null = null;
  function deselect() {
    if (pendingMenu) clearTimeout(pendingMenu);
    pendingMenu = null;
    selected = null;
    lift = 0;
  }
  onDestroy(() => pendingMenu && clearTimeout(pendingMenu));

  /** A link or a key keeps its own click. */
  function select(card: Card, e: MouseEvent & { currentTarget: HTMLElement }) {
    if ((e.target as HTMLElement).closest('a, button')) return;
    const again = wasSelected;
    deselect();
    if (e.detail > 1 || again) return;
    const path = card.path ?? '';
    selected = path;
    // The menu goes at the card where it stands, in the hand or over the
    // board, or at a nameplate's card above it.
    const at = e.currentTarget;
    pendingMenu = setTimeout(() => {
      pendingMenu = null;
      const face = at.matches('.note-plate') ? (at.parentElement?.querySelector('.peek .card') ?? at) : at;
      const anchor = face.getBoundingClientRect();
      onMenu(card, e, {
        anchor,
        onPlace: (box) => {
          if (selected === path) lift = Math.max(0, anchor.bottom + 0.25 * rem - box.top);
        },
        onClose: () => {
          if (selected === path) deselect();
        },
      });
    }, DOUBLE_CLICK_MS);
  }

  /** While cards stand, a nameplate's click stands its card too, or puts
   *  it back, as its right-click does; else it selects the card. */
  function plateClick(card: Card, e: MouseEvent & { currentTarget: HTMLElement }) {
    if (!spread) select(card, e);
    else if (e.detail === 1) flip(card.path ?? '');
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
   *  card's edge is the empty tray, no card's. */
  function track(e: PointerEvent & { currentTarget: HTMLElement }) {
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
    <button type="button" class="fold" aria-expanded={showHand} on:click={fold}>
      <svg class="caret" class:open={showHand} viewBox="96 64 512 512" fill="currentColor" aria-hidden="true"><path d={CARET_RIGHT} /></svg>
      <span class="ledger-label">{m.command_tray_title()}</span>
    </button>
    <span class="row-count">{cards.length}</span>
    {#if showHand}
      {#if beat}<span class="beat" title={beat}>{beat}</span>{/if}
    {:else}
      <!-- Folded, or under standing cards: a nameplate per card in its
           track's pigment, as Prep's track plates wear it. A standing
           card's own isn't brought up: it stands. -->
      <div class="plates">
        {#each held as d, i (d.card.id)}
          {@const path = d.card.path ?? ''}
          <div class="plate-slot" role="presentation" on:pointerenter={() => point(path)} on:pointerleave={() => point(null)}>
            {#if (pointed === path || selected === path) && !picked.includes(path)}
              <div
                class="peek"
                class:end={i >= held.length / 2}
                style:transform={selected === path && lift ? `translateY(-${lift}px)` : null}
              >
                <CardFace data={d} held />
              </div>
            {/if}
            <!-- svelte-ignore a11y_click_events_have_key_events -->
            <div
              class="note-plate"
              role="button"
              tabindex="-1"
              data-path={path}
              class:pigmented={!!d.pigment}
              class:spent={!!d.spent}
              class:pointed={pointed === path || selected === path}
              style:--pigment={d.pigment}
              title={d.name}
              on:mousedown={() => (wasSelected = selected === path)}
              on:click={(e) => plateClick(d.card, e)}
              on:contextmenu|preventDefault={() => flip(path)}
            >
              {d.name}
            </div>
          </div>
        {/each}
      </div>
    {/if}
  </div>

  {#if spread}
    <!-- The picked cards stood up over the board, each its note's height
         up to the board's. -->
    <div
      class="stand"
      style:left="calc({stand.left}px + 0.5rem)"
      style:right="calc({stand.right}px + 0.5rem)"
      style:height="calc({stand.height}px - 1rem)"
    >
      {#each held as d (d.card.id)}
        {@const path = d.card.path ?? ''}
        {#if picked.includes(path)}
          <!-- svelte-ignore a11y_click_events_have_key_events -->
          <div
            class="standing"
            role="presentation"
            data-path={path}
            style:margin-bottom={selected === path && lift ? `${lift}px` : null}
            style:max-height={selected === path && lift ? `calc(100% - ${lift}px)` : null}
            on:pointerenter={() => point(path)}
            on:pointerleave={() => point(null)}
            on:mousedown={() => (wasSelected = selected === path)}
            on:click={(e) => select(d.card, e)}
            on:contextmenu|preventDefault={() => flip(path)}
          >
            <CardFace data={d} held />
          </div>
        {/if}
      {/each}
    </div>
  {/if}

  {#if showHand}
    <div class="hand">
      <div
        class="cards"
        role="presentation"
        bind:clientWidth={room}
        on:pointermove={track}
        on:pointerleave={() => point(null)}
      >
        {#each held as d, i (d.card.id)}
          {@const path = d.card.path ?? ''}
          <!-- svelte-ignore a11y_click_events_have_key_events -->
          <div
            class="slot"
            role="button"
            tabindex="-1"
            data-path={path}
            class:look={pointed === path || selected === path}
            class:selected={selected === path}
            style:left="{i * step}px"
            style:width="{CARD_REM}rem"
            style:z-index={selected === path ? held.length + 1 : pointed === path ? held.length : i}
            on:mousedown={() => (wasSelected = selected === path)}
            on:click={(e) => select(d.card, e)}
            on:contextmenu|preventDefault={() => flip(path)}
          >
            <div class="lift" style:transform={selected === path && lift ? `translateY(-${lift}px)` : null}>
              <CardFace data={d} held />
            </div>
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
  /* Selected: the board's selected card's accent rule, raised a step, as
     a card readied to play, then onto its menu (lift). */
  .slot.selected :global(.card) {
    border-color: var(--text-accent);
  }

  .slot.selected .lift {
    transform: translateY(-0.4rem);
  }

  .slot.look .lift {
    height: auto;
    min-height: 100%;
    max-height: 28rem;
  }

  /* -- spread ------------------------------------------------------------ */

  /* Over the board from just above the plate to level with the session
     player's top, the cards standing on its floor side by side. A click
     between them falls to the dimmed board, which puts them back. */
  .stand {
    position: absolute;
    bottom: calc(100% + 0.5rem);
    display: flex;
    align-items: flex-end;
    gap: 0.5rem;
    pointer-events: none;
  }

  /* A reading measure each, narrower when more stand than fit. */
  .standing {
    flex: 0 1 28rem;
    min-width: 0;
    max-height: 100%;
    display: flex;
    flex-direction: column;
    pointer-events: auto;
  }

  .standing :global(.card) {
    flex: 1 1 auto;
    border-color: var(--text-accent);
  }
</style>
