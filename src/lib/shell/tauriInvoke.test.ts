import { describe, it, expect } from 'vitest';
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  parseRustCommands,
  parseInvokeCalls,
  checkInvokeCalls,
  formatMismatch,
  findMatching,
} from './tauriInvoke';

describe('parseRustCommands', () => {
  it('splits parameters into required and Option', () => {
    expect(
      parseRustCommands(`
        #[tauri::command]
        async fn create_collection(
            name: String,
            file_paths: Vec<String>,
            description: String,
            color: Option<String>,
        ) -> Result<Thing, String> { }
      `)
    ).toEqual([
      {
        name: 'create_collection',
        required: ['name', 'filePaths', 'description'],
        optional: ['color'],
      },
    ]);
  });

  it('camelCases parameter names the way Tauri exposes them', () => {
    expect(parseRustCommands('#[tauri::command] fn f(old_path: String) {}')[0].required).toEqual([
      'oldPath',
    ]);
  });

  it('drops the parameters Tauri injects rather than the caller passing', () => {
    const [cmd] = parseRustCommands(`
      #[tauri::command]
      fn get_mcp_config(app_handle: tauri::AppHandle, name: String) -> String {}
    `);
    expect(cmd.required).toEqual(['name']);
  });

  it('is not fooled by commas inside generics', () => {
    const [cmd] = parseRustCommands(
      '#[tauri::command] fn f(map: HashMap<String, String>, n: u32) {}'
    );
    expect(cmd.required).toEqual(['map', 'n']);
  });

  it('handles a command with no caller-supplied parameters', () => {
    expect(parseRustCommands('#[tauri::command] async fn get_stats() -> X {}')).toEqual([
      { name: 'get_stats', required: [], optional: [] },
    ]);
  });

  it('ignores plain functions', () => {
    expect(parseRustCommands('fn helper(a: String) {}')).toEqual([]);
  });

  it('finds every command in a file, not just the first', () => {
    const src = `
      #[tauri::command] fn a(x: String) {}
      fn between() {}
      #[tauri::command] async fn b(y: Option<u8>) {}
    `;
    expect(parseRustCommands(src).map((c) => c.name)).toEqual(['a', 'b']);
  });
});

describe('parseInvokeCalls', () => {
  it('reads the command name and its argument keys', () => {
    expect(parseInvokeCalls("invoke('rename_file', { oldPath: p, newName: n });")).toEqual([
      { command: 'rename_file', args: ['oldPath', 'newName'], line: 1 },
    ]);
  });

  it('sees through a generic type argument', () => {
    expect(parseInvokeCalls("invoke<Foo>('get_stats')")[0]).toEqual({
      command: 'get_stats',
      args: null,
      line: 1,
    });
  });

  it('accepts shorthand properties', () => {
    expect(parseInvokeCalls("invoke('f', { name, paths })")[0].args).toEqual(['name', 'paths']);
  });

  it('is not fooled by a comma inside a nested value', () => {
    expect(parseInvokeCalls("invoke('f', { a: g(1, 2), b: [3, 4] })")[0].args).toEqual(['a', 'b']);
  });

  it('is not fooled by a brace or comma inside a string', () => {
    expect(parseInvokeCalls("invoke('f', { a: 'x, y}', b: 1 })")[0].args).toEqual(['a', 'b']);
  });

  it('is not fooled by a template literal', () => {
    expect(parseInvokeCalls('invoke("f", { a: `${x}, {`, b: 1 })')[0].args).toEqual(['a', 'b']);
  });

  it('ignores keys that are only mentioned in a comment', () => {
    expect(parseInvokeCalls("invoke('f', {\n // color: c,\n name,\n})")[0].args).toEqual(['name']);
  });

  it('skips a call whose command name is a variable', () => {
    expect(parseInvokeCalls('invoke(command, { a: 1 })')).toEqual([]);
  });

  it('skips a call whose arguments come from a variable', () => {
    expect(parseInvokeCalls("invoke('f', payload)")).toEqual([]);
  });

  // A spread hides keys the source can't enumerate; flagging it would mean
  // failing correct code.
  it('skips a call whose argument object carries a spread', () => {
    expect(parseInvokeCalls("invoke('f', { ...base, a: 1 })")).toEqual([]);
  });

  it('reports the line the call starts on', () => {
    expect(parseInvokeCalls("\n\n\ninvoke('f', { a: 1 })")[0].line).toBe(4);
  });

  it('finds several calls in one file', () => {
    expect(parseInvokeCalls("invoke('a'); invoke('b', { x: 1 })").map((c) => c.command)).toEqual([
      'a',
      'b',
    ]);
  });
});

