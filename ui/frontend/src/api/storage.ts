import { request } from "./client";
import type { ApiResponse } from "./types/common";
import type {
  EmptyFolderQuarantineActionResponse,
  EmptyFolderQuarantineListResponse,
  EmptyFolderScanReport,
  EmptyFolderScanStatus,
} from "./types/storage";

export async function fetchEmptyFolderScan(
  root: string | null,
): Promise<ApiResponse<EmptyFolderScanReport>> {
  return request<EmptyFolderScanReport>("/analyze/storage/empty-folders/scan", {
    method: "POST",
    body: JSON.stringify({ root }),
  });
}

export async function fetchEmptyFolderScanStatus(): Promise<ApiResponse<EmptyFolderScanStatus>> {
  return request<EmptyFolderScanStatus>("/analyze/storage/empty-folders/scan-status");
}

export async function quarantineEmptyFolders(payload: {
  root_slugs?: string[];
  paths?: string[];
  quarantine_all: boolean;
  dry_run: boolean;
}): Promise<ApiResponse<EmptyFolderQuarantineActionResponse>> {
  return request<EmptyFolderQuarantineActionResponse>("/analyze/storage/empty-folders/quarantine", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchEmptyFolderQuarantineList(
  sessionId: string | null = null,
): Promise<ApiResponse<EmptyFolderQuarantineListResponse>> {
  const query = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : "";
  return request<EmptyFolderQuarantineListResponse>(
    `/analyze/storage/empty-folders/quarantine-list${query}`,
  );
}

export async function restoreEmptyFolders(
  sessionId: string,
  payload: { paths?: string[]; restore_all: boolean; dry_run: boolean },
): Promise<ApiResponse<EmptyFolderQuarantineActionResponse>> {
  return request<EmptyFolderQuarantineActionResponse>(
    `/analyze/storage/empty-folders/quarantine/${encodeURIComponent(sessionId)}/restore`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function deleteEmptyFolders(
  sessionId: string,
  payload: { paths?: string[]; delete_all: boolean; dry_run: boolean },
): Promise<ApiResponse<EmptyFolderQuarantineActionResponse>> {
  return request<EmptyFolderQuarantineActionResponse>(
    `/analyze/storage/empty-folders/quarantine/${encodeURIComponent(sessionId)}`,
    {
      method: "DELETE",
      body: JSON.stringify(payload),
    },
  );
}
