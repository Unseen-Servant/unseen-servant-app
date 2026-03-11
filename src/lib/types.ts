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
  game_system: string;
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
  name: string;
  file_paths: string[];
  file_count: number;
  created_at: string;
  description: string;
}

export interface CollectionsResult {
  collections: Record<string, CollectionInfo>;
  count: number;
}

export interface StatsResult {
  total_chunks: number;
  total_documents: number;
  collection_name: string;
  storage_bytes: number;
}

export interface CollectionMutationResult {
  name: string;
  file_count: number;
}