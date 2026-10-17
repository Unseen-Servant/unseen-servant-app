<script lang="ts">
  import StandaloneFrame from '../../../lib/shell/StandaloneFrame.svelte';
  import type { PageData } from './$types';

  export let data: PageData;
</script>

<StandaloneFrame id={data.id} />
