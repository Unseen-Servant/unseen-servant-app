<script lang="ts">
  // The one place a panel id becomes a component. Both hosts — the main
  // window's tabs and a pop-out's frame — render panels only through here,
  // which is what keeps a panel the same docked or standalone (PANELS.md).
  import LegendLorePanel from '../legend-lore/LegendLorePanel.svelte';
  import CommandPanel from '../command/CommandPanel.svelte';
  import ServantPanel from '../servant/ServantPanel.svelte';
  import type { PanelId } from './panels';

  export let id: PanelId;
  export let active: boolean;
</script>

{#if id === 'legend-lore'}
  <LegendLorePanel {active} />
{:else if id === 'command'}
  <CommandPanel />
{:else}
  <ServantPanel />
{/if}
