import type { RuntimeCheckResult } from "./runtime";

export type MissingAssetReferenceStatus =
  | "present"
  | "missing_on_disk"
  | "permission_error"
  | "unreadable_path"
  | "unsupported"
  | "already_removed";

export type RepairReadinessStatus = "ready" | "blocked";
export type MissingAssetRepairBlockerType =
  | "path"
  | "filesystem"
  | "scope"
  | "schema"
  | string;
export type MissingAssetBlockingSeverity = "warning" | "error" | string;

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
  repair_blocker_details: MissingAssetRepairBlocker[];
  message: string;
}

export interface MissingAssetRepairBlocker {
  blocker_code: string;
  blocker_type: MissingAssetRepairBlockerType;
  summary: string;
  details: Record<string, unknown>;
  affected_tables: string[];
  repair_covered_tables: string[];
  blocking_severity: MissingAssetBlockingSeverity;
  is_repairable: boolean;
}

export interface MissingAssetSupportedScopeMetadata {
  scanTables?: string[];
  scanPathField?: string;
  repairRestoreTables?: string[];
  repairCoveredDependencyTables?: string[];
  scanBlockers?: MissingAssetRepairBlocker[];
}

export interface MissingAssetScanResponse {
  domain: string;
  action: string;
  status: string;
  summary: string;
  generated_at: string;
  checks: RuntimeCheckResult[];
  findings: MissingAssetReferenceFinding[];
  metadata: Record<string, unknown> & {
    supportedScope?: MissingAssetSupportedScopeMetadata;
    blockingIssues?: string[];
  };
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

export type CatalogRemediationFindingKind =
  | "broken_db_original"
  | "zero_byte_file"
  | "fuse_hidden_orphan";
export type CatalogRemediationActionKind =
  | "broken_db_cleanup"
  | "broken_db_path_fix"
  | "zero_byte_delete"
  | "fuse_hidden_delete";
export type BrokenDbOriginalClassification =
  | "missing_confirmed"
  | "found_elsewhere"
  | "found_with_hash_match"
  | "unresolved_search_error";
export type ZeroByteClassification =
  | "zero_byte_upload_orphan"
  | "zero_byte_upload_critical"
  | "zero_byte_video_derivative"
  | "zero_byte_thumb_derivative"
  | "ignore_internal";
export type FuseHiddenOrphanClassification =
  | "blocked_in_use"
  | "deletable_orphan"
  | "check_failed";
export type CatalogRemediationOperationStatus =
  | "planned"
  | "applied"
  | "skipped"
  | "failed"
  | "already_removed";

export interface BrokenDbOriginalFinding {
  finding_id: string;
  kind: "broken_db_original";
  asset_id: string;
  asset_name: string | null;
  asset_type: string | null;
  expected_absolute_path: string | null;
  expected_database_path: string;
  expected_relative_path: string;
  classification: BrokenDbOriginalClassification;
  checksum_value: string | null;
  checksum_algorithm: string | null;
  checksum_match: boolean | null;
  eligible_actions: CatalogRemediationActionKind[];
  action_eligible: boolean;
  action_reason: string;
  found_root_slug: string | null;
  found_relative_path: string | null;
  found_absolute_path: string | null;
  found_size_bytes: number | null;
  expected_size_bytes: number | null;
  search_error: string | null;
  message: string;
}

export interface ZeroByteFinding {
  finding_id: string;
  kind: "zero_byte_file";
  root_slug: string;
  relative_path: string;
  absolute_path: string;
  file_name: string;
  size_bytes: number;
  classification: ZeroByteClassification;
  asset_id: string | null;
  asset_name: string | null;
  original_relative_path: string | null;
  eligible_actions: CatalogRemediationActionKind[];
  action_eligible: boolean;
  action_reason: string;
  message: string;
}

export interface FuseHiddenOrphanFinding {
  finding_id: string;
  kind: "fuse_hidden_orphan";
  root_slug: string;
  relative_path: string;
  absolute_path: string;
  file_name: string;
  size_bytes: number;
  classification: FuseHiddenOrphanClassification;
  eligible_actions: CatalogRemediationActionKind[];
  action_eligible: boolean;
  action_reason: string;
  in_use_check_tool: string | null;
  in_use_check_reason: string | null;
  message: string;
}

export interface CatalogRemediationScanResponse {
  domain: string;
  action: string;
  status: string;
  summary: string;
  generated_at: string;
  checks: RuntimeCheckResult[];
  broken_db_originals: BrokenDbOriginalFinding[];
  zero_byte_findings: ZeroByteFinding[];
  fuse_hidden_orphans: FuseHiddenOrphanFinding[];
  metadata: Record<string, unknown>;
  recommendations: string[];
}

export interface CatalogRemediationPreviewRequest {
  asset_ids?: string[];
  finding_ids?: string[];
  select_all: boolean;
}

export interface CatalogRemediationPreviewResponse {
  domain: string;
  action: string;
  status: string;
  summary: string;
  generated_at: string;
  checks: RuntimeCheckResult[];
  finding_kind: CatalogRemediationFindingKind;
  action_kind: CatalogRemediationActionKind;
  repair_run_id: string;
  selected_items: Array<Record<string, unknown>>;
  metadata: Record<string, unknown>;
  recommendations: string[];
}

export interface CatalogRemediationApplyResponse {
  domain: string;
  action: string;
  status: string;
  summary: string;
  generated_at: string;
  checks: RuntimeCheckResult[];
  finding_kind: CatalogRemediationFindingKind;
  action_kind: CatalogRemediationActionKind;
  repair_run_id: string;
  items: Array<{
    finding_id: string;
    kind: CatalogRemediationFindingKind;
    action_kind: CatalogRemediationActionKind;
    target_id: string;
    status: CatalogRemediationOperationStatus;
    message: string;
    details: Record<string, unknown>;
  }>;
  metadata: Record<string, unknown>;
  recommendations: string[];
}
