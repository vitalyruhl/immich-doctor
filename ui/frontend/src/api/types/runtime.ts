export type FileIntegrityStatus =
  | "FILE_OK"
  | "FILE_MISSING"
  | "FILE_EMPTY"
  | "FILE_PERMISSION_DENIED"
  | "FILE_TRUNCATED"
  | "FILE_CONTAINER_BROKEN"
  | "FILE_CORRUPTED"
  | "FILE_TYPE_MISMATCH"
  | "FILE_UNKNOWN_PROBLEM";

export type MetadataFailureCause =
  | "CAUSED_BY_MISSING_FILE"
  | "CAUSED_BY_EMPTY_FILE"
  | "CAUSED_BY_CORRUPTED_FILE"
  | "CAUSED_BY_PERMISSION_ERROR"
  | "CAUSED_BY_PATH_MISMATCH"
  | "CAUSED_BY_UNSUPPORTED_FORMAT"
  | "CAUSED_BY_RUNTIME_TOOLING_ERROR"
  | "IMMICH_BUG_SUSPECTED"
  | "UNKNOWN";

export type SuggestedAction =
  | "report_only"
  | "retry_jobs"
  | "requeue"
  | "fix_permissions"
  | "quarantine_corrupt"
  | "mark_unrecoverable"
  | "inspect_runtime_tooling"
  | "dangerous_unknown";

export interface RuntimeCheckResult {
  name: string;
  status: "pass" | "fail" | "warn" | "skip";
  message: string;
  details: Record<string, unknown>;
}

export interface FileIntegritySummaryItem {
  status: FileIntegrityStatus;
  count: number;
}

export interface FileIntegrityFinding {
  finding_id: string;
  asset_id: string;
  file_role: string;
  media_kind: string;
  path: string;
  status: FileIntegrityStatus;
  asset_file_id: string | null;
  message: string;
  size_bytes: number | null;
  detected_format: string | null;
  extension: string | null;
  details: Record<string, unknown>;
}

export interface RuntimeIntegrityInspectResponse {
  domain: string;
  action: string;
  status: string;
  summary: string;
  generated_at: string;
  metadata: Record<string, unknown>;
  checks: RuntimeCheckResult[];
  findings: FileIntegrityFinding[];
  summary_items: FileIntegritySummaryItem[];
  recommendations: string[];
}

export interface MetadataFailureSummaryItem {
  root_cause: MetadataFailureCause;
  count: number;
}

export interface MetadataFailureDiagnostic {
  diagnostic_id: string;
  asset_id: string;
  job_name: string;
  root_cause: MetadataFailureCause;
  failure_level: "primary" | "secondary";
  suggested_action: SuggestedAction;
  confidence: "high" | "medium" | "low";
  source_path: string;
  source_file_status: FileIntegrityStatus;
  source_message: string;
  available_actions: SuggestedAction[];
  file_findings: FileIntegrityFinding[];
  details: Record<string, unknown>;
}

export interface RuntimeMetadataFailuresInspectResponse {
  domain: string;
  action: string;
  status: string;
  summary: string;
  generated_at: string;
  metadata: Record<string, unknown>;
  checks: RuntimeCheckResult[];
  integrity_summary: FileIntegritySummaryItem[];
  metadata_summary: MetadataFailureSummaryItem[];
  diagnostics: MetadataFailureDiagnostic[];
  recommendations: string[];
}

export interface MetadataRepairAction {
  action: SuggestedAction;
  diagnostic_id: string;
  status: "detected" | "planned" | "repaired" | "skipped" | "failed";
  reason: string;
  path: string;
  supports_apply: boolean;
  dry_run: boolean;
  applied: boolean;
  details: Record<string, unknown>;
}

export interface RuntimeMetadataFailuresRepairResponse {
  domain: string;
  action: string;
  status: string;
  summary: string;
  generated_at: string;
  metadata: Record<string, unknown>;
  checks: RuntimeCheckResult[];
  diagnostics: MetadataFailureDiagnostic[];
  repair_actions: MetadataRepairAction[];
  post_validation: RuntimeMetadataFailuresInspectResponse | null;
  recommendations: string[];
}

export interface RuntimeRepairPrecondition {
  id: string;
  label: string;
  status: "ok" | "warning" | "error" | "unknown";
  blocking: boolean;
  summary: string;
  details: Record<string, unknown>;
}

export interface RuntimeRepairReadinessResponse {
  generatedAt: string;
  action: "fix_permissions";
  applyAllowed: boolean;
  blockingReasons: string[];
  preconditions: RuntimeRepairPrecondition[];
  snapshotPlan: {
    kind: "pre_repair";
    coverage: "files_only";
    willCreate: boolean;
    note: string;
  };
  undoVisibility: {
    journalUndoAvailable: boolean;
    automatedUndo: boolean;
    note: string;
  };
  restoreImplemented: boolean;
  limitations: string[];
}
