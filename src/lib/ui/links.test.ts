import { beforeEach, describe, expect, it, vi } from 'vitest';

const openUrl = vi.hoisted(() => vi.fn(async (_url: string) => {}));
vi.mock('@tauri-apps/plugin-opener', () => ({ openUrl }));

import { clickedHref, followWebLink, keepLinksOffTheWebview, openWebLink } from './links';

/** A click whose target sits inside a link to `href`, or inside none. */
function click(href: string | null) {
  const link = href === null ? null : { getAttribute: () => href };
  return {
    target: { closest: (selector: string) => (selector === 'a[href]' ? link : null) },
    preventDefault: vi.fn(),
  };
}

const asEvent = (e: ReturnType<typeof click>) => e as unknown as Event;

beforeEach(() => openUrl.mockClear());

describe('a click on a rendered link', () => {
  it('never navigates the webview, whatever the link', () => {
    for (const href of ['https://paizo.com', 'http://www.paizo.com', 'file:///etc/hosts', '#note:Ismark', 'mailto:gm@example.com', '']) {
      const e = click(href);
      expect(clickedHref(asEvent(e))).toBe(href);
      expect(e.preventDefault).toHaveBeenCalledOnce();
    }
  });

  it('leaves a click that is on no link alone', () => {
    const e = click(null);
    expect(clickedHref(asEvent(e))).toBeNull();
    keepLinksOffTheWebview(asEvent(e));
    followWebLink(asEvent(e));
    expect(e.preventDefault).not.toHaveBeenCalled();
    expect(openUrl).not.toHaveBeenCalled();
  });

  it('opens a web link in the browser, and nothing else', () => {
    followWebLink(asEvent(click('http://www.paizo.com')));
    expect(openUrl).toHaveBeenCalledExactlyOnceWith('http://www.paizo.com');
    openUrl.mockClear();
    for (const href of ['file:///etc/hosts', '#note:Ismark', 'mailto:gm@example.com', 'javascript:alert(1)']) {
      followWebLink(asEvent(click(href)));
      expect(openWebLink(href)).toBe(false);
    }
    expect(openUrl).not.toHaveBeenCalled();
  });

  it('reports a link the system would not open', async () => {
    openUrl.mockRejectedValueOnce(new Error('not allowed'));
    const onError = vi.fn();
    expect(openWebLink('https://paizo.com', onError)).toBe(true);
    await vi.waitFor(() => expect(onError).toHaveBeenCalledWith('Error: not allowed'));
  });

  it('is cancelled by the window backstop too', () => {
    const e = click('https://paizo.com');
    keepLinksOffTheWebview(asEvent(e));
    expect(e.preventDefault).toHaveBeenCalledOnce();
    expect(openUrl).not.toHaveBeenCalled();
  });
});
