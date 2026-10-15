<script lang="ts">
  // Command (docs/roadmap/2026-10-11-command-design.md). Prep: campaigns as
  // folders, the grid of tracks, the beat launcher for the active session.
  // Play: the session's board and its arrangement (PlayView). Tab switches
  // between them; the note editor serves both. Everything shown is re-read
  // from the sidecar; file state lives in NoteBuffer, which owns the save
  // rules.
  import { onDestroy, onMount, tick, type Snippet } from 'svelte';
  import type { UnlistenFn } from '@tauri-apps/api/event';
  import { openUrl, revealItemInDir } from '@tauri-apps/plugin-opener';
  import ActionButton from '../ui/ActionButton.svelte';
  import LatchKey from '../ui/LatchKey.svelte';
  import RenameField from '../ui/RenameField.svelte';
  import { CARET_RIGHT, PLAY } from '../ui/iconPaths';
  import { confirmPrompt } from '../shell/confirmStore';
  import KeyboardHelpOverlay from '../shell/KeyboardHelpOverlay.svelte';
  import { menuSlotHeld } from '../shell/menuSlot';
  import { chordHint } from '../shell/keybindings';
  import { appContext, setCampaign, setSession } from '../shell/shellState';
  import BeatColumn from './BeatColumn.svelte';
  import CommandMenu from './CommandMenu.svelte';
  import NoteEditor from './NoteEditor.svelte';
  import NoteReader from './NoteReader.svelte';
  import PlayView from './PlayView.svelte';
  import ShelfSidebar from './ShelfSidebar.svelte';
  import TrackGrid from './TrackGrid.svelte';
  import { commandApi, onLiveChange, onVaultChange, type PlanEdit, type PlanOp } from './api';
  import { columns, isAmbiguous, linkableNames, type Column } from './columns';
  import { action, choice, divider, heading, type MenuItem, type OpenMenu } from './menu';
  import { NoteBuffer, type BufferState } from './noteBuffer';
  import { activeSession, beatOrder, memberPaths, planRows, sessionNotePaths, unscheduled, type PlanRow } from './prep';
  import type { BeatEntry, CampaignIndex, CommandSettings, LiveSet, NoteEntry, VaultEvent } from './types';

  // True while the panel is visible: window-level keys do nothing otherwise
  // (PANELS.md).
  export let active: boolean = true;
  // The host's dock toggle (PANELS.md), drawn at the right of the bar.
  export let windowKey: Snippet | undefined = undefined;

  /** What a rename, move, spend or trash needs of a note or a beat. */
  type Named = { name: string; path: string };

  /** A note's name: its file's, without folders or `.md`. */
  const stem = (path: string) => path.split('/').pop()!.replace(/\.md$/i, '');

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
  /** The campaign key is the name field: Rename, from either of its menus. */
  let renaming = false;
  /** The campaign key, measured as a rename starts so the field takes
   *  just its width and the session's key doesn't move. */
  let campaignFace: HTMLButtonElement | null = null;
  let renameWidth = 0;
  function startRenaming() {
    renameWidth = campaignFace?.offsetWidth ?? 0;
    renaming = true;
  }
  /** The open note's title is its name field. */
  let renamingOpen = false;
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
  /** The beat column in Prep, the same. */
  let beatsOpen = true;

  /** The row clicked last, a note's or a beat's: what R renames. A note's
   *  wears Legend Lore's focus ring. */
  let selected: string | null = null;
  /** The focused beat (design §5.1, beat states): ringed, its notes lit
   *  across the tracks, until it's clicked again, another is, or Esc.
   *  Selecting or opening a note leaves it, so its notes can be read one
   *  by one. */
  let focusedBeat: string | null = null;
  /** The focused beat is armed: a click on a note puts it in the beat or
   *  takes it out. A flag on the focus, never a beat of its own. */
  let armed = false;
  $: armedBeat = armed ? focusedBeat : null;

  let editor: NoteEditor | undefined;
  /** The lists a selected row is in, for R. */
  let grid: TrackGrid | undefined;
  let shelf: ShelfSidebar | undefined;
  let beats: BeatColumn | undefined;
  /** The shortcut sheet, Legend Lore's. */
  let showHelp = false;
  let bufState: BufferState = { path: null, status: 'empty', error: null };
  // A note just opened takes the caret to the top; a reload keeps it.
  let freshOpen = false;

  /** The open note read rendered rather than edited (⌘E, Obsidian's
   *  reading view). It stays with the window as notes open, as a tab keeps
   *  its mode in Obsidian. */
  let reading = false;
  /** The editor's text, for the reader: what's loaded, then every edit. */
  let noteText = '';

  const buffer = new NoteBuffer(
    {
      read: (path) => commandApi.readNote(campaign!, path),
      save: (path, content, baseHash) => commandApi.saveNote(campaign!, path, content, baseHash),
    },
    (state) => (bufState = state),
    (content) => {
      noteText = content;
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
  $: openName = openEntry?.name ?? (bufState.path ? stem(bufState.path) : '');
  $: renamable = bufState.status !== 'conflict' && bufState.status !== 'unreadable';
  $: session = index ? activeSession(index, $appContext.session) : null;
  $: rows = index ? planRows(index, session) : [];
  $: spare = index ? unscheduled(index, session, true) : [];
  $: beatAt = (path: string | null) => index?.beats.find((b) => b.path === path) ?? null;
  $: members = memberPaths(beatAt(focusedBeat));
  $: inSession = index ? sessionNotePaths(index, session) : new Set<string>();
  // A note or beat that left (renamed, moved, trashed) can't stay selected,
  // nor a beat focused or armed.
  $: if (index && selected && !beatAt(selected) && !index.notes.some((n) => n.path === selected)) selected = null;
  $: if (index && focusedBeat && !beatAt(focusedBeat)) focusBeat(null);

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

  /** As run, for a rename field, which shows a refusal itself: resolves its
   *  reason, or null when the job went through, and leaves the error line
   *  alone. */
  function attempt(job: () => Promise<void>): Promise<string | null> {
    let refusal: string | null = null;
    queue = queue.then(async () => {
      try {
        await job();
      } catch (e) {
        refusal = String(e);
      }
    });
    return queue.then(() => refusal);
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
    selected = null;
    focusBeat(null);
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
    // Something live may be gone: reading the set again lets go of it.
    const held = live ? [live.beat, ...live.notes] : [];
    if (event.paths.some((p) => held.includes(p))) run(async () => applyLive(await commandApi.getLive(campaign!)));
  }

  /** Before Command rewrites a note's frontmatter, save what the editor
   *  holds for it, so the rewrite lands on it instead of conflicting. */
  async function settle(path: string) {
    if (bufState.path === path) await buffer.flush();
  }

  function onKeydown(e: KeyboardEvent) {
    if (!active || menu || menuSlotHeld()) return;
    // An open dialog's keys still bubble here past the inert page; they're
    // the dialog's, as in Legend Lore.
    if (document.querySelector('dialog[open]')) return;
    const target = e.target as HTMLElement | null;
    // ⌘E: read the open note or edit it, as Obsidian's, from the editor
    // too, but not while a name is typed.
    if ((e.metaKey || e.ctrlKey) && !e.altKey && !e.shiftKey && e.key.toLowerCase() === 'e' && bufState.status !== 'empty') {
      if (target?.closest('input, textarea')) return;
      e.preventDefault();
      toggleReading();
      return;
    }
    if (target?.closest('input, textarea, select, [contenteditable], .cm-editor')) return;
    // ? or ⌘/: the shortcut sheet, as in Legend Lore. Not from the editor,
    // where ⌘/ is CodeMirror's comment.
    const mod = e.metaKey || e.ctrlKey;
    if ((e.key === '?' && !mod && !e.altKey) || (mod && !e.altKey && e.key === '/')) {
      e.preventDefault();
      showHelp = true;
      return;
    }
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
    // R: the selected row is renamed where it stands, as Legend Lore's R
    // renames the focused one. Kept from the field it opens, or the R types
    // over the name.
    if (e.key.toLowerCase() === 'r' && !mod && !e.altKey && !e.shiftKey && !e.isComposing && selected && mode === 'prep') {
      e.preventDefault();
      if (e.repeat) return;
      for (const list of [grid, shelf, beats]) list?.rename(selected);
      return;
    }
    // Esc undoes the louder thing first, as in Legend Lore: the arm, then
    // the focused beat, then the selection. Prep's: Play has no arm.
    if (e.key === 'Escape' && mode === 'prep') {
      if (armed) armed = false;
      else if (focusedBeat) focusBeat(null);
      else selected = null;
    }
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
      selected = path;
      freshOpen = true;
      await buffer.open(path);
      // A new note is empty: there's nothing to read yet.
      reading = false;
      await tick();
      editor?.focus();
    });
  }

  /** Back to editing puts the caret in the text, as Obsidian does. */
  function toggleReading() {
    reading = !reading;
    if (!reading) void tick().then(() => editor?.focus());
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

  /** Any note: a track's, the shelf's, a beat, a session. The sidecar
   *  rewrites links to it and moves a session's board along. The workstation
   *  holds the active session by name, so renaming that one points it at the
   *  new name, or the index would fall back to the latest session. */
  function renameNote(note: Named, name: string): Promise<string | null> {
    const isSession = note.path === session?.path;
    return attempt(async () => {
      // A selected row or armed beat is pointed at its new path only once
      // the index holds it: before that, the guard on one that left clears it.
      const wasSelected = selected === note.path;
      const wasFocused = focusedBeat === note.path;
      const wasArmed = armedBeat === note.path;
      const isOpen = note.path === bufState.path;
      if (isOpen) await buffer.flush();
      const moved = await commandApi.renameNote(campaign!, note.path, name);
      if (isOpen) await buffer.retarget(moved.path);
      if (isSession) await setSession(stem(moved.path));
      await refreshIndex();
      if (wasSelected) selected = moved.path;
      if (wasFocused) focusBeat(moved.path, wasArmed);
    });
  }

  /** A note moved to a track or a group's folder, where it goes first.
   *  Dropped between rows there, `order` is that folder's notes with it in
   *  place, saved with the move so its refresh already shows it there. */
  function moveNote(note: NoteEntry, folder: string, order?: string[]) {
    run(async () => {
      const isOpen = note.path === bufState.path;
      const wasSelected = selected === note.path;
      if (isOpen) await buffer.flush();
      const moved = await commandApi.moveNote(campaign!, note.path, folder, order);
      if (isOpen) await buffer.retarget(moved.path);
      await refreshIndex();
      if (wasSelected) selected = moved.path;
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

  /** A click in Prep on anything but a row — empty space, a plate, a ghost
   *  row — drops the selection, as in Legend Lore's panels. Not in a field,
   *  a menu, or the editor, where the open note is worked on. */
  function releaseSelection(e: MouseEvent) {
    if (mode !== 'prep') return;
    if ((e.target as HTMLElement | null)?.closest('[data-row], input, [role="menu"], .inspector')) return;
    selected = null;
  }

  /** Hiding the beat column disarms, as closing Legend Lore's collections
   *  panel does: a click on a note mustn't file into a beat out of sight.
   *  The lit beat lets go too, or its notes would stay lit unexplained. */
  function toggleBeats() {
    beatsOpen = !beatsOpen;
    if (beatsOpen) return;
    focusBeat(null);
    if (beatAt(selected)) selected = null;
  }

  /** The one way the focus moves: focusing another beat, or none, disarms. */
  function focusBeat(path: string | null, arm = false) {
    focusedBeat = path;
    armed = !!path && arm;
  }

  /** A click on a beat focuses it; on the focused beat, it lets go. */
  function selectBeat(beat: BeatEntry) {
    selected = beat.path;
    focusBeat(focusedBeat === beat.path ? null : beat.path);
  }

  /** A right-click focuses without letting go, so the menu and the keys
   *  act on the beat it shows. An armed beat stays armed. */
  function focusOn(beat: BeatEntry) {
    selected = beat.path;
    if (focusedBeat !== beat.path) focusBeat(beat.path);
  }

  function armBeat(beat: BeatEntry) {
    // Disarming keeps the focus. Arming focuses, as in Legend Lore; the
    // editor waits for a double-click.
    if (armedBeat === beat.path) armed = false;
    else {
      selected = beat.path;
      focusBeat(beat.path, true);
    }
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

  /** Prep doesn't launch (design §5.1), but the live beat's ■ stops the
   *  set wherever it shows. */
  function stopLive() {
    run(async () => applyLive(await commandApi.stop(campaign!)));
  }

  /** The beats outside the plan, dragged into a new order. The list takes
   *  it at once, then the campaign keeps it (.unseen/command.json). */
  function orderBeats(visible: string[]) {
    if (!index) return;
    const order = beatOrder(index, visible);
    const rank = new Map(order.map((name, i) => [name, i]));
    index = { ...index, beats: [...index.beats].sort((a, b) => (rank.get(a.name) ?? 0) - (rank.get(b.name) ?? 0)) };
    run(async () => {
      await commandApi.orderBeats(campaign!, order);
      await refreshIndex();
    });
  }

  /** A note dropped on a beat joins it, as a book dropped on a collection. */
  function addToBeat(beat: BeatEntry, path: string) {
    run(async () => {
      await settle(beat.path);
      await commandApi.setMember(campaign!, beat.path, path, true);
      await refreshIndex();
    });
  }

  /** A new beat lands armed and selected, as a new collection does, and
   *  opens nothing: a double-click opens it. */
  function landBeat(path: string) {
    selected = path;
    focusBeat(path, true);
  }

  function createBeat(name: string, notes: string[] = []) {
    run(async () => {
      const path = await commandApi.createBeat(campaign!, name, notes, session?.path ?? null);
      await refreshIndex();
      landBeat(path);
    });
  }

  /** A plan entry naming a beat nobody has written yet: write it. */
  function writeBeat(row: PlanRow) {
    run(async () => {
      const path = await commandApi.createBeat(campaign!, row.link, [], null);
      await refreshIndex();
      landBeat(path);
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

  function renameTrack(track: string, name: string): Promise<string | null> {
    return attempt(async () => {
      const open = bufState.path;
      const inside = open !== null && open.startsWith(`${track}/`);
      if (inside) await buffer.flush();
      const renamed = await commandApi.renameTrack(campaign!, track, name);
      if (inside) await buffer.retarget(renamed.name + open!.slice(track.length));
      await refreshIndex();
    });
  }

  /** The tracks, dragged into a new order. The grid takes it at once, then
   *  the campaign keeps it (.unseen/command.json). */
  function orderTracks(order: string[]) {
    if (!index) return;
    index = { ...index, tracks: order };
    run(async () => {
      await commandApi.orderTracks(campaign!, order);
      await refreshIndex();
    });
  }

  /** A track's pigment, or none. The plate takes it at once, then the
   *  campaign keeps it (.unseen/command.json). */
  function pigmentTrack(track: string, pigment: string | null) {
    if (!index) return;
    const { [track]: _, ...others } = index.pigments;
    index = { ...index, pigments: pigment ? { ...others, [track]: pigment } : others };
    run(async () => {
      await commandApi.pigmentTrack(campaign!, track, pigment);
      await refreshIndex();
    });
  }

  /** A folder's notes, dragged into a new order in their column. The
   *  column takes it at once, then the campaign keeps it
   *  (.unseen/command.json). */
  function orderNotes(folder: string, names: string[]) {
    if (!index) return;
    index = { ...index, note_order: { ...index.note_order, [folder]: names } };
    run(async () => {
      await commandApi.orderNotes(campaign!, folder, names);
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

  /** New campaign: a fresh Untitled, as on a first launch. Rust opens it
   *  in every window; the list has to know it before this panel follows. */
  function newCampaign() {
    run(async () => {
      await commandApi.openUntitled();
      campaigns = await commandApi.listCampaigns();
    });
  }

  function renameCampaign(name: string): Promise<string | null> {
    return attempt(async () => {
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
      // Command is never left on nothing: a fresh Untitled, as on a first launch.
      await commandApi.openUntitled();
      await loadRoot();
    });
  }

  /** The switcher, as Obsidian's for vaults: every campaign, the open one
   *  lit. Then, as the session's menu, New campaign and what acts on the
   *  open one, Move to Trash under a rule. */
  function campaignMenu(e: MouseEvent) {
    dropMenu(e, 'campaign', [
      ...campaigns.map((c) => choice(c, c === campaign, () => openCampaign(c))),
      ...(campaigns.length ? [divider] : []),
      action('New campaign', newCampaign),
      ...(campaign
        ? [
            action(untitled ? 'Name campaign' : 'Rename campaign', startRenaming),
            action('Show in Finder', () => reveal()),
            divider,
            action('Move to Trash', trashCampaign, true),
          ]
        : []),
    ]);
  }

  /** Open a switcher's menu. It hangs off the key's body, not the face
   *  clicked inside it, so it lines up with the key's outer edge. */
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
        action('Rename', startRenaming),
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
    <!-- The campaign and the session, each a key in its own well that opens
         its switcher; what acts on the open one is in that menu (and, for
         the campaign, on right-click too). -->
    <div class="key-body">
      <!-- Renamed in the key's place, face and width: the session's key
           stays put. Not gated on the campaign: a rename leaves it while
           the folder moves, and the field stays to show a refusal. -->
      {#if renaming}
        <span class="key-field" style:width={renameWidth ? `${renameWidth}px` : null}>
          <RenameField
            value={untitled || !campaign ? '' : campaign}
            placeholder="Campaign name"
            label={untitled ? 'Name campaign' : 'Rename campaign'}
            onCommit={async (name) => {
              const refusal = await renameCampaign(name);
              if (!refusal) renaming = false;
              return refusal;
            }}
            onCancel={() => (renaming = false)}
          />
        </span>
      {:else}
        <button
          bind:this={campaignFace}
          type="button"
          class="key-face campaign-key"
          class:untitled
          class:none={!campaign}
          class:open={sunk === 'campaign'}
          title="Campaigns"
          on:click={campaignMenu}
          on:contextmenu|preventDefault={manageMenu}
        >
          <span class="key-name">{campaign ?? 'no campaign'}</span>
          {@render dropCaret()}
        </button>
      {/if}
    </div>
    {#if campaign}
      <!-- The session is the campaign's: Legend Lore's path mark between
           them, printed on the bar as a faceplate prints its signal flow,
           not a key. -->
      <span class="bar-sep" aria-hidden="true">›</span>
      <div class="key-body">
        {#if session}
          {@const current = session}
          <button
            type="button"
            class="key-face session-key"
            class:open={sunk === 'session'}
            title="Sessions"
            on:click={sessionMenu}
          >
            <span class="key-name">{current.name}</span>
            {@render dropCaret()}
          </button>
          <!-- The well's second key starts the next session from the bar;
               the menu keeps New session too. -->
          <button type="button" class="key-face key-add" title="New session" aria-label="New session" on:click={newSession}>
            <!-- Font Awesome "plus" icon (src/lib/ui/icons/plus-solid-full.svg) -->
            <svg viewBox="0 0 640 640" fill="currentColor" aria-hidden="true">
              <path d="M352 128C352 110.3 337.7 96 320 96C302.3 96 288 110.3 288 128L288 288L128 288C110.3 288 96 302.3 96 320C96 337.7 110.3 352 128 352L288 352L288 512C288 529.7 302.3 544 320 544C337.7 544 352 529.7 352 512L352 352L512 352C529.7 352 544 337.7 544 320C544 302.3 529.7 288 512 288L352 288L352 128z" />
            </svg>
          </button>
        {:else}
          <button type="button" class="key-face session-key ghost" on:click={newSession}>+ session</button>
        {/if}
      </div>
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
      <!-- The beat column's key, on the side the column opens: between the
           view switch and the window's key. Prep's, so dimmed and inert in
           Play, as the shelf's. Its lamp answers for the beats as Legend
           Lore's collections lamp answers for the mix: lit while a beat is
           armed or live, so a hidden column still says so. -->
      <div class="panel-keys" class:dimmed={mode === 'play'} inert={mode === 'play'}>
        <LatchKey
          open={beatsOpen}
          lit={armed || !!live?.beat}
          title={beatsOpen ? 'Hide the beats' : 'Show the beats'}
          label="Toggle the beats"
          onClick={toggleBeats}
        >
          <!-- Font Awesome "list-ol" icon (src/lib/ui/icons/list-ol-solid-full.svg) -->
          <svg viewBox="0 0 640 640" fill="currentColor">
            <path d="M64 136C64 122.8 74.7 112 88 112L136 112C149.3 112 160 122.7 160 136L160 240L184 240C197.3 240 208 250.7 208 264C208 277.3 197.3 288 184 288L88 288C74.7 288 64 277.3 64 264C64 250.7 74.7 240 88 240L112 240L112 160L88 160C74.7 160 64 149.3 64 136zM94.4 365.2C105.8 356.6 119.7 352 134 352L138.9 352C172.6 352 200 379.4 200 413.1C200 432.7 190.6 451 174.8 462.5L150.8 480L184 480C197.3 480 208 490.7 208 504C208 517.3 197.3 528 184 528L93.3 528C77.1 528 64 514.9 64 498.7C64 489.3 68.5 480.5 76.1 475L146.6 423.7C150 421.2 152 417.3 152 413.1C152 405.9 146.1 400 138.9 400L134 400C130.1 400 126.3 401.3 123.2 403.6L102.4 419.2C91.8 427.2 76.8 425 68.8 414.4C60.8 403.8 63 388.8 73.6 380.8L94.4 365.2zM288 128L544 128C561.7 128 576 142.3 576 160C576 177.7 561.7 192 544 192L288 192C270.3 192 256 177.7 256 160C256 142.3 270.3 128 288 128zM288 288L544 288C561.7 288 576 302.3 576 320C576 337.7 561.7 352 544 352L288 352C270.3 352 256 337.7 256 320C256 302.3 270.3 288 288 288zM288 448L544 448C561.7 448 576 462.3 576 480C576 497.7 561.7 512 544 512L288 512C270.3 512 256 497.7 256 480C256 462.3 270.3 448 288 448z"/>
          </svg>
        </LatchKey>
      </div>
    {/if}
    {@render windowKey?.()}
  </header>

  <div class="body">
    {#if !index}
      <div class="empty"></div>
    {:else}
      <div class="workspace" class:arming={mode === 'prep' && !!armedBeat} role="presentation" on:mousedown={releaseSelection}>
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
            bind:this={shelf}
            {campaign}
            {campaigns}
            {index}
            openPath={bufState.path}
            selectedPath={selected}
            onSelect={(note) => (selected = note.path)}
            {members}
            {inSession}
            {armed}
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
            bind:this={grid}
            {cols}
            pigments={index.pigments}
            openPath={bufState.path}
            selectedPath={selected}
            onSelect={(note) => (selected = note.path)}
            {members}
            litBeatName={beatAt(focusedBeat)?.name ?? null}
            {inSession}
            {armed}
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
            onReorderTracks={orderTracks}
            onPigmentTrack={pigmentTrack}
            onReorderNotes={orderNotes}
            onRevealTrack={(track) => reveal(track)}
          />
        </div>

        {#if beatsOpen}
          <BeatColumn
            bind:this={beats}
            {rows}
            {spare}
            sessionName={session?.name ?? null}
            focusedPath={focusedBeat}
            armedPath={armedBeat}
            onSelect={selectBeat}
            onFocus={focusOn}
            onOpen={(beat) => openPath(beat.path)}
            onArm={armBeat}
            liveBeat={live?.beat ?? null}
            onStop={stopLive}
            onCreate={createBeat}
            onWrite={writeBeat}
            onAddToPlan={(beat, to) => editPlan('add', { beat: beat.path, to })}
            onMove={(row, to) => editPlan('move', { at: row.at, to, expect: row.link })}
            onRemove={(row) => editPlan('remove', { at: row.at, expect: row.link })}
            onRename={renameNote}
            onSpent={setSpent}
            onReveal={(beat) => reveal(beat.path)}
            onTrash={(beat) => trashNote(beat, 'Beat')}
            onDropNote={addToBeat}
            onReorder={orderBeats}
          />
        {/if}
        {/if}

        <!-- Kept mounted while closed, so a note opening has an editor to
             land in; closed, it gives the grid its width back. -->
        <aside class="inspector" class:closed={bufState.status === 'empty'}>
          {#if bufState.status !== 'empty'}
            <!-- Legend Lore's inspector plate (InspectorPlate), level with the
                 track and beat plates across the seam: where the note lives
                 (its track, the pigment standing where the system's shield
                 does), the group › name path, and the plate's bracketed
                 actions, so the text below gets the pane's height. Spent
                 is a readout here; the rows' menus mark it. -->
            <div class="inspector-plate nameplate">
              <div class="line">
                {#if openEntry?.track}
                  {@const pigment = index?.pigments[openEntry.track]}
                  <span class="source">
                    {#if pigment}<span class="swatch" style:background={pigment} aria-hidden="true"></span>{/if}
                    <span class="source-track">{openEntry.track}</span>
                  </span>
                  <span class="rule" aria-hidden="true"></span>
                {/if}
                <span class="path">
                  {#if openEntry?.group}
                    <span class="path-head">
                      <span class="segment">{openEntry.group}</span>
                      <span class="sep" aria-hidden="true">›</span>
                    </span>
                  {/if}
                  <!-- The title is the note's name field, as Obsidian's inline
                       title: any note renames here, a beat or a session
                       included. Not while the disk and the editor disagree. -->
                  {#if renamingOpen && bufState.path}
                    {@const path = bufState.path}
                    <span class="note-name-field">
                      <RenameField
                        value={openName}
                        placeholder="Note name"
                        label="Rename note"
                        onCommit={async (name) => {
                          const refusal = await renameNote({ name: openName, path }, name);
                          if (!refusal) renamingOpen = false;
                          return refusal;
                        }}
                        onCancel={() => (renamingOpen = false)}
                      />
                    </span>
                  {:else}
                    <button
                      type="button"
                      class="note-name"
                      title="Rename"
                      disabled={!renamable}
                      on:click={() => (renamingOpen = true)}
                    >{openName}</button>
                  {/if}
                </span>
              </div>
              {#if openEntry?.spent}
                <span class="readout">spent {openEntry.spent}</span>
              {/if}
              {#if STATUS_TEXT[bufState.status]}
                <span class="readout">{STATUS_TEXT[bufState.status]}</span>
              {/if}
              <!-- Names what it switches to, as the plate's other actions
                   name what they do. -->
              <button
                type="button"
                class="plate-btn"
                title={(reading ? 'Edit the note' : 'Read the note rendered') + chordHint('command.read')}
                on:click={toggleReading}
              >{reading ? 'edit' : 'read'}</button>
              {#if openEntry?.source}
                {@const source = openEntry.source}
                <button
                  type="button"
                  class="plate-btn"
                  title="Open the book this came from, at its page"
                  on:click={() => void openUrl(source).catch((e) => (error = String(e)))}
                >source</button>
              {/if}
              <button type="button" class="plate-btn" title="Close the note" on:click={() => run(() => buffer.close())}>close</button>
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
          <!-- Reading hides the editor rather than unmounting it, so its
               undo history and caret are there on the way back. -->
          {#if reading && bufState.status !== 'empty'}
            <div class="editor-slot">
              <NoteReader
                text={noteText}
                resolves={(name) => nameSet.has(name.toLowerCase())}
                onFollow={followLink}
                onError={(message) => (error = message)}
              />
            </div>
          {/if}
          <div class="editor-slot" class:hidden={reading}>
            <NoteEditor
              bind:this={editor}
              names={() => (index ? linkableNames(index) : [])}
              resolves={(name) => nameSet.has(name.toLowerCase())}
              onEdit={(content) => {
                noteText = content;
                buffer.edit(content);
              }}
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

<KeyboardHelpOverlay visible={showHelp} onClose={() => (showHelp = false)} />

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

  /* The campaign and session keys, each in a latch's well (LatchKey
     .key-well), so they share one outline and floor with every well here.
     A name is its switcher's pick, so it sits on the raised fill as the
     current view segment and tab do, and sinks to the floor while its menu
     is open. Hover lightens the ink only, as on a latch. The session's well
     holds a second key, New session. */
  .key-body {
    flex-shrink: 0;
    display: flex;
    gap: 2px;
    padding: 2px;
    background: var(--bg-app);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-well);
  }

  .key-face {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    max-width: 16rem;
    height: 22px;
    padding: 0 0.5rem 0 0.55rem;
    background: var(--bg-header);
    border: none;
    border-radius: var(--radius-md);
    /* Both keys in one voice, the body face. The name is what's in
       effect, so it's lit as the current tab and view segment are: primary
       ink, while what's off (+ session, no campaign) stays tertiary. */
    font-family: var(--font-body);
    font-size: 0.95rem;
    color: var(--text-primary);
    cursor: pointer;
    transition: all var(--transition-fast);
    /* A right-click would otherwise select the word under it. */
    -webkit-user-select: none;
    user-select: none;
  }

  .key-face:active {
    transform: scale(0.97);
  }

  .key-name {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    text-align: left;
  }

  /* New session, the session well's second key: a latch's width, 2px from
     the switcher as Prep is from Play. An action, so it sits on the floor
     in off-ink until the pointer's on it, as a latch's glyph does. */
  .key-add {
    justify-content: center;
    width: 26px;
    padding: 0;
    background: transparent;
    color: var(--text-tertiary);
  }

  .key-add svg {
    width: 12px;
    height: 12px;
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

  .key-face:hover .drop-caret,
  .key-face.open .drop-caret {
    color: var(--text-primary);
  }

  .campaign-key {
    min-width: 9rem;
  }

  /* Not named yet. Italic says so without a badge; Name campaign, in its
     menu, is the way out. */
  .campaign-key.untitled,
  .campaign-key.none {
    font-style: italic;
  }

  /* Nothing picked: no campaign, or a campaign with no session yet. Off,
     so on the floor in tertiary ink. */
  .campaign-key.none,
  .session-key.ghost {
    background: transparent;
    color: var(--text-tertiary);
  }

  /* Late, so hover brightens every key's ink, the dim ones included. */
  .key-face:hover {
    color: var(--text-primary);
  }

  .key-face.open {
    background: transparent;
    color: var(--text-primary);
  }

  /* The campaign key's face while it's renamed: its height, inset and
     face, upright even for an Untitled one, so the name is typed where it
     was read. */
  .key-field {
    display: flex;
    align-items: center;
    height: 22px;
    min-width: 9rem;
    padding: 0 0.5rem 0 0.55rem;
    font-family: var(--font-body);
    font-size: 0.95rem;
  }

  /* Legend Lore's path mark (InspectorPlate .sep), printed on the panel
     rather than lit: secondary ink, a step above its tertiary so it sits
     with the names; the bar's gap spaces it. */
  .bar-sep {
    flex-shrink: 0;
    color: var(--text-secondary);
    -webkit-user-select: none;
    user-select: none;
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

  /* InspectorPlate's, at the track plates' height and inset (TrackGrid
     .nameplate) and ruled below as they are. Padded on the left to the
     text's inset (editorTheme .cm-content), so the path starts over the
     note it names. */
  .inspector-plate {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    gap: 0.6rem;
    padding: 0.2rem 0.9rem 0.15rem 1.1rem;
    border-bottom: 1px solid var(--border-subtle);
    font-family: var(--font-body);
  }

  /* One baseline for the track and the path, as InspectorPlate .line:
     centring each in its own box lets Crimson and Almendra drift apart. */
  .line {
    flex: 1;
    min-width: 0;
    display: flex;
    align-items: baseline;
    gap: 0.6rem;
  }

  /* The track, in the row voice InspectorPlate gives the book and system. */
  .source {
    flex: 0 0 auto;
    max-width: 10rem;
    display: flex;
    align-items: baseline;
    gap: 0.35rem;
    overflow: hidden;
    white-space: nowrap;
    font-size: 0.75rem;
    color: var(--text-secondary);
  }

  .source-track {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  /* The track's pigment, square as its plate (no glow: it names the
     track, it isn't lit), where the system's shield stands in Legend Lore. */
  .swatch {
    flex-shrink: 0;
    align-self: center;
    width: 7px;
    height: 7px;
    border-radius: var(--radius-cell);
  }

  /* The scope bar's master rule, between the track and the path. */
  .rule {
    flex-shrink: 0;
    align-self: center;
    width: 1px;
    height: 12px;
    background: var(--bg-category);
  }

  /* One line, and the name keeps its full width: only the group gives way
     (InspectorPlate .path; no shrink ratios, WebKit doesn't honour them). */
  .path {
    flex: 1;
    min-width: 0;
    display: flex;
    align-items: baseline;
    overflow: hidden;
    white-space: nowrap;
  }

  .path-head {
    flex: 0 1 auto;
    min-width: 0;
    display: flex;
    align-items: baseline;
    overflow: hidden;
    font-size: 0.75rem;
    font-variant-caps: all-small-caps;
    letter-spacing: 0.04em;
    color: var(--text-secondary);
  }

  .segment {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .sep {
    flex-shrink: 0;
    margin: 0 0.3rem;
    color: var(--text-tertiary);
    -webkit-user-select: none;
    user-select: none;
  }

  /* The leaf, InspectorPlate's .title. The pad and its negative margin let
     the hover fill reach past the letters while the name stays put. */
  .note-name {
    flex: 0 0 auto;
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    margin-left: -0.2rem;
    padding: 0 0.2rem;
    background: none;
    border: none;
    border-radius: var(--radius-sm);
    font-family: var(--font-heading);
    font-size: 0.8rem;
    color: var(--text-primary);
    text-align: left;
    cursor: text;
    transition: background var(--transition-fast);
  }

  .note-name:hover:not(:disabled) {
    background: var(--bg-focused);
  }

  .note-name:disabled {
    cursor: default;
  }

  /* As a Legend Lore rename: the field starts where the name did, in the
     title's face and size. */
  .note-name-field {
    flex: 1;
    min-width: 0;
    max-width: 22rem;
    font-family: var(--font-heading);
    font-size: 0.8rem;
  }

  .readout {
    flex-shrink: 0;
    font-size: 0.75rem;
    font-variant-numeric: tabular-nums;
    color: var(--text-tertiary);
  }

  .inspector-plate .plate-btn {
    flex-shrink: 0;
    white-space: nowrap;
  }

  .notice {
    flex-shrink: 0;
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: 0.6rem;
    padding: 0.4rem 1.1rem;
    font-size: 0.85rem;
    color: var(--text-danger);
    border-bottom: 1px solid var(--border-subtle);
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
