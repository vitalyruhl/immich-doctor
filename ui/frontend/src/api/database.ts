import { request } from "./client";
import type { ApiResponse } from "./types/common";
import type { DatabaseOverviewResponse } from "./types/database";

export async function fetchDatabaseOverview(): Promise<ApiResponse<DatabaseOverviewResponse>> {
  return request<DatabaseOverviewResponse>("/health/database");
}
