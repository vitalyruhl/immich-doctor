export type BackupJobState =
  | "pending"
  | "running"
  | "partial"
  | "completed"
  | "failed"
  | "unsupported"
  | "cancel_requested"
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
  | "basic_manifest_verified";
export type BackupSnapshotBasicValidity = "valid" | "invalid";

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
  summary: string;
  sourceScope: string;
  collectedAt?: string | null;
  durationSeconds?: number | null;
  cacheAgeSeconds?: number | null;
  stale: boolean;
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
  maskedValue: string;
  createdAt: string;
}

export interface BackupTargetTransportSettings {
  path?: string | null;
  host?: string | null;
  port?: number | null;
  share?: string | null;
  remotePath?: string | null;
  username?: string | null;
  authMode?: "password" | "private_key" | null;
  mountStrategy?: "system_mount" | "pre_mounted_path" | null;
  mountedPath?: string | null;
  hostKeyVerification?: "known_hosts" | "pinned_fingerprint" | "insecure_accept_any" | null;
  hostKeyReference?: string | null;
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
  host?: string;
  port?: number;
  share?: string;
  remotePath?: string;
  username?: string;
  authMode?: "password" | "private_key";
  mountStrategy?: "system_mount" | "pre_mounted_path";
  mountedPath?: string;
  hostKeyVerification?: "known_hosts" | "pinned_fingerprint" | "insecure_accept_any";
  hostKeyReference?: string;
  passwordSecret?: { label?: string; material?: string };
  privateKeySecret?: { label?: string; material?: string };
  retentionPolicy?: { mode: string; maxVersions?: number | null; pruneAutomatically: boolean };
}
