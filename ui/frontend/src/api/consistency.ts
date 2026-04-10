import { request } from "./client";
import type { ApiResponse } from "./types/common";
import type {
  CatalogJobRequest,
  CatalogWorkflowJobRecord,
} from "./types/catalog";
import type { CatalogRemediationScanResponse } from "./types/consistency";

const REMEDIATION_TIMEOUT_MS = 30000;

export async function fetchCatalogConsistencyJob(): Promise<
  ApiResponse<CatalogWorkflowJobRecord>
> {
  return request<CatalogWorkflowJobRecord>("/consistency/catalog");
}

export async function fetchCatalogRemediationFindings(): Promise<
  ApiResponse<CatalogRemediationScanResponse>
> {
  return request<CatalogRemediationScanResponse>(
    "/consistency/catalog-remediation/findings",
    undefined,
    REMEDIATION_TIMEOUT_MS,
  );
}

export async function startCatalogConsistencyJob(
  payload: CatalogJobRequest,
): Promise<ApiResponse<CatalogWorkflowJobRecord>> {
  return request<CatalogWorkflowJobRecord>("/consistency/catalog/start", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
