<script lang="ts">
  export let label: string = '';
  export let title: string = '';
  export let danger: boolean = false;
  export let disabled: boolean = false;
  export let onClick: () => void = () => {};
  export let buttonRef: HTMLButtonElement | undefined = undefined;
  // Marks this button as the modal's initial focus target. Modal.svelte
  // queries for [data-autofocus] after showModal(), so the attribute has
  // to be in the markup rather than set from a bound ref.
  export let initialFocus: boolean = false;

  // One form: bracketed text. Brackets are the affordance marker the design
  // conventions name alongside color and glow, and the label is the button's
  // accessible name — nothing here is icon-only.
</script>

<button
  type="button"
  class="action-btn"
  class:danger
  {disabled}
  data-autofocus={initialFocus || undefined}
  on:click={onClick}
  bind:this={buttonRef}
  title={title || label}
>
  <span>{label}</span>
</button>
