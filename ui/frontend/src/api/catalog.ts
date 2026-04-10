import { request } from "./client";
import type { ApiResponse } from "./types/common";
import type {
  CatalogJobRequest,
  CatalogJobWorkerResizeRequest,
  CatalogScanRequest,
  CatalogValidationReport,
  CatalogWorkflowJobRecord,
} from "./types/catalog";

const CATALOG_READ_TIMEOUT_MS = 30000;
const CATALOG_JOB_TIMEOUT_MS = 15000;

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
  return request<CatalogValidationReport>(
    `/analyze/catalog/status${buildQuery({ root })}`,
    undefined,
    CATALOG_READ_TIMEOUT_MS,
  );
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
  return request<CatalogWorkflowJobRecord>(
    "/analyze/catalog/scan-job",
    undefined,
    CATALOG_JOB_TIMEOUT_MS,
  );
}

export async function startCatalogScanJob(
  payload: CatalogJobRequest,
): Promise<ApiResponse<CatalogWorkflowJobRecord>> {
  return request<CatalogWorkflowJobRecord>("/analyze/catalog/scan-job/start", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function pauseCatalogScanJob(): Promise<ApiResponse<CatalogWorkflowJobRecord>> {
  return request<CatalogWorkflowJobRecord>("/analyze/catalog/scan-job/pause", {
    method: "POST",
  });
}

export async function resumeCatalogScanJob(): Promise<ApiResponse<CatalogWorkflowJobRecord>> {
  return request<CatalogWorkflowJobRecord>("/analyze/catalog/scan-job/resume", {
    method: "POST",
  });
}

export async function stopCatalogScanJob(): Promise<ApiResponse<CatalogWorkflowJobRecord>> {
  return request<CatalogWorkflowJobRecord>("/analyze/catalog/scan-job/stop", {
    method: "POST",
  });
}

export async function requestCatalogScanWorkers(
  payload: CatalogJobWorkerResizeRequest,
): Promise<ApiResponse<CatalogWorkflowJobRecord>> {
  return request<CatalogWorkflowJobRecord>("/analyze/catalog/scan-job/workers", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
