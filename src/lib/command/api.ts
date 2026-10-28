// Command's Tauri commands, typed. Every call reaches the sidecar through
// src-tauri/src/command.rs; a refusal rejects with the sidecar's own message.

import { invoke } from '@tauri-apps/api/core';
import { listen, type UnlistenFn } from '@tauri-apps/api/event';
import type {
  BoardOp,
  BoardView,
  CampaignIndex,
  CommandSettings,
  CopySource,
  LiveSet,
  Moved,
  NewSession,
  Note,
  NoteEntry,
  Renamed,
  SaveOutcome,
  VaultEvent,
} from './types';

export type PlanOp = 'add' | 'move' | 'remove';

export interface PlanEdit {
  beat?: string;
  at?: number;
  to?: number;
  /** The entry's name expected at `at`: a move or removal is refused when
   *  the plan on disk no longer has it there. */
  expect?: string;
}

type MaybeSettings = CommandSettings | null;

export const commandApi = {
  getSettings: () => invoke<CommandSettings>('command_get_settings'),
  chooseRoot: () => invoke<MaybeSettings>('command_choose_root'),
  listCampaigns: () => invoke<string[]>('command_list_campaigns'),
  /** A folder for the shelf to copy from, from the native picker: its
   *  path, or null when the GM cancels. */
  addPlace: () => invoke<string | null>('command_add_place'),
  forgetPlace: (path: string) => invoke<CommandSettings>('command_forget_place', { path }),
  getPlace: (path: string) => invoke<{ notes: NoteEntry[] }>('command_get_place', { path }),
  /** New campaign: a fresh Untitled, opened in every window. Returns its name. */
  openUntitled: () => invoke<string>('command_open_untitled'),
  renameCampaign: (name: string, newName: string) =>
    invoke<Renamed>('command_rename_campaign', { name, newName }),
  getCampaign: (name: string) => invoke<CampaignIndex>('command_get_campaign', { name }),
  createTrack: (campaign: string, name: string) => invoke<string>('command_create_track', { campaign, name }),
  renameTrack: (campaign: string, name: string, newName: string) =>
    invoke<Renamed>('command_rename_track', { campaign, name, newName }),
  /** The campaign's tracks by name, in the order the GM dragged them. */
  orderTracks: (campaign: string, order: string[]) => invoke<string[]>('command_order_tracks', { campaign, order }),
  /** A track's pigment, or none; answers with every track's. */
  pigmentTrack: (campaign: string, track: string, pigment: string | null) =>
    invoke<Record<string, string>>('command_pigment_track', { campaign, track, pigment }),
  /** Whether a track holds notes or images; answers with every track's. */
  kindTrack: (campaign: string, track: string, kind: 'note' | 'image') =>
    invoke<Record<string, 'note' | 'image'>>('command_kind_track', { campaign, track, kind }),
  /** Images picked with the native picker, copied into `track`: their
   *  paths, none when the GM cancels. */
  pickImages: (campaign: string, track: string) => invoke<string[]>('command_pick_images', { campaign, track }),
  /** A folder's notes by name, in the order the GM dragged them. */
  orderNotes: (campaign: string, folder: string, order: string[]) =>
    invoke<string[]>('command_order_notes', { campaign, folder, order }),
  readNote: (campaign: string, path: string) => invoke<Note>('command_read_note', { campaign, path }),
  saveNote: (campaign: string, path: string, content: string, baseHash: string) =>
    invoke<SaveOutcome>('command_save_note', { campaign, path, content, baseHash }),
  createNote: (campaign: string, folder: string, name: string) =>
    invoke<string>('command_create_note', { campaign, folder, name }),
  renameNote: (campaign: string, path: string, newName: string) =>
    invoke<Moved>('command_rename_note', { campaign, path, newName }),
  /** Into `folder`, first among its notes, or in `order` when given. */
  moveNote: (campaign: string, path: string, folder: string, order?: string[]) =>
    invoke<Moved>('command_move_note', { campaign, path, folder, order: order ?? null }),
  /** Another campaign's note, or a place's, copied onto this one's shelf. */
  copyNote: (campaign: string, from: CopySource, path: string) =>
    invoke<string>('command_copy_note', {
      campaign,
      fromCampaign: from.kind === 'campaign' ? from.name : null,
      fromPlace: from.kind === 'place' ? from.path : null,
      path,
    }),
  /** An image dropped from Finder, copied onto the campaign's shelf: the
   *  copy's path. The bytes go raw, not as JSON; the names ride in headers,
   *  URI-encoded since a header is ASCII. */
  addImage: (campaign: string, name: string, bytes: ArrayBuffer, track: string | null = null) =>
    invoke<string>('command_add_image', new Uint8Array(bytes), {
      headers: {
        campaign: encodeURIComponent(campaign),
        name: encodeURIComponent(name),
        // Into an image track; without one, onto the shelf.
        ...(track ? { track: encodeURIComponent(track) } : {}),
      },
    }),
  createBeat: (campaign: string, name: string, notes: string[], session: string | null) =>
    invoke<string>('command_create_beat', { campaign, name, notes, session }),
  /** The campaign's beats by name, in the order the GM dragged them. */
  orderBeats: (campaign: string, order: string[]) => invoke<string[]>('command_order_beats', { campaign, order }),
  setMember: (campaign: string, beat: string, note: string, member: boolean) =>
    invoke<string[]>('command_set_member', { campaign, beat, note, member }),
  createSession: (campaign: string) => invoke<NewSession>('command_create_session', { campaign }),
  editPlan: (campaign: string, session: string, op: PlanOp, edit: PlanEdit) =>
    invoke<string[]>('command_edit_plan', {
      campaign,
      session,
      op,
      beat: edit.beat ?? null,
      at: edit.at ?? null,
      to: edit.to ?? null,
      expect: edit.expect ?? null,
    }),
  setSpent: (campaign: string, path: string, spent: boolean) =>
    invoke<string | null>('command_set_spent', { campaign, path, spent }),
  setSpendOnLaunch: (enabled: boolean) => invoke<CommandSettings>('command_set_spend_on_launch', { enabled }),
  getBoard: (campaign: string, session: string) => invoke<BoardView>('command_get_board', { campaign, session }),
  editBoard: (campaign: string, session: string, ops: BoardOp[]) =>
    invoke<BoardView>('command_edit_board', { campaign, session, ops }),
  /** What Arrange by beat would do to the board, for `editBoard` to apply. */
  arrangeBoard: (campaign: string, session: string) =>
    invoke<{ ops: BoardOp[] }>('command_arrange_board', { campaign, session }).then((r) => r.ops),
  getLive: (campaign: string) => invoke<LiveSet>('command_get_live', { campaign }),
  launch: (campaign: string, beat: string) => invoke<LiveSet>('command_launch', { campaign, beat }),
  setLive: (campaign: string, note: string, live: boolean) =>
    invoke<LiveSet>('command_set_live', { campaign, note, live }),
  orderLive: (campaign: string, notes: string[]) => invoke<LiveSet>('command_order_live', { campaign, notes }),
  stop: (campaign: string) => invoke<LiveSet>('command_stop', { campaign }),
  /** A line at the end of the session note's own text. */
  jot: (campaign: string, session: string, text: string) => invoke<string>('command_jot', { campaign, session, text }),
  /** A campaign (no path), or a note or folder inside one, to the OS trash. */
  trash: (campaign: string, path: string | null) => invoke<void>('command_trash', { campaign, path }),
};

/** Follow every campaign's live set, relayed by Rust as whole snapshots. */
export function onLiveChange(handler: (live: LiveSet) => void): Promise<UnlistenFn> {
  return listen<LiveSet>('command://live', (e) => handler(e.payload));
}

/** Follow the campaign folder's change events, relayed by Rust. */
export function onVaultChange(handler: (event: VaultEvent) => void): Promise<UnlistenFn> {
  return listen<VaultEvent>('command://vault', (e) => handler(e.payload));
}
