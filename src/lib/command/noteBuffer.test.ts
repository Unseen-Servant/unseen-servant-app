import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NoteBuffer, RETRY_DELAY_MS, SAVE_DELAY_MS, type BufferState, type NoteIO, type PendingNote } from './noteBuffer';
import type { Note, SaveOutcome } from './types';

/** A fake disk that refuses stale saves the way the sidecar does. */
function fakeDisk(files: Record<string, string>) {
  const disk = new Map(Object.entries(files));
  const hash = (content: string) => `h:${content}`;
  const saves: { path: string; content: string; baseHash: string }[] = [];
  const held: (PendingNote | null)[] = [];
  const io: NoteIO = {
    hold: (pending) => held.push(pending),
    read: vi.fn(async (path: string): Promise<Note> => {
      const content = disk.get(path);
      if (content === undefined) throw new Error(`Nothing at '${path}'`);
      return { path, name: path, content, hash: hash(content) };
    }),
    save: vi.fn(async (path: string, content: string, baseHash: string): Promise<SaveOutcome> => {
      saves.push({ path, content, baseHash });
      const current = disk.get(path)!;
      if (hash(current) !== baseHash) return { status: 'conflict', hash: hash(current) };
      disk.set(path, content);
      return { status: 'saved', hash: hash(content) };
    }),
  };
  return { disk, io, saves, held, hash };
}

