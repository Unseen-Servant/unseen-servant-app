// The note editor's look, all from the app's tokens: CodeMirror on the raw
// Markdown source (design §7), styled rather than rendered, so what the GM
// types is exactly what lands in the file.

import { HighlightStyle } from '@codemirror/language';
import { Decoration, EditorView, MatchDecorator, ViewPlugin, type DecorationSet, type ViewUpdate } from '@codemirror/view';
import { tags } from '@lezer/highlight';

export const editorTheme = EditorView.theme(
  {
    '&': {
      height: '100%',
      color: 'var(--text-primary)',
      backgroundColor: 'transparent',
      fontSize: '1rem',
    },
    '&.cm-focused': { outline: 'none' },
    '.cm-scroller': {
      fontFamily: 'var(--font-body)',
      lineHeight: '1.55',
    },
    '.cm-content': {
      padding: '0.75rem 1rem 3rem',
      caretColor: 'var(--text-accent)',
    },
    '.cm-cursor, .cm-dropCursor': { borderLeftColor: 'var(--text-accent)' },
    '&.cm-focused > .cm-scroller > .cm-selectionLayer .cm-selectionBackground, .cm-selectionBackground, .cm-content ::selection':
      { backgroundColor: 'color-mix(in srgb, var(--text-accent) 22%, transparent)' },
    // Syntax colouring (a YAML string, say) can nest inside the link mark;
    // the link's colour still wins.
    '.cm-wikilink, .cm-wikilink span': { color: 'var(--text-accent)' },
    '.cm-wikilink-missing, .cm-wikilink-missing span': {
      color: 'var(--text-secondary)',
      textDecoration: 'underline dashed',
      textDecorationColor: 'var(--text-accent)',
      textUnderlineOffset: '3px',
    },
    '.cm-tooltip': {
      backgroundColor: 'var(--bg-container)',
      border: '1px solid var(--border-subtle)',
      borderRadius: 'var(--radius-md)',
      boxShadow: 'var(--shadow-dropdown)',
    },
    '.cm-tooltip.cm-tooltip-autocomplete > ul': {
      fontFamily: 'var(--font-body)',
      maxHeight: 'var(--menu-max-height)',
      minWidth: 'var(--submenu-width)',
    },
    '.cm-tooltip.cm-tooltip-autocomplete > ul > li': {
      padding: '0.15rem 0.6rem',
      color: 'var(--text-primary)',
    },
    '.cm-tooltip.cm-tooltip-autocomplete > ul > li[aria-selected]': {
      backgroundColor: 'var(--bg-focused)',
      color: 'var(--text-primary)',
    },
    '.cm-completionMatchedText': {
      textDecoration: 'none',
      color: 'var(--text-accent)',
    },
  },
  { dark: true },
);

export const markdownHighlight = HighlightStyle.define([
  { tag: tags.heading, fontFamily: 'var(--font-heading)', fontWeight: '400' },
  { tag: tags.heading1, fontSize: '1.45em' },
  { tag: tags.heading2, fontSize: '1.25em' },
  { tag: tags.heading3, fontSize: '1.1em' },
  { tag: tags.emphasis, fontStyle: 'italic' },
  { tag: tags.strong, fontWeight: '700' },
  { tag: tags.strikethrough, textDecoration: 'line-through' },
  { tag: [tags.link, tags.url], color: 'var(--text-accent)' },
  { tag: tags.monospace, fontFamily: 'var(--font-mono)', fontSize: '0.88em' },
  { tag: tags.quote, color: 'var(--text-secondary)', fontStyle: 'italic' },
  // Markdown's own marks (#, *, >, list bullets) and rules recede.
  { tag: [tags.processingInstruction, tags.contentSeparator, tags.meta], color: 'var(--text-tertiary)' },
  // YAML frontmatter: keys quiet, values read as content.
  { tag: [tags.propertyName, tags.definition(tags.propertyName)], color: 'var(--text-secondary)' },
  { tag: [tags.string, tags.number, tags.bool, tags.null], color: 'var(--text-primary)' },
  { tag: [tags.punctuation, tags.separator, tags.squareBracket, tags.brace], color: 'var(--text-tertiary)' },
]);

/** The note a wikilink names: its target, without alias, heading, folder or
 *  `.md`. A table cell's escaped pipe (`\|`) counts as the alias bar. */
export function linkTarget(inner: string): string {
  const target = inner.split(/\\?\||#/)[0].trim();
  return (target.split('/').pop() ?? '').replace(/\.md$/i, '');
}

/** Marks `[[links]]`: parchment when they resolve, dashed when nothing in
 *  the campaign answers to the name. `data-target` carries the name for
 *  ⌘-click to follow. */
export function wikilinkMarks(resolves: (name: string) => boolean) {
  const decorator = new MatchDecorator({
    regexp: /\[\[([^[\]\n]+?)\]\]/g,
    decoration: (m) => {
      const name = linkTarget(m[1]);
      return Decoration.mark({
        class: resolves(name) ? 'cm-wikilink' : 'cm-wikilink cm-wikilink-missing',
        attributes: { 'data-target': name },
      });
    },
  });
  return ViewPlugin.fromClass(
    class {
      decorations: DecorationSet;
      constructor(view: EditorView) {
        this.decorations = decorator.createDeco(view);
      }
      update(update: ViewUpdate) {
        this.decorations = decorator.updateDeco(update, this.decorations);
      }
    },
    { decorations: (v) => v.decorations },
  );
}
