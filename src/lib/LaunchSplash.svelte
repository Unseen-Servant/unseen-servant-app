<script lang="ts">
  import { fade } from 'svelte/transition';

  export let visible: boolean = true;
  export let onDismiss: () => void = () => {};

  function handleClick() {
    onDismiss();
  }
</script>

{#if visible}
  <div
    class="splash"
    role="presentation"
    on:click={handleClick}
    transition:fade={{ duration: 200 }}
  >
    <div class="stack">
      <img class="icon" src="/icon.png" alt="" draggable="false" />
      <h1 class="title font-heading">Legend Lore</h1>
      <span class="byline">Unseen Servant</span>
    </div>
  </div>
{/if}

<style>
  .splash {
    position: fixed;
    inset: 0;
    z-index: 9999;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--bg-container);
    cursor: default;
    user-select: none;
    -webkit-user-select: none;
  }

  .stack {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.6rem;
  }

  .icon {
    width: 96px;
    height: 96px;
    image-rendering: -webkit-optimize-contrast;
    pointer-events: none;
  }

  .title {
    margin: 0;
    font-size: 1.6rem;
    color: var(--text-primary);
    letter-spacing: 0.02em;
  }

  .byline {
    font-family: var(--font-heading, var(--font-body));
    font-size: 0.7rem;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--text-tertiary);
  }
</style>
