// Command's Tauri commands, typed. Every call reaches the sidecar through
// src-tauri/src/command.rs; a refusal rejects with the sidecar's own message.

import { invoke } from '@tauri-apps/api/core';
import { listen, type UnlistenFn } from '@tauri-apps/api/event';
import type { CampaignIndex, CommandSettings, Moved, Note, Renamed, SaveOutcome, VaultEvent } from './types';

type MaybeSettings = CommandSettings | null;

export const commandApi = {
  getSettings: () => invoke<CommandSettings>('command_get_settings'),
  chooseRoot: () => invoke<MaybeSettings>('command_choose_root'),
  listCampaigns: () => invoke<string[]>('command_list_campaigns'),
  createCampaign: (name: string) => invoke<string>('command_create_campaign', { name }),
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
  /** A campaign (no path), or a note or folder inside one, to the OS trash. */
  trash: (campaign: string, path: string | null) => invoke<void>('command_trash', { campaign, path }),
};

/** Follow the campaign folder's change events, relayed by Rust. */
export function onVaultChange(handler: (event: VaultEvent) => void): Promise<UnlistenFn> {
  return listen<VaultEvent>('command://vault', (e) => handler(e.payload));
}
