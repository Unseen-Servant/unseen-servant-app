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
}

export interface FileErrorEntry {
  path: string;
  error: string;
}

export interface IndexStatusSummary {
  add: number;
  remove: number;
  update: number;
  up_to_date: number;
  errors: number;
}

export interface IndexStatusResult {
  to_add: FileStatusEntry[];
  to_remove: FileStatusEntry[];
  to_update: FileStatusEntry[];
  up_to_date: FileStatusEntry[];
  errors: FileErrorEntry[];
  summary: IndexStatusSummary;
}

export interface SyncResult {
  added: number;
  removed: number;
  updated: number;
  errors: string[];
  total_indexed: number;
}