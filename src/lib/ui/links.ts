// A click on a link in rendered Markdown: a PDF's text in Legend Lore, a
// note or a text card in Command. Followed as written, an anchor loads its
// address into the app's own webview, and the app is gone until it is
// started again; so a click never does that. A web link opens in the
// browser, and anything else is the caller's to act on.

import { openUrl } from '@tauri-apps/plugin-opener';

/** The href of the link `e` landed on, with the navigation cancelled; null
 *  when it landed on no link. */
export function clickedHref(e: Event): string | null {
  const target = e.target as Element | null;
  const link = target?.closest?.('a[href]');
  if (!link) return null;
  e.preventDefault();
  return link.getAttribute('href') ?? '';
}

/** Open `href` in the browser when it is a web address. Whether it was one. */
export function openWebLink(href: string, onError: (message: string) => void = () => {}): boolean {
  if (!/^https?:/i.test(href)) return false;
  void openUrl(href).catch((err) => onError(String(err)));
  return true;
}

/** For a container whose links are web links or nothing (a PDF's text). */
export function followWebLink(e: Event): void {
  const href = clickedHref(e);
  if (href) openWebLink(href);
}

/** The window's backstop, under every container's own handler: whatever
 *  renders a link, a click on it doesn't navigate. */
export function keepLinksOffTheWebview(e: Event): void {
  clickedHref(e);
}
