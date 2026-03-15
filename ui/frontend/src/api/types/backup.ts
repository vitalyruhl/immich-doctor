export interface BackupSnapshotSummary {
  snapshotId: string;
  createdAt: string;
  kind: "pre_repair" | "post_repair" | "periodic" | "manual";
  coverage: "files_only" | "db_only" | "paired";
  repairRunId: string | null;
  verified: boolean;
  manifestPath: string;
  fileArtifactCount: number;
  hasDbArtifact: boolean;
  basicValidity: "valid" | "invalid";
  validityMessage: string;
}

export interface BackupSnapshotsResponse {
  generatedAt: string;
  items: BackupSnapshotSummary[];
  limitations: string[];
}

export interface BackupExecutionSummary {
  domain: string;
  action: string;
  status: "SUCCESS" | "WARN" | "FAIL";
  summary: string;
  warnings: string[];
  details: Record<string, unknown>;
}

export interface BackupExecutionResponse {
  generatedAt: string;
  requestedKind: "manual" | "pre_repair";
  result: BackupExecutionSummary;
  snapshot: BackupSnapshotSummary | null;
  limitations: string[];
}
