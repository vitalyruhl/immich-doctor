export type BackupJobState =
  | "pending"
  | "running"
  | "partial"
  | "completed"
  | "failed"
  | "unsupported"
  | "cancel_requested"
  | "canceled";
export type BackupSizeEstimateStatus =
  | "unknown"
  | "stale"
  | "queued"
  | "running"
  | "partial"
  | "completed"
  | "failed"
  | "unsupported"
  | "canceled";

export type BackupTargetType = "local" | "smb" | "ssh" | "rsync";
export type BackupSnapshotCoverage = "files_only" | "db_only" | "paired";
export type BackupRequestedKind = "manual" | "pre_repair";
export type BackupTargetVerificationStatus =
  | "unknown"
  | "ready"
  | "warning"
  | "failed"
  | "running"
  | "unsupported";
export type BackupRestoreReadiness = "not_implemented" | "partial";
export type BackupVerificationLevel =
  | "none"
  | "transport_success_only"
  | "destination_exists"
  | "basic_manifest_verified"
  | "copied_files_sha256";
export type BackupSnapshotBasicValidity = "valid" | "invalid";
export type BackupAssetComparisonStatus =
  | "pending"
  | "identical"
  | "missing_in_backup"
  | "mismatch"
  | "conflict"
  | "restore_candidate"
  | "restored"
  | "skipped"
  | "failed";

export interface BackupSnapshotSummary {
  snapshotId: string;
  createdAt: string;
  kind: "pre_repair" | "post_repair" | "periodic" | "manual";
  coverage: BackupSnapshotCoverage;
  repairRunId: string | null;
  manifestPath: string;
  fileArtifactCount: number;
  hasDbArtifact: boolean;
  basicValidity: BackupSnapshotBasicValidity;
  validityMessage: string;
}

export interface BackupSnapshotsResponse {
  generatedAt: string;
  items: BackupSnapshotSummary[];
  limitations: string[];
}

export interface BackupSizeCategory {
  name: string;
  label: string;
  path: string | null;
  bytes: number | null;
  fileCount: number | null;
}

export interface BackupSizeScopeEstimate {
  scope: "database" | "storage";
  label: string;
  state: BackupJobState;
  sourceScope: string;
  representation: string;
  bytes: number | null;
  fileCount: number | null;
  collectedAt?: string | null;
  durationSeconds?: number | null;
  stale: boolean;
  categories: BackupSizeCategory[];
  warnings: string[];
  metadata: Record<string, unknown>;
  error?: string | null;
}

export interface BackupSizeEstimateResponse {
  generatedAt: string;
  jobId: string | null;
  state: BackupJobState;
  status: BackupSizeEstimateStatus;
  summary: string;
  sourceScope: string;
  collectedAt?: string | null;
  durationSeconds?: number | null;
  cacheAgeSeconds?: number | null;
  stale: boolean;
  staleReason?: string | null;
  scopes: BackupSizeScopeEstimate[];
  progress?: {
    scope?: string | null;
    message: string;
    current?: number | null;
    total?: number | null;
    unit?: string | null;
    currentPath?: string | null;
  } | null;
  warnings: string[];
  limitations: string[];
}

export interface SecretReferenceSummary {
  secretId: string;
  kind: string;
  label: string;
  createdAt: string;
}

export interface BackupTargetTransportSettings {
  path?: string | null;
  host?: string | null;
  port?: number | null;
  share?: string | null;
  remotePath?: string | null;
  username?: string | null;
  authMode?: "agent" | "password" | "private_key" | null;
  mountStrategy?: "system_mount" | "pre_mounted_path" | null;
  mountedPath?: string | null;
  knownHostMode?: "strict" | "accept_new" | "disabled" | null;
  knownHostReference?: string | null;
  domain?: string | null;
  mountOptions?: string | null;
  passwordSecretRef?: SecretReferenceSummary | null;
  privateKeySecretRef?: SecretReferenceSummary | null;
}

export interface BackupTargetConfig {
  targetId: string;
  targetName: string;
  targetType: BackupTargetType;
  enabled: boolean;
  transport: BackupTargetTransportSettings;
  verificationStatus: BackupTargetVerificationStatus;
  lastTestResult?: {
    checkedAt: string;
    status: BackupTargetVerificationStatus;
    summary: string;
    warnings: string[];
    details: Record<string, unknown>;
  } | null;
  lastSuccessfulBackup?: {
    backupId: string;
    completedAt: string;
    sourceScope: string;
    bytesTransferred?: number | null;
    verificationLevel: BackupVerificationLevel;
    snapshotId?: string | null;
  } | null;
  retentionPolicy: {
    mode: string;
    maxVersions?: number | null;
    pruneAutomatically: boolean;
  };
  restoreReadiness: BackupRestoreReadiness;
  sourceScope: string;
  schedulingCompatible: boolean;
  warnings: string[];
  createdAt: string;
  updatedAt: string;
}

