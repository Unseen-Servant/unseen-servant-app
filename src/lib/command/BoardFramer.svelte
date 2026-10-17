<script lang="ts">
  // Frames cards in the board's viewport when `request` changes — a launch
  // frames the live cards (design §5.2) — and says where the viewport was
  // left when the board closes, so it opens there again. It sits inside
  // <SvelteFlow>, where the viewport's controls are reachable.
  import { onDestroy } from 'svelte';
  import { useSvelteFlow, type Viewport } from '@xyflow/svelte';

  /** Card ids to frame; a new object asks again. Empty frames everything. */
  export let request: { ids: string[] } | null = null;
  /** Px of the board's left edge something floats over (Board's covered):
   *  the cards are framed a grid square clear of it. */
  export let covered = 0;
  /** Told the viewport as the board closes (Board's onLeave). */
  export let onLeave: (viewport: Viewport) => void;

  const flow = useSvelteFlow();
  onDestroy(() => onLeave(flow.getViewport()));
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
