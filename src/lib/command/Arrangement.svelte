<script lang="ts">
  // Play's arrangement (design §5.2): the session's plan, each beat with
  // its play key and the times it was launched, then the log as it was
  // written, and the jot line that adds to it.
  import { PLAY } from '../ui/iconPaths';
  import type { PlanRow } from './prep';
  import type { BeatEntry, LogEntry } from './types';

  export let rows: PlanRow[];
  export let log: LogEntry[];
  /** The beat the live set was launched from. */
  export let liveBeat: string | null;
  export let onLaunch: (beat: BeatEntry) => void;
  /** Clears the live set: the live beat's key, as in Prep. */
  export let onStop: () => void;
  export let onShow: (beat: BeatEntry) => void;
  export let onEdit: (beat: BeatEntry) => void;
  export let onJot: (text: string) => void;

  let jot = '';
  let logEl: HTMLElement | undefined;

  const GLYPHS: Record<LogEntry['kind'], string> = {
    launch: '▶',
    spent: '✓',
    unspent: '○',
    captured: '+',
    jot: '·',
  };

  /** When each beat was launched, from the log. */
  $: launches = log.reduce((out, e) => {
    if (e.kind === 'launch' && e.path && e.time) out.set(e.path, [...(out.get(e.path) ?? []), e.time]);
    return out;
  }, new Map<string, string[]>());

  // The newest entry stays in view as the log grows.
  $: if (logEl && log.length) requestAnimationFrame(() => logEl && (logEl.scrollTop = logEl.scrollHeight));

  function submit() {
    const text = jot.trim();
    if (!text) return;
    jot = '';
    onJot(text);
  }
</script>

