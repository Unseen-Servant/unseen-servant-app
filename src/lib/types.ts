export interface FileItem {
  name: string;
  path: string;
  is_dir: boolean;
  children: FileItem[] | null;
}