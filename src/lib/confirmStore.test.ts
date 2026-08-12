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
});
