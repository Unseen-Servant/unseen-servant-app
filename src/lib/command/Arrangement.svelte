<script lang="ts">
  // Play's arrangement (design §5.2): the session's plan, worked as Legend
  // Lore's collections panel: a click focuses a beat, ↑↓ move the focus, and
  // Space launches the focused beat, or stops it while it's live, as P/Space
  // play a collection. A beat's transport sits at the row's end; the live
  // beat's ■ stops the set, and the key beside it frames the live cards.
  import { PLAY } from '../ui/iconPaths';
  import { hoverLive } from '../ui/inputModality';
  import { menuSlotHeld } from '../shell/menuSlot';
  import CommandMenu from './CommandMenu.svelte';
  import { action, divider, keyed, type MenuItem, type OpenMenu } from './menu';
  import { memberPaths, type PlanRow } from './prep';
  import type { BeatEntry } from './types';

  export let rows: PlanRow[];
  /** True while the panel is visible: keys do nothing otherwise (PANELS.md). */
  export let active: boolean;
  /** The beat the live set was launched from. */
  export let liveBeat: string | null;
  export let onLaunch: (beat: BeatEntry) => void;
  /** Clears the live set: the live beat's key, as in Prep. */
  export let onStop: () => void;
  /** Brings the live cards back into view on the board. */
  export let onReframe: () => void;
  export let onEdit: (beat: BeatEntry) => void;
  export let onSpent: (beat: BeatEntry, spent: boolean) => void;

  let menu: OpenMenu | null = null;

  /** The focused beat: ringed, and what Space launches. */
  let focused: string | null = null;
  $: beats = rows.flatMap((r) => (r.beat ? [r.beat] : []));
  // A beat that left the plan can't stay focused.
  $: if (focused && !beats.some((b) => b.path === focused)) focused = null;

  // Hover latched on pointerenter, as Legend Lore's rows.
  let hovered: string | null = null;
  function leave(path: string) {
    if (hovered === path) hovered = null;
  }

  /** The live beat's key stops the set; launching it again would only log
   *  it twice. */
  function toggle(beat: BeatEntry) {
    if (beat.path === liveBeat) onStop();
    else onLaunch(beat);
  }

  /** ↑↓ step the focus. With none, the first lands on the live beat, or on
   *  the plan's first or last beat. */
  function step(by: 1 | -1) {
    if (!beats.length) return;
    const at = beats.findIndex((b) => b.path === focused);
    if (at < 0) {
      const live = beats.find((b) => b.path === liveBeat);
      focused = (live ?? (by > 0 ? beats[0] : beats[beats.length - 1])).path;
    } else {
      focused = beats[Math.min(Math.max(at + by, 0), beats.length - 1)].path;
    }
  }

  function onKeydown(e: KeyboardEvent) {
    if (!active || menu || menuSlotHeld()) return;
    if (document.querySelector('dialog[open]')) return;
    if (e.metaKey || e.ctrlKey || e.altKey || e.shiftKey) return;
    const target = e.target as HTMLElement | null;
    if (target?.closest('input, textarea, select, [contenteditable], .cm-editor')) return;
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      step(e.key === 'ArrowDown' ? 1 : -1);
    } else if (e.key === ' ') {
      // Space is the DAW's play/stop, as in Legend Lore's collections.
      e.preventDefault();
      if (e.repeat) return;
      const beat = beats.find((b) => b.path === focused);
      if (beat) toggle(beat);
    } else if (e.key === 'Escape' && focused) {
      focused = null;
    }
  }

  // The transport first, as a collection's menu has it. A right-click
  // focuses, so the menu and Space act on the same beat.
  function beatMenu(e: MouseEvent, beat: BeatEntry) {
    focused = beat.path;
    const playing = beat.path === liveBeat;
    const items: MenuItem[] = [
      keyed(playing ? 'Stop' : 'Launch', 'command.play', () => toggle(beat)),
      ...(playing ? [action('Frame the live cards', onReframe)] : []),
      divider,
      action(beat.spent ? 'Mark unspent' : 'Mark spent', () => onSpent(beat, !beat.spent)),
      action('Edit beat', () => onEdit(beat)),
    ];
    menu = { x: e.clientX, y: e.clientY, items };
  }
</script>

