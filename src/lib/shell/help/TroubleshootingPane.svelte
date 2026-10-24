<script lang="ts">
  import type { Snippet } from 'svelte';
  import { openUrl } from '@tauri-apps/plugin-opener';
  import { ParaglideMessage } from '@inlang/paraglide-js-svelte';
  import { m } from '../../paraglide/messages';

  export let onOpenDataDir: () => void = () => {};

  const SUPPORT_EMAIL = 'guild@unseenservant.games';
</script>

{#snippet em({ children }: { children?: Snippet })}<em>{@render children?.()}</em>{/snippet}

<!-- One entry per problem, found by the messages the app shows for it
     (quoted as the code words them), then what to do. -->
<div class="pane">
  <section class="entry">
    <h3 class="entry-title section-title">{m.trouble_embedder()}</h3>
    <p class="shows">{m.trouble_embedder_shows()}</p>
    <p class="fix"><ParaglideMessage message={m.trouble_embedder_fix} {em} /></p>
  </section>

  <section class="entry">
    <h3 class="entry-title section-title">{m.trouble_index()}</h3>
    <p class="shows">{m.trouble_index_shows()}</p>
    <p class="fix"><ParaglideMessage message={m.trouble_index_fix} {em} /></p>
  </section>

  <section class="entry">
    <h3 class="entry-title section-title">{m.trouble_weak()}</h3>
    <p class="shows">{m.trouble_weak_shows()}</p>
    <p class="fix">
      <ParaglideMessage message={m.trouble_weak_fix} {em}>
        {#snippet strong({ children })}<strong>{@render children?.()}</strong>{/snippet}
      </ParaglideMessage>
    </p>
  </section>

  <section class="entry">
    <h3 class="entry-title section-title">{m.trouble_mcp()}</h3>
    <p class="shows">{m.trouble_mcp_shows()}</p>
    <p class="fix">{m.trouble_mcp_fix()}</p>
  </section>

  <section class="entry">
    <h3 class="entry-title section-title">{m.trouble_offline()}</h3>
    <p class="shows">{m.trouble_offline_shows()}</p>
    <p class="fix"><ParaglideMessage message={m.trouble_offline_fix} {em} /></p>
    <button class="btn-link" on:click={onOpenDataDir}>{m.trouble_offline_reveal()}</button>
  </section>

  <section class="entry">
    <h3 class="entry-title section-title">{m.trouble_library()}</h3>
    <p class="shows">{m.trouble_library_shows()}</p>
    <p class="fix"><ParaglideMessage message={m.trouble_library_fix} {em} /></p>
  </section>

  <section class="entry">
    <h3 class="entry-title section-title">{m.trouble_campaigns()}</h3>
    <p class="shows">{m.trouble_campaigns_shows()}</p>
    <p class="fix"><ParaglideMessage message={m.trouble_campaigns_fix} {em} /></p>
  </section>

  <section class="entry">
    <h3 class="entry-title section-title">{m.trouble_stuck()}</h3>
    <p class="fix"><ParaglideMessage message={m.trouble_stuck_fix} {em} /></p>
    <button class="btn-link" on:click={() => openUrl(`mailto:${SUPPORT_EMAIL}`).catch(() => {})}>{SUPPORT_EMAIL}</button>
  </section>
</div>

<style>
  /* Same vocabulary as the Guides steps (GettingStartedSteps.svelte):
     Almendra titles, body text at 0.85rem, bracketed actions. The quoted
     messages sit a step quieter, so the eye lands on the fix. */
  .pane {
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
    font-family: var(--font-body);
  }

  .entry {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
  }

  .entry-title {
    margin: 0;
  }

  .shows {
    margin: 0;
    font-size: 0.78rem;
    font-style: italic;
    color: var(--text-tertiary);
    line-height: 1.4;
  }

  .fix {
    margin: 0;
    font-size: 0.85rem;
    color: var(--text-secondary);
    line-height: 1.45;
  }
  .fix strong {
    color: var(--text-primary);
    font-weight: 600;
  }
  .fix em {
    font-style: italic;
  }

  .btn-link {
    align-self: flex-start;
  }
</style>
