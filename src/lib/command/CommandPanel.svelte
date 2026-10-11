<script lang="ts">
  // Command (docs/roadmap/2026-10-11-command-design.md). Phase 1, the vault:
  // campaigns as folders, the Prep grid of tracks, and the note editor.
  // Everything shown is re-read from the sidecar; file state lives in
  // NoteBuffer, which owns the save rules.
  import { onDestroy, onMount, type Snippet } from 'svelte';
  import type { UnlistenFn } from '@tauri-apps/api/event';
  import { revealItemInDir } from '@tauri-apps/plugin-opener';
  import ActionButton from '../ui/ActionButton.svelte';
  import { confirmPrompt } from '../shell/confirmStore';
  import { appContext, setCampaign } from '../shell/shellState';
  import CommandMenu from './CommandMenu.svelte';
  import InlineName from './InlineName.svelte';
  import NoteEditor from './NoteEditor.svelte';
  import TrackGrid from './TrackGrid.svelte';
  import { commandApi, onVaultChange } from './api';
  import { columns, isAmbiguous, linkableNames, type Column } from './columns';
  import { action, divider, heading, type OpenMenu } from './menu';
  import { NoteBuffer, type BufferState } from './noteBuffer';
  import type { CampaignIndex, CommandSettings, NoteEntry, VaultEvent } from './types';

  // The host's dock toggle (PANELS.md), drawn at the right of the bar.
  export let windowKey: Snippet | undefined = undefined;

  let settings: CommandSettings | null = null;
  let campaigns: string[] = [];
  /** The open campaign: `index` and the buffer both belong to it. */
  let campaign: string | null = null;
  let index: CampaignIndex | null = null;
  let error: string | null = null;
  let menu: OpenMenu | null = null;
  let naming: 'campaign' | 'rename-campaign' | null = null;
  let mounted = false;
  let unlisten: Promise<UnlistenFn> | null = null;

  let editor: NoteEditor | undefined;
  let bufState: BufferState = { path: null, status: 'empty', error: null };
  // A note just opened takes the caret to the top; a reload keeps it.
  let freshOpen = false;

  const buffer = new NoteBuffer(
    {
      read: (path) => commandApi.readNote(campaign!, path),
      save: (path, content, baseHash) => commandApi.saveNote(campaign!, path, content, baseHash),
    },
    (state) => (bufState = state),
    (content) => {
      editor?.setContent(content, !freshOpen);
      freshOpen = false;
    },
  );

  $: cols = index ? columns(index) : ([] as Column[]);
  $: nameSet = new Set((index?.notes ?? []).map((n) => n.name.toLowerCase()));
  $: openEntry = index?.notes.find((n) => n.path === bufState.path) ?? null;

  // -- running things -----------------------------------------------------

  // One job at a time: campaign switches, refreshes and actions all touch
  // `campaign`, `index` and the buffer, and must not interleave.
  let queue: Promise<void> = Promise.resolve();
  function run(job: () => Promise<void>): Promise<void> {
    queue = queue.then(async () => {
      try {
        await job();
      } catch (e) {
        error = String(e);
      }
    });
    return queue;
  }

  async function loadRoot() {
    settings = await commandApi.getSettings();
    campaigns = settings.root ? await commandApi.listCampaigns() : [];
  }

  async function leaveCampaign() {
    await buffer.close();
    campaign = null;
    index = null;
  }

  async function enterCampaign(name: string | null) {
    if (name === campaign && index) return;
    await leaveCampaign();
    if (name && campaigns.includes(name)) {
      index = await commandApi.getCampaign(name);
      campaign = name;
    }
  }

  async function refreshIndex() {
    if (!campaign) return;
    try {
      index = await commandApi.getCampaign(campaign);
      editor?.refreshLinks();
    } catch {
      await refreshAll();
    }
  }

  async function refreshAll() {
    await loadRoot();
    if (campaign && !campaigns.includes(campaign)) await leaveCampaign();
    else if (campaign) {
      index = await commandApi.getCampaign(campaign);
      editor?.refreshLinks();
      await buffer.diskChanged();
    }
    await enterCampaign($appContext.campaign);
  }

  // Follow the workstation's active campaign, in every window.
  $: wanted = $appContext.campaign;
  $: if (mounted) run(() => enterCampaign(wanted));

  let refreshTimer: ReturnType<typeof setTimeout> | null = null;
  function onVault(event: VaultEvent) {
    if (event.campaign === null) {
      run(refreshAll);
      return;
    }
    if (event.campaign !== campaign) return;
    if (bufState.path && event.paths.includes(bufState.path)) void buffer.diskChanged();
    if (refreshTimer) clearTimeout(refreshTimer);
    refreshTimer = setTimeout(() => run(refreshIndex), 120);
  }

  onMount(() => {
    unlisten = onVaultChange(onVault);
    run(loadRoot).then(() => (mounted = true));
  });

  onDestroy(() => {
    if (refreshTimer) clearTimeout(refreshTimer);
    void unlisten?.then((stop) => stop());
    void buffer.close();
  });

  // -- paths --------------------------------------------------------------

  function absolute(rel?: string): string {
    return [settings!.root, campaign, rel].filter(Boolean).join('/');
  }

  function reveal(rel?: string) {
    revealItemInDir(absolute(rel)).catch((e) => (error = String(e)));
  }

  // -- notes --------------------------------------------------------------

  function openNote(note: NoteEntry) {
    if (note.path === bufState.path) return;
    run(async () => {
      freshOpen = true;
      await buffer.open(note.path);
    });
  }

  function createNote(folder: string, name: string) {
    run(async () => {
      const path = await commandApi.createNote(campaign!, folder, name);
      await refreshIndex();
      freshOpen = true;
      await buffer.open(path);
      editor?.focus();
    });
  }

  function followLink(name: string) {
    const target = index?.notes.find((n) => n.name.toLowerCase() === name.toLowerCase());
    if (target) {
      openNote(target);
      return;
    }
    const track = openEntry?.track ?? cols[0]?.track;
    if (!track || !name) return;
    run(async () => {
      const create = await confirmPrompt.request({
        title: 'New note',
        message: `Nothing is named “${name}” yet. Start it in ${track}?`,
        confirmLabel: 'Create',
      });
      if (create) createNote(track, name);
    });
  }

  function renameNote(note: NoteEntry, name: string) {
    run(async () => {
      const isOpen = note.path === bufState.path;
      if (isOpen) await buffer.flush();
      const moved = await commandApi.renameNote(campaign!, note.path, name);
      if (isOpen) await buffer.retarget(moved.path);
      await refreshIndex();
    });
  }

  function moveNote(note: NoteEntry, track: string) {
    run(async () => {
      const isOpen = note.path === bufState.path;
      if (isOpen) await buffer.flush();
      const moved = await commandApi.moveNote(campaign!, note.path, track);
      if (isOpen) await buffer.retarget(moved.path);
      await refreshIndex();
    });
  }

  function trashNote(note: NoteEntry) {
    run(async () => {
      const confirmed = await confirmPrompt.request({
        title: 'Move to Trash',
        rows: [{ label: 'Note', value: note.name }],
        message: 'Links to it will show as missing until it comes back.',
        confirmLabel: 'Move to Trash',
        danger: true,
      });
      if (!confirmed) return;
      if (note.path === bufState.path) await buffer.close();
      await commandApi.trash(campaign!, note.path);
      await refreshIndex();
    });
  }

  // -- tracks -------------------------------------------------------------

  function createTrack(name: string) {
    run(async () => {
      await commandApi.createTrack(campaign!, name);
      await refreshIndex();
    });
  }

  function renameTrack(track: string, name: string) {
    run(async () => {
      const open = bufState.path;
      const inside = open !== null && open.startsWith(`${track}/`);
      if (inside) await buffer.flush();
      const renamed = await commandApi.renameTrack(campaign!, track, name);
      if (inside) await buffer.retarget(renamed.name + open!.slice(track.length));
      await refreshIndex();
    });
  }

  function trashTrack(column: Column) {
    run(async () => {
      const confirmed = await confirmPrompt.request({
        title: 'Move to Trash',
        rows: [
          { label: 'Track', value: column.track },
          { label: 'Notes', value: String(column.count), to: 'Trash' },
        ],
        message: 'The folder and every note in it go to the Trash.',
        confirmLabel: 'Move to Trash',
        danger: true,
      });
      if (!confirmed) return;
      if (bufState.path?.startsWith(`${column.track}/`)) await buffer.close();
      await commandApi.trash(campaign!, column.track);
      await refreshIndex();
    });
  }

  // -- campaigns ----------------------------------------------------------

  function chooseRoot() {
    run(async () => {
      const chosen = await commandApi.chooseRoot();
      if (!chosen) return;
      await leaveCampaign();
      await loadRoot();
      await enterCampaign($appContext.campaign);
    });
  }

  function openCampaign(name: string | null) {
    run(() => setCampaign(name));
  }

  function createCampaign(name: string) {
    run(async () => {
      const created = await commandApi.createCampaign(name);
      campaigns = await commandApi.listCampaigns();
      await setCampaign(created);
    });
  }

  function renameCampaign(name: string) {
    run(async () => {
      const old = campaign!;
      await leaveCampaign();
      const renamed = await commandApi.renameCampaign(old, name);
      campaigns = await commandApi.listCampaigns();
      await setCampaign(renamed.name);
      await enterCampaign(renamed.name);
    });
  }

  function trashCampaign() {
    run(async () => {
      const name = campaign!;
      const confirmed = await confirmPrompt.request({
        title: 'Move to Trash',
        rows: [
          { label: 'Campaign', value: name },
          { label: 'Notes', value: String(index?.notes.length ?? 0), to: 'Trash' },
        ],
        message: 'The campaign folder and everything in it go to the Trash.',
        confirmLabel: 'Move to Trash',
        danger: true,
      });
      if (!confirmed) return;
      await leaveCampaign();
      await commandApi.trash(name, null);
      await setCampaign(null);
      await loadRoot();
    });
  }

  function campaignMenu(e: MouseEvent) {
    const box = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const others = campaigns.filter((c) => c !== campaign);
    menu = {
      x: box.left,
      y: box.bottom + 4,
      items: [
        ...(others.length ? [heading('campaigns'), ...others.map((c) => action(c, () => openCampaign(c))), divider] : []),
        action('New campaign', () => (naming = 'campaign')),
        action('Rename', () => (naming = 'rename-campaign')),
        action('Show in Finder', () => reveal()),
        action('Close campaign', () => openCampaign(null)),
        divider,
        action('Change campaigns folder', chooseRoot),
        action('Move to Trash', trashCampaign, true),
      ],
    };
  }

  // -- the inspector ------------------------------------------------------

  const STATUS_TEXT: Partial<Record<BufferState['status'], string>> = {
    dirty: 'edited',
    saving: 'saving…',
  };
