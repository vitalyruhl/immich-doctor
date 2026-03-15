import { request } from "./client";
import type { ApiResponse } from "./types/common";
import type { BackupExecutionResponse, BackupSnapshotsResponse } from "./types/backup";

export async function fetchBackupSnapshots(): Promise<ApiResponse<BackupSnapshotsResponse>> {
  return request<BackupSnapshotsResponse>("/backup/snapshots");
}

export async function runBackupFiles(
  kind: "manual" | "pre_repair",
): Promise<ApiResponse<BackupExecutionResponse>> {
  return request<BackupExecutionResponse>("/backup/files", {
    method: "POST",
    body: JSON.stringify({ kind }),
  });
}
