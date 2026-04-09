import { request } from "./client";
import type { ApiResponse } from "./types/common";
import type {
  CatalogJobRequest,
  CatalogScanRequest,
  CatalogValidationReport,
  CatalogWorkflowJobRecord,
} from "./types/catalog";

function buildQuery(params: Record<string, string | number | null | undefined>): string {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === null || value === undefined || value === "") {
      return;
    }
    search.set(key, String(value));
  });
  const query = search.toString();
  return query ? `?${query}` : "";
}

export async function startCatalogScan(
  payload: CatalogScanRequest,
): Promise<ApiResponse<CatalogValidationReport>> {
  return request<CatalogValidationReport>("/analyze/catalog/scan", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchCatalogStatus(
  root?: string | null,
): Promise<ApiResponse<CatalogValidationReport>> {
  return request<CatalogValidationReport>(`/analyze/catalog/status${buildQuery({ root })}`);
}

export async function fetchCatalogZeroByte(
  root?: string | null,
  limit = 100,
): Promise<ApiResponse<CatalogValidationReport>> {
  return request<CatalogValidationReport>(
    `/analyze/catalog/zero-byte${buildQuery({ root, limit })}`,
  );
}

export async function fetchCatalogScanJob(): Promise<ApiResponse<CatalogWorkflowJobRecord>> {
  return request<CatalogWorkflowJobRecord>("/analyze/catalog/scan-job");
}

export async function startCatalogScanJob(
  payload: CatalogJobRequest,
): Promise<ApiResponse<CatalogWorkflowJobRecord>> {
  return request<CatalogWorkflowJobRecord>("/analyze/catalog/scan-job/start", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