describe('findMatching', () => {
  it('throws rather than guessing when the source is unbalanced', () => {
    expect(() => findMatching('foo({ a: 1', 3, `'"\``)).toThrow(/Unbalanced/);
  });
});

describe('checkInvokeCalls', () => {
  const commands = [
    { name: 'create_collection', required: ['name', 'description'], optional: ['color'] },
    { name: 'get_stats', required: [], optional: [] },
  ];

  it('passes a call that supplies every required argument', () => {
    const calls = [{ command: 'create_collection', args: ['name', 'description'], line: 1 }];
    expect(checkInvokeCalls(commands, calls, 'f.ts')).toEqual([]);
  });

  it('allows an optional argument to be present or absent', () => {
    const withColor = [
      { command: 'create_collection', args: ['name', 'description', 'color'], line: 1 },
    ];
    expect(checkInvokeCalls(commands, withColor, 'f.ts')).toEqual([]);
  });

  // The regression this whole file exists for.
  it('catches a dropped required argument', () => {
    const calls = [{ command: 'create_collection', args: ['name'], line: 7 }];
    const [found] = checkInvokeCalls(commands, calls, 'page.svelte');
    expect(found.missing).toEqual(['description']);
    expect(found.line).toBe(7);
  });

  it('catches an argument the command does not declare', () => {
    const calls = [
      { command: 'create_collection', args: ['name', 'description', 'nope'], line: 1 },
    ];
    expect(checkInvokeCalls(commands, calls, 'f.ts')[0].unknown).toEqual(['nope']);
  });

  it('catches a call passing no arguments to a command that needs them', () => {
    const calls = [{ command: 'create_collection', args: null, line: 1 }];
    expect(checkInvokeCalls(commands, calls, 'f.ts')[0].missing).toEqual(['name', 'description']);
  });

  it('catches a command name that does not exist', () => {
    const calls = [{ command: 'get_statz', args: null, line: 1 }];
    expect(checkInvokeCalls(commands, calls, 'f.ts')).toHaveLength(1);
  });

  it('passes a no-argument command called with no arguments', () => {
    expect(checkInvokeCalls(commands, [{ command: 'get_stats', args: null, line: 1 }], 'f.ts'))
      .toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// The guard itself, against the real tree.
// ---------------------------------------------------------------------------

const root = fileURLToPath(new URL('../../..', import.meta.url));

function walk(dir: string, match: (name: string) => boolean): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === 'node_modules' || entry.name.startsWith('.')) continue;
    const full = join(dir, entry.name);
    if (entry.isDirectory()) out.push(...walk(full, match));
    else if (match(entry.name)) out.push(full);
  }
  return out;
}

describe('every invoke() matches its #[tauri::command]', () => {
  const rustFiles = walk(join(root, 'src-tauri', 'src'), (n) => n.endsWith('.rs'));
  const commands = rustFiles.flatMap((f) => parseRustCommands(readFileSync(f, 'utf8')));

  const frontendFiles = walk(
    join(root, 'src'),
    (n) => (n.endsWith('.svelte') || n.endsWith('.ts')) && !n.endsWith('.test.ts')
  );
  const perFile = frontendFiles.map((f) => ({
    file: f.slice(root.length),
    calls: parseInvokeCalls(readFileSync(f, 'utf8')),
  }));
  const totalCalls = perFile.reduce((n, f) => n + f.calls.length, 0);

  // Without these, a parser that silently stops matching turns the guard
  // below into a test that always passes.
  it('found the Rust commands', () => {
    expect(rustFiles.length).toBeGreaterThan(0);
    expect(commands.length).toBeGreaterThanOrEqual(30);
    expect(commands.some((c) => c.required.length > 0)).toBe(true);
    expect(commands.some((c) => c.optional.length > 0)).toBe(true);
  });

  it('found the frontend call sites', () => {
    expect(totalCalls).toBeGreaterThanOrEqual(40);
    expect(perFile.filter((f) => f.calls.length > 0).length).toBeGreaterThanOrEqual(4);
    expect(perFile.some((f) => f.calls.some((c) => (c.args?.length ?? 0) > 0))).toBe(true);
  });

  it('has no call Tauri would reject', () => {
    const mismatches = perFile.flatMap((f) => checkInvokeCalls(commands, f.calls, f.file));
    expect(mismatches.map(formatMismatch).join('\n\n')).toBe('');
  });
});
