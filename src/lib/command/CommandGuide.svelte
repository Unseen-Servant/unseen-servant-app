<script lang="ts">
  import type { Snippet } from 'svelte';
  import { ParaglideMessage } from '@inlang/paraglide-js-svelte';
  import { m } from '../paraglide/messages';
</script>

{#snippet em({ children }: { children?: Snippet })}<em>{@render children?.()}</em>{/snippet}
{#snippet strong({ children }: { children?: Snippet })}<strong>{@render children?.()}</strong>{/snippet}

<!-- Help → Guides for Command: the loop from a campaign to the table, one
     step per section, in the Legend Lore guide's shape
     (GettingStartedSteps.svelte). -->
<div class="manual">
  <section class="field">
    <h3 class="field-title section-title">{m.command_guide_campaigns()}</h3>
    <p class="field-desc"><ParaglideMessage message={m.command_guide_campaigns_desc} {em} /></p>
  </section>

  <section class="field">
    <h3 class="field-title section-title">{m.command_guide_tracks()}</h3>
    <p class="field-desc"><ParaglideMessage message={m.command_guide_tracks_desc} {em} {strong} /></p>
  </section>

  <section class="field">
    <h3 class="field-title section-title">{m.command_guide_beats()}</h3>
    <p class="field-desc"><ParaglideMessage message={m.command_guide_beats_desc} {em} {strong} /></p>
  </section>

  <section class="field">
    <h3 class="field-title section-title">{m.command_guide_play()}</h3>
    <p class="field-desc"><ParaglideMessage message={m.command_guide_play_desc} {em} {strong} /></p>
  </section>

  <section class="field">
    <h3 class="field-title section-title">{m.command_guide_tools()}</h3>
    <p class="field-desc"><ParaglideMessage message={m.command_guide_tools_desc} {strong} /></p>
    <p class="field-desc"><ParaglideMessage message={m.command_guide_tools_select} {strong} /></p>
    <p class="field-desc">{m.command_guide_tools_arrange()}</p>
  </section>

  <section class="field">
    <h3 class="field-title section-title">{m.command_guide_images()}</h3>
    <p class="field-desc"><ParaglideMessage message={m.command_guide_images_desc} {em} /></p>
    <p class="field-desc">{m.command_guide_images_beat()}</p>
    <p class="field-desc"><ParaglideMessage message={m.command_guide_images_tracks} {em} {strong} /></p>
  </section>

  <section class="field">
    <h3 class="field-title section-title">{m.command_guide_session()}</h3>
    <p class="field-desc"><ParaglideMessage message={m.command_guide_session_desc} {strong} /></p>
  </section>
</div>

<style>
  /* GettingStartedSteps' vocabulary: stacked .field sections, Almendra
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
