import type { RuntimeCheckResult } from "./runtime";

export type CatalogSectionStatus = "pass" | "fail" | "warn" | "skip";
export type CatalogJobState =
  | "pending"
  | "running"
  | "pausing"
  | "paused"
  | "resuming"
  | "stopping"
  | "stopped"
  | "partial"
  | "completed"
  | "failed"
  | "unsupported"
  | "cancel_requested"
  | "canceled";

export interface CatalogValidationSection<T = Record<string, unknown>> {
  name: string;
  status: CatalogSectionStatus;
  rows: T[];
}

export interface CatalogValidationReport {
  domain: string;
  action: string;
  status: string;
  summary: string;
  generated_at: string;
  metadata: Record<string, unknown>;
  checks: RuntimeCheckResult[];
  sections: CatalogValidationSection[];
  metrics: Array<{
    name: string;
    value: number | string | boolean | null;
  }>;
  recommendations: string[];
}

export interface CatalogScanRequest {
  root?: string | null;
  resume_session_id?: string | null;
  max_files?: number | null;
}

export interface CatalogJobRequest {
  force: boolean;
}

export interface CatalogJobWorkerResizeRequest {
  workers: number;
}

export interface CatalogScanRuntimeDetails {
  scanState:
    | "idle"
    | "running"
    | "pausing"
    | "paused"
    | "resuming"
    | "stopping"
    | "stopped"
    | "completed"
    | "failed";
  configuredWorkerCount: number;
  activeWorkerCount: number;
  workerResize?: {
    supported: boolean;
    semantics: "next_run_only" | string;
    message?: string;
    requestedWorkerCount?: number;
    appliedImmediately?: boolean;
  };
}

export interface CatalogJobProgress {
  phase?: string | null;
  current?: number | null;
  total?: number | null;
  percent?: number | null;
  message?: string | null;
  rootSlug?: string | null;
  rootsCompleted?: string[];
  filesSeen?: number | null;
  filesIndexed?: number | null;
  bytesSeen?: number | null;
  directoriesDiscovered?: number | null;
  directoriesTotal?: number | null;
  directoriesCompleted?: number | null;
  pendingDirectories?: number | null;
  lastRelativePath?: string | null;
  dbMissingCount?: number | null;
  storageMissingCount?: number | null;
  orphanCount?: number | null;
  unmappedCount?: number | null;
  resumeSessionId?: string | null;
}

export interface CatalogWorkflowJobRecord {
  jobId: string | null;
  jobType: string;
  state: CatalogJobState;
  summary: string;
  createdAt: string;
  updatedAt: string;
  startedAt: string | null;
  completedAt: string | null;
  cancelRequested: boolean;
  error: string | null;
  result: Record<string, unknown> & {
    progress?: CatalogJobProgress;
    runtime?: CatalogScanRuntimeDetails;
    workerResize?: {
      supported: boolean;
      semantics: "next_run_only" | string;
      message?: string;
      requestedWorkerCount?: number;
      appliedImmediately?: boolean;
      configuredWorkerCount?: number;
    };
    report?: CatalogValidationReport;
    reports?: Array<{
      rootSlug: string;
      report: CatalogValidationReport;
    }>;
    blockedBy?: Record<string, unknown>;
    requiresScan?: boolean;
  };
}

export interface CatalogRootRow {
  id: number;
  slug: string;
  setting_name: string;
  root_type: string;
  absolute_path: string;
  enabled: number;
  created_at: string;
  updated_at: string;
}

export interface CatalogSnapshotRow {
  root_slug: string;
  root_type: string;
  snapshot_id: number | null;
  generation: number | null;
  status: string | null;
  started_at: string | null;
  committed_at: string | null;
  item_count: number | null;
  zero_byte_count: number | null;
}

export interface CatalogSessionRow {
  id: string;
  status: string;
  started_at: string;
  heartbeat_at: string;
  completed_at: string | null;
  max_files: number | null;
  files_seen: number;
  bytes_seen: number;
  directories_completed: number;
  error_count: number;
  last_relative_path: string | null;
  snapshot_id: number;
  root_slug: string;
  root_type: string;
  root_path: string;
}

export interface CatalogZeroByteRow {
  root_slug: string;
  relative_path: string;
  file_name: string;
  extension: string | null;
  size_bytes: number;
  modified_at_fs: string | null;
  snapshot_id: number;
  generation: number;
}
