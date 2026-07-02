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
      <div class="icon-wrap">
        <div class="glow" aria-hidden="true"></div>
        <img class="icon" src="/logo.svg" alt="" draggable="false" />
      </div>
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
    background: var(--bg-app);
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

  .icon-wrap {
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .glow {
    position: absolute;
    inset: -40%;
    border-radius: 50%;
    background: radial-gradient(
      circle,
      color-mix(in srgb, var(--text-accent) 45%, transparent) 0%,
      transparent 70%
    );
    opacity: 0;
    pointer-events: none;
    animation: glow-in 900ms ease-out forwards;
  }

  .icon {
    width: 96px;
    height: 96px;
    image-rendering: -webkit-optimize-contrast;
    pointer-events: none;
    animation: icon-pulse 2.4s ease-in-out infinite;
  }

  .title {
    margin: 0;
    font-size: 1.6rem;
    color: var(--text-primary);
    letter-spacing: 0.02em;
    opacity: 0;
    animation: rise-in 300ms ease-out 200ms forwards;
  }

  .byline {
    font-family: var(--font-heading, var(--font-body));
    font-size: 0.7rem;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--text-tertiary);
    opacity: 0;
    animation: rise-in 300ms ease-out 350ms forwards;
  }

  @keyframes icon-pulse {
    0%, 100% { transform: scale(1); }
    50% { transform: scale(1.04); }
  }

  @keyframes rise-in {
    from { opacity: 0; transform: translateY(6px); }
    to { opacity: 1; transform: translateY(0); }
  }

  @keyframes glow-in {
    0% { opacity: 0; }
    45% { opacity: 1; }
    100% { opacity: 0.35; }
  }

  @media (prefers-reduced-motion: reduce) {
    .icon {
      animation: none;
      transform: none;
    }
    .title,
    .byline {
      animation: none;
      opacity: 1;
      transform: none;
    }
    .glow {
      animation: none;
      opacity: 0.25;
    }
  }
</style>
