// Command's Tauri commands, typed. Every call reaches the sidecar through
// src-tauri/src/command.rs; a refusal rejects with the sidecar's own message.

import { invoke } from '@tauri-apps/api/core';
import { listen, type UnlistenFn } from '@tauri-apps/api/event';
import type {
  BoardOp,
  BoardView,
  CampaignIndex,
  Captured,
  CommandSettings,
  LiveSet,
  Moved,
  NewSession,
  Note,
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
  /** New campaign: a fresh Untitled, opened in every window. Returns its name. */
  openUntitled: () => invoke<string>('command_open_untitled'),
  renameCampaign: (name: string, newName: string) =>
    invoke<Renamed>('command_rename_campaign', { name, newName }),
  getCampaign: (name: string) => invoke<CampaignIndex>('command_get_campaign', { name }),
  createTrack: (campaign: string, name: string) => invoke<string>('command_create_track', { campaign, name }),
  renameTrack: (campaign: string, name: string, newName: string) =>
    invoke<Renamed>('command_rename_track', { campaign, name, newName }),
  readNote: (campaign: string, path: string) => invoke<Note>('command_read_note', { campaign, path }),
  saveNote: (campaign: string, path: string, content: string, baseHash: string) =>
    invoke<SaveOutcome>('command_save_note', { campaign, path, content, baseHash }),
  createNote: (campaign: string, folder: string, name: string) =>
    invoke<string>('command_create_note', { campaign, folder, name }),
  renameNote: (campaign: string, path: string, newName: string) =>
    invoke<Moved>('command_rename_note', { campaign, path, newName }),
  moveNote: (campaign: string, path: string, folder: string) =>
    invoke<Moved>('command_move_note', { campaign, path, folder }),
  /** Another campaign's note, copied onto this one's shelf. */
  copyNote: (campaign: string, fromCampaign: string, path: string) =>
    invoke<string>('command_copy_note', { campaign, fromCampaign, path }),
  createBeat: (campaign: string, name: string, notes: string[], session: string | null) =>
    invoke<string>('command_create_beat', { campaign, name, notes, session }),
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
  /** From Play, pass the session: the change is logged there. */
  setSpent: (campaign: string, path: string, spent: boolean, session: string | null = null) =>
    invoke<string | null>('command_set_spent', { campaign, path, spent, session }),
  setSpendOnLaunch: (enabled: boolean) => invoke<CommandSettings>('command_set_spend_on_launch', { enabled }),
  getBoard: (campaign: string, session: string) => invoke<BoardView>('command_get_board', { campaign, session }),
  editBoard: (campaign: string, session: string, ops: BoardOp[]) =>
    invoke<BoardView>('command_edit_board', { campaign, session, ops }),
  getLive: (campaign: string) => invoke<LiveSet>('command_get_live', { campaign }),
  launch: (campaign: string, beat: string, session: string | null) =>
    invoke<LiveSet>('command_launch', { campaign, beat, session }),
  setLive: (campaign: string, note: string, live: boolean) =>
    invoke<LiveSet>('command_set_live', { campaign, note, live }),
  stop: (campaign: string) => invoke<LiveSet>('command_stop', { campaign }),
  capture: (campaign: string, session: string, name: string) =>
    invoke<Captured>('command_capture', { campaign, session, name }),
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
