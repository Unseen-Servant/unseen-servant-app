import { readable, type Readable } from 'svelte/store';
import { invoke } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';

/** A Rust-owned snapshot; `seq` is bumped on every change. */
export interface Sequenced {
  seq: number;
}

/**
 * A per-window store that mirrors state Rust owns (PANELS.md: windows don't
 * share JS state). Rust pushes every change as `event`; the store also pulls
 * the current snapshot with `command` once it is listening, so a window that
 * mounts late still starts in sync. Listening first leaves no gap for a
 * change to slip through, and `seq` drops a pulled snapshot that lands after
 * a newer pushed one — the same handshake as the splash's boot state.
 *
 * `initial` must match Rust's starting state (seq 0).
 */
export function rustMirror<T extends Sequenced>(
  event: string,
  command: string,
  initial: T,
): Readable<T> {
  return readable(initial, (set) => {
    let current = initial;
    let stopped = false;
    const apply = (snap: T) => {
      if (stopped || snap.seq <= current.seq) return;
      current = snap;
      set(snap);
    };

    const unlisten = listen<T>(event, (e) => apply(e.payload));
    unlisten
      .then(() => invoke<T>(command))
      .then(apply)
      .catch((err) => console.error(`Failed to mirror ${command}:`, err));

    return () => {
      stopped = true;
      unlisten.then((stop) => stop()).catch(() => {});
    };
  });
}
