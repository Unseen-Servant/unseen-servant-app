<script>
  import '../app.css';
  import { keepLinksOffTheWebview } from '../lib/ui/links';
</script>

<!-- Under every tool's own link handling, in every window. -->
<svelte:document on:click={keepLinksOffTheWebview} />

<slot />
