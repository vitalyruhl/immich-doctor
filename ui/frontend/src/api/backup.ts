import { request } from "./client";
import type { ApiResponse } from "./types/common";
import type {
  BackupAssetWorkflowOverviewResponse,
  BackupExecutionStatusResponse,
  BackupRestoreActionResponse,
  BackupSizeEstimateResponse,
  BackupSnapshotsResponse,
  BackupTestCopyResponse,
  BackupTargetDraft,
  BackupTargetMutationResponse,
  BackupTargetValidationResponse,
  BackupTargetsOverviewResponse,
} from "./types/backup";

export async function fetchBackupSnapshots(): Promise<ApiResponse<BackupSnapshotsResponse>> {
  return request<BackupSnapshotsResponse>("/backup/snapshots");
}

export async function fetchBackupSizeEstimate(): Promise<ApiResponse<BackupSizeEstimateResponse>> {
  return request<BackupSizeEstimateResponse>("/backup/size-estimate");
}

export async function collectBackupSizeEstimate(
  force = false,
): Promise<ApiResponse<BackupSizeEstimateResponse>> {
  return request<BackupSizeEstimateResponse>("/backup/size-estimate/collect", {
    method: "POST",
    body: JSON.stringify({ force }),
  });
}

export async function fetchBackupTargets(): Promise<ApiResponse<BackupTargetsOverviewResponse>> {
  return request<BackupTargetsOverviewResponse>("/backup/targets");
}

export async function createBackupTarget(
  payload: BackupTargetDraft,
): Promise<ApiResponse<BackupTargetMutationResponse>> {
  return request<BackupTargetMutationResponse>("/backup/targets", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateBackupTarget(
  targetId: string,
  payload: BackupTargetDraft,
): Promise<ApiResponse<BackupTargetMutationResponse>> {
  return request<BackupTargetMutationResponse>(`/backup/targets/${targetId}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function deleteBackupTarget(
  targetId: string,
): Promise<ApiResponse<BackupTargetMutationResponse>> {
  return request<BackupTargetMutationResponse>(`/backup/targets/${targetId}`, {
    method: "DELETE",
  });
}

export async function fetchBackupTargetValidation(
  targetId: string,
): Promise<ApiResponse<BackupTargetValidationResponse>> {
  return request<BackupTargetValidationResponse>(`/backup/targets/${targetId}/validation`);
}

export async function startBackupTargetValidation(
  targetId: string,
): Promise<ApiResponse<BackupTargetValidationResponse>> {
  return request<BackupTargetValidationResponse>(`/backup/targets/${targetId}/validate`, {
    method: "POST",
  });
}

export async function fetchCurrentBackupExecution(): Promise<
  ApiResponse<BackupExecutionStatusResponse>
> {
  return request<BackupExecutionStatusResponse>("/backup/executions/current");
}

export async function startManualBackupExecution(
  targetId: string,
  kind: "manual" | "pre_repair" = "manual",
): Promise<ApiResponse<BackupExecutionStatusResponse>> {
  return request<BackupExecutionStatusResponse>("/backup/executions", {
    method: "POST",
    body: JSON.stringify({ target_id: targetId, kind }),
  });
}

export async function cancelManualBackupExecution(): Promise<
  ApiResponse<BackupExecutionStatusResponse>
> {
  return request<BackupExecutionStatusResponse>("/backup/executions/cancel", {
    method: "POST",
  });
}

export async function fetchBackupAssetWorkflowOverview(
  targetId: string,
): Promise<ApiResponse<BackupAssetWorkflowOverviewResponse>> {
  return request<BackupAssetWorkflowOverviewResponse>(`/backup/targets/${targetId}/assets/overview`);
}

export async function runBackupTestCopy(
  targetId: string,
): Promise<ApiResponse<BackupTestCopyResponse>> {
  return request<BackupTestCopyResponse>(`/backup/targets/${targetId}/assets/test-copy`, {
    method: "POST",
  });
}

export async function runBackupRestoreAction(
  targetId: string,
  assetIds: string[],
  apply = false,
): Promise<ApiResponse<BackupRestoreActionResponse>> {
  return request<BackupRestoreActionResponse>(`/backup/targets/${targetId}/assets/restore`, {
    method: "POST",
    body: JSON.stringify({ asset_ids: assetIds, apply }),
  });
}
