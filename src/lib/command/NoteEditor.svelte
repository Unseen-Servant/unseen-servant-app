<script lang="ts">
  // CodeMirror on a note's raw Markdown (design §7). It holds no file
  // state: NoteBuffer decides what's loaded and when it saves; this reports
  // edits and shows what it's handed.
  import { onDestroy, onMount } from 'svelte';
  import { Compartment, EditorState, type Extension } from '@codemirror/state';
  import { EditorView, drawSelection, keymap } from '@codemirror/view';
  import { defaultKeymap, history, historyKeymap } from '@codemirror/commands';
  import { markdown } from '@codemirror/lang-markdown';
  import { yamlFrontmatter } from '@codemirror/lang-yaml';
  import { syntaxHighlighting } from '@codemirror/language';
  import { autocompletion, completionKeymap } from '@codemirror/autocomplete';
  import { editorTheme, markdownHighlight, wikilinkMarks } from './editorTheme';
  import { wikilinkCompletion } from './wikilinks';

  /** The campaign's note names, read at completion time. */
  export let names: () => string[];
  export let resolves: (name: string) => boolean;
  export let onEdit: (content: string) => void;
  /** ⌘-click on a link. */
  export let onFollow: (name: string) => void;
  export let readOnly: boolean = false;

  let host: HTMLDivElement;
  let view: EditorView | null = null;
  const links = new Compartment();
  const editable = new Compartment();

  function extensions(content: string): Extension[] {
    return [
      // A file written with CRLF stays CRLF: CodeMirror joins lines with \n
      // unless told otherwise, which would rewrite every line ending.
      content.includes('\r\n') ? EditorState.lineSeparator.of('\r\n') : [],
      history(),
      drawSelection(),
      EditorView.lineWrapping,
      keymap.of([...completionKeymap, ...defaultKeymap, ...historyKeymap]),
      yamlFrontmatter({ content: markdown() }),
      syntaxHighlighting(markdownHighlight),
      autocompletion({ override: [wikilinkCompletion(names)], icons: false }),
      links.of(wikilinkMarks(resolves)),
      editable.of(EditorView.editable.of(!readOnly)),
      editorTheme,
      EditorView.domEventHandlers({
        mousedown(event) {
          const link = (event.target as HTMLElement).closest('.cm-wikilink');
          if (!link || !(event.metaKey || event.ctrlKey)) return false;
          event.preventDefault();
          onFollow(link.getAttribute('data-target') ?? '');
          return true;
        },
      }),
      EditorView.updateListener.of((update) => {
        if (update.docChanged) onEdit(update.state.doc.toString());
      }),
    ];
  }

  /** Show content from disk. A fresh state, so undo can't step back into
   *  another note or across a reload; `keepCaret` holds the caret's place
   *  when the same note reloads. */
  export function setContent(content: string, keepCaret: boolean) {
    if (!view) return;
    const head = keepCaret ? Math.min(view.state.selection.main.head, content.length) : 0;
    view.setState(EditorState.create({ doc: content, selection: { anchor: head }, extensions: extensions(content) }));
  }

  /** Redraw link marks after the campaign's names changed. */
  export function refreshLinks() {
    view?.dispatch({ effects: links.reconfigure(wikilinkMarks(resolves)) });
  }

  export function focus() {
    view?.focus();
  }

  $: view?.dispatch({ effects: editable.reconfigure(EditorView.editable.of(!readOnly)) });

  onMount(() => {
    view = new EditorView({ parent: host, state: EditorState.create({ doc: '', extensions: extensions('') }) });
  });

  onDestroy(() => view?.destroy());
</script>

<div class="note-editor" bind:this={host}></div>

<style>
  .note-editor {
    height: 100%;
    min-height: 0;
  }
</style>
