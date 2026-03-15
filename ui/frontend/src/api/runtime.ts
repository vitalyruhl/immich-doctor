import { request } from "./client";
import type { ApiResponse } from "./types/common";
import type {
  RuntimeIntegrityInspectResponse,
  RuntimeMetadataFailuresInspectResponse,
  RuntimeMetadataFailuresRepairResponse,
  RuntimeRepairReadinessResponse,
  SuggestedAction,
} from "./types/runtime";

export async function fetchRuntimeIntegrityInspect(
  limit = 100,
): Promise<ApiResponse<RuntimeIntegrityInspectResponse>> {
  return request<RuntimeIntegrityInspectResponse>(
    `/runtime/integrity/inspect?limit=${limit}&offset=0&include_derivatives=true`,
  );
}

export async function fetchRuntimeMetadataFailuresInspect(
  limit = 100,
): Promise<ApiResponse<RuntimeMetadataFailuresInspectResponse>> {
  return request<RuntimeMetadataFailuresInspectResponse>(
    `/runtime/metadata-failures/inspect?limit=${limit}&offset=0`,
  );
}

export async function repairRuntimeMetadataFailures(
  diagnosticId: string,
  action: SuggestedAction,
  apply: boolean,
): Promise<ApiResponse<RuntimeMetadataFailuresRepairResponse>> {
  return request<RuntimeMetadataFailuresRepairResponse>("/runtime/metadata-failures/repair", {
    method: "POST",
    body: JSON.stringify({
      apply,
      diagnostic_ids: [diagnosticId],
      retry_jobs: action === "retry_jobs",
      requeue: action === "requeue",
      fix_permissions: action === "fix_permissions",
      quarantine_corrupt: action === "quarantine_corrupt",
      mark_unrecoverable: action === "mark_unrecoverable",
    }),
  });
}

export async function fetchRuntimeRepairReadiness(): Promise<
  ApiResponse<RuntimeRepairReadinessResponse>
> {
  return request<RuntimeRepairReadinessResponse>("/runtime/metadata-failures/repair-readiness");
}
