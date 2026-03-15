export interface RepairRunSummary {
  repairRunId: string;
  startedAt: string;
  endedAt: string | null;
  scope: Record<string, unknown>;
  status: "planned" | "running" | "completed" | "partial" | "failed";
  preRepairSnapshotId: string | null;
  postRepairSnapshotId: string | null;
  hasJournalEntries: boolean;
  journalEntryCount: number;
  undoAvailable: boolean;
}

export interface RepairJournalEntry {
  entryId: string;
  createdAt: string;
  operationType: string;
  status: "planned" | "applied" | "skipped" | "failed";
  assetId: string | null;
  table: string | null;
  originalPath: string | null;
  quarantinePath: string | null;
  undoType: string;
  undoPayload: Record<string, unknown>;
  errorDetails: Record<string, unknown> | null;
}

export interface RepairRunDetail {
  repairRunId: string;
  startedAt: string;
  endedAt: string | null;
  scope: Record<string, unknown>;
  status: "planned" | "running" | "completed" | "partial" | "failed";
  liveStateFingerprint: string;
  planTokenId: string;
  preRepairSnapshotId: string | null;
  postRepairSnapshotId: string | null;
  journalEntryCount: number;
  undoAvailable: boolean;
  journalAvailable: boolean;
}

export interface RepairRunsResponse {
  generatedAt: string;
  items: RepairRunSummary[];
}

export interface RepairRunDetailResponse {
  generatedAt: string;
  repairRun: RepairRunDetail;
  journalEntries: RepairJournalEntry[];
  limitations: string[];
}

export interface QuarantineSummaryResponse {
  generatedAt: string;
  path: string;
  foundationState: "ok" | "warning" | "error" | "unknown";
  pathSummary: string;
  indexPresent: boolean;
  itemCount: number;
  workflowImplemented: boolean;
  message: string;
}
