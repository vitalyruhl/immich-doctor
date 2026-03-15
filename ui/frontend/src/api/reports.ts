import { request } from "./client";
import type { ApiResponse } from "./types/common";

export interface ReportPlaceholderResponse {
  items: Array<{
    id: string;
    title: string;
    available: boolean;
  }>;
}

export async function fetchReportPlaceholders(): Promise<ApiResponse<ReportPlaceholderResponse>> {
  if (import.meta.env.VITE_USE_MOCK_API === "true") {
    return {
      data: {
        items: [
          { id: "logs", title: "[MOCKED!] Logs endpoint not wired yet.", available: false },
          { id: "reports", title: "[MOCKED!] Reports endpoint not wired yet.", available: false },
        ],
      },
      mocked: true,
      source: "mock",
    };
  }

  return request<ReportPlaceholderResponse>("/reports");
}
