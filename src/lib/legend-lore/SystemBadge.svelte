<script lang="ts">
  import { SHIELD } from '../ui/iconPaths';

  export let tag: string;
  // Metadata, not a pill — for dense rows where the system is context
  // rather than content (the collections panel's file rows): the shield and
  // the name in small secondary text, no fill. Right-aligned in its row and
  // capped, so the file name keeps the width and a long system name is the
  // one that ellipsizes.
  export let inline = false;
</script>

{#if inline}
  <span class="sys-inline" title={tag}>
    <svg class="sys-shield" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round" aria-hidden="true">
      <path d={SHIELD}/>
    </svg>
    <span class="sys-name">{tag}</span>
  </span>
{:else}
  <span class="game-system-badge" title={tag}>
    <!-- Shield — a game system -->
    <svg class="badge-die" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round" aria-hidden="true">
      <path d={SHIELD}/>
    </svg>
    {tag}
  </span>
{/if}

<style>
  /* Monochrome parchment — systems carry a shield, not a color. The 20%
     color-mix is the one tint recipe for identity fills. */
  .game-system-badge {
    display: inline-block;
    max-width: 9rem;
    overflow: hidden;
    text-overflow: ellipsis;
    padding: 0.1rem 0.4rem;
    border-radius: var(--radius-sm);
    font-size: 0.75rem;
    font-family: var(--font-body);
    background: color-mix(in srgb, var(--text-accent) 20%, transparent);
    color: var(--text-accent);
    white-space: nowrap;
    border: 1px solid transparent;
    transition: border-color var(--transition-fast);
  }
  .badge-die {
    width: 10px;
    height: 10px;
    vertical-align: -1px;
    margin-right: 0.25rem;
  }
  /* Content-sized up to a cap, measured against the built-in tags
     (sidecar game_systems.py) at this size: 4.25rem holds the shield and
     every one whole — Black Hack is the widest at 4.17rem — except the two
     longest, Dragonbane (4.55) and MORK BORG (5.26), which lose a few
     letters to the ellipsis. The file name keeps the rest of the row; the
     row pushes the tag to the right. */
  .sys-inline {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    flex: 0 1 auto;
    min-width: 0;
    max-width: 4.25rem;
    margin-left: 0.5rem;
    font-size: 0.75rem;
    color: var(--text-secondary);
  }
  .sys-shield {
    flex-shrink: 0;
    width: 10px;
    height: 10px;
  }
  .sys-name {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
</style>
