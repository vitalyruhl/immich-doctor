import { request } from "./client";
import type { ApiResponse } from "./types/common";
import type {
  CatalogJobRequest,
  CatalogWorkflowJobRecord,
} from "./types/catalog";
import type {
  CatalogIgnoredFindingsResponse,
  CatalogQuarantineResponse,
  CatalogRemediationActionResponse,
  CatalogRemediationScanResponse,
  CatalogRemediationStateItemPayload,
} from "./types/consistency";

const REMEDIATION_TIMEOUT_MS = 90000;

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

export async function refreshCatalogRemediationFindings(): Promise<
  ApiResponse<CatalogRemediationScanResponse>
> {
  return request<CatalogRemediationScanResponse>(
    "/consistency/catalog-remediation/refresh",
    {
      method: "POST",
    },
    REMEDIATION_TIMEOUT_MS,
  );
}

export async function applyCatalogBrokenDbActionDirect(payload: {
  asset_ids: string[];
  action_kind: string;
}): Promise<ApiResponse<Record<string, unknown>>> {
  return request<Record<string, unknown>>(
    "/consistency/catalog-remediation/broken-db-originals/apply-direct",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    REMEDIATION_TIMEOUT_MS,
  );
}

export async function fetchCatalogIgnoredFindings(): Promise<
  ApiResponse<CatalogIgnoredFindingsResponse>
> {
  return request<CatalogIgnoredFindingsResponse>("/consistency/catalog-remediation/ignored");
}

export async function ignoreCatalogFindings(payload: {
  items: CatalogRemediationStateItemPayload[];
}): Promise<ApiResponse<CatalogIgnoredFindingsResponse>> {
  return request<CatalogIgnoredFindingsResponse>("/consistency/catalog-remediation/ignored", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function releaseCatalogIgnoredFindings(payload: {
  ignored_item_ids: string[];
  release_all?: boolean;
}): Promise<ApiResponse<CatalogIgnoredFindingsResponse>> {
  return request<CatalogIgnoredFindingsResponse>(
    "/consistency/catalog-remediation/ignored/release",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function fetchCatalogQuarantine(): Promise<
  ApiResponse<CatalogQuarantineResponse>
> {
  return request<CatalogQuarantineResponse>("/consistency/catalog-remediation/quarantine");
}

export async function quarantineCatalogFindings(payload: {
  items: CatalogRemediationStateItemPayload[];
}): Promise<ApiResponse<CatalogRemediationActionResponse>> {
  return request<CatalogRemediationActionResponse>(
    "/consistency/catalog-remediation/quarantine",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    REMEDIATION_TIMEOUT_MS,
  );
}

export async function restoreCatalogQuarantine(payload: {
  quarantine_item_ids: string[];
  apply_all?: boolean;
}): Promise<ApiResponse<CatalogRemediationActionResponse>> {
  return request<CatalogRemediationActionResponse>(
    "/consistency/catalog-remediation/quarantine/restore",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    REMEDIATION_TIMEOUT_MS,
  );
}

export async function deleteCatalogQuarantine(payload: {
  quarantine_item_ids: string[];
  apply_all?: boolean;
}): Promise<ApiResponse<CatalogRemediationActionResponse>> {
  return request<CatalogRemediationActionResponse>(
    "/consistency/catalog-remediation/quarantine/delete",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
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
