import { request } from "./client";
import type { ApiResponse } from "./types/common";
import type { BackupSnapshotsResponse } from "./types/backup";

export async function fetchBackupSnapshots(): Promise<ApiResponse<BackupSnapshotsResponse>> {
  return request<BackupSnapshotsResponse>("/backup/snapshots");
}
