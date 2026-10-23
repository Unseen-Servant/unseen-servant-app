<script lang="ts">
  import { ParaglideMessage } from '@inlang/paraglide-js-svelte';
  import ReadyTag from '../shell/help/ReadyTag.svelte';
  import { m } from '../paraglide/messages';

  export let mcpConnected: boolean = false;
  export let onCopyMcpConfig: () => void;
</script>

<!-- Help → Guides for the Servant: an AI agent reaching both tools over MCP,
     in the Legend Lore guide's shape (GettingStartedSteps.svelte). Any MCP
     client: the guide names none. -->
<div class="manual">
  <section class="field">
    <div class="field-title-row">
      <h3 class="field-title section-title">
        <ParaglideMessage message={m.servant_guide_agent}>
          {#snippet opt({ children })}<span class="opt">{@render children?.()}</span>{/snippet}
        </ParaglideMessage>
      </h3>
      <ReadyTag lit={mcpConnected} state={mcpConnected ? m.servant_guide_connected() : m.servant_guide_not_detected()} />
    </div>
    <p class="field-desc">{m.servant_guide_intro()}</p>
    <button class="btn-link" on:click={onCopyMcpConfig}>{m.servant_guide_copy()}</button>
    <p class="field-desc">
      <ParaglideMessage message={m.servant_guide_paste}>
        {#snippet em({ children })}<em>{@render children?.()}</em>{/snippet}
      </ParaglideMessage>
    </p>
    <p class="field-desc">{m.servant_guide_scope()}</p>
  </section>
</div>

<style>
  /* GettingStartedSteps' vocabulary: .field sections, Almendra titles with
     the step's ReadyTag at the right, body text at 0.85rem. */
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

  .field-title-row {
    display: flex;
    align-items: baseline;
    gap: 0.75rem;
  }

  .field-title {
    flex: 1;
    min-width: 0;
    margin: 0;
  }

  .opt {
    font-family: var(--font-body);
    font-size: 0.78rem;
    color: var(--text-tertiary);
    font-weight: normal;
    margin-left: 0.3rem;
  }

  .field-desc {
    font-family: var(--font-body);
    font-size: 0.85rem;
    color: var(--text-secondary);
    line-height: 1.45;
    margin: 0;
  }
  .field-desc em {
    font-style: italic;
  }

  .btn-link {
    align-self: flex-start;
  }
</style>
