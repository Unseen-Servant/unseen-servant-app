import { describe, expect, it, vi } from 'vitest';

vi.mock('@tauri-apps/api/core', () => ({ convertFileSrc: (path: string) => `asset://localhost/${encodeURIComponent(path)}` }));

import { embedImages, imageSource, parseEmbed, rehypeEmbeds, relativeImage, resolveImage, type ImageSource } from './embeds';

const images = ['Maps/Barovia.png', 'NPCs/Ismark.JPG', 'Shelf/crest.webp', 'Old/crest.webp', 'Sessions/handout.svg'];

describe('parseEmbed', () => {
  it('reads the target and a width, as Obsidian does', () => {
    expect(parseEmbed('map.png')).toEqual({ target: 'map.png', width: null });
    expect(parseEmbed('Maps/map.png|300')).toEqual({ target: 'Maps/map.png', width: 300 });
    expect(parseEmbed('map.png|300x200')).toEqual({ target: 'map.png', width: 300 });
    expect(parseEmbed('map.png|the village')).toEqual({ target: 'map.png', width: null });
    // In a table the bar is escaped.
    expect(parseEmbed('map.png\\|120')).toEqual({ target: 'map.png', width: 120 });
  });
});

describe('resolveImage', () => {
  it('finds an image by its name or a path ending in it, in any case', () => {
    expect(resolveImage(images, 'Strahd', 'barovia.PNG')).toBe('Maps/Barovia.png');
    expect(resolveImage(images, 'Strahd', 'Maps/Barovia.png')).toBe('Maps/Barovia.png');
    expect(resolveImage(images, 'Strahd', 'Strahd/NPCs/Ismark.jpg')).toBe('NPCs/Ismark.JPG');
  });

  it('answers nothing when no image or two share the name', () => {
    expect(resolveImage(images, 'Strahd', 'gone.png')).toBeNull();
    expect(resolveImage(images, 'Strahd', 'Other/Barovia.png')).toBeNull();
    expect(resolveImage(images, 'Strahd', 'crest.webp')).toBeNull();
    expect(resolveImage(images, 'Strahd', 'Shelf/crest.webp')).toBe('Shelf/crest.webp');
  });
});

describe('relativeImage', () => {
  it('reads a path from the note’s folder', () => {
    expect(relativeImage(images, 'NPCs/Ireena.md', 'Ismark.jpg')).toBe('NPCs/Ismark.JPG');
    expect(relativeImage(images, 'NPCs/Ireena.md', '../Maps/Barovia.png')).toBe('Maps/Barovia.png');
    expect(relativeImage(images, 'Overview.md', './Maps/Barovia.png')).toBe('Maps/Barovia.png');
    expect(relativeImage(images, 'Overview.md', '../Barovia.png')).toBeNull();
  });
});

describe('imageSource', () => {
  it('loads what an embed names from the campaigns folder, relative paths first', () => {
    const source = imageSource('/Users/gm/Unseen Servant', 'Strahd', images);
    expect(source.embed('Barovia.png', null)).toBe(`asset://localhost/${encodeURIComponent('/Users/gm/Unseen Servant/Strahd/Maps/Barovia.png')}`);
    // Obsidian's "shortest path" link: not beside the note, so by name.
    expect(source.embed('Barovia.png', 'NPCs/Ireena.md')).toContain('Maps%2FBarovia.png');
    expect(source.embed('gone.png', null)).toBeNull();
    expect(source.file('Shelf/crest.webp')).toContain('Shelf%2Fcrest.webp');
  });

  it('serves nothing without a campaigns folder', () => {
    const source = imageSource(null, 'Strahd', images);
    expect(source.embed('Barovia.png', null)).toBeNull();
    expect(source.file('Maps/Barovia.png')).toBeNull();
  });
});

describe('embedImages', () => {
  it('turns an image embed into a Markdown image, leaving other embeds and links', () => {
    expect(embedImages('See ![[Maps/Barovia.png|300]] and ![[Ismark]] or [[Ireena]].')).toBe(
      `See ![Barovia.png](#embed:${encodeURIComponent('Maps/Barovia.png|300')}) and ![[Ismark]] or [[Ireena]].`,
    );
  });
});

describe('rehypeEmbeds', () => {
  const img = (src: string) => ({ type: 'element', tagName: 'img', properties: { src, alt: 'x' } as Record<string, unknown>, children: [] });
  const source: ImageSource = {
    embed: (target, from) => (target === 'Barovia.png' || (from && target === 'Ismark.jpg') ? `asset://${target}` : null),
    file: () => null,
  };

  it('loads embeds and relative images, keeps web images, and dashes what names nothing', () => {
    const tree = {
      type: 'root',
      children: [
        {
          type: 'element',
          tagName: 'p',
          properties: {},
          children: [
            img(`#embed:${encodeURIComponent('Barovia.png|300')}`),
            img('Ismark.jpg'),
            img(`#embed:${encodeURIComponent('gone.png')}`),
            img('https://example.com/a.png'),
          ],
        },
      ],
    };
    rehypeEmbeds(source, 'NPCs/Ireena.md')(tree);
    const [embed, relative, missing, web] = tree.children[0].children as ReturnType<typeof img>[];
    expect(embed.properties).toEqual({ src: 'asset://Barovia.png', alt: 'x', width: 300 });
    expect(relative.properties.src).toBe('asset://Ismark.jpg');
    expect(missing).toEqual({ type: 'element', tagName: 'span', properties: { className: ['embed-missing'] }, children: [{ type: 'text', value: 'gone.png' }] });
    expect(web.properties.src).toBe('https://example.com/a.png');
  });
});
