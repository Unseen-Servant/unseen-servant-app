// The open note: what was loaded, what the editor holds, and the rule both
// earlier Command apps broke — a save goes to the path it was loaded from,
// carrying the hash it was loaded at (design §3.5, §7). The sidecar refuses
// a save whose hash no longer matches the disk; that refusal becomes a
// conflict the GM resolves, never a silent overwrite.
//
// Framework-free so the save rules are testable; the editor component feeds
// it edits and applies the content it hands back.

import type { Note, SaveOutcome } from './types';

export interface NoteIO {
  read(path: string): Promise<Note>;
  save(path: string, content: string, baseHash: string): Promise<SaveOutcome>;
}

export type BufferStatus =
  | 'empty' //      nothing open
  | 'clean' //      the editor matches the disk
  | 'dirty' //      edited, save pending
  | 'saving' //     a save is in flight
  | 'conflict' //   the file changed on disk under unsaved edits
  | 'unreadable'; // the file couldn't be read (moved, deleted, sidecar down)

export interface BufferState {
  path: string | null;
  status: BufferStatus;
  /** What went wrong, for 'unreadable' and failed saves. */
  error: string | null;
}

export const SAVE_DELAY_MS = 600;

export class NoteBuffer {
  private path: string | null = null;
  private baseHash = '';
  /** The content at baseHash. */
  private saved = '';
  /** The editor's content. */
  private current = '';
  private diskHash: string | null = null;
  private saving: Promise<void> | null = null;
  private recheck = false;
  private conflicted = false;
  private unreadable: string | null = null;
  private error: string | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;

  constructor(
    private io: NoteIO,
    private onState: (state: BufferState) => void,
    /** Put this content in the editor (a load or a reload from disk). */
    private onReplace: (content: string) => void,
  ) {}

  get state(): BufferState {
    let status: BufferStatus;
    if (this.path === null) status = 'empty';
    else if (this.unreadable !== null) status = 'unreadable';
    else if (this.conflicted) status = 'conflict';
    else if (this.saving) status = 'saving';
    else if (this.current !== this.saved) status = 'dirty';
    else status = 'clean';
    return { path: this.path, status, error: this.unreadable ?? this.error };
  }

  /** Open `path`, saving whatever is pending on the current note first. */
  async open(path: string): Promise<void> {
    await this.flush();
    this.cancelTimer();
    this.path = path;
    this.conflicted = false;
    this.unreadable = this.error = null;
    await this.load(path);
  }

  /** Close the note, saving what's pending first. */
  async close(): Promise<void> {
    await this.flush();
    this.cancelTimer();
    this.path = null;
    this.saved = this.current = this.baseHash = '';
    this.conflicted = false;
    this.unreadable = this.error = null;
    this.emit();
  }

  /** The editor's content changed. */
  edit(content: string): void {
    if (this.path === null) return;
    this.current = content;
    this.error = null;
    if (!this.conflicted && this.unreadable === null) this.schedule();
    this.emit();
  }

  /** Save now if anything is pending (switching notes, renaming, leaving). */
  async flush(): Promise<void> {
    this.cancelTimer();
    if (this.saving) await this.saving;
    if (this.path !== null && !this.conflicted && this.unreadable === null && this.current !== this.saved) {
      await this.save();
    }
  }

  /** The open note now lives at `path` (renamed or moved by Command). Its
   *  content may have been rewritten too, so it is re-read. */
  async retarget(path: string): Promise<void> {
    this.path = path;
    this.unreadable = null;
    await this.diskChanged();
  }

  /** The file changed on disk — an event named it. A clean buffer follows
   *  the disk; a dirty one becomes a conflict. Our own saves echo back
   *  here too, and are recognised by their hash. */
  async diskChanged(): Promise<void> {
    if (this.path === null) return;
    if (this.saving) {
      this.recheck = true;
      return;
    }
    const path = this.path;
    let note: Note;
    try {
      note = await this.io.read(path);
    } catch (e) {
      if (this.path !== path) return;
      this.unreadable = String(e);
      this.cancelTimer();
      this.emit();
      return;
    }
    if (this.path !== path) return;
    this.unreadable = null;
    if (note.hash === this.baseHash) {
      this.emit();
      return;
    }
    if (this.current === this.saved) {
      this.accept(note);
    } else {
      this.conflicted = true;
      this.diskHash = note.hash;
      this.cancelTimer();
    }
    this.emit();
  }

  /** Resolve a conflict by taking what's on disk. */
  async reload(): Promise<void> {
    if (this.path === null) return;
    this.conflicted = false;
    await this.load(this.path);
  }

  /** Resolve a conflict by writing the editor's content over the disk. */
  async keepMine(): Promise<void> {
    if (this.path === null || !this.conflicted || this.diskHash === null) return;
    this.baseHash = this.diskHash;
    this.conflicted = false;
    await this.save();
  }

  private async load(path: string): Promise<void> {
    try {
      const note = await this.io.read(path);
      if (this.path !== path) return;
      this.unreadable = null;
      this.accept(note);
    } catch (e) {
      if (this.path !== path) return;
      this.unreadable = String(e);
      this.saved = this.current = this.baseHash = '';
      this.onReplace('');
    }
    this.emit();
  }

  private accept(note: Note): void {
    this.baseHash = note.hash;
    this.saved = this.current = note.content;
    this.diskHash = null;
    this.onReplace(note.content);
  }

  private save(): Promise<void> {
    const path = this.path!;
    const content = this.current;
    const run = async () => {
      try {
        const outcome = await this.io.save(path, content, this.baseHash);
        if (this.path !== path) return;
        if (outcome.status === 'saved') {
          this.baseHash = outcome.hash;
          this.saved = content;
        } else {
          this.conflicted = true;
          this.diskHash = outcome.hash;
        }
      } catch (e) {
        if (this.path === path) this.error = String(e);
      }
    };
    this.saving = run().finally(() => {
      this.saving = null;
    });
    this.emit();
    return this.saving.then(() => this.settle(path));
  }

  /** After a save: handle a disk change that arrived during it, or keep
   *  saving edits typed while it was in flight. */
  private async settle(path: string): Promise<void> {
    if (this.path !== path) return;
    if (this.recheck) {
      this.recheck = false;
      await this.diskChanged();
      return;
    }
    if (!this.conflicted && this.error === null && this.current !== this.saved) this.schedule();
    this.emit();
  }

  private schedule(): void {
    this.cancelTimer();
    this.timer = setTimeout(() => {
      this.timer = null;
      if (!this.saving) void this.save();
      else this.schedule();
    }, SAVE_DELAY_MS);
  }

  private cancelTimer(): void {
    if (this.timer !== null) clearTimeout(this.timer);
    this.timer = null;
  }

  private emit(): void {
    this.onState(this.state);
  }
}
