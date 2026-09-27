<script lang="ts">
  import { SHIELD } from '../ui/iconPaths';

  export let tag: string;
</script>

<span class="game-system-badge" title={tag}>
  <!-- Shield — a game system -->
  <svg class="badge-die" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round" aria-hidden="true">
    <path d={SHIELD}/>
  </svg>
  {tag}
</span>

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
</style>