export interface BackupTargetsOverviewResponse {
  generatedAt: string;
  configPath: string;
  configRoot: string;
  items: BackupTargetConfig[];
  limitations: string[];
}

export interface BackupTargetMutationResponse {
  applied: boolean;
  summary: string;
  item?: BackupTargetConfig;
  targetId?: string;
}

export interface BackupTargetValidationResponse {
  generatedAt: string;
  jobId: string | null;
  targetId: string;
  targetType?: BackupTargetType;
  state: BackupJobState;
  summary: string;
  checks: Array<{ name: string; status: string; message: string; details?: Record<string, unknown> }>;
  warnings: string[];
}

export interface BackupExecutionStatusResponse {
  generatedAt: string;
  jobId: string | null;
  targetId?: string;
  targetType?: BackupTargetType;
  requestedKind?: BackupRequestedKind;
  coverage?: BackupSnapshotCoverage;
  restoreReadiness?: BackupRestoreReadiness;
  state: BackupJobState;
  summary: string;
  report?: {
    sourceScope?: string;
    targetType?: BackupTargetType;
    bytesPlanned?: number | null;
    bytesTransferred?: number | null;
    fileCounts?: { planned?: number | null; transferred?: number | null } | null;
    durationSeconds?: number | null;
    warnings?: string[];
    verificationLevel?: BackupVerificationLevel;
    versionId?: string;
    snapshotId?: string;
    validationChecks?: Array<{ name: string; status: string; message: string }>;
    details?: Record<string, unknown>;
  } | null;
  snapshot: BackupSnapshotSummary | null;
  warnings: string[];
}

export interface BackupTargetDraft {
  targetName: string;
  targetType: BackupTargetType;
  enabled: boolean;
  path?: string;
  connectionString?: string;
  host?: string;
  port?: number;
  share?: string;
  remotePath?: string;
  username?: string;
  authMode?: "agent" | "password" | "private_key";
  mountStrategy?: "system_mount" | "pre_mounted_path";
  mountedPath?: string;
  knownHostMode?: "strict" | "accept_new" | "disabled";
  knownHostReference?: string;
  domain?: string;
  mountOptions?: string;
  passwordSecret?: { label?: string; material?: string; secretId?: string };
  privateKeySecret?: { label?: string; material?: string; secretId?: string };
  retentionPolicy?: { mode: string; maxVersions?: number | null; pruneAutomatically: boolean };
}

export interface BackupAssetSide {
  exists: boolean;
  relativePath: string;
  absolutePath: string | null;
  size: number | null;
  modifiedAt: string | null;
  mimeType: string | null;
  previewKind: "image" | "video" | null;
}

export interface BackupAssetComparisonItem {
  assetId: string;
  status: BackupAssetComparisonStatus;
  syncEligible: boolean;
  restoreEligible: boolean;
  source: BackupAssetSide;
  backup: BackupAssetSide;
  comparison: {
    method: string;
    decision: string;
    sourceHash?: string | null;
    backupHash?: string | null;
    details: Record<string, unknown>;
  };
}

export interface BackupFolderComparisonItem {
  folder: string;
  sourceFileCount: number;
  backupFileCount: number;
  sourceTotalBytes: number;
  backupTotalBytes: number;
  fileDelta: number;
  sizeDeltaBytes: number;
  suspicious: boolean;
  reasons: string[];
}

export interface BackupAssetWorkflowOverviewResponse {
  generatedAt: string;
  targetId: string;
  targetType: BackupTargetType;
  supported: boolean;
  sourceRoot: string | null;
  backupRoot: string | null;
  summary: string;
  warnings: string[];
  limitations: string[];
  comparison: {
    totalItems: number;
    statusCounts: Record<string, number>;
    displayedItems: number;
    truncated: boolean;
    items: BackupAssetComparisonItem[];
  };
  folders: {
    suspiciousCount: number;
    items: BackupFolderComparisonItem[];
  };
}

export interface BackupTestCopyResponse {
  generatedAt: string;
  targetId: string;
  supported: boolean;
  summary: string;
  warnings: string[];
  result: {
    assetId: string | null;
    sourcePath: string | null;
    targetPath: string | null;
    copied: boolean;
    verified: boolean;
    verificationMethod: string;
    error: string | null;
    details: Record<string, unknown>;
  } | null;
}

export interface BackupRestoreActionResponse {
  generatedAt: string;
  targetId: string;
  apply: boolean;
  supported: boolean;
  summary: string;
  warnings: string[];
  results: Array<{
    assetId: string;
    sourcePath: string;
    backupPath: string;
    actionAttempted: string;
    actionOutcome: string;
    resultStatus: BackupAssetComparisonStatus;
    reason: string;
    quarantinePath: string | null;
    details: Record<string, unknown>;
  }>;
}
