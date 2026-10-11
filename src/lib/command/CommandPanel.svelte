<script lang="ts">
  // Command (docs/roadmap/2026-10-11-command-design.md). Prep: campaigns as
  // folders, the grid of tracks, the beat launcher for the active session,
  // and the note editor. Everything shown is re-read from the sidecar; file
  // state lives in NoteBuffer, which owns the save rules.
  import { onDestroy, onMount, type Snippet } from 'svelte';
  import type { UnlistenFn } from '@tauri-apps/api/event';
  import { revealItemInDir } from '@tauri-apps/plugin-opener';
  import ActionButton from '../ui/ActionButton.svelte';
  import { confirmPrompt } from '../shell/confirmStore';
  import { menuSlotHeld } from '../shell/menuSlot';
  import { appContext, setCampaign, setSession } from '../shell/shellState';
  import BeatColumn from './BeatColumn.svelte';
  import CommandMenu from './CommandMenu.svelte';
  import InlineName from './InlineName.svelte';
  import NoteEditor from './NoteEditor.svelte';
  import TrackGrid from './TrackGrid.svelte';
  import { commandApi, onVaultChange, type PlanEdit, type PlanOp } from './api';
  import { columns, isAmbiguous, linkableNames, type Column } from './columns';
  import { action, divider, heading, type OpenMenu } from './menu';
  import { NoteBuffer, type BufferState } from './noteBuffer';
  import { activeSession, memberPaths, planRows, sessionNotePaths, unscheduled, type PlanRow } from './prep';
  import type { BeatEntry, CampaignIndex, CommandSettings, NoteEntry, VaultEvent } from './types';

  // True while the panel is visible: window-level keys do nothing otherwise
  // (PANELS.md).
  export let active: boolean = true;
  // The host's dock toggle (PANELS.md), drawn at the right of the bar.
  export let windowKey: Snippet | undefined = undefined;

  /** What a rename, move, spend or trash needs of a note or a beat. */
  type Named = { name: string; path: string };

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

  /** The beat whose notes are lit; the armed one, if any, is also selected. */
  let selectedBeat: string | null = null;
  let armedBeat: string | null = null;

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
  $: session = index ? activeSession(index, $appContext.session) : null;
  $: rows = index ? planRows(index, session) : [];
  $: spare = index ? unscheduled(index, session) : [];
  $: beatAt = (path: string | null) => index?.beats.find((b) => b.path === path) ?? null;
  $: members = memberPaths(beatAt(selectedBeat));
  $: inSession = index ? sessionNotePaths(index, session) : new Set<string>();
  // A beat that left (renamed, trashed) can't stay selected or armed.
  $: if (index && selectedBeat && !beatAt(selectedBeat)) selectedBeat = null;
  $: if (index && armedBeat && !beatAt(armedBeat)) armedBeat = null;

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
    selectedBeat = armedBeat = null;
  }

  /** Point the workstation's session at one of this campaign's: the one
   *  already chosen if it's here, else the latest. */
  async function settleSession() {
    if (!index) return;
    const wantedSession = activeSession(index, $appContext.session)?.name ?? null;
    if (wantedSession !== $appContext.session) await setSession(wantedSession);
  }

  async function enterCampaign(name: string | null) {
    if (name === campaign && index) return;
    await leaveCampaign();
    if (name && campaigns.includes(name)) {
      index = await commandApi.getCampaign(name);
      campaign = name;
      await settleSession();
    }
  }

  async function refreshIndex() {
    if (!campaign) return;
    try {
      index = await commandApi.getCampaign(campaign);
      editor?.refreshLinks();
      await settleSession();
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
      await settleSession();
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

  /** Before Command rewrites a note's frontmatter, save what the editor
   *  holds for it, so the rewrite lands on it instead of conflicting. */
  async function settle(path: string) {
    if (bufState.path === path) await buffer.flush();
  }

  function onKeydown(e: KeyboardEvent) {
    if (!active || e.key !== 'Escape' || !armedBeat || menuSlotHeld()) return;
    const target = e.target as HTMLElement | null;
    if (target?.closest('input, textarea, .cm-editor')) return;
    armedBeat = null;
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

  function openPath(path: string) {
    if (path === bufState.path) return;
    run(async () => {
      freshOpen = true;
      await buffer.open(path);
    });
  }

  function createNote(folder: string, name: string) {
    run(async () => {
      const path = await commandApi.createNote(campaign!, folder, name);
      // A note started while a beat is armed lands in it.
      if (armedBeat) await commandApi.setMember(campaign!, armedBeat, path, true);
      await refreshIndex();
      freshOpen = true;
      await buffer.open(path);
      editor?.focus();
    });
  }

  function followLink(name: string) {
    const target = index?.notes.find((n) => n.name.toLowerCase() === name.toLowerCase());
    if (target) {
      openPath(target.path);
      return;
    }
    const track = openEntry?.track && index?.tracks.includes(openEntry.track) ? openEntry.track : cols[0]?.track;
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

  function retargetSelection(from: string, to: string) {
    if (selectedBeat === from) selectedBeat = to;
    if (armedBeat === from) armedBeat = to;
  }

  function renameNote(note: Named, name: string) {
    run(async () => {
      const isOpen = note.path === bufState.path;
      if (isOpen) await buffer.flush();
      const moved = await commandApi.renameNote(campaign!, note.path, name);
      retargetSelection(note.path, moved.path);
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

  function trashNote(note: Named, kind = 'Note') {
    run(async () => {
      const confirmed = await confirmPrompt.request({
        title: 'Move to Trash',
        rows: [{ label: kind, value: note.name }],
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

  function setSpent(note: Named, spent: boolean) {
    run(async () => {
      await settle(note.path);
      await commandApi.setSpent(campaign!, note.path, spent);
      await refreshIndex();
    });
  }

  // -- beats --------------------------------------------------------------

  function selectBeat(beat: BeatEntry) {
    selectedBeat = beat.path;
    if (armedBeat !== beat.path) armedBeat = null;
    openPath(beat.path);
  }

  function armBeat(beat: BeatEntry) {
    if (armedBeat === beat.path) {
      armedBeat = null;
      return;
    }
    armedBeat = selectedBeat = beat.path;
    openPath(beat.path);
  }

  function toggleMember(note: NoteEntry) {
    const beat = armedBeat;
    if (!beat) return;
    run(async () => {
      await settle(beat);
      await commandApi.setMember(campaign!, beat, note.path, !memberPaths(beatAt(beat)).has(note.path));
      await refreshIndex();
    });
  }

  function landBeat(path: string) {
    armedBeat = selectedBeat = path;
    freshOpen = true;
    return buffer.open(path);
  }

  function createBeat(name: string) {
    run(async () => {
      const path = await commandApi.createBeat(campaign!, name, [], session?.path ?? null);
      await refreshIndex();
      await landBeat(path);
    });
  }

  /** A plan entry naming a beat nobody has written yet: write it. */
  function writeBeat(row: PlanRow) {
    run(async () => {
      const path = await commandApi.createBeat(campaign!, row.link, [], null);
      await refreshIndex();
      await landBeat(path);
    });
  }

  function editPlan(op: PlanOp, edit: PlanEdit) {
    const target = session;
    if (!target) return;
    run(async () => {
      await settle(target.path);
      try {
        await commandApi.editPlan(campaign!, target.path, op, edit);
      } finally {
        await refreshIndex();
      }
    });
  }

  // -- sessions -----------------------------------------------------------

  function newSession() {
    run(async () => {
      const made = await commandApi.createSession(campaign!);
      await setSession(made.name);
      await refreshIndex();
    });
  }

  function trashSession() {
    const target = session;
    if (!target) return;
    run(async () => {
      const confirmed = await confirmPrompt.request({
        title: 'Move to Trash',
        rows: [
          { label: 'Session', value: target.name },
          { label: 'Beats', value: String(target.beats.length), to: 'kept', unchanged: true },
        ],
        message: 'The session note goes; its beats stay in Beats/.',
        confirmLabel: 'Move to Trash',
        danger: true,
      });
      if (!confirmed) return;
      if (bufState.path === target.path) await buffer.close();
      await commandApi.trash(campaign!, target.path);
      await setSession(null);
      await refreshIndex();
    });
  }

  function sessionMenu(e: MouseEvent) {
    const box = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const others = [...(index?.sessions ?? [])].reverse().filter((s) => s.path !== session?.path);
    menu = {
      x: box.left,
      y: box.bottom + 4,
      items: [
        ...(others.length
          ? [heading('sessions'), ...others.map((s) => action(s.date ? `${s.name} · ${s.date}` : s.name, () => run(() => setSession(s.name)))), divider]
          : []),
        action('New session', newSession),
        ...(session
          ? [
              action('Edit session note', () => openPath(session!.path)),
              action('Show in Finder', () => reveal(session!.path)),
              divider,
              action('Move to Trash', trashSession, true),
            ]
          : []),
      ],
    };
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

<svelte:window on:keydown={onKeydown} />

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
      <span class="bar-sep" aria-hidden="true">·</span>
      {#if session}
        <button type="button" class="session-key" title="Sessions" on:click={sessionMenu}>
          {session.name}{#if session.date}<span class="session-date">{session.date}</span>{/if}<span class="drop" aria-hidden="true">▾</span>
        </button>
      {:else}
        <button type="button" class="session-key ghost" on:click={newSession}>+ session</button>
      {/if}
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
      <div class="prep" class:arming={!!armedBeat}>
        <div class="grid-pane">
          <TrackGrid
            {cols}
            openPath={bufState.path}
            {members}
            {inSession}
            armed={!!armedBeat}
            ambiguous={(name) => isAmbiguous(index!, name)}
            onOpen={(note) => openPath(note.path)}
            onToggleMember={toggleMember}
            onSpent={setSpent}
            onCreateNote={createNote}
            onRenameNote={renameNote}
            onMoveNote={moveNote}
            onTrashNote={(note) => trashNote(note)}
            onRevealNote={(note) => reveal(note.path)}
            onCreateTrack={createTrack}
            onRenameTrack={renameTrack}
            onTrashTrack={trashTrack}
            onRevealTrack={(track) => reveal(track)}
          />
        </div>

        <BeatColumn
          {rows}
          {spare}
          sessionName={session?.name ?? null}
          selectedPath={selectedBeat}
          armedPath={armedBeat}
          onSelect={selectBeat}
          onArm={armBeat}
          onCreate={createBeat}
          onWrite={writeBeat}
          onAddToPlan={(beat) => editPlan('add', { beat: beat.path })}
          onMove={(row, to) => editPlan('move', { at: row.at, to, expect: row.link })}
          onRemove={(row) => editPlan('remove', { at: row.at, expect: row.link })}
          onRename={renameNote}
          onSpent={setSpent}
          onReveal={(beat) => reveal(beat.path)}
          onTrash={(beat) => trashNote(beat, 'Beat')}
        />

        <!-- Kept mounted while closed, so a note opening has an editor to
             land in; closed, it gives the grid its width back. -->
        <aside class="inspector" class:closed={bufState.status === 'empty'}>
          {#if bufState.status !== 'empty'}
            <div class="inspector-head">
              <span class="note-name">{openEntry?.name ?? bufState.path?.split('/').pop()?.replace(/\.md$/, '')}</span>
              {#if openEntry?.track}
                <span class="crumb">{[openEntry.track, openEntry.group].filter(Boolean).join(' › ')}</span>
              {/if}
              <span class="save-state">{STATUS_TEXT[bufState.status] ?? ''}</span>
              {#if openEntry}
                {@const note = openEntry}
                <label class="spent-toggle" title={note.spent ? `Spent ${note.spent}` : 'Mark spent'}>
                  <input
                    type="checkbox"
                    class="app-checkbox"
                    checked={!!note.spent}
                    on:change={(e) => setSpent(note, e.currentTarget.checked)}
                  />
                  spent
                </label>
              {/if}
              <ActionButton label="close" title="Close the note" onClick={() => run(() => buffer.close())} />
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
          {/if}
          <div class="editor-slot">
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
    gap: 0.5rem;
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

  .bar-sep {
    color: var(--text-tertiary);
  }

  .campaign-key,
  .session-key {
    display: flex;
    align-items: baseline;
    gap: 0.35rem;
    padding: 0.1rem 0.35rem;
    background: none;
    border: none;
    border-radius: var(--radius-sm);
    cursor: pointer;
    transition: background var(--transition-fast), color var(--transition-fast);
  }

  .session-key {
    font-family: var(--font-body);
    font-size: 0.95rem;
    color: var(--text-secondary);
  }

  .session-key.ghost {
    color: var(--text-tertiary);
  }

  .campaign-key:hover,
  .session-key:hover {
    background: var(--bg-focused);
    color: var(--text-primary);
  }

  .campaign-key:active,
  .session-key:active {
    transform: scale(0.97);
  }

  .session-date {
    font-size: 0.75rem;
    font-variant-numeric: tabular-nums;
    color: var(--text-tertiary);
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

  /* While a beat is armed, a click on a note edits the beat: the cursor
     says so before the click does. */
  .prep.arming .grid-pane {
    cursor: copy;
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

  .inspector.closed {
    display: none;
  }

  .inspector-head {
    flex-shrink: 0;
    display: flex;
    align-items: baseline;
    gap: 0.6rem;
    padding: 0.55rem 0.75rem 0.4rem 1rem;
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

  .spent-toggle {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    gap: 0.3rem;
    font-size: 0.8rem;
    color: var(--text-secondary);
    cursor: pointer;
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

  .editor-slot {
    flex: 1;
    min-height: 0;
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
