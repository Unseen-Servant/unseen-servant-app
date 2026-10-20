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
  /** Each track's kind: a hit goes to a note track, an image to an image
   *  track (images design §3.2). */
  kinds: Record<string, 'note' | 'image'>;
}

export interface Sent {
  campaign: string;
  path: string;
}

export const sendTargets = () => invoke<SendTargets>('command_send_targets');

/** The targets a note, or an image, may go to: the shelf, which holds
 *  both, then the tracks of its kind, as Live keeps audio off MIDI tracks. */
export function targetsFor(targets: SendTargets, kind: 'note' | 'image'): SendTargets {
  return { ...targets, tracks: targets.tracks.filter((t) => (targets.kinds[t] ?? 'note') === kind) };
}

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

/** Copy an image from the library into `track`, an image track, or onto
 *  the campaign's shelf when it's null (images design §6). */
export function sendImage(path: string, track: string | null): Promise<Sent> {
  return invoke<Sent>('command_send_image', { track, path });
}

/** Keep the hit in `track`, or on the campaign's shelf when it's null. */
export function sendToCommand(result: SearchResultItem, track: string | null): Promise<Sent> {
  return invoke<Sent>('command_send', { track, ...sentNote(result) });
}
