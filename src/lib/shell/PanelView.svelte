<script lang="ts">
  // The one place a panel id becomes a component. Both hosts — the main
  // window's tabs and a pop-out's frame — render panels only through here,
  // which is what keeps a panel the same docked or standalone (PANELS.md).
  import LegendLorePanel from '../legend-lore/LegendLorePanel.svelte';
  import CommandPanel from '../command/CommandPanel.svelte';
  import ServantPanel from '../servant/ServantPanel.svelte';
  import type { Snippet } from 'svelte';
  import type { PanelId } from './panels';

  export let id: PanelId;
  export let active: boolean;
  // The host's dock toggle. A panel without a header of its own leaves it
  // out (PANELS.md).
  export let windowKey: Snippet;
</script>

{#if id === 'legend-lore'}
  <LegendLorePanel {active} {windowKey} />
{:else if id === 'command'}
  <CommandPanel {active} {windowKey} />
{:else}
  <ServantPanel />
{/if}
