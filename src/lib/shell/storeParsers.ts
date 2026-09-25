// Defensive parsers for tauri-plugin-store reads.
//
// `store.get<T>(key)` types the return as `T | null` but the actual value
// is whatever JSON happens to be in `settings.json`. If the file was
// hand-edited (or a downgrade wrote the old shape, or a third-party
// process corrupted it), the typed slot can hold a wildly wrong value
// — and downstream code that assumes the type would crash or behave
// strangely.
//
// Each parser returns the value when it matches the expected shape,
// `undefined` otherwise. Callers fall back to defaults instead of
// throwing or coercing. Easier to reason about than the existing
// `typeof x === 'boolean'` checks scattered across the call sites.

export function parseString(v: unknown): string | undefined {
  return typeof v === 'string' ? v : undefined;
}

export function parseBoolean(v: unknown): boolean | undefined {
  return typeof v === 'boolean' ? v : undefined;
}

export function parseStringArray(v: unknown): string[] | undefined {
  if (!Array.isArray(v)) return undefined;
  if (v.some((x) => typeof x !== 'string')) return undefined;
  return v as string[];
}

export function parseEnum<T extends string>(
  v: unknown,
  allowed: readonly T[],
): T | undefined {
  return typeof v === 'string' && (allowed as readonly string[]).includes(v)
    ? (v as T)
    : undefined;
}

export function parseRecord(
  v: unknown,
): Record<string, unknown> | undefined {
  return v !== null && typeof v === 'object' && !Array.isArray(v)
    ? (v as Record<string, unknown>)
    : undefined;
}
