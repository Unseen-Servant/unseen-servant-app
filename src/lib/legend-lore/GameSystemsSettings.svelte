<script lang="ts">
  import { invoke } from '@tauri-apps/api/core';
  import { ParaglideMessage } from '@inlang/paraglide-js-svelte';
  import type { KnownGameSystem } from './types';
  import { SHIELD } from '../ui/iconPaths';
  import Modal from '../shell/Modal.svelte';
  import ActionButton from '../ui/ActionButton.svelte';
  import CommitSwitch from '../ui/CommitSwitch.svelte';
  import { confirmPrompt } from '../shell/confirmStore';
  import { m } from '../paraglide/messages';

  export let knownSystems: KnownGameSystem[] = [];
  export let onSystemsChanged: () => void = () => {};

  // Sort state
  let sortDirection: 'asc' | 'desc' = 'asc';

  function toggleSort() {
    sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
  }

  $: sorted = [...knownSystems].sort((a, b) => {
    const cmp = a.tag.localeCompare(b.tag, undefined, { sensitivity: 'base' });
    return sortDirection === 'desc' ? -cmp : cmp;
  });

  // Modal state
  let showModal = false;
  let modalMode: 'add' | 'edit' = 'add';
  let modalTag = '';
  let modalKeywords = '';
  // Stored color rides along untouched on edit — nothing in the UI reads
  // or writes system colors anymore (color belongs to collections).
  let modalColor: string | null = null;
  let modalError = '';
  let editOriginalTag = '';
  let editOriginalKeywords = '';
  let editIsBuiltin = false;
  let editIsCustomized = false;

  // No tagInput ref and no focus call: Modal.svelte's text-input heuristic
  // already focuses the Tag field, once, after showModal(). Two focus calls
  // racing across a reactive flush is what [data-autofocus] exists to avoid.

  // Save is enabled only when there is a tag and either we're adding
  // or the user actually changed something — same convention as the
  // Collection modal.
  $: dirty = modalMode === 'add' || (
    modalTag.trim() !== editOriginalTag ||
    modalKeywords !== editOriginalKeywords
  );
  $: canSave = modalTag.trim().length > 0 && dirty;

  function openAddModal() {
    modalMode = 'add';
    modalTag = '';
    modalKeywords = '';
    modalColor = null;
    modalError = '';
    editOriginalTag = '';
    editOriginalKeywords = '';
    editIsBuiltin = false;
    editIsCustomized = false;
    showModal = true;
  }

  function openEditModal(sys: KnownGameSystem) {
    modalMode = 'edit';
    modalTag = sys.tag;
    modalKeywords = (sys.keywords || []).join(', ');
    modalColor = sys.color ?? null;
    modalError = '';
    editOriginalTag = sys.tag;
    editOriginalKeywords = modalKeywords;
    editIsBuiltin = sys.is_builtin ?? false;
    editIsCustomized = sys.is_customized ?? false;
    showModal = true;
  }

  function closeModal() {
    showModal = false;
    modalError = '';
  }

  function handleWindowKey(event: KeyboardEvent) {
    if (!showModal) return;
    // A confirm prompt stacks above this modal, and window keydown still
    // fires behind an open <dialog>. Enter there belongs to the focused
    // button in the prompt, not to Save.
    if ($confirmPrompt) return;
    if (event.key !== 'Enter' || !canSave) return;
    // Plain Enter saves from any text input (matches the rest of the
    // app's "Enter commits" feel); Cmd/Ctrl+Enter still works globally.
    const target = event.target as HTMLElement | null;
    const inTextInput = target instanceof HTMLInputElement && target.type === 'text';
    if (event.metaKey || event.ctrlKey || inTextInput) {
      event.preventDefault();
      handleSave();
    }
  }

  function parseKeywords(raw: string): string[] {
    return raw.split(',').map(k => k.trim().toLowerCase()).filter(k => k.length > 0);
  }

  async function handleSave() {
    const tag = modalTag.trim();
    if (!tag) { modalError = m.lore_gamesystems_tag_required(); return; }
    const keywords = parseKeywords(modalKeywords);
    const color = modalColor || null;

    try {
      if (modalMode === 'add') {
        await invoke('create_custom_game_system', { tag, keywords, color });
      } else {
        // Edit mode: works for both custom and built-in (backend creates override if needed)
        await invoke('update_custom_game_system', { originalTag: editOriginalTag, tag, keywords, color });
      }
      closeModal();
      onSystemsChanged();
    } catch (e: any) {
      modalError = e?.toString()?.replace(/^.*?:\s*/, '') || m.lore_gamesystems_save_failed();
    }
  }

  async function handleDelete() {
    // What goes is the tag and its keywords, and the prompt shows both rather
    // than naming one and summarising the other. The reassurance — that
    // deleting a definition retags nothing — stays in the message rather than
    // becoming a fourth row: this page has no count of tagged files, so the
    // row could only have read "files already tagged → unchanged", which is
    // prose sitting in a column of names and figures. A row earns its place
    // by carrying a value; when the value would be a sentence, it is a
    // sentence.
    const confirmed = await confirmPrompt.request({
      title: m.lore_gamesystems_delete_title(),
      rows: [
        { label: m.lore_gamesystems_tag(), value: editOriginalTag },
        { label: m.lore_gamesystems_keywords(), value: modalKeywords || '—' },
      ],
      message: m.lore_gamesystems_delete_message(),
      confirmLabel: m.lore_gamesystems_delete_confirm(),
      danger: true,
    });
    if (!confirmed) return;
    try {
      await invoke('delete_custom_game_system', { tag: editOriginalTag });
      closeModal();
      onSystemsChanged();
    } catch (e: any) {
      modalError = e?.toString()?.replace(/^.*?:\s*/, '') || m.lore_gamesystems_delete_failed();
    }
  }

  async function handleReset() {
    // The one genuine transition among these rows: the keywords you edited
    // become the built-in set again. The tag itself is identity and survives,
    // so it has no `to`.
    const confirmed = await confirmPrompt.request({
      title: m.lore_gamesystems_reset_title(),
      rows: [
        { label: m.lore_gamesystems_tag(), value: editOriginalTag },
        { label: m.lore_gamesystems_keywords(), value: modalKeywords || '—', to: m.lore_gamesystems_to_builtin() },
      ],
      message: m.lore_gamesystems_reset_message(),
      confirmLabel: m.lore_gamesystems_reset_confirm(),
      danger: true,
    });
    if (!confirmed) return;
    try {
      await invoke('delete_custom_game_system', { tag: editOriginalTag });
      closeModal();
      onSystemsChanged();
    } catch (e: any) {
      modalError = e?.toString()?.replace(/^.*?:\s*/, '') || m.lore_gamesystems_reset_failed();
    }
  }
