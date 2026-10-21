import { describe, expect, test, vi } from 'vitest';
import { openDialogs } from './dialogStack';
import { setFocusedTool, setRegion } from './focus';
import { bindKeys, dispatchKey, hostKeys, type KeyContext } from './keys';

function key(
  k: string,
  mods: Partial<Pick<KeyboardEvent, 'metaKey' | 'ctrlKey' | 'shiftKey' | 'altKey'>> = {},
  target: EventTarget | null = null,
): KeyboardEvent {
  return {
    key: k,
    code: '',
    metaKey: false,
    ctrlKey: false,
    shiftKey: false,
    altKey: false,
    isComposing: false,
    repeat: false,
    target,
    preventDefault: vi.fn(),
    ...mods,
  } as unknown as KeyboardEvent;
}

const field = { closest: (s: string) => (s.includes('input') ? {} : null) } as unknown as EventTarget;
const editor = { closest: (s: string) => (s.includes('.cm-editor') ? {} : null) } as unknown as EventTarget;

describe('dispatchKey', () => {
  test('tries handlers in binding order and stops at the first to take the key', () => {
    const seen: string[] = [];
    const a = bindKeys(() => (seen.push('a'), false));
    const b = bindKeys(() => (seen.push('b'), true));
    const c = bindKeys(() => (seen.push('c'), true));
    const e = key('x');
    dispatchKey(e);
    expect(seen).toEqual(['a', 'b']);
    expect(e.preventDefault).toHaveBeenCalledOnce();
    a(); b(); c();
  });

  test('a key nobody takes keeps its default', () => {
    const unbind = bindKeys(() => false);
    const e = key('x');
    dispatchKey(e);
    expect(e.preventDefault).not.toHaveBeenCalled();
    unbind();
  });

  test('an unbound handler is not tried', () => {
    const handler = vi.fn(() => true);
    bindKeys(handler)();
    dispatchKey(key('x'));
    expect(handler).not.toHaveBeenCalled();
  });

  test('stands down while a dialog is up', () => {
    const handler = vi.fn(() => true);
    const unbind = bindKeys(handler);
    openDialogs.register();
    dispatchKey(key('x'));
    openDialogs.release();
    expect(handler).not.toHaveBeenCalled();
    dispatchKey(key('x'));
    expect(handler).toHaveBeenCalledOnce();
    unbind();
  });

  test('reads typing and the editor off the target once, for every handler', () => {
    let ctx: KeyContext | undefined;
    const unbind = bindKeys((_, c) => ((ctx = c), true));
    dispatchKey(key('x', {}, editor));
    expect(ctx).toMatchObject({ typing: true, editor: true, menu: false });
    dispatchKey(key('x', {}, field));
    expect(ctx).toMatchObject({ typing: true, editor: false });
    dispatchKey(key('x'));
    expect(ctx).toMatchObject({ typing: false, editor: false });
    unbind();
  });
});

describe('dispatchKey places', () => {
  test('tries the overlay, then the region, then the tool, then global, whatever the binding order', () => {
    const seen: string[] = [];
    const unbind = [
      bindKeys(() => (seen.push('global'), false)),
      bindKeys(() => (seen.push('tool'), false), { tool: 'legend-lore' }),
      bindKeys(() => (seen.push('region'), false), { tool: 'legend-lore', region: 'collections' }),
      bindKeys(() => (seen.push('overlay'), false), 'overlay'),
    ];
    setRegion('legend-lore', 'collections');
    setFocusedTool('legend-lore');
    dispatchKey(key('x'));
    expect(seen).toEqual(['overlay', 'region', 'tool', 'global']);
    unbind.forEach((u) => u());
    setFocusedTool(null);
  });

  test("a region's and a tool's handlers run only while they are on the path", () => {
    const seen: string[] = [];
    const unbind = [
      bindKeys(() => (seen.push('ll:collections'), false), { tool: 'legend-lore', region: 'collections' }),
      bindKeys(() => (seen.push('ll:filters'), false), { tool: 'legend-lore', region: 'filters' }),
      bindKeys(() => (seen.push('ll'), false), { tool: 'legend-lore' }),
      bindKeys(() => (seen.push('command'), false), { tool: 'command' }),
    ];
    setRegion('legend-lore', 'filters');
    setFocusedTool('legend-lore');
    dispatchKey(key('x'));
    expect(seen).toEqual(['ll:filters', 'll']);
    seen.length = 0;
    setFocusedTool('command');
    dispatchKey(key('x'));
    expect(seen).toEqual(['command']);
    seen.length = 0;
    setFocusedTool(null);
    dispatchKey(key('x'));
    expect(seen).toEqual([]);
    unbind.forEach((u) => u());
  });

  test('a region taking the key keeps it from the tool and from global', () => {
    const tool = vi.fn(() => true);
    const unbind = [
      bindKeys(tool),
      bindKeys(() => true, { tool: 'legend-lore', region: 'collections' }),
    ];
    setRegion('legend-lore', 'collections');
    setFocusedTool('legend-lore');
    const e = key('x');
    dispatchKey(e);
    expect(tool).not.toHaveBeenCalled();
    expect(e.preventDefault).toHaveBeenCalledOnce();
    unbind.forEach((u) => u());
    setFocusedTool(null);
  });
});

describe('hostKeys', () => {
  function host() {
    const open = { settings: vi.fn(), shortcuts: vi.fn() };
    return { open, handle: hostKeys(open) };
  }
  const ctx = (over: Partial<KeyContext> = {}): KeyContext => ({ typing: false, editor: false, menu: false, ...over });

  test('? opens the sheet off fields, and types in them', () => {
    const { open, handle } = host();
    expect(handle(key('?', { shiftKey: true }), ctx())).toBe(true);
    expect(handle(key('?'), ctx({ typing: true }))).toBe(false);
    expect(open.shortcuts).toHaveBeenCalledOnce();
  });

  test('⌘/ opens the sheet from a field too, but not from the editor', () => {
    const { open, handle } = host();
    expect(handle(key('/', { metaKey: true }), ctx({ typing: true }))).toBe(true);
    expect(handle(key('/', { ctrlKey: true }), ctx({ typing: true, editor: true }))).toBe(false);
    expect(handle(key('/'), ctx())).toBe(false);
    expect(open.shortcuts).toHaveBeenCalledOnce();
  });

  test('⌘, opens settings, unshifted only', () => {
    const { open, handle } = host();
    expect(handle(key(',', { metaKey: true }), ctx())).toBe(true);
    expect(handle(key(',', { metaKey: true, shiftKey: true }), ctx())).toBe(false);
    expect(handle(key(',', { ctrlKey: true, altKey: true }), ctx())).toBe(false);
    expect(open.settings).toHaveBeenCalledOnce();
  });
});
