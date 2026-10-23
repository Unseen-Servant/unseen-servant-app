<script lang="ts">
  import type { KnownGameSystem } from './types';
  import { SHIELD } from '../ui/iconPaths';
  import { m } from '../paraglide/messages';

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
    <!-- Shield — one ink for every system -->
    <svg class="sys-die" viewBox="0 0 24 24" fill="none" stroke="var(--text-secondary)" stroke-width="2.2" stroke-linejoin="round" aria-hidden="true">
      <path d={SHIELD}/>
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
    {m.lore_systemtag_clear()}
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
     primary ink: identity rides on the shield, the same way a collection row
     carries its pigment in the gem and not the name. */
  .sys-tag {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-weight: 600;
  }
</style>
