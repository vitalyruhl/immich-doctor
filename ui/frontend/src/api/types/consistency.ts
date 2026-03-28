import type { RuntimeCheckResult } from "./runtime";

export type MissingAssetReferenceStatus =
  | "present"
  | "missing_on_disk"
  | "permission_error"
  | "unreadable_path"
  | "unsupported"
  | "already_removed";

export type RepairReadinessStatus = "ready" | "blocked";

export type MissingAssetOperationStatus =
  | "planned"
  | "applied"
  | "skipped"
  | "failed"
  | "restored"
  | "deleted"
  | "already_removed";

export interface MissingAssetPreviewRequest {
  asset_ids: string[];
  select_all: boolean;
  limit?: number;
  offset?: number;
}

export interface MissingAssetApplyRequest {
  repair_run_id: string;
}

export interface MissingAssetRestoreRequest {
  restore_point_ids: string[];
  select_all: boolean;
}

export interface MissingAssetRestorePointDeleteRequest {
  restore_point_ids: string[];
  select_all: boolean;
}

export interface MissingAssetReferenceFinding {
  finding_id: string;
  asset_id: string;
  asset_type: string;
  status: MissingAssetReferenceStatus;
  logical_path: string;
  resolved_physical_path: string;
  owner_id: string | null;
  created_at: string | null;
  updated_at: string | null;
  scan_timestamp: string;
  repair_readiness: RepairReadinessStatus;
  repair_blockers: string[];
  message: string;
}

export interface MissingAssetScanResponse {
  domain: string;
  action: string;
  status: string;
  summary: string;
  generated_at: string;
  checks: RuntimeCheckResult[];
  findings: MissingAssetReferenceFinding[];
  metadata: Record<string, unknown>;
  recommendations: string[];
}

export interface MissingAssetPreviewResponse {
  domain: string;
  action: string;
  status: string;
  summary: string;
  generated_at: string;
  checks: RuntimeCheckResult[];
  selected_findings: MissingAssetReferenceFinding[];
  repair_run_id: string;
  metadata: Record<string, unknown>;
  recommendations: string[];
}

export interface MissingAssetOperationItem {
  asset_id: string;
  status: MissingAssetOperationStatus;
  restore_point_id: string | null;
  message: string;
  record_count: number;
  details: Record<string, unknown>;
}

export interface MissingAssetApplyResponse {
  domain: string;
  action: string;
  status: string;
  summary: string;
  generated_at: string;
  checks: RuntimeCheckResult[];
  repair_run_id: string;
  items: MissingAssetOperationItem[];
  metadata: Record<string, unknown>;
  recommendations: string[];
}

export interface MissingAssetRestorePointRecordSummary {
  table: string;
  row_count: number;
}

export interface MissingAssetRestorePoint {
  restore_point_id: string;
  repair_run_id: string;
  asset_id: string;
  created_at: string;
  status: "available" | "restored";
  record_count: number;
  logical_path: string;
  records: MissingAssetRestorePointRecordSummary[];
}

export interface MissingAssetRestorePointsResponse {
  domain: string;
  action: string;
  status: string;
  summary: string;
  generated_at: string;
  checks: RuntimeCheckResult[];
  items: MissingAssetRestorePoint[];
  metadata: Record<string, unknown>;
}

export interface MissingAssetRestoreResponse {
  domain: string;
  action: string;
  status: string;
  summary: string;
  generated_at: string;
  checks: RuntimeCheckResult[];
  repair_run_id: string;
  items: MissingAssetOperationItem[];
  metadata: Record<string, unknown>;
}

export interface MissingAssetRestorePointDeleteResponse {
  domain: string;
  action: string;
  status: string;
  summary: string;
  generated_at: string;
  checks: RuntimeCheckResult[];
  items: Array<{
    restore_point_id: string;
    status: "deleted";
  }>;
  metadata: Record<string, unknown>;
}