</script>

<section class="command">
  <header class="bar">
    {#if naming}
      <div class="bar-name">
        <InlineName
          value={naming === 'rename-campaign' ? (campaign ?? '') : ''}
          placeholder="Campaign name"
          label={naming === 'campaign' ? 'New campaign' : 'Rename campaign'}
          onCommit={(name) => {
            const mode = naming;
            naming = null;
            if (mode === 'campaign') createCampaign(name);
            else renameCampaign(name);
          }}
          onCancel={() => (naming = null)}
        />
      </div>
    {:else if campaign}
      <button type="button" class="campaign-key" title="Campaigns" on:click={campaignMenu}>
        {campaign}<span class="drop" aria-hidden="true">▾</span>
      </button>
    {:else}
      <span class="bar-title">Command</span>
    {/if}
    <span class="spacer"></span>
    {@render windowKey?.()}
  </header>

  <div class="body">
    {#if settings === null}
      <div class="empty"></div>
    {:else if !settings.root}
      <div class="empty">
        <p class="lede">Command keeps each campaign as a folder of Markdown notes — yours, readable in any editor.</p>
        <ActionButton label="choose campaigns folder" onClick={chooseRoot} />
      </div>
    {:else if !index}
      <div class="empty">
        <div class="campaign-list">
          <div class="ledger-label list-head">campaigns</div>
          {#each campaigns as name (name)}
            <button type="button" class="campaign-row" on:click={() => openCampaign(name)}>{name}</button>
          {/each}
          {#if naming === null}
            <button type="button" class="campaign-row ghost" on:click={() => (naming = 'campaign')}>+ campaign</button>
          {/if}
        </div>
        <p class="root">
          <span class="root-path" title={settings.root}>{settings.root}</span>
          <ActionButton label="change" title="Change campaigns folder" onClick={chooseRoot} />
        </p>
      </div>
    {:else}
      <div class="prep">
        <div class="grid-pane">
          <TrackGrid
            {cols}
            openPath={bufState.path}
            ambiguous={(name) => isAmbiguous(index!, name)}
            onOpen={openNote}
            onCreateNote={createNote}
            onRenameNote={renameNote}
            onMoveNote={moveNote}
            onTrashNote={trashNote}
            onRevealNote={(note) => reveal(note.path)}
            onCreateTrack={createTrack}
            onRenameTrack={renameTrack}
            onTrashTrack={trashTrack}
            onRevealTrack={(track) => reveal(track)}
          />
        </div>

        <aside class="inspector">
          {#if bufState.status !== 'empty'}
            <div class="inspector-head">
              <span class="note-name">{openEntry?.name ?? bufState.path?.split('/').pop()?.replace(/\.md$/, '')}</span>
              {#if openEntry?.track}
                <span class="crumb">{[openEntry.track, openEntry.group].filter(Boolean).join(' › ')}</span>
              {/if}
              <span class="save-state">{STATUS_TEXT[bufState.status] ?? ''}</span>
            </div>
            {#if bufState.status === 'conflict'}
              <div class="notice" role="alert">
                <span>Changed on disk while you were editing.</span>
                <ActionButton label="reload" title="Take what's on disk" onClick={() => void buffer.reload()} />
                <ActionButton label="keep mine" title="Write your version over it" onClick={() => void buffer.keepMine()} />
              </div>
            {:else if bufState.status === 'unreadable'}
              <div class="notice" role="alert">
                <span>Can't read this note from disk — your text is still here.</span>
              </div>
            {:else if bufState.error}
              <div class="notice" role="alert"><span>Not saved: {bufState.error}</span></div>
            {/if}
          {:else}
            <p class="inspector-hint">Pick a note to edit it, or <em>+ note</em> to start one.</p>
          {/if}
          <div class="editor-slot" class:hidden={bufState.status === 'empty'}>
            <NoteEditor
              bind:this={editor}
              names={() => (index ? linkableNames(index) : [])}
              resolves={(name) => nameSet.has(name.toLowerCase())}
              onEdit={(content) => buffer.edit(content)}
              onFollow={followLink}
              readOnly={bufState.status === 'empty' || bufState.status === 'unreadable'}
            />
          </div>
        </aside>
      </div>
    {/if}
  </div>

  {#if error}
    <div class="error-line" role="alert">
      <span class="error-text">{error}</span>
      <ActionButton label="dismiss" onClick={() => (error = null)} />
    </div>
  {/if}
</section>

{#if menu}
  <CommandMenu x={menu.x} y={menu.y} items={menu.items} onClose={() => (menu = null)} />
{/if}

<style>
  .command {
    height: 100%;
    display: flex;
    flex-direction: column;
    background: var(--bg-app);
    color: var(--text-primary);
  }

  .bar {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    gap: 0.75rem;
    height: var(--header-height);
    padding: 0 0.75rem;
    background: var(--bg-header);
    border-bottom: 1px solid var(--border-subtle);
  }

  .bar-title,
  .campaign-key {
    font-family: var(--font-heading);
    font-size: 1.05rem;
    color: var(--text-primary);
  }

  .bar-title {
    color: var(--text-secondary);
  }

  .campaign-key {
    display: flex;
    align-items: baseline;
    gap: 0.35rem;
    padding: 0.1rem 0.35rem;
    background: none;
    border: none;
    border-radius: var(--radius-sm);
    cursor: pointer;
    transition: background var(--transition-fast);
  }

  .campaign-key:hover {
    background: var(--bg-focused);
  }

  .campaign-key:active {
    transform: scale(0.97);
  }

  .drop {
    font-family: var(--font-body);
    font-size: 0.7rem;
    color: var(--text-tertiary);
  }

  .bar-name {
    width: 16rem;
    font-size: 0.95rem;
  }

  .spacer {
    flex: 1;
  }

  .body {
    flex: 1;
    min-height: 0;
  }

  .empty {
    height: 100%;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 1rem;
    padding: 2rem;
  }

  .lede {
    margin: 0;
    max-width: 28rem;
    text-align: center;
    color: var(--text-secondary);
  }

  .campaign-list {
    display: flex;
    flex-direction: column;
    width: 18rem;
    max-height: 60vh;
    overflow-y: auto;
  }

  .list-head {
    padding: 0 0.5rem 0.35rem;
  }

  .campaign-row {
    padding: 0.25rem 0.5rem;
    background: none;
    border: none;
    border-radius: var(--radius-sm);
    font-family: var(--font-heading);
    font-size: 1.05rem;
    text-align: left;
    color: var(--text-primary);
    cursor: pointer;
    transition: background var(--transition-fast);
  }

  .campaign-row:hover {
    background: var(--bg-focused);
  }

  .campaign-row:active {
    transform: scale(0.97);
  }

  .campaign-row.ghost {
    font-family: var(--font-body);
    font-size: 0.9rem;
    color: var(--text-tertiary);
  }

  .campaign-row.ghost:hover {
    color: var(--text-primary);
  }

  .root {
    display: flex;
    align-items: baseline;
    gap: 0.5rem;
    margin: 0;
    max-width: 32rem;
    font-size: 0.8rem;
    color: var(--text-tertiary);
  }

  .root-path {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-family: var(--font-mono);
    font-size: 0.75rem;
  }

  .prep {
    height: 100%;
    display: flex;
  }

  .grid-pane {
    flex: 1;
    min-width: 0;
  }

  /* The inspector reads on vellum, as Legend Lore's does. */
  .inspector {
    flex: 0 0 min(36%, 30rem);
    display: flex;
    flex-direction: column;
    min-height: 0;
    background: var(--bg-vellum);
    border-left: 1px solid var(--border-subtle);
  }

  .inspector-head {
    flex-shrink: 0;
    display: flex;
    align-items: baseline;
    gap: 0.6rem;
    padding: 0.55rem 1rem 0.4rem;
    border-bottom: 1px solid var(--border-subtle);
  }

  .note-name {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-family: var(--font-heading);
    font-size: 1.1rem;
  }

  .crumb {
    flex-shrink: 0;
    font-size: 0.8rem;
    color: var(--text-tertiary);
  }

  .save-state {
    flex-shrink: 0;
    margin-left: auto;
    font-size: 0.75rem;
    color: var(--text-tertiary);
  }

  .notice {
    flex-shrink: 0;
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: 0.6rem;
    padding: 0.4rem 1rem;
    font-size: 0.85rem;
    color: var(--text-danger);
    border-bottom: 1px solid var(--border-subtle);
  }

  .inspector-hint {
    margin: auto;
    padding: 2rem;
    color: var(--text-tertiary);
    text-align: center;
  }

  .inspector-hint em {
    font-style: normal;
    color: var(--text-secondary);
  }

  .editor-slot {
    flex: 1;
    min-height: 0;
  }

  .editor-slot.hidden {
    display: none;
  }

  .error-line {
    flex-shrink: 0;
    display: flex;
    align-items: baseline;
    gap: 0.75rem;
    padding: 0.3rem 0.75rem;
    font-size: 0.85rem;
    color: var(--text-danger);
    background: var(--bg-container);
    border-top: 1px solid var(--border-subtle);
  }

  .error-text {
    flex: 1;
    min-width: 0;
  }
</style>
