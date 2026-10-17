<script lang="ts">
  // Reading mode (design §7): the note rendered, as Obsidian's reading view.
  // A board card's rendering (NoteCard: the body without its frontmatter,
  // `[[links]]` made followable, GFM for the tables), in the editor's type
  // and inset, so the toggle changes the markup and not the page. Editing
  // stays on the source.
  import Markdown, { type Plugin } from 'svelte-exmarkdown';
  import { gfmPlugin } from 'svelte-exmarkdown/gfm';
  import { openUrl } from '@tauri-apps/plugin-opener';
  import { NOTE_HREF, bodyOf, linkify, rehypeMissingLinks } from './board';

  /** The editor's text, unsaved keystrokes included. */
  export let text: string;
  export let resolves: (name: string) => boolean;
  /** A click on a note's link. */
  export let onFollow: (name: string) => void;
  export let onError: (message: string) => void;

  let plugins: Plugin[];
  $: plugins = [gfmPlugin(), { rehypePlugin: [rehypeMissingLinks, resolves] }];

  /** As a card's links: a note's opens the note, a web link the browser,
   *  and nothing navigates the webview. */
  function onClick(e: MouseEvent) {
    const link = (e.target as HTMLElement).closest('a');
    if (!link) return;
    e.preventDefault();
    const href = link.getAttribute('href') ?? '';
    if (href.startsWith(NOTE_HREF)) onFollow(decodeURIComponent(href.slice(NOTE_HREF.length)));
    else if (/^https?:/i.test(href)) void openUrl(href).catch((err) => onError(String(err)));
  }
</script>

<!-- Links are anchors with an href, so the keyboard reaches them and Enter
     brings the click handled here. -->
<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
<div class="reader" on:click={onClick}>
  <Markdown md={linkify(bodyOf(text))} {plugins} />
</div>

<style>
  /* The editor's face, size, measure and inset (editorTheme: .cm-scroller,
     .cm-content, and CodeMirror's own 6px/2px line padding), so the text
     doesn't jump sideways on a toggle. */
  .reader {
    height: 100%;
    overflow-y: auto;
    padding: 0.75rem calc(1rem + 2px) 3rem calc(1.1rem + 6px);
    font-family: var(--font-body);
    font-size: 1rem;
    line-height: 1.55;
    color: var(--text-primary);
    word-break: break-word;
  }

  .reader :global(> *:first-child) { margin-top: 0; }
  .reader :global(> *:last-child) { margin-bottom: 0; }

  /* Headings as the editor sets them (editorTheme markdownHighlight). */
  .reader :global(:is(h1, h2, h3, h4, h5, h6)) {
    font-family: var(--font-heading);
    font-weight: 400;
    font-size: 1em;
    line-height: 1.3;
    margin: 0.9em 0 0.3em;
  }
  .reader :global(h1) { font-size: 1.45em; }
  .reader :global(h2) { font-size: 1.25em; }
  .reader :global(h3) { font-size: 1.1em; }

  /* From here, SearchInspector's .snippet rules. */
  .reader :global(p) { margin: 0.4em 0; }
  .reader :global(ul),
  .reader :global(ol) { margin: 0.4em 0; padding-left: 1.25em; }
  .reader :global(li) { margin: 0.1em 0; }
  .reader :global(strong) { font-weight: 700; }
  .reader :global(code) {
    font-family: var(--font-mono);
    font-size: 0.88em;
    padding: 0 0.25em;
    background: var(--bg-app);
    border-radius: var(--radius-cell);
  }
  .reader :global(pre) {
    margin: 0.45em 0;
    padding: 0.4em 0.6em;
    background: var(--bg-app);
    border-radius: var(--radius-sm);
    overflow-x: auto;
  }
  .reader :global(pre code) { background: transparent; padding: 0; }
  /* Italic and secondary, as the editor shows a quote. */
  .reader :global(blockquote) {
    margin: 0.45em 0;
    padding-left: 0.75em;
    border-left: 2px solid var(--border-subtle);
    color: var(--text-secondary);
    font-style: italic;
  }
  .reader :global(hr) {
    border: none;
    border-top: 1px solid var(--border-subtle);
    margin: 0.9em 0;
  }
  .reader :global(img) { max-width: 100%; height: auto; }

  /* Links as the editor marks them: parchment, or dashed where nothing in
     the campaign answers. No underline otherwise; hover brightens. */
  .reader :global(a) {
    color: var(--text-accent);
    text-decoration: none;
    cursor: pointer;
    transition: filter var(--transition-fast);
  }
  .reader :global(a:hover) { filter: brightness(1.25); }
  .reader :global(a.missing) {
    color: var(--text-secondary);
    text-decoration: underline dashed;
    text-decoration-color: var(--text-accent);
    text-underline-offset: 3px;
  }

  .reader :global(table) {
    display: block;
    width: fit-content;
    max-width: 100%;
    overflow-x: auto;
    border-collapse: collapse;
    margin: 0.5em 0;
    font-size: 0.88em;
    border: 1px solid var(--border-subtle);
    background: var(--bg-app);
  }
  .reader :global(thead) { background: var(--bg-header); }
  .reader :global(th),
  .reader :global(td) {
    border: 1px solid var(--border-subtle);
    padding: 0.25em 0.5em;
    vertical-align: top;
    text-align: left;
  }
  .reader :global(th) {
    font-weight: 600;
    color: var(--text-accent);
  }
</style>
