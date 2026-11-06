<script lang="ts">
  import type { Snippet } from 'svelte';
  import { ParaglideMessage } from '@inlang/paraglide-js-svelte';
  import { m } from '../paraglide/messages';
</script>

{#snippet em({ children }: { children?: Snippet })}<em>{@render children?.()}</em>{/snippet}
{#snippet strong({ children }: { children?: Snippet })}<strong>{@render children?.()}</strong>{/snippet}

<!-- Help → Guides for Foresight: an encounter from its first row to its
     clearing, in Command's guide's shape (CommandGuide.svelte). -->
<div class="manual">
  <section class="field">
    <h3 class="field-title section-title">{m.foresight_guide_start()}</h3>
    <p class="field-desc"><ParaglideMessage message={m.foresight_guide_start_desc} {em} /></p>
    <p class="field-desc">{m.foresight_guide_start_note()}</p>
  </section>

  <section class="field">
    <h3 class="field-title section-title">{m.foresight_guide_turns()}</h3>
    <p class="field-desc"><ParaglideMessage message={m.foresight_guide_turns_desc} {strong} /></p>
  </section>

  <section class="field">
    <h3 class="field-title section-title">{m.foresight_guide_rows()}</h3>
    <p class="field-desc"><ParaglideMessage message={m.foresight_guide_rows_desc} {strong} /></p>
  </section>

  <section class="field">
    <h3 class="field-title section-title">{m.foresight_guide_out()}</h3>
    <p class="field-desc"><ParaglideMessage message={m.foresight_guide_out_desc} {strong} /></p>
  </section>

  <section class="field">
    <h3 class="field-title section-title">{m.foresight_guide_columns()}</h3>
    <p class="field-desc"><ParaglideMessage message={m.foresight_guide_columns_desc} {em} {strong} /></p>
    <p class="field-desc"><ParaglideMessage message={m.foresight_guide_cells} {em} {strong} /></p>
  </section>

  <section class="field">
    <h3 class="field-title section-title">{m.foresight_guide_notes()}</h3>
    <p class="field-desc"><ParaglideMessage message={m.foresight_guide_notes_desc} {em} /></p>
    <p class="field-desc"><ParaglideMessage message={m.foresight_guide_notes_open} {em} /></p>
    <p class="field-desc"><ParaglideMessage message={m.foresight_guide_notes_encounter} {em} /></p>
    <p class="field-desc"><ParaglideMessage message={m.foresight_guide_notes_windows} {strong} /></p>
  </section>

  <section class="field">
    <h3 class="field-title section-title">{m.foresight_guide_clear()}</h3>
    <p class="field-desc">{m.foresight_guide_clear_desc()}</p>
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
