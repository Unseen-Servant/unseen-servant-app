/**
 * Cross-checking `invoke()` calls against their `#[tauri::command]`
 * signatures.
 *
 * `invoke` takes an untyped object, so nothing in the toolchain links the
 * frontend to the Rust it calls: drop a required argument and svelte-check
 * still passes, the build still succeeds, and the failure only appears when
 * a user clicks the thing. That happened — the collection-creation refactor
 * dropped `description`, which Rust declares as `String` rather than
 * `Option<String>`, and both ways of making a collection died with an
 * invalid-args error.
 *
 * These are deliberately narrow parsers, not real ones. They throw rather
 * than guess: a guard that quietly stops matching anything is worse than no
 * guard, so the accompanying test also asserts it found a plausible amount
 * of work to do.
 */

export interface RustCommand {
  name: string;
  /** camelCase, as the JS side must spell them. */
  required: string[];
  optional: string[];
}

export interface InvokeCall {
  command: string;
  /** Top-level keys of the argument object; null when none was passed. */
  args: string[] | null;
  line: number;
}

export interface InvokeMismatch {
  file: string;
  line: number;
  command: string;
  missing: string[];
  unknown: string[];
}

/**
 * Parameters Tauri injects itself — they never appear in the JS payload.
 * Matched on the type, since the parameter name is the author's choice.
 */
const INJECTED_PARAM = /\b(AppHandle|State\s*<|WebviewWindow|Window|Runtime)\b/;

function snakeToCamel(name: string): string {
  return name.replace(/_(\w)/g, (_, c: string) => c.toUpperCase());
}

/** Index of the closing quote for the string opening at `start`. */
function skipString(source: string, start: number): number {
  const quote = source[start];
  for (let i = start + 1; i < source.length; i++) {
    if (source[i] === '\\') {
      i++;
      continue;
    }
    if (source[i] === quote) return i;
  }
  throw new Error(`Unterminated ${quote} string at offset ${start}`);
}

/** Index just past a comment starting at `start`, or -1 if none starts there. */
function skipComment(source: string, start: number): number {
  if (source[start] !== '/') return -1;
  if (source[start + 1] === '/') {
    const nl = source.indexOf('\n', start);
    return nl < 0 ? source.length : nl;
  }
  if (source[start + 1] === '*') {
    const end = source.indexOf('*/', start + 2);
    if (end < 0) throw new Error(`Unterminated block comment at offset ${start}`);
    return end + 1;
  }
  return -1;
}

const CLOSERS: Record<string, string> = { '(': ')', '{': '}', '[': ']' };

/**
 * Index of the delimiter closing the one at `openIndex`, ignoring anything
 * inside strings and comments. Throws if the source is unbalanced — better
 * a loud test failure than a silently truncated parse.
 */
export function findMatching(source: string, openIndex: number, quotes: string): number {
  const open = source[openIndex];
  const close = CLOSERS[open];
  if (!close) throw new Error(`Not an opening delimiter: ${open}`);
  let depth = 0;
  for (let i = openIndex; i < source.length; i++) {
    const ch = source[i];
    if (quotes.includes(ch)) {
      i = skipString(source, i);
      continue;
    }
    const past = skipComment(source, i);
    if (past >= 0) {
      i = past;
      continue;
    }
    if (ch === open) depth++;
    else if (ch === close && --depth === 0) return i;
  }
  throw new Error(`Unbalanced ${open} at offset ${openIndex}`);
}

/**
 * Split on commas that aren't nested inside brackets, strings, or comments.
 * `angles` counts `<`/`>` as nesting — right for Rust generics, wrong for
 * JS, where they're comparisons.
 */
function splitTopLevel(body: string, quotes: string, angles: boolean): string[] {
  const parts: string[] = [];
  let depth = 0;
  let start = 0;
  for (let i = 0; i < body.length; i++) {
    const ch = body[i];
    if (quotes.includes(ch)) {
      i = skipString(body, i);
      continue;
    }
    const past = skipComment(body, i);
    if (past >= 0) {
      i = past;
      continue;
    }
    if ('([{'.includes(ch) || (angles && ch === '<')) depth++;
    else if (')]}'.includes(ch) || (angles && ch === '>')) depth--;
    else if (ch === ',' && depth === 0) {
      parts.push(body.slice(start, i));
      start = i + 1;
    }
  }
  parts.push(body.slice(start));
  return parts;
}

/** Strip line and block comments so key extraction sees only code. */
function stripComments(text: string): string {
  let out = '';
  for (let i = 0; i < text.length; i++) {
    const past = skipComment(text, i);
    if (past >= 0) {
      i = past;
      continue;
    }
    out += text[i];
  }
  return out;
}

