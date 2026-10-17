import { describe, it, expect } from 'vitest';
import { readFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { BOOK, CARET_RIGHT, CIRCLE, CIRCLE_RING, FOLDER, FOLDER_OPEN, GEM, GEM_OUTLINE, MARK, PLAY, SHIELD } from './iconPaths';

function vendoredPath(file: string): string {
  const svg = readFileSync(new URL(`./icons/${file}`, import.meta.url), 'utf8');
  const match = svg.match(/\sd="([^"]+)"/);
  if (!match) throw new Error(`no path data in ${file}`);
  return match[1];
}

function svelteFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = `${dir}/${entry.name}`;
    if (entry.isDirectory()) return svelteFiles(full);
    return entry.name.endsWith('.svelte') ? [full] : [];
  });
}

describe('vendored sources', () => {
  // A Font Awesome bump should fail here rather than silently leaving the
  // shipped glyph a version behind its source file.
  it('book matches its vendored file', () => {
    expect(BOOK).toBe(vendoredPath('book-solid-full.svg'));
  });
  it('caret-right matches its vendored file', () => {
    expect(CARET_RIGHT).toBe(vendoredPath('caret-right-solid-full.svg'));
  });
  it('circle matches its vendored file', () => {
    expect(CIRCLE).toBe(vendoredPath('circle-solid-full.svg'));
  });
  it('circle ring matches its vendored file', () => {
    expect(CIRCLE_RING).toBe(vendoredPath('circle-regular-full.svg'));
  });
  it('folder matches its vendored file', () => {
    expect(FOLDER).toBe(vendoredPath('folder-solid-full.svg'));
  });
  it('folder-open matches its vendored file', () => {
    expect(FOLDER_OPEN).toBe(vendoredPath('folder-open-solid-full.svg'));
  });
  it('play matches its vendored file', () => {
    expect(PLAY).toBe(vendoredPath('play-solid-full.svg'));
  });
});

describe('shared glyphs', () => {
  // Re-inlining a shared path is how the eight copies of the old die glyph happened.
  it('are not re-inlined in components', () => {
    const src = fileURLToPath(new URL('../..', import.meta.url));
    const shared: Record<string, string> = {
      BOOK,
      CARET_RIGHT,
      CIRCLE,
      CIRCLE_RING,
      FOLDER,
      FOLDER_OPEN,
      GEM,
      GEM_OUTLINE,
      MARK,
      PLAY,
      SHIELD,
    };
    const offenders = svelteFiles(src).flatMap((file) => {
      const text = readFileSync(file, 'utf8');
      return Object.entries(shared)
        .filter(([, path]) => text.includes(`d="${path}"`))
        .map(([name]) => `${file.slice(src.length)} inlines ${name}`);
    });
    expect(offenders).toEqual([]);
  });
});
