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
  CatalogRemediationFindingDetailResponse,
  CatalogRemediationGroupKey,
  CatalogRemediationGroupPageResponse,
  CatalogRemediationOverviewResponse,
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

export async function fetchCatalogRemediationOverview(): Promise<
  ApiResponse<CatalogRemediationOverviewResponse>
> {
  return request<CatalogRemediationOverviewResponse>(
    "/consistency/catalog-remediation/groups",
    undefined,
    REMEDIATION_TIMEOUT_MS,
  );
}

export async function refreshCatalogRemediationOverview(): Promise<
  ApiResponse<CatalogRemediationOverviewResponse>
> {
  return request<CatalogRemediationOverviewResponse>(
    "/consistency/catalog-remediation/groups/refresh",
    {
      method: "POST",
    },
    REMEDIATION_TIMEOUT_MS,
  );
}

export async function fetchCatalogRemediationGroupPage(
  groupKey: CatalogRemediationGroupKey,
  payload: {
    limit?: number | null;
    offset?: number;
  } = {},
): Promise<ApiResponse<CatalogRemediationGroupPageResponse>> {
  const query = new URLSearchParams();
  if (payload.limit !== undefined && payload.limit !== null) {
    query.set("limit", String(payload.limit));
  }
  if (payload.offset !== undefined) {
    query.set("offset", String(payload.offset));
  }
  const suffix = query.size ? `?${query.toString()}` : "";
  return request<CatalogRemediationGroupPageResponse>(
    `/consistency/catalog-remediation/groups/${groupKey}${suffix}`,
    undefined,
    REMEDIATION_TIMEOUT_MS,
  );
}

export async function fetchCatalogRemediationFindingDetail(
  groupKey: CatalogRemediationGroupKey,
  findingId: string,
): Promise<ApiResponse<CatalogRemediationFindingDetailResponse>> {
  return request<CatalogRemediationFindingDetailResponse>(
    `/consistency/catalog-remediation/groups/${groupKey}/items/${encodeURIComponent(findingId)}`,
    undefined,
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

export async function applyCatalogFindingActionDirect(payload: {
  finding_ids: string[];
  action_kind: string;
}): Promise<ApiResponse<Record<string, unknown>>> {
  return request<Record<string, unknown>>(
    "/consistency/catalog-remediation/findings/apply-direct",
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
