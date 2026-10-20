<script lang="ts">
  // Hands the board Svelte Flow's projection from the screen to the board's
  // own coordinates, for the toolbar's clicks and drags (Board's overlay).
  // It sits inside <SvelteFlow>, where the flow is reachable, as
  // BoardFramer does.
  import { useSvelteFlow, type XYPosition } from '@xyflow/svelte';

  export let toBoard: (point: XYPosition) => XYPosition;

  const flow = useSvelteFlow();
  toBoard = (point) => flow.screenToFlowPosition(point);
</script>
