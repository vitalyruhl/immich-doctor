export interface StorageCheckResult {
  name: string;
  status: string;
  message: string;
  details?: Record<string, unknown>;
}

export interface EmptyDirectoryFinding {
  root_slug: string;
  relative_path: string;
  absolute_path: string;
  depth: number;
  size_bytes: number | null;
  last_modified_at: string | null;
  child_count_before: number;
  is_orphan_parent: boolean;
}

export interface EmptyFolderScanReport {
  domain: string;
  action: string;
  status: string;
  summary: string;
  generated_at: string;
  metadata: Record<string, unknown>;
  checks: StorageCheckResult[];
  total_empty_dirs: number;
  total_orphan_parents: number;
  reclaimed_space_bytes: number;
  roots_scanned: number;
  root_slugs_scanned: string[];
  roots_with_errors: Record<string, string>;
  findings: EmptyDirectoryFinding[];
  orphan_parents: EmptyDirectoryFinding[];
  symlink_directories: Array<Record<string, string>>;
  entry_errors: Array<Record<string, string>>;
}

export interface EmptyFolderScanStatus {
  status: string;
  progress: number;
  eta_seconds: number | null;
  rootSlug?: string;
  relativePath?: string;
  directoriesScanned?: number;
  emptyDirectoriesFound?: number;
  message?: string;
}

export interface EmptyDirQuarantineItem {
  quarantine_item_id: string;
  session_id: string;
  root_slug: string;
  relative_path: string;
  original_path: string;
  quarantine_path: string;
  reason: string;
  size_bytes: number | null;
  last_modified_at: string | null;
  mode: number | null;
  state: string;
  created_at: string;
  state_changed_at: string | null;
  deleted_at: string | null;
}

export interface EmptyFolderQuarantineListResponse {
  session_id: string | null;
  count: number;
  items: EmptyDirQuarantineItem[];
}

export interface EmptyFolderQuarantineActionResponse {
  summary: string;
  dry_run: boolean;
  session_id?: string | null;
  quarantined_count?: number;
  restored_count?: number;
  deleted_count?: number;
  items?: EmptyDirQuarantineItem[];
  restored?: EmptyDirQuarantineItem[];
  deleted?: EmptyDirQuarantineItem[];
  failed: Array<Record<string, string>>;
}