<section class="arrangement" aria-label="Arrangement">
  <header class="nameplate">
    <span class="ledger-label">plan</span>
    <span class="count">{rows.length}</span>
  </header>
  <div class="plan">
    {#each rows as row (row.at + ':' + row.link)}
      {#if row.beat}
        {@const beat = row.beat}
        {@const playing = beat.path === liveBeat}
        <div class="beat-row" class:spent={!!beat.spent}>
          <!-- The live beat's key is the lit ■ that stops it, as in Prep:
               launching it again would only log it twice. -->
          <button
            type="button"
            class="play-key"
            class:playing
            aria-pressed={playing}
            title={playing ? `Stop ${beat.name}` : `Launch ${beat.name}`}
            on:click={() => (playing ? onStop() : onLaunch(beat))}
          >
            {#if playing}
              <span class="stop-mark" aria-hidden="true"></span>
            {:else}
              <svg viewBox="0 0 640 640" fill="currentColor" aria-hidden="true"><path d={PLAY} /></svg>
            {/if}
          </button>
          <button
            type="button"
            class="beat-name"
            title={`Show ${beat.name} on the board — double-click to edit it`}
            on:click={() => onShow(beat)}
            on:dblclick={() => onEdit(beat)}
          >
            {beat.name}
          </button>
          {#if launches.get(beat.path)}
            <span class="times">{launches.get(beat.path)?.join(' · ')}</span>
          {/if}
          {#if beat.spent}<span class="spent-mark" aria-label="spent">✓</span>{/if}
        </div>
      {:else}
        <div class="beat-row missing" title={`No beat is named “${row.link}” yet`}>
          <span class="key-spacer"></span>
          <span class="beat-name">{row.link}</span>
        </div>
      {/if}
    {:else}
      <p class="quiet">Nothing planned. Beats added to the session in Prep show here.</p>
    {/each}
  </div>

  <header class="nameplate log-head">
    <span class="ledger-label">log</span>
  </header>
  <ol class="log" bind:this={logEl}>
    {#each log as entry, i (i)}
      <li class="entry {entry.kind}">
        <span class="time">{entry.time ?? ''}</span>
        <span class="glyph" aria-hidden="true">{GLYPHS[entry.kind]}</span>
        <span class="what">{entry.kind === 'jot' ? entry.text : entry.link}</span>
      </li>
    {:else}
      <li class="quiet">What happens at the table lands here.</li>
    {/each}
  </ol>
  <form class="jot-line" on:submit|preventDefault={submit}>
    <input
      type="text"
      bind:value={jot}
      placeholder="jot…"
      aria-label="Add a line to the log"
      spellcheck="false"
    />
  </form>
</section>

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

  .log-head {
    border-top: 1px solid var(--border-subtle);
  }

  .count {
    margin-left: auto;
    font-size: 0.75rem;
    font-variant-numeric: tabular-nums;
    color: var(--text-tertiary);
  }

  .plan {
    flex: 0 1 auto;
    max-height: 45%;
    overflow-y: auto;
    padding: 0.25rem;
  }

  .beat-row {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.15rem 0.35rem;
    font-size: 0.9rem;
    line-height: 1.5;
  }

  .beat-row:hover {
    background: var(--bg-focused);
  }

  /* The live beat wears only its lit key (design §5.1, beat states). */
  .beat-row.spent .beat-name {
    opacity: var(--opacity-out-of-scope);
  }

  .beat-row.spent:hover .beat-name {
    opacity: var(--opacity-out-of-scope-hover);
  }

  .beat-name {
    flex: 1;
    min-width: 0;
    padding: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    background: none;
    border: none;
    font: inherit;
    text-align: left;
    color: var(--text-primary);
    cursor: pointer;
  }

  .beat-row.missing .beat-name {
    color: var(--text-secondary);
    text-decoration: underline dashed;
    text-decoration-color: var(--text-accent);
    text-underline-offset: 3px;
    cursor: default;
  }

  /* Legend Lore's transport key (CollectionsPanel .tr-btn). */
  .play-key,
  .key-spacer {
    flex-shrink: 0;
    width: 18px;
    height: 18px;
  }

  .play-key {
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

  .play-key svg {
    width: 9px;
    height: 9px;
    display: block;
  }

  .play-key:hover {
    color: var(--text-secondary);
    border-color: var(--text-secondary);
  }

  .play-key:active {
    transform: scale(0.97);
  }

  .play-key.playing {
    color: var(--text-active);
    border-color: var(--text-active);
    background: color-mix(in srgb, var(--text-active) 15%, transparent);
    filter: var(--glow-active);
  }

  /* Prep's stop mark (BeatColumn .stop-mark). */
  .stop-mark {
    width: 6px;
    height: 6px;
    background: currentColor;
  }

  .times,
  .spent-mark {
    flex-shrink: 0;
    font-size: 0.72rem;
    font-variant-numeric: tabular-nums;
    color: var(--text-tertiary);
  }

  .log {
    flex: 1;
    min-height: 0;
    margin: 0;
    padding: 0.35rem 0.6rem;
    overflow-y: auto;
    list-style: none;
  }

  .entry {
    display: flex;
    align-items: baseline;
    gap: 0.4rem;
    font-size: 0.85rem;
    line-height: 1.45;
  }

  .time {
    flex: 0 0 2.6rem;
    font-size: 0.72rem;
    font-variant-numeric: tabular-nums;
    color: var(--text-tertiary);
  }

  .glyph {
    flex: 0 0 0.8rem;
    font-size: 0.72rem;
    text-align: center;
    color: var(--text-tertiary);
  }

  .what {
    min-width: 0;
    color: var(--text-primary);
  }

  .entry:not(.jot) .what {
    color: var(--text-accent);
  }

  .quiet {
    margin: 0.4rem 0.35rem;
    font-size: 0.8rem;
    color: var(--text-tertiary);
  }

  .jot-line {
    flex-shrink: 0;
    padding: 0.4rem 0.5rem 0.5rem;
    border-top: 1px solid var(--border-subtle);
  }

  .jot-line input {
    width: 100%;
    box-sizing: border-box;
    padding: 0.25rem 0.45rem;
    background: var(--bg-container);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    font-family: var(--font-body);
    font-size: 0.85rem;
    color: var(--text-primary);
  }

  .jot-line input:focus {
    outline: none;
    border-color: var(--text-accent);
  }
</style>
