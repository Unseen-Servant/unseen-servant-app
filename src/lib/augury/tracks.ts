// Augury's Tracks set (design §6): a pad for each track of the campaign open
// in Command, which draws one of the track's unspent notes at random. A
// crossing between the tools' windows, so it goes through Rust
// (command_draw_tracks), as Legend Lore's Send to Command does: Augury asks,
// and Rust knows the campaign.

import { invoke } from '@tauri-apps/api/core';
import { listen, type UnlistenFn } from '@tauri-apps/api/event';

export interface DrawTrack {
  name: string;
  pigment: string | null;
  /** The track's unspent notes and images, by name. */
  notes: string[];
}

export interface DrawTracks {
  campaign: string | null;
  tracks: DrawTrack[];
}

export const drawTracks = () => invoke<DrawTracks>('command_draw_tracks');

/** Follow the campaign folder's changes, which Rust relays to every window
 *  (command.rs VAULT_EVENT): a note written, spent or moved in Command. */
export function onVaultChange(handler: () => void): Promise<UnlistenFn> {
  return listen('command://vault', () => handler());
}
