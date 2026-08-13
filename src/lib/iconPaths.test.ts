import { describe, it, expect } from 'vitest';
import { readFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { BOOK, DICE_D6, DIE_OUTLINE, FOLDER_OPEN, RIBBON_FILLED, RIBBON_OUTLINE } from './iconPaths';

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
  it('dice-d6 matches its vendored file', () => {
    expect(DICE_D6).toBe(vendoredPath('dice-d6-solid-full.svg'));
  });

  it('book matches its vendored file', () => {
    expect(BOOK).toBe(vendoredPath('book-solid-full.svg'));
  });
});

describe('shared glyphs', () => {
  // Re-inlining a shared path is how the eight dice-d6 copies happened.
  it('are not re-inlined in components', () => {
    const src = fileURLToPath(new URL('..', import.meta.url));
    const shared: Record<string, string> = {
      DICE_D6,
      BOOK,
      FOLDER_OPEN,
      RIBBON_FILLED,
      RIBBON_OUTLINE,
      ...Object.fromEntries(DIE_OUTLINE.map((d, i) => [`DIE_OUTLINE[${i}]`, d])),
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