/**
 * Every `#[tauri::command]` in a Rust source file, with its JS-visible
 * parameters split into required and `Option<…>`.
 *
 * Rust strings are `"…"` only here: `'` opens a lifetime, not a char, in
 * anything that appears in these signatures.
 */
export function parseRustCommands(source: string): RustCommand[] {
  const commands: RustCommand[] = [];
  const marker = /#\[tauri::command[^\]]*\]/g;
  let m: RegExpExecArray | null;
  while ((m = marker.exec(source)) !== null) {
    const after = source.slice(m.index + m[0].length);
    const sig = /^\s*(?:#\[[^\]]*\]\s*)*(?:pub\s+)?(?:async\s+)?fn\s+(\w+)\s*\(/.exec(after);
    if (!sig) continue;
    const openParen = m.index + m[0].length + sig[0].length - 1;
    const params = source.slice(openParen + 1, findMatching(source, openParen, '"'));

    const required: string[] = [];
    const optional: string[] = [];
    for (const raw of splitTopLevel(params, '"', true)) {
      const param = stripComments(raw).trim();
      if (!param || !param.includes(':')) continue;
      const colon = param.indexOf(':');
      const name = param.slice(0, colon).replace(/^mut\s+/, '').trim();
      const type = param.slice(colon + 1);
      if (!/^\w+$/.test(name) || INJECTED_PARAM.test(type)) continue;
      (/\bOption\s*</.test(type) ? optional : required).push(snakeToCamel(name));
    }
    commands.push({ name: sig[1], required, optional });
  }
  return commands;
}

/**
 * Every `invoke('name', { … })` in a frontend file.
 *
 * Calls whose command name isn't a literal, or whose argument object isn't
 * a literal (a variable, or one carrying a spread), are skipped: their keys
 * can't be known from the source alone, and guessing would mean false
 * failures on correct code.
 */
export function parseInvokeCalls(source: string): InvokeCall[] {
  const calls: InvokeCall[] = [];
  const marker = /\binvoke\s*(?:<[^<>()]*>)?\s*\(/g;
  let m: RegExpExecArray | null;
  while ((m = marker.exec(source)) !== null) {
    const openParen = m.index + m[0].length - 1;
    const inner = source.slice(openParen + 1, findMatching(source, openParen, `'"\``));
    const named = /^\s*(['"])([\w:|.]+)\1\s*(,|$)/.exec(inner);
    if (!named) continue;

    const line = source.slice(0, m.index).split('\n').length;
    const rest = inner.slice(named[0].length);
    const objStart = rest.search(/\S/);
    if (objStart < 0) {
      calls.push({ command: named[2], args: null, line });
      continue;
    }
    if (rest[objStart] !== '{') continue; // args came from a variable

    const body = rest.slice(objStart + 1, findMatching(rest, objStart, `'"\``));
    const keys: string[] = [];
    let analyzable = true;
    for (const raw of splitTopLevel(body, `'"\``, false)) {
      const part = stripComments(raw).trim();
      if (!part) continue;
      if (part.startsWith('...')) {
        analyzable = false;
        break;
      }
      const key = (part.includes(':') ? part.slice(0, part.indexOf(':')) : part).trim();
      if (!/^\w+$/.test(key)) {
        analyzable = false;
        break;
      }
      keys.push(key);
    }
    if (analyzable) calls.push({ command: named[2], args: keys, line });
  }
  return calls;
}

/**
 * Calls that would fail Tauri's argument deserialization. Commands absent
 * from `commands` are reported too — a typo'd name fails just as hard as a
 * missing argument.
 */
export function checkInvokeCalls(
  commands: RustCommand[],
  calls: InvokeCall[],
  file: string
): InvokeMismatch[] {
  const byName = new Map(commands.map((c) => [c.name, c]));
  const mismatches: InvokeMismatch[] = [];
  for (const call of calls) {
    const command = byName.get(call.command);
    if (!command) {
      mismatches.push({
        file,
        line: call.line,
        command: call.command,
        missing: ['<no such #[tauri::command]>'],
        unknown: [],
      });
      continue;
    }
    const passed = new Set(call.args ?? []);
    const known = new Set([...command.required, ...command.optional]);
    const missing = command.required.filter((a) => !passed.has(a));
    const unknown = [...passed].filter((a) => !known.has(a));
    if (missing.length || unknown.length) {
      mismatches.push({ file, line: call.line, command: call.command, missing, unknown });
    }
  }
  return mismatches;
}

export function formatMismatch(m: InvokeMismatch): string {
  const parts = [`${m.file}:${m.line}  invoke('${m.command}')`];
  if (m.missing.length) parts.push(`missing required arg(s): ${m.missing.join(', ')}`);
  if (m.unknown.length) parts.push(`no such arg(s): ${m.unknown.join(', ')}`);
  return parts.join('\n      ');
}
