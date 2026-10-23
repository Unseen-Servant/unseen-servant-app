<script lang="ts">
  import type { Snippet } from 'svelte';
  import { openUrl } from '@tauri-apps/plugin-opener';
  import { ParaglideMessage } from '@inlang/paraglide-js-svelte';
  import ReadyTag from '../shell/help/ReadyTag.svelte';
  import { m } from '../paraglide/messages';

  export let sidecarConnected: boolean = true;
  export let ollamaRunning: boolean = false;
  export let ollamaModelReady: boolean = false;
  export let folderSelected: boolean = false;
  export let filesIndexed: boolean = false;
  export let onSelectFolder: () => void;

  // What the Ollama lamp means in words (ReadyTag).
  const OLLAMA_STATE = {
    unknown: m.lore_start_ollama_unknown,
    ready: m.lore_start_ready,
    model: m.lore_start_ollama_model,
    missing: m.lore_start_ollama_missing,
  };

  // Ollama is probed through the sidecar: with the sidecar down its state is
  // unknown, and "not detected" would send a working setup to reinstall it.
  let ollamaState: keyof typeof OLLAMA_STATE;
  $: ollamaState = !sidecarConnected
    ? 'unknown'
    : ollamaRunning && ollamaModelReady
      ? 'ready'
      : ollamaRunning
        ? 'model'
        : 'missing';
</script>

{#snippet em({ children }: { children?: Snippet })}<em>{@render children?.()}</em>{/snippet}
{#snippet strong({ children }: { children?: Snippet })}<strong>{@render children?.()}</strong>{/snippet}

<!-- Each step leads with what to do; its lamp reads the live state. -->
<div class="manual">
  <section class="field">
    <div class="field-title-row">
      <h3 class="field-title section-title">Ollama</h3>
      <ReadyTag
        lit={ollamaState === 'ready'}
        half={ollamaState === 'model'}
        state={OLLAMA_STATE[ollamaState]()}
      />
    </div>
    <p class="field-desc">
      {m.lore_start_ollama_desc()}
      {#if ollamaState === 'unknown'}
        {m.lore_start_ollama_desc_unknown()}
      {:else if ollamaState === 'missing'}
        {m.lore_start_ollama_desc_missing()}
      {:else if ollamaState === 'model'}
        {m.lore_start_ollama_desc_model()}
      {/if}
    </p>
    {#if ollamaState === 'missing'}
      <button class="btn-link" on:click={() => openUrl('https://ollama.com').catch(() => {})}>ollama.com</button>
    {:else if ollamaState === 'model'}
      <code class="command">ollama pull bge-m3</code>
    {/if}
  </section>

  <section class="field">
    <div class="field-title-row">
      <h3 class="field-title section-title">{m.lore_start_folder()}</h3>
      <ReadyTag lit={folderSelected} state={folderSelected ? m.lore_start_ready() : m.lore_start_folder_none()} />
    </div>
    <p class="field-desc"><ParaglideMessage message={m.lore_start_folder_desc} {strong} /></p>
    <p class="field-desc"><ParaglideMessage message={m.lore_start_folder_images} {em} /></p>
    {#if !folderSelected}
      <button class="btn-link" on:click={onSelectFolder}>{m.lore_start_choose_folder()}</button>
    {/if}
  </section>

  <section class="field">
    <div class="field-title-row">
      <h3 class="field-title section-title">{m.lore_start_index()}</h3>
      <ReadyTag lit={filesIndexed} state={filesIndexed ? m.lore_start_ready() : m.lore_start_index_none()} />
    </div>
    <p class="field-desc"><ParaglideMessage message={m.lore_start_index_desc} {em} {strong} /></p>
  </section>

  <section class="field">
    <div class="field-title-row">
      <h3 class="field-title section-title">
        <ParaglideMessage message={m.lore_start_collections}>
          {#snippet opt({ children })}<span class="opt">{@render children?.()}</span>{/snippet}
        </ParaglideMessage>
      </h3>
    </div>
    <p class="field-desc"><ParaglideMessage message={m.lore_start_collections_desc} {strong} /></p>
    <p class="field-desc"><ParaglideMessage message={m.lore_start_collections_arm} {strong} /></p>
  </section>
</div>

<style>
  /* Shape mirrors LibrarySettings: stacked .field sections at 1.25rem
     gap, .field-title in Almendra at 0.95rem, .field-desc in body at
     0.85rem. The Setup-specific bits — right-aligned ReadyTag and
     command box — extend that vocabulary rather than replace it. */
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
  .field-desc strong {
    color: var(--text-primary);
    font-weight: 600;
  }
  .field-desc em {
    color: var(--text-secondary);
    font-style: italic;
  }

  .command {
    align-self: flex-start;
    padding: 0.3rem 0.55rem;
    background: var(--bg-focused);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    font-family: var(--font-mono);
    font-size: 0.75rem;
    color: var(--text-primary);
    user-select: all;
    -webkit-user-select: all;
  }

  .btn-link {
    align-self: flex-start;
  }
</style>
