<script lang="ts">
  import type { Snippet } from 'svelte';
  import { ParaglideMessage } from '@inlang/paraglide-js-svelte';
  import { m } from '../paraglide/messages';
</script>

{#snippet em({ children }: { children?: Snippet })}<em>{@render children?.()}</em>{/snippet}
{#snippet strong({ children }: { children?: Snippet })}<strong>{@render children?.()}</strong>{/snippet}

<!-- Help → Guides for Augury: rolling first, then what the readout says,
     then the sets, in Command's guide's shape (CommandGuide.svelte). -->
<div class="manual">
  <section class="field">
    <h3 class="field-title section-title">{m.augury_guide_rolling()}</h3>
    <p class="field-desc"><ParaglideMessage message={m.augury_guide_rolling_desc} {em} {strong} /></p>
  </section>

  <section class="field">
    <h3 class="field-title section-title">{m.augury_guide_readout()}</h3>
    <p class="field-desc">{m.augury_guide_readout_desc()}</p>
  </section>

  <section class="field">
    <h3 class="field-title section-title">{m.augury_guide_bonus()}</h3>
    <p class="field-desc"><ParaglideMessage message={m.augury_guide_bonus_desc} {strong} /></p>
  </section>

  <section class="field">
    <h3 class="field-title section-title">{m.augury_guide_sets()}</h3>
    <p class="field-desc"><ParaglideMessage message={m.augury_guide_sets_desc} {em} /></p>
  </section>

  <section class="field">
    <h3 class="field-title section-title">{m.augury_guide_words()}</h3>
    <p class="field-desc"><ParaglideMessage message={m.augury_guide_words_desc} {em} /></p>
  </section>

  <section class="field">
    <h3 class="field-title section-title">{m.augury_guide_custom()}</h3>
    <p class="field-desc"><ParaglideMessage message={m.augury_guide_custom_desc} {em} {strong} /></p>
  </section>
</div>

<style>
  /* CommandGuide's vocabulary, verbatim: stacked .field sections, Almendra
     titles, body text at 0.85rem. */
  .manual {
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
    width: 100%;
    font-family: var(--font-body);
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: 0.45rem;
  }

  .field-title {
    margin: 0;
  }

  .field-desc {
    font-family: var(--font-body);
    font-size: 0.85rem;
    color: var(--text-secondary);
    line-height: 1.45;
    margin: 0;
  }
  .field-desc strong {
    color: var(--text-primary);
    font-weight: 600;
  }
  .field-desc em {
    font-style: italic;
  }
</style>
