<script lang="ts">
  import type { KnownGameSystem } from './types';

  // The rows behind both game-system pickers: the tree row's context-menu
  // submenu and the standalone SystemTagMenu. Rendered straight into the
  // caller's menu element with no wrapper, so the caller's own row queries
  // (`.submenu > [data-mi]`) still see them as direct children.
  export let knownSystems: KnownGameSystem[] = [];
  export let tags: string[] = [];
  // One tag per call — each surface already owned the merge into the full
  // array, and the clear handler differs too (the dropdown closes itself).
  export let onToggle: (tag: string) => void = () => {};
  export let onClear: () => void = () => {};
</script>

{#each knownSystems as sys}
  <button
    class="menu-row"
    data-mi="item"
    role="menuitemcheckbox"
    aria-checked={tags.includes(sys.tag)}
    on:click={() => onToggle(sys.tag)}
  >
    <span class="menu-pip" class:on={tags.includes(sys.tag)} aria-hidden="true"></span>
    <!-- Font Awesome "dice-d6" — one fill for every system -->
    <svg class="sys-die" viewBox="0 0 640 640" fill="var(--text-secondary)" aria-hidden="true">
      <path d="M288.4 72.3C308 61.2 332 61.2 351.6 72.3L527.6 172C547.6 183.4 560 204.6 560 227.7L560 425.1C560 448.1 547.6 469.4 527.6 480.8L351.6 580.5C332 591.6 308 591.6 288.5 580.5L112.5 480.8C92.4 469.5 80 448.2 80 425.2L80 227.8C80 204.8 92.4 183.5 112.4 172.1L288.4 72.4zM166.6 219.6C157.8 216.5 147.8 219.9 142.8 228.2C137.8 236.5 139.6 246.9 146.4 253.2L149.6 255.6L299.8 345.8L299.8 494.5C299.8 505.5 308.8 514.5 319.8 514.5C330.8 514.5 339.8 505.5 339.8 494.5L339.8 345.8L490.1 255.6C499.6 249.9 502.7 237.6 497 228.2C491.3 218.8 479 215.7 469.6 221.3L319.9 311.1L170.2 221.3L166.5 219.6z"/>
    </svg>
    <span class="sys-tag" title={sys.tag}>{sys.tag}</span>
  </button>
{/each}
<!-- Only a divider with something on both sides of it: a file tagged with a
     system that has since been disabled in Settings has no rows above, and
     the menu would otherwise open on a rule. -->
{#if knownSystems.length > 0 && tags.length > 0}
  <hr class="menu-divider" />
{/if}
{#if tags.length > 0}
  <button class="menu-row danger" data-mi="item" role="menuitem" on:click={onClear}>
    Clear tags
  </button>
{/if}

<style>
  .sys-die {
    width: 11px;
    height: 11px;
    flex-shrink: 0;
  }
  /* Tags are user-written and uncapped — ellipsize against --menu-max-width
     rather than stretching the menu or scrolling it sideways. The label stays
     primary ink: identity rides on the die, the same way a collection row
     carries its pigment in the ribbon and not the name. */
  .sys-tag {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-weight: 600;
  }
</style>
