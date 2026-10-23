<script lang="ts">
  // Command's section of the status bar: where the table is — campaign and
  // session — and the beat that's live. The panel hoists it into the slot
  // its host keeps in the bar (PANELS.md); the bar's own styles dress the
  // rules.
  import { m } from '../paraglide/messages';

  export let campaign: string | null;
  export let session: string | null;
  export let liveBeat: string | null;
</script>

{#if campaign}
  <span class="rule" aria-hidden="true"></span>
  <span class="where" title={session ? m.command_session_where({ campaign, session }) : campaign}>
    <span class="name">{campaign}</span>
    {#if session}
      <span class="sep" aria-hidden="true">›</span>
      <span class="name">{session}</span>
    {/if}
  </span>
  {#if liveBeat}
    <span class="rule" aria-hidden="true"></span>
    <span class="live" title={m.command_session_live({ beat: liveBeat })}>
      <span class="cell" aria-hidden="true"></span>
      <span class="name beat">{liveBeat}</span>
    </span>
  {/if}
{/if}

<style>
  .where,
  .live {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
  }
  .name {
    max-width: 24ch;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .sep {
    color: var(--text-tertiary);
  }
  /* Live is playing: the transport's purple cell, as on a tool's key, ahead
     of the beat's name in parchment — the beat is content. */
  .cell {
    width: 6px;
    height: 6px;
    border-radius: var(--radius-cell);
    background: var(--text-active);
    filter: var(--glow-active);
  }
  .beat {
    color: var(--text-accent);
  }
</style>
