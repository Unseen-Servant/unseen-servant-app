<script lang="ts">
  export let kind: 'confirm' | 'discard' = 'confirm';
  export let label: string = '';
  export let title: string = '';
  export let danger: boolean = false;
  export let compact: boolean = false;
  export let disabled: boolean = false;
  export let onClick: () => void = () => {};
  export let buttonRef: HTMLButtonElement | undefined = undefined;
  // Marks this button as the modal's initial focus target. Modal.svelte
  // queries for [data-autofocus] after showModal(), so the attribute has
  // to be in the markup rather than set from a bound ref.
  export let initialFocus: boolean = false;
</script>

<button
  type="button"
  class="action-btn"
  class:confirm={kind === 'confirm'}
  class:discard={kind === 'discard'}
  class:danger
  class:compact
  {disabled}
  data-autofocus={initialFocus || undefined}
  on:click={onClick}
  bind:this={buttonRef}
  title={title || label}
  aria-label={label || title || (kind === 'confirm' ? 'Confirm' : 'Discard')}
>
  {#if kind === 'confirm'}
    <!-- Font Awesome "circle-check" (static/icons/circle-check-solid-full.svg) -->
    <svg viewBox="0 0 640 640" fill="currentColor" aria-hidden="true">
      <path d="M320 576C178.6 576 64 461.4 64 320C64 178.6 178.6 64 320 64C461.4 64 576 178.6 576 320C576 461.4 461.4 576 320 576zM438 209.7C427.3 201.9 412.3 204.3 404.5 215L285.1 379.2L233 327.1C223.6 317.7 208.4 317.7 199.1 327.1C189.8 336.5 189.7 351.7 199.1 361L271.1 433C276.1 438 282.9 440.5 289.9 440C296.9 439.5 303.3 435.9 307.4 430.2L443.3 243.2C451.1 232.5 448.7 217.5 438 209.7z"/>
    </svg>
  {:else}
    <!-- Font Awesome "circle-xmark" (static/icons/circle-xmark-solid-full.svg) -->
    <svg viewBox="0 0 640 640" fill="currentColor" aria-hidden="true">
      <path d="M320 576C461.4 576 576 461.4 576 320C576 178.6 461.4 64 320 64C178.6 64 64 178.6 64 320C64 461.4 178.6 576 320 576zM231 231C240.4 221.6 255.6 221.6 264.9 231L319.9 286L374.9 231C384.3 221.6 399.5 221.6 408.8 231C418.1 240.4 418.2 255.6 408.8 264.9L353.8 319.9L408.8 374.9C418.2 384.3 418.2 399.5 408.8 408.8C399.4 418.1 384.2 418.2 374.9 408.8L319.9 353.8L264.9 408.8C255.5 418.2 240.3 418.2 231 408.8C221.7 399.4 221.6 384.2 231 374.9L286 319.9L231 264.9C221.6 255.5 221.6 240.3 231 231z"/>
    </svg>
  {/if}
  {#if !compact && label}
    <span>{label}</span>
  {/if}
</button>
