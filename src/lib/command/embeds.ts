// Images in notes (#407): Obsidian's `![[map.png]]` embeds, and relative
// `![alt](path)` ones, resolved within the campaign as links are and loaded
// through Tauri's asset protocol, which Rust scopes to the campaigns folder.

import { convertFileSrc } from '@tauri-apps/api/core';
import type { Readable } from 'svelte/store';

/** The files a card or an embed shows as a picture: the sidecar's list
 *  (vault.IMAGE_SUFFIXES). */
export const IMAGE = /\.(png|jpe?g|gif|webp|svg)$/i;

/** An embed's target and width: `map.png|300` sets the width, as in
 *  Obsidian, and so does `|300x200`, the height following the image. */
export function parseEmbed(inner: string): { target: string; width: number | null } {
  const [target, ...rest] = inner.split(/\\?\|/);
  const size = rest.map((r) => /^\s*(\d+)(?:x\d+)?\s*$/.exec(r)).find(Boolean);
  return { target: target.trim(), width: size ? Number(size[1]) : null };
}

const fold = (parts: string[]) => parts.map((p) => p.toLowerCase());

/** The image a name or a path ending in it names among the campaign's
 *  `images`, compared case-insensitively as a note's name is: `map.png`,
 *  `Maps/map.png`, or a path from a vault rooted above the campaign
 *  (`Strahd/Maps/map.png`). Null when none answers, or more than one. */
export function resolveImage(images: string[], campaign: string, target: string): string | null {
  const parts = fold(target.split('/').filter(Boolean));
  if (!parts.length) return null;
  const hits = images.filter((rel) => {
    const location = fold([campaign, ...rel.split('/')]);
    const n = Math.min(parts.length, location.length);
    return parts.slice(-n).join('/') === location.slice(-n).join('/');
  });
  return hits.length === 1 ? hits[0] : null;
}

/** The image a relative `![alt](path)` in the note at `from` names, read
 *  from the note's folder: one of `images`, or null. */
export function relativeImage(images: string[], from: string, path: string): string | null {
  const parts = from.split('/').slice(0, -1);
  for (const part of path.split('/')) {
    if (part === '..') {
      if (!parts.pop()) return null;
    } else if (part && part !== '.') parts.push(part);
  }
  const rel = parts.join('/').toLowerCase();
  return images.find((i) => i.toLowerCase() === rel) ?? null;
}

/** Whether a drag carries files from outside the app: Finder's. The app's
 *  own drags carry none, and native drag and drop stays off, so a drop of
 *  them is the page's own (#407). */
export const carriesFiles = (e: DragEvent) => !!e.dataTransfer?.types.includes('Files');

/** The images among a drop's files. */
export const droppedImages = (e: DragEvent) => [...(e.dataTransfer?.files ?? [])].filter((f) => IMAGE.test(f.name));

/** Where a card or the reader gets the URL the webview loads an image
 *  from; null when nothing in the campaign answers. */
export interface ImageSource {
  /** The image an embed names: by name, or (with the note's path `from`)
   *  relative to its note. */
  embed(target: string, from: string | null): string | null;
  /** The campaign's image at `rel`, an image card's. */
  file(rel: string): string | null;
}

/** The open campaign's ImageSource. A relative path that names nothing
 *  from the note's folder is tried as a name or a path, as Obsidian's
 *  "shortest path" links write it. Without a campaigns folder, nothing
 *  resolves. */
export function imageSource(root: string | null, campaign: string, images: string[]): ImageSource {
  const url = (rel: string | null) => (root && rel ? convertFileSrc(`${root}/${campaign}/${rel}`) : null);
  return {
    embed: (target, from) =>
      url((from !== null && relativeImage(images, from, target)) || resolveImage(images, campaign, target)),
    file: (rel) => url(rel),
  };
}

/** Where the board's cards find the campaign's ImageSource (Svelte
 *  context, a store): functions in a node's data would make Svelte Flow
 *  take the nodes for deeply reactive state. */
export const IMAGE_SOURCE = Symbol('image source');
export type ImageSourceStore = Readable<ImageSource>;

/** Where `embedImages` points an embed for `rehypeEmbeds` to resolve. */
const EMBED_SRC = '#embed:';

/** `![[map.png|300]]` as a Markdown image `rehypeEmbeds` resolves. An
 *  embed of anything but an image (a note's transclusion) stays as
 *  written. */
export function embedImages(md: string): string {
  return md.replace(/!\[\[([^[\]\n]+?)\]\]/g, (whole, inner: string) => {
    const { target } = parseEmbed(inner);
    if (!IMAGE.test(target)) return whole;
    return `![${target.split('/').pop()}](${EMBED_SRC}${encodeURIComponent(inner)})`;
  });
}

/** `text` with its percent-escapes undone, or as it is when they're
 *  malformed. */
function decoded(text: string): string {
  try {
    return decodeURIComponent(text);
  } catch {
    return text;
  }
}

/** The slice of a hast tree `rehypeEmbeds` reads. */
interface HastNode {
  type: string;
  tagName?: string;
  value?: string;
  properties?: Record<string, unknown>;
  children?: HastNode[];
}

/** A rehype plugin: each image `embedImages` made, and each relative
 *  `![alt](path)` in the note at `from`, loads what it names from
 *  `source`, at its width when it has one. One naming nothing becomes its
 *  name, dashed as a missing link is (`.embed-missing`). */
export function rehypeEmbeds(source: ImageSource, from: string | null) {
  return (tree: HastNode) => {
    const visit = (node: HastNode) => {
      node.children = node.children?.map((child) => {
        const src = child.tagName === 'img' ? child.properties?.src : undefined;
        if (typeof src !== 'string') {
          visit(child);
          return child;
        }
        let url: string | null;
        let name: string;
        let width: number | null = null;
        if (src.startsWith(EMBED_SRC)) {
          const embed = parseEmbed(decoded(src.slice(EMBED_SRC.length)));
          ({ width } = embed);
          name = embed.target;
          url = source.embed(embed.target, null);
        } else if (!/^[a-z][a-z\d+.-]*:|^[/#]/i.test(src) && from !== null) {
          // A relative path, not a web or data URL.
          name = decoded(src);
          url = source.embed(name, from);
        } else {
          return child;
        }
        if (!url) return { type: 'element', tagName: 'span', properties: { className: ['embed-missing'] }, children: [{ type: 'text', value: name }] };
        return { ...child, properties: { ...child.properties, src: url, ...(width ? { width } : {}) } };
      });
    };
    visit(tree);
  };
}
