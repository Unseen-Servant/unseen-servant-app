import { beforeEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';

const tauri = vi.hoisted(() => ({
  invoke: vi.fn(),
  listen: vi.fn(),
}));
vi.mock('@tauri-apps/api/core', () => ({ invoke: tauri.invoke }));
vi.mock('@tauri-apps/api/event', () => ({ listen: tauri.listen }));

import { rustMirror } from './rustMirror';

interface Snap { seq: number; value: string | null }

const INITIAL: Snap = { seq: 0, value: null };

let push: ((payload: Snap) => void) | null;
let unlisten: ReturnType<typeof vi.fn>;
let resolvePull: (snap: Snap) => void;

beforeEach(() => {
  push = null;
  unlisten = vi.fn();
  tauri.listen.mockReset().mockImplementation(async (_event: string, handler: (e: { payload: Snap }) => void) => {
    push = (payload) => handler({ payload });
    return unlisten;
  });
  tauri.invoke.mockReset().mockImplementation(
    () => new Promise<Snap>((resolve) => { resolvePull = resolve; }),
  );
});

const flush = () => new Promise((r) => setTimeout(r, 0));

describe('rustMirror', () => {
  it('listens before it pulls, then adopts the pulled snapshot', async () => {
    const store = rustMirror('ctx://changed', 'get_ctx', INITIAL);
    const stop = store.subscribe(() => {});
    expect(tauri.listen).toHaveBeenCalledWith('ctx://changed', expect.any(Function));
    await flush();
    expect(tauri.invoke).toHaveBeenCalledWith('get_ctx');
    resolvePull({ seq: 3, value: 'Strahd' });
    await flush();
    expect(get(store)).toEqual({ seq: 3, value: 'Strahd' });
    stop();
  });

  it('drops a pulled snapshot older than a pushed one', async () => {
    const store = rustMirror('ctx://changed', 'get_ctx', INITIAL);
    const stop = store.subscribe(() => {});
    await flush();
    push!({ seq: 5, value: 'Into the Odd' });
    resolvePull({ seq: 4, value: 'Strahd' });
    await flush();
    expect(get(store)).toEqual({ seq: 5, value: 'Into the Odd' });
    stop();
  });

  it('follows pushes in order and ignores replays', async () => {
    const store = rustMirror('ctx://changed', 'get_ctx', INITIAL);
    const stop = store.subscribe(() => {});
    await flush();
    resolvePull({ seq: 0, value: null });
    await flush();
    push!({ seq: 1, value: 'Strahd' });
    push!({ seq: 2, value: null });
    push!({ seq: 1, value: 'Strahd' });
    expect(get(store)).toEqual({ seq: 2, value: null });
    stop();
  });

  it('stops listening when the last subscriber leaves', async () => {
    const store = rustMirror('ctx://changed', 'get_ctx', INITIAL);
    const stop = store.subscribe(() => {});
    await flush();
    stop();
    await flush();
    expect(unlisten).toHaveBeenCalledOnce();
  });
});
