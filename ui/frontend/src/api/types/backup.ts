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
