// Search-pipeline settings (General settings tab). These are sidecar-wide:
// the values persist in the sidecar's data dir and apply to every caller
// (app search bar and MCP), with explicit per-request fields still winning.
// See docs/retrieval/2026-07-11-search-settings-design.md.

export interface SearchSettings {
  rerank: boolean;
  rerank_candidates: number;
  spell_correction: boolean;
  hybrid: boolean;
  variant_expansion: boolean;
}

export const RERANK_POOL_MIN = 10;
export const RERANK_POOL_MAX = 200;

export const DEFAULT_SEARCH_SETTINGS: SearchSettings = {
  rerank: true,
  rerank_candidates: 50,
  spell_correction: true,
  hybrid: false,
  variant_expansion: false,
};

// Preset pool sizes offered by the General tab. The API accepts any
// clamped 10-200 value (e.g. set directly over HTTP); the dropdown adds a
// "Custom (N)" entry for such values rather than silently rewriting them.
export const RERANK_POOL_PRESETS: ReadonlyArray<{ value: number; label: string }> = [
  { value: 10, label: 'Fastest' },
  { value: 25, label: 'Fast' },
  { value: 50, label: 'Balanced' },
  { value: 100, label: 'Thorough' },
  { value: 200, label: 'Exhaustive' },
];

export function clampPoolSize(value: number): number {
  if (!Number.isFinite(value)) return DEFAULT_SEARCH_SETTINGS.rerank_candidates;
  return Math.max(RERANK_POOL_MIN, Math.min(RERANK_POOL_MAX, Math.round(value)));
}

/** Coerce a sidecar response (or anything else) into a full SearchSettings.
 *  Missing or mistyped fields fall back to defaults so an older sidecar or a
 *  failed response can never wedge the settings pane. */
export function normalizeSearchSettings(raw: unknown): SearchSettings {
  const source = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>;
  const bool = (key: keyof SearchSettings): boolean =>
    typeof source[key] === 'boolean'
      ? (source[key] as boolean)
      : (DEFAULT_SEARCH_SETTINGS[key] as boolean);
  return {
    rerank: bool('rerank'),
    rerank_candidates:
      typeof source.rerank_candidates === 'number'
        ? clampPoolSize(source.rerank_candidates)
        : DEFAULT_SEARCH_SETTINGS.rerank_candidates,
    spell_correction: bool('spell_correction'),
    hybrid: bool('hybrid'),
    variant_expansion: bool('variant_expansion'),
  };
}
