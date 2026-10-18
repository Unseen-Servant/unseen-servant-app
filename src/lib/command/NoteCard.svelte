<script lang="ts">
  // A card on the session board (design §5.2): a note's face (CardFace),
  // sized by the GM to show as much of it as the table needs, with the
  // points its lines connect to.
  import { Handle, NodeResizer, Position } from '@xyflow/svelte';
  import { getContext } from 'svelte';
  import CardFace from './CardFace.svelte';
  import { CARD_ACTIONS, type CardActions, type CardData } from './board';

  export let data: CardData;
  export let selected: boolean = false;

  const actions = getContext<CardActions>(CARD_ACTIONS);
  const SIDES = [
    ['top', Position.Top],
    ['right', Position.Right],
    ['bottom', Position.Bottom],
    ['left', Position.Left],
  ] as const;
</script>

<NodeResizer
  minWidth={140}
  minHeight={56}
  isVisible={selected}
  onResizeEnd={(_, frame) => actions.frame(data.card, frame)}
/>
{#each SIDES as [id, position] (id)}
  <Handle type="source" {id} {position} />
{/each}
<CardFace {data} />
