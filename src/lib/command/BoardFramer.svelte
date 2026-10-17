<script lang="ts">
  // Frames cards in the board's viewport when `request` changes — a launch
  // frames the live cards (design §5.2). It sits inside <SvelteFlow>, where
  // the viewport's controls are reachable.
  import { useSvelteFlow } from '@xyflow/svelte';

  /** Card ids to frame; a new object asks again. Empty frames everything. */
  export let request: { ids: string[] } | null = null;
  /** Px of the board's left edge something floats over (Board's covered):
   *  the cards are framed a grid square clear of it. */
  export let covered = 0;

  const flow = useSvelteFlow();
  let last: { ids: string[] } | null = null;

  $: if (request && request !== last) {
    last = request;
    const ids = request.ids;
    // After the nodes the request came with are laid out.
    requestAnimationFrame(() => {
      void flow.fitView({
        nodes: ids.length ? ids.map((id) => ({ id })) : undefined,
        padding: covered ? { x: 0.15, y: 0.15, left: `${covered + 24}px` } : 0.15,
        maxZoom: 1.1,
        duration: 250,
      });
    });
  }
</script>
