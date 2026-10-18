export interface FileItem {
  name: string;
  path: string;
  is_dir: boolean;
  children: FileItem[] | null;
}

export interface FileStatusEntry {
  path: string;
  filename: string;
  chunk_count?: number;
  game_system?: string;
  game_systems?: string[];
  indexed_at?: string;
}

export interface GameSystemsResult {
  game_systems: string[];
  count: number;
}

export interface KnownGameSystem {
  tag: string;
  keywords?: string[];
  color?: string | null;
  is_builtin?: boolean;
  is_customized?: boolean;
}

export interface KnownGameSystemsResult {
  systems: KnownGameSystem[];
}

export interface FileErrorEntry {
  path: string;
  error: string;
}

export interface IndexStatusSummary {
  add: number;
  remove: number;
  auto_remove: number;
  rename: number;
  update: number;
  up_to_date: number;
  errors: number;
  stale: number;
  outdated: number;
}

export interface RenameEntry {
  old_path: string;
  new_path: string;
  filename: string;
}

export interface IndexStatusResult {
  to_add: FileStatusEntry[];
  to_remove: FileStatusEntry[];
  to_auto_remove: FileStatusEntry[];
  to_rename: RenameEntry[];
  to_update: FileStatusEntry[];
  up_to_date: FileStatusEntry[];
  errors: FileErrorEntry[];
  stale_paths: string[];
  outdated: string[];
  summary: IndexStatusSummary;
}

export interface RenameMapping {
  old_path: string;
  new_path: string;
}

export interface SyncResult {
  added: number;
  removed: number;
  auto_removed: number;
  renamed: number;
  updated: number;
  errors: string[];
  total_indexed: number;
  chunks_total: number;
  renames: RenameMapping[];
  auto_removed_paths: string[];
  stale_paths: string[];
  // Books whose text couldn't be extracted (a scanned PDF); the panel
  // unticks them.
  unindexable_paths: string[];
}

export interface CollectionInfo {
  id: string;
  name: string;
  file_paths: string[];
  file_count: number;
  created_at: string;
  updated_at: string;
  last_used_at: string | null;
  description: string;
  color: string | null;
  archived: boolean;
}

export interface CollectionsResult {
  collections: Record<string, CollectionInfo>;
  count: number;
}

export interface StatsResult {
  total_chunks: number;
  total_documents: number;
  storage_bytes: number;
}

export interface CollectionMutationResult {
  name: string;
  file_count: number;
}

/** A cross-edition twin folded into another result (roadmap 2.3) — the
 * same section printed in a different book. */
export interface AlsoIn {
  filename: string;
  source: string;
  page_start: number;
  page_end: number;
  page_label_start: string;
  page_label_end: string;
  section_id: string;
}

export interface SearchResultItem {
  /** The whole assembled section the hit sits in (roadmap 2.5). */
  text: string;
  filename: string;
  source: string;
  section_heading: string;
  page_start: number;
  page_end: number;
  game_system: string;
  relevance: number;
  /** Ordinal relevance tier computed server-side on the result's own
   * score scale; absent only for responses from an older sidecar. */
  tier?: 'strong' | 'good' | 'weak';
  reranked?: boolean;
  // Required, not optional: every search response reaches the frontend
  // through the Rust `search_index` command, whose struct defaults these
  // and always serialises them — blank string, false, or [] — even when
  // an older sidecar omits them.
  /** The embed unit that actually matched, inside `text`. */
  matched_text: string;
  /** The chunk the unit belongs to — a middle ground between the two. */
  chunk_text: string;
  section_id: string;
  section_path: string;
  /** Page numbers printed on the paper. Blank means "cite the physical
   * span" — a label would mislabel a wider returned section. */
  page_label_start: string;
  page_label_end: string;
  /** True when a context budget cut this result back to its matched unit. */
  truncated: boolean;
  also_in: AlsoIn[];
}

export interface SearchResponse {
  results: SearchResultItem[];
  message?: string;
  /** The backend ran out of distinct sections before filling n_results —
   * the only honest end-of-list signal. A short result list is not one:
   * section dedupe, near-dup collapse and context packing all shorten it
   * while more sections remain for a larger request. Always present (the
   * Rust command defaults it to false). */
  exhausted: boolean;
}

export type BucketPolicy = 'silent' | 'ask';

// 0 = never check in the background. Other values are seconds.
export type BackgroundCheckInterval = 0 | 15 | 30 | 60 | 300;

export const BACKGROUND_CHECK_OPTIONS: { value: BackgroundCheckInterval; label: string }[] = [
  { value: 15, label: 'Every 15 seconds' },
  { value: 30, label: 'Every 30 seconds' },
  { value: 60, label: 'Every minute' },
  { value: 300, label: 'Every 5 minutes' },
  { value: 0, label: 'Never' },
];

export interface SyncPreferences {
  backgroundCheckInterval: BackgroundCheckInterval;
  diskEventsPolicy: BucketPolicy;
  selectionPolicy: BucketPolicy;
  deselectionPolicy: BucketPolicy;
  modificationPolicy: BucketPolicy;
}

export const DEFAULT_SYNC_PREFERENCES: SyncPreferences = {
  backgroundCheckInterval: 60,
  diskEventsPolicy: 'silent',
  selectionPolicy: 'ask',
  deselectionPolicy: 'ask',
  modificationPolicy: 'ask',
};

export interface PromptCounts {
  // Disk events, split by what the user sees: an indexed book found under a
  // new path, and a selected book no longer on disk (indexed or not).
  moved: number;
  missing: number;
  add: number;
  remove: number;
  update: number;
  errors: number;
}

export type SyncAction =
  | { kind: 'noop' }
  | { kind: 'silent' }
  | { kind: 'prompt'; counts: PromptCounts };