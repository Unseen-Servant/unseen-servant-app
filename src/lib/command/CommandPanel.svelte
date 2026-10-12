<script lang="ts">
  // Command (docs/roadmap/2026-10-11-command-design.md). Prep: campaigns as
  // folders, the grid of tracks, the beat launcher for the active session.
  // Play: the session's board and its arrangement (PlayView). Tab switches
  // between them; the note editor serves both. Everything shown is re-read
  // from the sidecar; file state lives in NoteBuffer, which owns the save
  // rules.
  import { onDestroy, onMount, type Snippet } from 'svelte';
  import type { UnlistenFn } from '@tauri-apps/api/event';
  import { openUrl, revealItemInDir } from '@tauri-apps/plugin-opener';
  import ActionButton from '../ui/ActionButton.svelte';
  import LatchKey from '../ui/LatchKey.svelte';
  import { CARET_RIGHT, PLAY } from '../ui/iconPaths';
  import { confirmPrompt } from '../shell/confirmStore';
  import { menuSlotHeld } from '../shell/menuSlot';
  import { chordHint } from '../shell/keybindings';
  import { appContext, setCampaign, setSession } from '../shell/shellState';
  import BeatColumn from './BeatColumn.svelte';
  import CommandMenu from './CommandMenu.svelte';
  import InlineName from './InlineName.svelte';
  import NoteEditor from './NoteEditor.svelte';
  import PlayView from './PlayView.svelte';
  import ShelfSidebar from './ShelfSidebar.svelte';
  import TrackGrid from './TrackGrid.svelte';
  import { commandApi, onLiveChange, onVaultChange, type PlanEdit, type PlanOp } from './api';
  import { columns, isAmbiguous, linkableNames, type Column } from './columns';
  import { action, choice, divider, heading, type MenuItem, type OpenMenu } from './menu';
  import { NoteBuffer, type BufferState } from './noteBuffer';
  import { activeSession, memberPaths, planRows, sessionNotePaths, unscheduled, type PlanRow } from './prep';
  import type { BeatEntry, CampaignIndex, CommandSettings, LiveSet, NoteEntry, VaultEvent } from './types';

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
  /** A switcher's menu, and whose: its key stays sunk while it is open. */
  let switcher: OpenMenu | null = null;
  let switcherFor: 'campaign' | 'session' | null = null;
  /** The campaign key is the name field: the pen or Rename. */
  let renaming = false;
  /** The session key is the name field: its menu's Rename. */
  let renamingSession = false;
  let mounted = false;
  let unlisten: Promise<UnlistenFn> | null = null;
  let unlistenLive: Promise<UnlistenFn> | null = null;

  /** Which view this panel shows. Per window: Prep on the laptop and Play
   *  on the second screen is two windows. */
  let mode: 'prep' | 'play' = 'prep';
  /** The open campaign's live set (design §6.2), newest by `seq`. */
  let live: LiveSet | null = null;
  let play: PlayView | undefined;
  /** The shelf sidebar in Prep (design §3.6), open until the GM hides it. */
  let shelfOpen = true;

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

  // Named by Command and not yet by the GM: the sidecar's rule
  // (vault.is_untitled). Command opens on one, and leaving it blank removes it.
  $: untitled = !!campaign && /^Untitled(?: [1-9][0-9]*)?$/.test(campaign);
  $: sunk = menu && menu === switcher ? switcherFor : null;
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
    live = null;
    selectedBeat = armedBeat = null;
  }

  /** A live set snapshot, from an answer or the event relay: kept if it's
   *  this campaign's and newer than the one held. */
  function applyLive(next: LiveSet) {
    if (next.campaign !== campaign) return;
    if (live && live.campaign === next.campaign && next.seq <= live.seq) return;
    live = next;
  }

  async function loadLive() {
    if (!campaign) return;
    live = null;
    applyLive(await commandApi.getLive(campaign));
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
      await loadLive();
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
      await loadLive();
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
    play?.diskChanged(event.paths);
    if (refreshTimer) clearTimeout(refreshTimer);
    refreshTimer = setTimeout(() => run(refreshIndex), 120);
  }

  /** Before Command rewrites a note's frontmatter, save what the editor
   *  holds for it, so the rewrite lands on it instead of conflicting. */
  async function settle(path: string) {
    if (bufState.path === path) await buffer.flush();
  }

  function onKeydown(e: KeyboardEvent) {
    if (!active || menu || menuSlotHeld()) return;
    const target = e.target as HTMLElement | null;
    if (target?.closest('input, textarea, select, [contenteditable], .cm-editor')) return;
    // Tab: Prep ⇄ Play, Live's key for its two views, as Legend Lore's
    // tree ⇄ systems. ⇧Tab too: with two views, direction means nothing.
    if (e.key === 'Tab' && !e.metaKey && !e.ctrlKey && !e.altKey && index) {
      e.preventDefault();
      mode = mode === 'prep' ? 'play' : 'prep';
      return;
    }
    // ⌘B: the shelf, as it is Legend Lore's collections sidebar.
    if ((e.metaKey || e.ctrlKey) && !e.altKey && e.key.toLowerCase() === 'b' && index && mode === 'prep') {
      e.preventDefault();
      shelfOpen = !shelfOpen;
      return;
    }
    if (e.key === 'Escape' && armedBeat) armedBeat = null;
  }

  onMount(() => {
    unlisten = onVaultChange(onVault);
    unlistenLive = onLiveChange(applyLive);
    run(loadRoot).then(() => (mounted = true));
  });

  onDestroy(() => {
    if (refreshTimer) clearTimeout(refreshTimer);
    void unlisten?.then((stop) => stop());
    void unlistenLive?.then((stop) => stop());
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

  /** Spending from Play is logged in the session; from Prep it isn't. */
  /** Another campaign's note, copied onto this shelf — and into the armed
   *  beat, if there is one, as a note started then would be. */
  function copyNote(fromCampaign: string, note: NoteEntry) {
    run(async () => {
      const path = await commandApi.copyNote(campaign!, fromCampaign, note.path);
      if (armedBeat) await commandApi.setMember(campaign!, armedBeat, path, true);
      await refreshIndex();
    });
  }

  function setSpent(note: Named, spent: boolean) {
    const logIn = mode === 'play' ? (session?.path ?? null) : null;
    run(async () => {
      await settle(note.path);
      await commandApi.setSpent(campaign!, note.path, spent, logIn);
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

  /** The session's note takes the new name, and its board follows it
   *  (board.follow_rename). The workstation holds the session by name, so
   *  it's pointed at the new one too, or the index would fall back to the
   *  latest session. */
  function renameSession(name: string) {
    const target = session!;
    run(async () => {
      const isOpen = target.path === bufState.path;
      if (isOpen) await buffer.flush();
      const moved = await commandApi.renameNote(campaign!, target.path, name);
      if (isOpen) await buffer.retarget(moved.path);
      await setSession(moved.path.split('/').pop()!.replace(/\.md$/i, ''));
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
        message: 'The session note and its board go; its beats stay in Beats/.',
        confirmLabel: 'Move to Trash',
        danger: true,
      });
      if (!confirmed) return;
      if (bufState.path === target.path) await buffer.close();
      await commandApi.trash(campaign!, target.path);
      // Its board goes with it; a session never arranged has none.
      await commandApi.trash(campaign!, target.path.replace(/\.md$/i, '.canvas')).catch(() => {});
      await setSession(null);
      await refreshIndex();
    });
  }

  function sessionMenu(e: MouseEvent) {
    const others = [...(index?.sessions ?? [])].reverse().filter((s) => s.path !== session?.path);
    dropMenu(e, 'session', [
      ...(others.length
        ? [heading('sessions'), ...others.map((s) => action(s.date ? `${s.name} · ${s.date}` : s.name, () => run(() => setSession(s.name)))), divider]
        : []),
      action('New session', newSession),
      ...(session
        ? [
            action('Edit session note', () => openPath(session!.path)),
            action('Rename', () => (renamingSession = true)),
            action('Show in Finder', () => reveal(session!.path)),
            divider,
            action('Move to Trash', trashSession, true),
          ]
        : []),
    ]);
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

  function openCampaign(name: string) {
    run(() => setCampaign(name));
  }

  /** New campaign: a fresh Untitled, as at launch. Rust opens it in every
   *  window; the list has to know it before this panel follows. */
  function newCampaign() {
    run(async () => {
      await commandApi.openUntitled();
      campaigns = await commandApi.listCampaigns();
    });
  }

  function renameCampaign(name: string) {
    run(async () => {
      const old = campaign!;
      await leaveCampaign();
      try {
        const renamed = await commandApi.renameCampaign(old, name);
        campaigns = await commandApi.listCampaigns();
        await setCampaign(renamed.name);
        await enterCampaign(renamed.name);
      } catch (e) {
        // Refused (the name is taken, say): back to the campaign as it was.
        await enterCampaign(old);
        throw e;
      }
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
      // Command is never left on nothing: a fresh Untitled, as at launch.
      await commandApi.openUntitled();
      await loadRoot();
    });
  }

  /** The switcher, as Obsidian's for vaults: every campaign, the open one
   *  lit, and New campaign at the bottom. */
  function campaignMenu(e: MouseEvent) {
    dropMenu(e, 'campaign', [
      ...campaigns.map((c) => choice(c, c === campaign, () => openCampaign(c))),
      ...(campaigns.length ? [divider] : []),
      action('New campaign', newCampaign),
    ]);
  }

  /** Open a switcher's menu. It hangs off the well, not the half clicked,
   *  so it lines up with the keycap's outer edge. */
  function dropMenu(e: MouseEvent, key: 'campaign' | 'session', items: MenuItem[]) {
    const box = (e.currentTarget as HTMLElement).parentElement!.getBoundingClientRect();
    menu = switcher = { x: box.left, y: box.bottom + 4, items };
    switcherFor = key;
  }

  /** Right-click: what acts on the open campaign, as right-click manages a
   *  track or a note. */
  function manageMenu(e: MouseEvent) {
    if (!campaign) return;
    menu = {
      x: e.clientX,
      y: e.clientY,
      items: [
        action('Rename', () => (renaming = true)),
        action('Show in Finder', () => reveal()),
        divider,
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

{#snippet dropCaret()}
  <!-- Font Awesome caret-right, turned down by .drop-caret -->
  <svg class="drop-caret" viewBox="96 64 512 512" fill="currentColor" aria-hidden="true">
    <path d={CARET_RIGHT} />
  </svg>
{/snippet}

{#snippet pen()}
  <!-- Font Awesome "pen-to-square" icon (src/lib/ui/icons/pen-to-square-solid-full.svg) -->
  <svg viewBox="0 0 640 640" fill="currentColor" aria-hidden="true">
    <path d="M535.6 85.7C513.7 63.8 478.3 63.8 456.4 85.7L432 110.1L529.9 208L554.3 183.6C576.2 161.7 576.2 126.3 554.3 104.4L535.6 85.7zM236.4 305.7C230.3 311.8 225.6 319.3 222.9 327.6L193.3 416.4C190.4 425 192.7 434.5 199.1 441C205.5 447.5 215 449.7 223.7 446.8L312.5 417.2C320.7 414.5 328.2 409.8 334.4 403.7L496 241.9L398.1 144L236.4 305.7zM160 128C107 128 64 171 64 224L64 480C64 533 107 576 160 576L416 576C469 576 512 533 512 480L512 384C512 366.3 497.7 352 480 352C462.3 352 448 366.3 448 384L448 480C448 497.7 433.7 512 416 512L160 512C142.3 512 128 497.7 128 480L128 224C128 206.3 142.3 192 160 192L256 192C273.7 192 288 177.7 288 160C288 142.3 273.7 128 256 128L160 128z"/>
  </svg>
{/snippet}

<section class="command">
  <header class="bar">
    {#if index}
      <!-- Leftmost, where Legend Lore's panel keys sit. The shelf is Prep's,
           so in Play the key stays put, dimmed and inert, and the switchers
           beside it don't move when Tab flips the view. -->
      <div class="panel-keys" class:dimmed={mode === 'play'} inert={mode === 'play'}>
        <LatchKey
          open={shelfOpen}
          lamp={false}
          title={(shelfOpen ? 'Hide the shelf' : 'Show the shelf') + chordHint('sidebar.toggle')}
          label="Toggle the shelf"
          onClick={() => (shelfOpen = !shelfOpen)}
        >
          <!-- Font Awesome "box-archive" icon (src/lib/ui/icons/box-archive-solid-full.svg) -->
          <svg viewBox="0 0 640 640" fill="currentColor">
            <path d="M64 128C64 110.3 78.3 96 96 96L544 96C561.7 96 576 110.3 576 128L576 160C576 177.7 561.7 192 544 192L96 192C78.3 192 64 177.7 64 160L64 128zM96 240L544 240L544 480C544 515.3 515.3 544 480 544L160 544C124.7 544 96 515.3 96 480L96 240zM248 304C234.7 304 224 314.7 224 328C224 341.3 234.7 352 248 352L392 352C405.3 352 416 341.3 416 328C416 314.7 405.3 304 392 304L248 304z"/>
          </svg>
        </LatchKey>
      </div>
    {/if}
    {#if renaming && campaign}
      <div class="bar-name">
        <InlineName
          value={untitled ? '' : campaign}
          placeholder="Campaign name"
          label={untitled ? 'Name campaign' : 'Rename campaign'}
          onCommit={(name) => {
            renaming = false;
            renameCampaign(name);
          }}
          onCancel={() => (renaming = false)}
        />
      </div>
    {:else}
      <!-- The campaign and the session, each one keycap in a well, split in
           two: the switcher (right-click on the campaign's for its own menu)
           and the pen — naming the campaign, opening the session's note. -->
      <div class="cap-well">
        <button
          type="button"
          class="cap-key campaign-key"
          class:untitled
          class:none={!campaign}
          class:open={sunk === 'campaign'}
          title="Campaigns"
          on:click={campaignMenu}
          on:contextmenu|preventDefault={manageMenu}
        >
          <span class="cap-name">{campaign ?? 'no campaign'}</span>
          {@render dropCaret()}
        </button>
        {#if campaign}
          <button
            type="button"
            class="cap-pen"
            title={untitled ? 'Name this campaign' : 'Rename this campaign'}
            aria-label={untitled ? 'Name this campaign' : 'Rename this campaign'}
            on:click={() => (renaming = true)}
          >
            {@render pen()}
          </button>
        {/if}
      </div>
      {#if renamingSession && session}
        <div class="bar-name">
          <InlineName
            value={session.name}
            placeholder="Session name"
            label="Rename session"
            onCommit={(name) => {
              renamingSession = false;
              renameSession(name);
            }}
            onCancel={() => (renamingSession = false)}
          />
        </div>
      {:else if campaign}
        <div class="cap-well">
          {#if session}
            {@const current = session}
            <button
              type="button"
              class="cap-key session-key"
              class:open={sunk === 'session'}
              title="Sessions"
              on:click={sessionMenu}
            >
              <span class="cap-name">{current.name}{#if current.date}<span class="session-date">{current.date}</span>{/if}</span>
              {@render dropCaret()}
            </button>
            <button
              type="button"
              class="cap-pen"
              title="Edit the session note"
              aria-label="Edit the session note"
              on:click={() => openPath(current.path)}
            >
              {@render pen()}
            </button>
          {:else}
            <button type="button" class="cap-key session-key ghost" on:click={newSession}>+ session</button>
          {/if}
        </div>
      {/if}
    {/if}
    <span class="spacer"></span>
    {#if index}
      <!-- View switch — Legend Lore's (Header .view-switch): a picker, not a
           mode, so the current segment sits on a raised fill instead of
           lighting purple. Both glyphs are drawn with viewBox="64 64 512 512",
           the 640 box cropped, so they fill the segment as Legend Lore's
           folder-tree and layer-group do. -->
      <div class="view-switch" role="group" aria-label="Command view">
        <button
          class="view-segment"
          class:current={mode === 'prep'}
          on:click={() => (mode = 'prep')}
          title={'Prep' + chordHint('view.toggle')}
          aria-label="Prep"
          aria-pressed={mode === 'prep'}
        >
          <!-- Font Awesome "table-columns" icon (src/lib/ui/icons/table-columns-solid-full.svg) -->
          <svg viewBox="64 64 512 512" fill="currentColor" class="toggle-icon">
            <path d="M96 160C96 124.7 124.7 96 160 96L480 96C515.3 96 544 124.7 544 160L544 480C544 515.3 515.3 544 480 544L160 544C124.7 544 96 515.3 96 480L96 160zM160 224L160 480L288 480L288 224L160 224zM480 224L352 224L352 480L480 480L480 224z"/>
          </svg>
        </button>
        <button
          class="view-segment"
          class:current={mode === 'play'}
          on:click={() => (mode = 'play')}
          title={'Play' + chordHint('view.toggle')}
          aria-label="Play"
          aria-pressed={mode === 'play'}
        >
          <svg viewBox="64 64 512 512" fill="currentColor" class="toggle-icon">
            <path d={PLAY} />
          </svg>
        </button>
      </div>
    {/if}
    {@render windowKey?.()}
  </header>

  <div class="body">
    {#if !index}
      <div class="empty"></div>
    {:else}
      <div class="workspace" class:arming={mode === 'prep' && !!armedBeat}>
        {#if mode === 'play'}
          {#if session && campaign}
            <PlayView
              bind:this={play}
              {active}
              {campaign}
              {index}
              {session}
              {live}
              {run}
              onLive={applyLive}
              onEdit={openPath}
              onFollow={followLink}
              onSpent={setSpent}
            />
          {:else}
            <div class="empty">
              <p class="lede">Play runs a session: its board, what's live, and the log.</p>
              <ActionButton label="new session" onClick={newSession} />
            </div>
          {/if}
        {:else}
        {#if shelfOpen && campaign}
          <ShelfSidebar
            {campaign}
            {campaigns}
            {index}
            openPath={bufState.path}
            {members}
            {inSession}
            armed={!!armedBeat}
            ambiguous={(name) => isAmbiguous(index!, name)}
            onOpen={(note) => openPath(note.path)}
            onToggleMember={toggleMember}
            onCreate={(name) => createNote('Shelf', name)}
            onRename={renameNote}
            onSpent={setSpent}
            onMove={moveNote}
            onReveal={(note) => reveal(note.path)}
            onTrash={(note) => trashNote(note)}
            onCopy={copyNote}
          />
        {/if}
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
        {/if}

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
              {#if openEntry?.source}
                {@const source = openEntry.source}
                <ActionButton label="source" title="Open the book this came from, at its page" onClick={() => void openUrl(source).catch((e) => (error = String(e)))} />
              {/if}
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
    /* Legend Lore's header inset (Header .header), so the wells at either
       end sit where its keys do. Its header has no bottom rule; the 1px on
       top gives back what this one's takes, so the keys centre at the same
       height and don't jump between tabs. */
    padding: 1px 0.5rem 0;
    background: var(--bg-header);
    border-bottom: 1px solid var(--border-subtle);
  }

  /* The campaign and session keys: each a keycap in a well, LatchKey's
     cut, split by a 1px groove into the switcher and the pen. Both halves
     sit on the raised fill; hover lifts one by a grey step, and a switcher
     sinks to the well floor while its menu is open. */
  .cap-well {
    flex-shrink: 0;
    display: flex;
    gap: 1px;
    padding: 2px;
    background: var(--bg-app);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-well);
  }

  .cap-key,
  .cap-pen {
    display: flex;
    align-items: center;
    height: 22px;
    padding: 0;
    background: var(--bg-header);
    border: none;
    border-radius: var(--radius-md);
    cursor: pointer;
    transition: all var(--transition-fast);
    /* A right-click would otherwise select the word under it. */
    -webkit-user-select: none;
    user-select: none;
  }

  .cap-key {
    gap: 0.5rem;
    max-width: 16rem;
    padding: 0 0.5rem 0 0.55rem;
    font-size: 0.95rem;
  }

  /* Squared where the groove parts it from the pen. */
  .cap-key:not(:last-child) {
    border-top-right-radius: 0;
    border-bottom-right-radius: 0;
  }

  .cap-pen {
    justify-content: center;
    width: 26px;
    color: var(--text-tertiary);
    border-top-left-radius: 0;
    border-bottom-left-radius: 0;
  }

  .cap-pen svg {
    width: 12px;
    height: 12px;
  }

  .cap-key:active,
  .cap-pen:active {
    transform: scale(0.97);
  }

  .cap-name {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    text-align: left;
  }

  /* Font Awesome caret-right turned down: always a drop, never a
     disclosure, so it doesn't take app.css's .caret. */
  .drop-caret {
    flex-shrink: 0;
    width: 8px;
    height: 8px;
    transform: rotate(90deg);
    color: var(--text-tertiary);
    transition: color var(--transition-fast);
  }

  .cap-key:hover .drop-caret,
  .cap-key.open .drop-caret {
    color: var(--text-primary);
  }

  .campaign-key {
    min-width: 9rem;
    font-family: var(--font-heading);
    font-size: 0.875rem;
    color: var(--text-primary);
  }

  /* Not named yet. Italic says so without a badge; the pen beside it is
     the way out. */
  .campaign-key.untitled,
  .campaign-key.none {
    font-style: italic;
  }

  .campaign-key.none {
    color: var(--text-tertiary);
  }

  /* One voice below the campaign: body face, secondary ink. */
  .session-key {
    font-family: var(--font-body);
    color: var(--text-secondary);
  }

  .session-key.ghost {
    color: var(--text-tertiary);
  }

  .session-date {
    margin-left: 0.4rem;
    font-size: 0.75rem;
    font-variant-numeric: tabular-nums;
    color: var(--text-tertiary);
  }

  /* Late, so hover brightens every cap, the dim ones included — and an
     open switcher stays sunk under the pointer. */
  .cap-key:hover,
  .cap-pen:hover {
    background: var(--bg-focused);
    color: var(--text-primary);
  }

  .cap-key.open {
    background: var(--bg-app);
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

  .workspace {
    height: 100%;
    display: flex;
  }

  .workspace > .empty {
    flex: 1;
  }

  .grid-pane {
    flex: 1;
    min-width: 0;
  }

  /* While a beat is armed, a click on a note edits the beat: the cursor
     says so before the click does. */
  .workspace.arming .grid-pane {
    cursor: copy;
  }

  /* Legend Lore's panel keys (Header .panel-keys): latches side by side. */
  .panel-keys {
    display: flex;
    gap: 0.3rem;
  }

  .panel-keys.dimmed {
    opacity: var(--opacity-out-of-scope);
  }

  /* Prep ⇄ Play: Legend Lore's view switch (Header .view-switch), rule for
     rule — two icon segments in a darker well, the current one raised. */
  .view-switch {
    display: flex;
    gap: 2px;
    padding: 2px;
    background: var(--bg-app);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-well);
    flex-shrink: 0;
  }

  .view-segment {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 22px;
    background: transparent;
    border: none;
    border-radius: var(--radius-md);
    color: var(--text-tertiary);
    cursor: pointer;
    padding: 0;
    transition: all var(--transition-fast);
  }

  .view-segment:hover {
    color: var(--text-primary);
  }

  .view-segment.current {
    background: var(--bg-header);
    color: var(--text-primary);
  }

  .toggle-icon {
    width: 14px;
    height: 14px;
    display: block;
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