function setup(files: Record<string, string>) {
  const fake = fakeDisk(files);
  const states: BufferState[] = [];
  const editor = { content: '' };
  const buffer = new NoteBuffer(
    fake.io,
    (s) => states.push(s),
    (c) => (editor.content = c),
  );
  return { ...fake, buffer, editor, last: () => states[states.length - 1] };
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe('NoteBuffer', () => {
  it('loads a note into the editor clean', async () => {
    const t = setup({ 'NPCs/Ismark.md': 'Brother.' });
    await t.buffer.open('NPCs/Ismark.md');
    expect(t.editor.content).toBe('Brother.');
    expect(t.last()).toEqual({ path: 'NPCs/Ismark.md', status: 'clean', error: null });
  });

  it('saves edits after a pause, to the loaded path with the loaded hash', async () => {
    const t = setup({ 'NPCs/Ismark.md': 'Brother.' });
    await t.buffer.open('NPCs/Ismark.md');
    t.buffer.edit('Brother of Ireena.');
    expect(t.last().status).toBe('dirty');
    await vi.advanceTimersByTimeAsync(SAVE_DELAY_MS);
    expect(t.saves).toEqual([{ path: 'NPCs/Ismark.md', content: 'Brother of Ireena.', baseHash: 'h:Brother.' }]);
    expect(t.disk.get('NPCs/Ismark.md')).toBe('Brother of Ireena.');
    expect(t.last().status).toBe('clean');
  });

  it('flushes pending edits to the note they belong to before opening another', async () => {
    // The Electron app wrote one note's text into the next one opened.
    const t = setup({ 'NPCs/Innkeeper.md': 'Innkeeper.', 'PCs/Makander.md': 'Makander.' });
    await t.buffer.open('NPCs/Innkeeper.md');
    t.buffer.edit('Innkeeper, edited.');
    await t.buffer.open('PCs/Makander.md');
    expect(t.disk.get('NPCs/Innkeeper.md')).toBe('Innkeeper, edited.');
    expect(t.disk.get('PCs/Makander.md')).toBe('Makander.');
    expect(t.editor.content).toBe('Makander.');
    await vi.advanceTimersByTimeAsync(SAVE_DELAY_MS * 2);
    expect(t.saves).toHaveLength(1);
  });

  it('follows the disk while clean', async () => {
    const t = setup({ 'a.md': 'one' });
    await t.buffer.open('a.md');
    t.disk.set('a.md', 'edited in Obsidian');
    await t.buffer.diskChanged();
    expect(t.editor.content).toBe('edited in Obsidian');
    expect(t.last().status).toBe('clean');
  });

  it('turns a disk change under unsaved edits into a conflict, and stops saving', async () => {
    const t = setup({ 'a.md': 'one' });
    await t.buffer.open('a.md');
    t.buffer.edit('mine');
    t.disk.set('a.md', 'theirs');
    await t.buffer.diskChanged();
    expect(t.last().status).toBe('conflict');
    expect(t.editor.content).toBe('one'); // the editor keeps what the GM typed; onReplace wasn't called
    await vi.advanceTimersByTimeAsync(SAVE_DELAY_MS * 2);
    expect(t.saves).toEqual([]);
    expect(t.disk.get('a.md')).toBe('theirs');
  });

  it('resolves a conflict by keeping mine or by reloading', async () => {
    const t = setup({ 'a.md': 'one' });
    await t.buffer.open('a.md');
    t.buffer.edit('mine');
    t.disk.set('a.md', 'theirs');
    await t.buffer.diskChanged();
    await t.buffer.keepMine();
    expect(t.disk.get('a.md')).toBe('mine');
    expect(t.last().status).toBe('clean');

    t.buffer.edit('mine again');
    t.disk.set('a.md', 'theirs again');
    await t.buffer.diskChanged();
    await t.buffer.reload();
    expect(t.editor.content).toBe('theirs again');
    expect(t.last().status).toBe('clean');
  });

  it('recognises its own save echoing back as a disk change', async () => {
    const t = setup({ 'a.md': 'one' });
    await t.buffer.open('a.md');
    t.buffer.edit('two');
    await vi.advanceTimersByTimeAsync(SAVE_DELAY_MS);
    t.editor.content = 'sentinel';
    await t.buffer.diskChanged();
    expect(t.editor.content).toBe('sentinel');
    expect(t.last().status).toBe('clean');
  });

  it('defers a disk change that lands during a save instead of calling it a conflict', async () => {
    const t = setup({ 'a.md': 'one' });
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    const realSave = t.io.save;
    t.io.save = async (...args) => {
      await gate;
      return realSave(...args);
    };
    await t.buffer.open('a.md');
    t.buffer.edit('two');
    const flushed = t.buffer.flush();
    await vi.advanceTimersByTimeAsync(0);
    expect(t.last().status).toBe('saving');
    const event = t.buffer.diskChanged(); // the watcher saw our write before the save returned
    release();
    await flushed;
    await event;
    expect(t.last().status).toBe('clean');
    expect(t.disk.get('a.md')).toBe('two');
  });

  it('reports a refused save as a conflict', async () => {
    const t = setup({ 'a.md': 'one' });
    await t.buffer.open('a.md');
    t.disk.set('a.md', 'changed, no event yet');
    t.buffer.edit('mine');
    await vi.advanceTimersByTimeAsync(SAVE_DELAY_MS);
    expect(t.last().status).toBe('conflict');
    expect(t.disk.get('a.md')).toBe('changed, no event yet');
  });

  it('keeps the text when the file disappears', async () => {
    const t = setup({ 'a.md': 'one' });
    await t.buffer.open('a.md');
    t.buffer.edit('unsaved');
    t.disk.delete('a.md');
    await t.buffer.diskChanged();
    expect(t.last().status).toBe('unreadable');
    expect(t.last().error).toContain("Nothing at 'a.md'");
    expect(t.editor.content).toBe('one'); // not wiped
    await vi.advanceTimersByTimeAsync(SAVE_DELAY_MS * 2);
    expect(t.saves).toEqual([]);
  });

  it('stays on a note whose save failed rather than opening another over it', async () => {
    const t = setup({ 'a.md': 'one', 'b.md': 'other' });
    await t.buffer.open('a.md');
    t.buffer.edit('an evening of typing');
    t.io.save = async () => {
      throw new Error('sidecar down');
    };
    expect(await t.buffer.open('b.md')).toBe(false);
    expect(t.last()).toEqual({ path: 'a.md', status: 'dirty', error: 'Error: sidecar down' });
    expect(t.editor.content).toBe('one'); // onReplace wasn't called: the editor keeps the typing
    expect(await t.buffer.close()).toBe(false);
    expect(t.last().path).toBe('a.md');
    expect(await t.buffer.flush()).toBe(false);

    // The GM gives the text up.
    expect(await t.buffer.open('b.md', true)).toBe(true);
    expect(t.editor.content).toBe('other');
    expect(t.last()).toEqual({ path: 'b.md', status: 'clean', error: null });
    expect(t.disk.get('a.md')).toBe('one');
  });

  it('does not open or close over a conflict, or over a file that went away, unless told to', async () => {
    const t = setup({ 'a.md': 'one', 'b.md': 'other' });
    await t.buffer.open('a.md');
    t.buffer.edit('mine');
    t.disk.set('a.md', 'theirs');
    await t.buffer.diskChanged();
    expect(await t.buffer.open('b.md')).toBe(false);
    expect(await t.buffer.close()).toBe(false);
    expect(t.last()).toEqual({ path: 'a.md', status: 'conflict', error: null });
    await t.buffer.keepMine();
    expect(await t.buffer.open('b.md')).toBe(true);
    expect(t.disk.get('a.md')).toBe('mine');

    t.buffer.edit('other, edited');
    t.disk.delete('b.md');
    await t.buffer.diskChanged();
    expect(await t.buffer.close()).toBe(false);
    expect(t.last().status).toBe('unreadable');
    expect(await t.buffer.close(true)).toBe(true);
    expect(t.last()).toEqual({ path: null, status: 'empty', error: null });
  });

  it('tries a failed save again until it lands', async () => {
    const t = setup({ 'a.md': 'one' });
    const realSave = t.io.save;
    let down = true;
    let tries = 0;
    t.io.save = async (...args) => {
      tries++;
      if (down) throw new Error('sidecar down');
      return realSave(...args);
    };
    await t.buffer.open('a.md');
    t.buffer.edit('two');
    await vi.advanceTimersByTimeAsync(SAVE_DELAY_MS);
    expect(t.last()).toEqual({ path: 'a.md', status: 'dirty', error: 'Error: sidecar down' });
    await vi.advanceTimersByTimeAsync(RETRY_DELAY_MS);
    expect(tries).toBe(2);
    down = false;
    await vi.advanceTimersByTimeAsync(RETRY_DELAY_MS);
    expect(t.disk.get('a.md')).toBe('two');
    expect(t.last()).toEqual({ path: 'a.md', status: 'clean', error: null });
    // And nothing more once it is on disk.
    await vi.advanceTimersByTimeAsync(RETRY_DELAY_MS * 3);
    expect(tries).toBe(3);
  });

  it('flushes what was typed while a save was in flight', async () => {
    const t = setup({ 'a.md': 'one', 'b.md': 'other' });
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    const realSave = t.io.save;
    t.io.save = async (...args) => {
      await gate;
      return realSave(...args);
    };
    await t.buffer.open('a.md');
    t.buffer.edit('two');
    const opened = t.buffer.open('b.md');
    await vi.advanceTimersByTimeAsync(0);
    t.buffer.edit('two and a half');
    release();
    expect(await opened).toBe(true);
    expect(t.disk.get('a.md')).toBe('two and a half');
    expect(t.editor.content).toBe('other');
  });

  it('hands over the text that is not on disk, and takes it back once it is', async () => {
    const t = setup({ 'a.md': 'one' });
    await t.buffer.open('a.md');
    expect(t.held).toEqual([]);
    t.buffer.edit('two');
    t.buffer.edit('two!');
    expect(t.held).toEqual([
      { path: 'a.md', content: 'two', baseHash: 'h:one' },
      { path: 'a.md', content: 'two!', baseHash: 'h:one' },
    ]);
    await vi.advanceTimersByTimeAsync(SAVE_DELAY_MS);
    expect(t.held.at(-1)).toBeNull();
    expect(t.held).toHaveLength(3);

    // A conflict's text stays handed over, and goes when the GM reloads.
    t.buffer.edit('mine');
    t.disk.set('a.md', 'theirs');
    await t.buffer.diskChanged();
    expect(t.held.at(-1)).toEqual({ path: 'a.md', content: 'mine', baseHash: 'h:two!' });
    await t.buffer.reload();
    expect(t.held.at(-1)).toBeNull();

    // Given up with the note.
    t.buffer.edit('unsaved');
    t.io.save = async () => {
      throw new Error('sidecar down');
    };
    await t.buffer.close(true);
    expect(t.held.at(-1)).toBeNull();
  });

  it('follows a rename to the new path', async () => {
    const t = setup({ 'NPCs/Ismark.md': 'x' });
    await t.buffer.open('NPCs/Ismark.md');
    t.disk.set('NPCs/Ismark the Lesser.md', 'x');
    t.disk.delete('NPCs/Ismark.md');
    await t.buffer.retarget('NPCs/Ismark the Lesser.md');
    expect(t.last()).toEqual({ path: 'NPCs/Ismark the Lesser.md', status: 'clean', error: null });
  });
});