<svelte:window on:keydown={onKeydown} />

<section class="arrangement" aria-label="Play">
  <header class="nameplate">
    <span class="ledger-label">play</span>
  </header>
  <div class="plan">
    {#each rows as row (row.at + ':' + row.link)}
      {#if row.beat}
        {@const beat = row.beat}
        {@const playing = beat.path === liveBeat}
        <!-- The row focuses, as a collection's does; double-click opens the
             beat in the editor, as rows do in Command. -->
        <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
        <div
          class="beat-row"
          class:focused={beat.path === focused}
          class:spent={!!beat.spent}
          class:hovered={$hoverLive && hovered === beat.path}
          title={beat.spent ? `${beat.name} — spent ${beat.spent}` : beat.name}
          on:click={(e) => e.detail <= 1 && (focused = beat.path)}
          on:dblclick={() => onEdit(beat)}
          on:contextmenu|preventDefault={(e) => beatMenu(e, beat)}
          on:pointerenter={() => (hovered = beat.path)}
          on:pointerleave={() => leave(beat.path)}
        >
          <span class="beat-name">{beat.name}</span>
          {#if beat.spent}<span class="spent-mark" aria-label="spent">✓</span>{/if}
          <!-- Legend Lore's transport: hidden at rest, shown on the hovered or
               focused row, kept while live. The keys take a double-click's
               first click only: its second would undo the first. -->
          <span class="tr" class:engaged={playing}>
            <button
              type="button"
              class="tr-btn"
              class:playing
              aria-pressed={playing}
              title={`${playing ? 'Stop' : 'Launch'} ${beat.name} (Space)`}
              on:click|stopPropagation={(e) => e.detail <= 1 && toggle(beat)}
            >
              {#if playing}
                <span class="stop-mark" aria-hidden="true"></span>
              {:else}
                <svg viewBox="0 0 640 640" fill="currentColor" aria-hidden="true"><path d={PLAY} /></svg>
              {/if}
            </button>
            {#if playing}
              <button
                type="button"
                class="tr-btn"
                title="Frame the live cards"
                aria-label="Frame the live cards"
                on:click|stopPropagation={onReframe}
              >
                <!-- Font Awesome "expand" icon (src/lib/ui/icons/expand-solid-full.svg),
                     its viewBox cropped to the glyph so it fills the well as the
                     arm circle does. -->
                <svg class="frame-glyph" viewBox="96 96 448 448" fill="currentColor" aria-hidden="true">
                  <path d="M128 96C110.3 96 96 110.3 96 128L96 224C96 241.7 110.3 256 128 256C145.7 256 160 241.7 160 224L160 160L224 160C241.7 160 256 145.7 256 128C256 110.3 241.7 96 224 96L128 96zM160 416C160 398.3 145.7 384 128 384C110.3 384 96 398.3 96 416L96 512C96 529.7 110.3 544 128 544L224 544C241.7 544 256 529.7 256 512C256 494.3 241.7 480 224 480L160 480L160 416zM416 96C398.3 96 384 110.3 384 128C384 145.7 398.3 160 416 160L480 160L480 224C480 241.7 494.3 256 512 256C529.7 256 544 241.7 544 224L544 128C544 110.3 529.7 96 512 96L416 96zM544 416C544 398.3 529.7 384 512 384C494.3 384 480 398.3 480 416L480 480L416 480C398.3 480 384 494.3 384 512C384 529.7 398.3 544 416 544L512 544C529.7 544 544 529.7 544 512L544 416z" />
                </svg>
              </button>
            {/if}
          </span>
          <!-- The notes it lights, as Prep's count. -->
          <span class="row-count">{memberPaths(beat).size}</span>
        </div>
      {:else}
        <div class="beat-row missing" title={`No beat is named “${row.link}” yet`}>
          <span class="beat-name">{row.link}</span>
        </div>
      {/if}
    {:else}
      <p class="quiet">Nothing planned. Beats added to the session in Prep show here.</p>
    {/each}
  </div>
</section>

{#if menu}
  <CommandMenu x={menu.x} y={menu.y} items={menu.items} onClose={() => (menu = null)} />
{/if}

<style>
  .arrangement {
    flex: 0 0 14rem;
    min-width: 0;
    display: flex;
    flex-direction: column;
    min-height: 0;
    border-right: 1px solid var(--border-subtle);
    background: var(--bg-app);
  }

  /* Centred, not baseline-aligned, as Legend Lore's panel head: the
     min-height sets the plate and the name sits in its middle whatever
     shares it. On the baseline, a count's taller line pushed the name
     down, so a plate without one (+ track, the beats) sat higher. */
  .nameplate {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    gap: 0.4rem;
    /* Prep's plates' height (TrackGrid .nameplate), a note row's, so the
       plate under the bar holds still across Tab. */
    min-height: 1.65rem;
    padding: 0.2rem 0.6rem 0.15rem;
    background: var(--bg-container);
    border-bottom: 1px solid var(--border-subtle);
  }

  .plan {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding: 0.25rem;
  }

  /* The session planner's row (BeatColumn .beat-row), a collection's: a
     note row's height, the rule slot reserved on the left. The name starts
     under the plate's: its 0.6rem inset, less the list's padding and the
     rule. */
  .beat-row {
    display: flex;
    align-items: center;
    gap: 0.3rem;
    padding: 0.15rem 0.35rem 0.15rem calc(0.6rem - 0.25rem - 3px);
    border-left: 3px solid transparent;
    font-size: 0.9rem;
    line-height: 1.5;
    color: var(--text-primary);
    cursor: pointer;
    transition: background var(--transition-fast);
    -webkit-user-select: none;
    user-select: none;
  }

  /* Legend Lore's row states: a latched grey-step hover, and a ring on the
     focused beat. */
  .beat-row.hovered {
    background: var(--bg-container);
  }

  .beat-row.focused {
    box-shadow: var(--ring-focus);
  }

  .beat-row.spent .beat-name {
    opacity: var(--opacity-out-of-scope);
  }

  .beat-row.spent.hovered .beat-name {
    opacity: var(--opacity-out-of-scope-hover);
  }

  .beat-name {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .beat-row.missing {
    cursor: default;
  }

  .beat-row.missing .beat-name {
    color: var(--text-secondary);
    text-decoration: underline dashed;
    text-decoration-color: var(--text-accent);
    text-underline-offset: 3px;
  }

  .spent-mark {
    flex-shrink: 0;
    font-size: 0.75rem;
    font-variant-numeric: tabular-nums;
    color: var(--text-tertiary);
  }

  /* A collection's transport (CollectionsPanel .tr): hidden at rest, shown
     on the hovered or focused row, kept while live. */
  .tr {
    display: inline-flex;
    gap: 0.25rem;
    flex-shrink: 0;
    opacity: 0;
    transition: opacity var(--transition-fast);
  }

  .beat-row.hovered .tr,
  .beat-row.focused .tr,
  .tr.engaged {
    opacity: 1;
  }

  /* Legend Lore's transport keys: a glyph in a well, purple and lit while
     playing. */
  .tr-btn {
    flex-shrink: 0;
    width: 18px;
    height: 18px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0;
    background: transparent;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    color: var(--text-tertiary);
    cursor: pointer;
    transition: all var(--transition-fast);
  }

  .tr-btn:hover {
    color: var(--text-secondary);
    border-color: var(--text-secondary);
  }

  .tr-btn:active {
    transform: scale(0.97);
  }

  .tr-btn.playing {
    color: var(--text-active);
    border-color: var(--text-active);
    background: color-mix(in srgb, var(--text-active) 15%, transparent);
    filter: var(--glow-active);
  }

  .tr-btn svg {
    display: block;
    width: 9px;
    height: 9px;
  }

  /* Even sizes centre on whole pixels in the 16px well, as Legend Lore's
     arm circle; the ▶ stays 9px, off-centre on purpose. */
  .tr-btn .frame-glyph {
    width: 8px;
    height: 8px;
  }

  .stop-mark {
    width: 6px;
    height: 6px;
    background: currentColor;
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
    border-radius: var(--radius-sm);
    background: color-mix(in srgb, var(--text-tertiary) 18%, transparent);
    color: var(--text-secondary);
    font-size: 0.65rem;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    line-height: 1;
  }

  .quiet {
    margin: 0.4rem 0.35rem;
    font-size: 0.8rem;
    color: var(--text-tertiary);
  }
</style>
