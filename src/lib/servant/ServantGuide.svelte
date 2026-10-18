<script lang="ts">
  import ReadyTag from '../shell/help/ReadyTag.svelte';

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
        AI agent <span class="opt">(optional)</span>
      </h3>
      <ReadyTag lit={mcpConnected} state={mcpConnected ? 'Connected' : 'Not detected'} />
    </div>
    <p class="field-desc">
      An AI agent that speaks MCP can search your Legend Lore library and read
      and write your Command campaigns. Help &rarr; Reference lists its tools.
    </p>
    <button class="btn-link" on:click={onCopyMcpConfig}>copy MCP config</button>
    <p class="field-desc">
      Paste it into the agent's MCP settings (inside its <em>mcpServers</em> if
      others are listed) and restart the agent. Keep Unseen Servant running;
      closing its window doesn't quit it.
    </p>
    <p class="field-desc">
      The agent searches the whole library unless it names a collection: what
      plays here doesn't scope it. What its tools return goes to the agent's
      model, which may run in the cloud; the PDFs themselves stay here.
    </p>
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
