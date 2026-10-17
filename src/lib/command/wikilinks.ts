// `[[` completion over the campaign's note names. The matching is plain
// functions so it's testable without an editor; `wikilinkCompletion` wraps
// it as a CodeMirror completion source.

import type { Completion, CompletionContext, CompletionResult } from '@codemirror/autocomplete';
import type { EditorView } from '@codemirror/view';

/** An open `[[` before the caret, with no `]`, `|`, `#` or line break since:
 *  the caret is inside a link target. */
const OPEN_TARGET = /\[\[[^[\]|#\n]*$/;

/** The typed part of a link target ending at the caret, or null when the
 *  caret isn't in one. `from` is where the target starts. */
export function openTarget(before: string): { from: number; typed: string } | null {
  const m = OPEN_TARGET.exec(before);
  if (!m) return null;
  return { from: m.index + 2, typed: m[0].slice(2) };
}

/** What completing `name` inserts, given the text right after the caret:
 *  the closing brackets unless they're already there. */
export function insertion(name: string, after: string): string {
  return after.startsWith(']]') ? name : `${name}]]`;
}

export function wikilinkCompletion(names: () => string[]) {
  return (ctx: CompletionContext): CompletionResult | null => {
    const line = ctx.state.doc.lineAt(ctx.pos);
    const target = openTarget(line.text.slice(0, ctx.pos - line.from));
    if (!target) return null;
    const from = line.from + target.from;
    const options: Completion[] = names().map((name) => ({
      label: name,
      apply: (view: EditorView, _c: Completion, start: number, end: number) => {
        const insert = insertion(name, view.state.sliceDoc(end, end + 2));
        const close = insert.endsWith(']]') ? 0 : 2;
        view.dispatch({
          changes: { from: start, to: end, insert },
          selection: { anchor: start + insert.length + close },
        });
      },
    }));
    return { from, options, validFor: /^[^[\]|#\n]*$/ };
  };
}
