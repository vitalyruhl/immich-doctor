import { request } from "./client";
import type { ApiResponse } from "./types/common";
import type {
  QuarantineSummaryResponse,
  RepairRunDetailResponse,
  RepairRunsResponse,
} from "./types/repair";

export async function fetchRepairRuns(): Promise<ApiResponse<RepairRunsResponse>> {
  return request<RepairRunsResponse>("/repair/runs");
}

export async function fetchRepairRunDetail(
  repairRunId: string,
): Promise<ApiResponse<RepairRunDetailResponse>> {
  return request<RepairRunDetailResponse>(`/repair/runs/${repairRunId}`);
}

export async function fetchQuarantineSummary(): Promise<ApiResponse<QuarantineSummaryResponse>> {
  return request<QuarantineSummaryResponse>("/repair/quarantine/summary");
}
