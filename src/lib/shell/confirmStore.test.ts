import { describe, it, expect } from 'vitest';
import { get } from 'svelte/store';
import { createConfirmStore } from './confirmStore';

/** Let queued promise callbacks run. */
const settle = () => new Promise<void>((r) => setTimeout(r, 0));

describe('confirm store', () => {
  it('publishes the request while it is pending, and nothing when idle', () => {
    const store = createConfirmStore();
    expect(get(store)).toBeNull();

    void store.request({ title: 'Delete collection', message: 'Sure?', danger: true });

    expect(get(store)).toMatchObject({
      title: 'Delete collection',
      message: 'Sure?',
      danger: true,
    });
  });

  it('does not resolve until answered', async () => {
    const store = createConfirmStore();
    let settled = false;
    void store.request({ title: 'Wait' }).then(() => { settled = true; });

    await settle();

    expect(settled).toBe(false);
  });

  it('resolves true and clears the prompt when answered yes', async () => {
    const store = createConfirmStore();
    const answer = store.request({ title: 'Go' });

    store.answer(true);

    expect(await answer).toBe(true);
    expect(get(store)).toBeNull();
  });

  it('resolves false and clears the prompt when answered no', async () => {
    const store = createConfirmStore();
    const answer = store.request({ title: 'Go' });

    store.answer(false);

    expect(await answer).toBe(false);
    expect(get(store)).toBeNull();
  });

  it('ignores an answer when nothing is pending', () => {
    const store = createConfirmStore();

    expect(() => store.answer(true)).not.toThrow();
    expect(get(store)).toBeNull();
  });

  // A caller awaiting a superseded prompt must not hang forever — the
  // page is inert while a dialog is open, so this is a race rather than
  // a reachable flow, but an unresolved promise strands whatever state
  // the caller was mid-way through updating.
  it('supersedes a pending request, resolving the old one false', async () => {
    const store = createConfirmStore();
    const first = store.request({ title: 'First' });

    const second = store.request({ title: 'Second' });

    expect(await first).toBe(false);
    expect(get(store)).toMatchObject({ title: 'Second' });

    store.answer(true);
    expect(await second).toBe(true);
  });

  // Rows are optional per call site: a caller with no figures in hand keeps
  // using `message`, so adoption never blocks on data the page can't cheaply
  // get (delete-file has no chunk count — see the design's Readout data).
  it('carries readout rows through untouched, and omits them when absent', () => {
    const store = createConfirmStore();

    void store.request({
      title: 'Delete collection',
      danger: true,
      rows: [
        { label: 'Track', value: 'Session 14' },
        { label: 'Files', value: '12', to: 'Loose', unchanged: true },
      ],
    });

    expect(get(store)?.rows).toEqual([
      { label: 'Track', value: 'Session 14' },
      { label: 'Files', value: '12', to: 'Loose', unchanged: true },
    ]);

    void store.request({ title: 'Delete file', message: 'Move it to Trash?', danger: true });

    expect(get(store)?.rows).toBeUndefined();
  });
});
