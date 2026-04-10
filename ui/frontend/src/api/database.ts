import { request } from "./client";
import type { ApiResponse } from "./types/common";
import type { DatabaseOverviewResponse } from "./types/database";

const DATABASE_OVERVIEW_TIMEOUT_MS = 30000;

export async function fetchDatabaseOverview(): Promise<ApiResponse<DatabaseOverviewResponse>> {
  return request<DatabaseOverviewResponse>(
    "/health/database",
    undefined,
    DATABASE_OVERVIEW_TIMEOUT_MS,
  );
}