</script>

<svelte:window on:keydown={handleWindowKey} />

<div class="game-systems-settings">
  <div class="list-header">
    <button class="col-header col-tag ledger-label" on:click={toggleSort}>{m.lore_gamesystems_tag()}</button>
    <span class="col-header col-keywords ledger-label">{m.lore_gamesystems_keywords()}</span>
    <button class="add-btn" title={m.lore_gamesystems_add_custom()} on:click={openAddModal}>+</button>
  </div>
  <div class="systems-list">
    {#each sorted as sys}
      <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
      <div class="system-row" on:click={() => openEditModal(sys)}>
        <span class="system-icon" aria-hidden="true">
          <!-- Shield — a game system -->
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round">
            <path d={SHIELD}/>
          </svg>
        </span>
        <span class="system-tag">{sys.tag}</span>
        <span class="system-keywords">{(sys.keywords || []).slice(0, 3).join(', ')}{(sys.keywords || []).length > 3 ? '...' : ''}</span>
        <div class="system-labels">
          {#if sys.is_builtin}
            <span class="label readout-label builtin-label">{sys.is_customized ? m.lore_gamesystems_customized() : m.lore_gamesystems_builtin()}</span>
          {:else}
            <span class="label readout-label custom-label">{m.lore_gamesystems_custom()}</span>
          {/if}
        </div>
      </div>
    {/each}
  </div>
</div>

<Modal
  visible={showModal}
  onClose={closeModal}
  title={modalMode === 'add' ? m.lore_gamesystems_add_title() : m.lore_gamesystems_edit_title()}
  size="sm"
  escapeWord="close"
>
  <div class="modal-bays">
    <div class="modal-bay">
      <span class="ledger-label">{m.lore_gamesystems_tag()}</span>
      <input
        id="sys-tag"
        type="text"
        class="input"
        bind:value={modalTag}
        placeholder={m.lore_gamesystems_tag_placeholder()}
      />
    </div>

    <div class="modal-bay">
      <span class="ledger-label">{m.lore_gamesystems_keywords()}</span>
      <input
        id="sys-keywords"
        type="text"
        class="input"
        bind:value={modalKeywords}
        placeholder={m.lore_gamesystems_keywords_placeholder()}
      />
      <!-- The one sentence here that changes what you type. How matching
           normalises case and punctuation is true, useful once, and re-read
           never — it lives in Help → Reference now. -->
      <p class="hint">
        <ParaglideMessage message={m.lore_gamesystems_keywords_hint} inputs={{ tag: modalTag.trim() || 'Cairn' }}>
          {#snippet em({ children })}<em>{@render children?.()}</em>{/snippet}
        </ParaglideMessage>
      </p>
    </div>

    {#if modalError}
      <div class="error-msg">{modalError}</div>
    {/if}

    <!-- Destructive actions sit in a bay, not on the commit rail: the strip is
         where this unit's commit lives, and a secondary that undoes the record
         is not that commit. These raise a prompt rather than committing, so
         they wear bracketed danger text and no switch face — a face carries a
         key, and nothing here implements one. See the design's "A face is a
         promise, and only a commit may make it". -->
    {#if modalMode === 'edit' && (editIsBuiltin ? editIsCustomized : true)}
      <div class="modal-bay">
        <div class="modal-well danger-bay">
          <div class="modal-well-row action-row">
            <span class="row-text">
              {editIsBuiltin
                ? m.lore_gamesystems_reset_desc()
                : m.lore_gamesystems_delete_desc()}
            </span>
            {#if editIsBuiltin}
              <ActionButton danger label={m.lore_gamesystems_reset_key()} onClick={handleReset} />
            {:else}
              <ActionButton danger label={m.lore_gamesystems_delete_key()} onClick={handleDelete} />
            {/if}
          </div>
        </div>
      </div>
    {/if}
  </div>

  <!-- Activation, not removal: saving a system creates or updates a record.
       The face reads ↵ and handleWindowKey above honours it — plain Enter from
       either text input, ⌘/Ctrl+Enter from anywhere in the unit — with the
       browser's own activation covering Enter while the switch itself holds
       focus. The face is only honest because all three paths exist. -->
  <svelte:fragment slot="commit">
    <CommitSwitch
      label={modalMode === 'add' ? m.lore_gamesystems_add() : m.lore_gamesystems_save()}
      onClick={handleSave}
      disabled={!canSave}
    />
  </svelte:fragment>
</Modal>

<style>
  .game-systems-settings {
    display: flex;
    flex-direction: column;
    height: 100%;
  }

  .list-header {
    display: flex;
    align-items: center;
    padding: 0.35rem 0.75rem;
    gap: 0.5rem;
    border-bottom: 1px solid var(--border-subtle);
    flex-shrink: 0;
  }

  .col-header {
    background: none;
    border: none;
    color: var(--text-secondary);
    text-align: left;
    padding: 0;
    transition: color var(--transition-fast);
  }

  button.col-header {
    cursor: pointer;
  }
  button.col-header:hover {
    color: var(--text-primary);
  }

  .col-tag {
    min-width: 80px;
    flex-shrink: 0;
    /* Push the tag-column header past the icon column on each row. */
    padding-left: 1rem;
  }

  .col-keywords {
    flex: 1;
    cursor: default;
  }

  .add-btn {
    background: none;
    border: 1px solid var(--border-subtle);
    color: var(--text-secondary);
    font-size: 1rem;
    line-height: 1;
    width: 1.5rem;
    height: 1.5rem;
    border-radius: var(--radius-md);
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    transition: all var(--transition-fast);
  }
  .add-btn:hover {
    color: var(--text-accent);
    border-color: var(--text-accent);
  }

  .systems-list {
    flex: 1;
    overflow-y: auto;
    padding: 0.25rem 0;
  }

  .system-row {
    display: flex;
    align-items: center;
    padding: 0.35rem 0.75rem;
    gap: 0.5rem;
    cursor: pointer;
    transition: background var(--transition-fast);
  }
  .system-row:hover {
    background: var(--bg-focused);
  }

  .system-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    color: var(--text-accent);
  }
  .system-icon svg {
    width: 0.85rem;
    height: 0.85rem;
    display: block;
  }

  .system-tag {
    font-size: 0.8rem;
    color: var(--text-primary);
    font-weight: 600;
    min-width: 80px;
    flex-shrink: 0;
  }

  .system-keywords {
    font-size: 0.75rem;
    color: var(--text-tertiary);
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .system-labels {
    display: flex;
    gap: 0.25rem;
    flex-shrink: 0;
  }

  .label {
    padding: 0.1rem 0.3rem;
    border-radius: var(--radius-sm);
  }

  .builtin-label {
    color: var(--text-tertiary);
    border: 1px solid var(--border-subtle);
  }

  .custom-label {
    color: var(--text-accent);
    border: 1px solid var(--border-accent);
  }

  /* Modal unit. The bays own the padding and the spacing between things
     (.modal-bays / .modal-bay in app.css), so what is left here is only what
     the fields themselves look like. Nothing below may carry a margin: it
     would add to the bay's gap rather than replace it, which is why .hint
     lost the 0.4rem it used to need. */
  .input {
    padding: 0.4rem 0.6rem;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    font-family: var(--font-body);
    font-size: 0.85rem;
    background: var(--bg-focused);
    color: var(--text-primary);
  }
  .input:focus {
    outline: 1px solid var(--text-accent);
    outline-offset: -1px;
    border-color: var(--border-subtle);
  }

  .hint {
    margin: 0;
    font-family: var(--font-body);
    font-size: 0.75rem;
    color: var(--text-secondary);
    line-height: 1.4;
  }
  .hint em {
    font-style: normal;
    color: var(--text-accent);
  }

  .error-msg {
    font-size: 0.75rem;
    color: var(--text-danger);
  }
</style>
