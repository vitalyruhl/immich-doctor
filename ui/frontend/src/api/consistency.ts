import { request } from "./client";
import type { ApiResponse } from "./types/common";
import type { CatalogJobRequest, CatalogWorkflowJobRecord } from "./types/catalog";
import type {
  MissingAssetApplyRequest,
  MissingAssetApplyResponse,
  MissingAssetPreviewRequest,
  MissingAssetPreviewResponse,
  MissingAssetReferenceFinding,
  MissingAssetRestorePointDeleteRequest,
  MissingAssetRestorePointDeleteResponse,
  MissingAssetRestorePointsResponse,
  MissingAssetRestoreRequest,
  MissingAssetRestoreResponse,
  MissingAssetScanResponse,
} from "./types/consistency";

export async function fetchMissingAssetFindings(): Promise<ApiResponse<MissingAssetScanResponse>> {
  return request<MissingAssetScanResponse>(
    "/consistency/missing-asset-references/findings",
    undefined,
    30000,
  );
}

export async function previewMissingAssetRemovals(
  payload: MissingAssetPreviewRequest,
): Promise<ApiResponse<MissingAssetPreviewResponse>> {
  return request<MissingAssetPreviewResponse>(
    "/consistency/missing-asset-references/preview",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function applyMissingAssetRemovals(
  payload: MissingAssetApplyRequest,
): Promise<ApiResponse<MissingAssetApplyResponse>> {
  return request<MissingAssetApplyResponse>("/consistency/missing-asset-references/apply", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchMissingAssetRestorePoints(): Promise<
  ApiResponse<MissingAssetRestorePointsResponse>
> {
  return request<MissingAssetRestorePointsResponse>(
    "/consistency/missing-asset-references/restore-points",
  );
}

export async function restoreMissingAssetRestorePoints(
  payload: MissingAssetRestoreRequest,
): Promise<ApiResponse<MissingAssetRestoreResponse>> {
  return request<MissingAssetRestoreResponse>(
    "/consistency/missing-asset-references/restore-points/restore",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function deleteMissingAssetRestorePoints(
  payload: MissingAssetRestorePointDeleteRequest,
): Promise<ApiResponse<MissingAssetRestorePointDeleteResponse>> {
  return request<MissingAssetRestorePointDeleteResponse>(
    "/consistency/missing-asset-references/restore-points/delete",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function fetchCatalogConsistencyJob(): Promise<
  ApiResponse<CatalogWorkflowJobRecord>
> {
  return request<CatalogWorkflowJobRecord>("/consistency/catalog");
}

export async function startCatalogConsistencyJob(
  payload: CatalogJobRequest,
): Promise<ApiResponse<CatalogWorkflowJobRecord>> {
  return request<CatalogWorkflowJobRecord>("/consistency/catalog/start", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export type {
  MissingAssetReferenceFinding,
  MissingAssetRestorePointDeleteRequest,
  MissingAssetRestorePointDeleteResponse,
};
