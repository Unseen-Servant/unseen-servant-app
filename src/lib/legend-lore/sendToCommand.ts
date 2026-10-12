// Send to Command (Command design doc §8): a search hit kept as a note in a
// track of the campaign open in Command. The one crossing between the two
// tools' windows, so it goes through Rust (architecture D4): Legend Lore
// says what the hit is; Rust knows the campaign; the sidecar writes the
// note and Command's windows hear of it from the vault watcher.

import { invoke } from '@tauri-apps/api/core';
import { bookTitle, pageCitation, pdfFileUrl } from './pdfUrl';
import type { SearchResultItem } from './types';

/** The open campaign and its tracks; no campaign, nowhere to send. */
export interface SendTargets {
  campaign: string | null;
  tracks: string[];
}

export interface Sent {
  campaign: string;
  path: string;
}

export const sendTargets = () => invoke<SendTargets>('command_send_targets');

/** The note a hit becomes: named after its section, holding the section's
 *  text, with its book and page as the source a card opens. */
export function sentNote(result: SearchResultItem) {
  const title = bookTitle(result.filename);
  const pages = pageCitation(result.page_start, result.page_end, result.page_label_start, result.page_label_end);
  return {
    name: result.section_heading.replace(/\*\*/g, '').trim() || title,
    text: result.text,
    source: pdfFileUrl(result.source, result.page_start > 0 ? result.page_start : null),
    cite: pages ? `${title}, ${pages}` : title,
  };
}

export function sendToCommand(result: SearchResultItem, track: string): Promise<Sent> {
  return invoke<Sent>('command_send', { track, ...sentNote(result) });
}
