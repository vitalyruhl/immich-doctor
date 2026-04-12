import type { RuntimeCheckResult } from "./runtime";

export type CatalogRemediationFindingKind =
  | "broken_db_original"
  | "zero_byte_file"
  | "fuse_hidden_orphan";
export type CatalogRemediationGroupKey = "broken-db" | "zero-byte" | "fuse-hidden";
export type CatalogRemediationRowActionId =
  | "ignore"
  | "quarantine"
  | "delete"
  | "mark_removed"
  | "repair_path";
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

export interface BrokenDbOriginalFinding {
  finding_id: string;
  kind: "broken_db_original";
  asset_id: string;
  asset_name: string | null;
  asset_type: string | null;
  owner_id: string | null;
  owner_label: string | null;
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
  owner_id: string | null;
  owner_label: string | null;
  db_reference_kind: string | null;
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
  owner_id: string | null;
  owner_label: string | null;
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

export interface CatalogRemediationOverviewGroup {
  key: CatalogRemediationGroupKey;
  title: string;
  description: string;
  count: number;
}

export interface CatalogRemediationOverviewResponse {
  summary: string;
  generated_at: string | null;
  metadata: Record<string, unknown>;
  recommendations: string[];
  groups: CatalogRemediationOverviewGroup[];
}

export interface CatalogRemediationListItem {
  finding_id: string;
  group_key: CatalogRemediationGroupKey;
  title: string;
  subtitle: string;
  owner_label: string | null;
  owner_hint: string | null;
  classification: string;
  message: string;
  summary_path: string | null;
  summary_context: string | null;
  status_reason: string;
  blocked_reason: string | null;
  actions: CatalogRemediationRowActionId[];
  payload: CatalogRemediationStateItemPayload;
}

export interface CatalogRemediationGroupPageResponse {
  group_key: CatalogRemediationGroupKey;
  title: string;
  description: string;
  generated_at: string | null;
  offset: number;
  limit: number | null;
  total: number;
  items: CatalogRemediationListItem[];
}

export interface CatalogRemediationFindingDetailLine {
  label: string;
  value: string;
}

export interface CatalogRemediationFindingDetailResponse {
  group_key: CatalogRemediationGroupKey;
  finding_id: string;
  title: string;
  message: string;
  details: CatalogRemediationFindingDetailLine[];
}

export interface CatalogRemediationStateItemPayload {
  finding_id: string;
  category_key: string;
  title: string;
  source_path?: string | null;
  asset_id?: string | null;
  owner_id?: string | null;
  owner_label?: string | null;
  root_slug?: string | null;
  relative_path?: string | null;
  original_relative_path?: string | null;
  db_reference_kind?: string | null;
  size_bytes?: number | null;
  reason?: string | null;
}

export interface IgnoredFindingItem {
  ignored_item_id: string;
  finding_id: string;
  category_key: string;
  title: string;
  owner_id: string | null;
  owner_label: string | null;
  source_path: string | null;
  original_relative_path: string | null;
  reason: string;
  details: Record<string, unknown>;
  created_at: string;
  released_at: string | null;
  state: string;
}

export interface CatalogIgnoredFindingsResponse {
  generated_at: string;
  summary: string;
  items: IgnoredFindingItem[];
}

export interface QuarantineItemView {
  quarantine_item_id: string;
  repair_run_id: string;
  asset_id: string | null;
  source_path: string;
  quarantine_path: string;
  reason: string;
  checksum: string | null;
  size_bytes: number | null;
  restorable: boolean;
  owner_id: string | null;
  owner_label: string | null;
  category_key: string | null;
  finding_id: string | null;
  source_kind: string | null;
  root_slug: string | null;
  relative_path: string | null;
  original_relative_path: string | null;
  db_reference_kind: string | null;
  state: string;
  state_changed_at: string | null;
  deleted_at: string | null;
  created_at: string;
}

export interface CatalogQuarantineResponse {
  generated_at: string;
  summary: string;
  items: QuarantineItemView[];
}

export interface CatalogRemediationActionResponse {
  generated_at: string;
  summary: string;
  items: Array<Record<string, unknown>>;
}
