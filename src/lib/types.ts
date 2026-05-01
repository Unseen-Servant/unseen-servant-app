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
}

export interface GameSystemsResult {
  game_systems: string[];
  count: number;
}

export interface SetGameSystemResult {
  filename: string;
  game_system: string;
  chunks_updated: number;
}

export interface KnownGameSystem {
  tag: string;
  keywords?: string[];
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
  active_context: string | null;
}

export interface ActiveContextResult {
  active_context: string | null;
}

export interface OrphanFile {
  path: string;
  filename: string;
  game_system: string;
  size_bytes: number;
}

export interface AnchorFile {
  path: string;
  filename: string;
  count: number;
  collections: string[];
}

export interface OverlapPair {
  a: string;
  b: string;
  count: number;
}

export interface StaleCollection {
  name: string;
  last_used_at: string | null;
  file_count: number;
}

export interface LibraryHealthResult {
  orphans: OrphanFile[];
  anchors: AnchorFile[];
  overlap: OverlapPair[];
  stale: StaleCollection[];
}

export interface StatsResult {
  total_chunks: number;
  total_documents: number;
  collection_name: string;
  storage_bytes: number;
  reclaimable_bytes: number;
}

export interface CollectionMutationResult {
  name: string;
  file_count: number;
}

export interface SearchResultItem {
  text: string;
  filename: string;
  source: string;
  section_heading: string;
  page_start: number;
  page_end: number;
  game_system: string;
  relevance: number;
}

export interface SearchResponse {
  results: SearchResultItem[];
  message?: string;
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
  disk: number;
  add: number;
  remove: number;
  update: number;
  errors: number;
}

export type SyncAction =
  | { kind: 'noop' }
  | { kind: 'silent' }
  | { kind: 'prompt'; counts: PromptCounts };