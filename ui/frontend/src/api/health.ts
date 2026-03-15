import { request } from "./client";
import type { ApiResponse } from "./types/common";
import type { HealthItem, HealthOverviewResponse } from "./types/health";

function buildMockHealthItems(): HealthItem[] {
  return [
    {
      id: "immich-connectivity",
      title: "Immich connectivity",
      status: "unknown",
      summary: "[MOCKED!] Backend connectivity is not wired yet.",
      details: "Mock adapter is enabled for local UI foundation work.",
      updatedAt: new Date().toISOString(),
      blocking: true,
      source: "[MOCKED!] ui/local-adapter",
    },
    {
      id: "db-reachability",
      title: "DB reachability",
      status: "unknown",
      summary: "[MOCKED!] PostgreSQL health is not wired yet.",
      details: "No real backend call has been executed.",
      updatedAt: new Date().toISOString(),
      blocking: true,
      source: "[MOCKED!] ui/local-adapter",
    },
    {
      id: "storage-reachability",
      title: "Storage reachability",
      status: "warning",
      summary: "[MOCKED!] Storage mounts need backend verification.",
      details: "Placeholder state is intentionally not green.",
      updatedAt: new Date().toISOString(),
      blocking: true,
      source: "[MOCKED!] ui/local-adapter",
    },
    {
      id: "path-consistency-readiness",
      title: "Path consistency readiness",
      status: "unknown",
      summary: "[MOCKED!] Consistency checks are not connected yet.",
      details: "Future backend source: consistency validate summary.",
      updatedAt: new Date().toISOString(),
      blocking: false,
      source: "[MOCKED!] ui/local-adapter",
    },
    {
      id: "backup-target-readiness",
      title: "Backup target readiness",
      status: "unknown",
      summary: "[MOCKED!] Backup readiness is not wired yet.",
      details: "No fake success is shown.",
      updatedAt: new Date().toISOString(),
      blocking: false,
      source: "[MOCKED!] ui/local-adapter",
    },
    {
      id: "scheduler-runtime-readiness",
      title: "Scheduler/runtime readiness",
      status: "unknown",
      summary: "[MOCKED!] Runtime and scheduler checks are pending.",
      details: "Future backend source: runtime health and scheduler state.",
      updatedAt: new Date().toISOString(),
      blocking: false,
      source: "[MOCKED!] ui/local-adapter",
    },
  ];
}

export async function fetchHealthOverview(): Promise<ApiResponse<HealthOverviewResponse>> {
  if (import.meta.env.VITE_USE_MOCK_API === "true") {
    return {
      data: {
        items: buildMockHealthItems(),
        mocked: true,
      },
      mocked: true,
      source: "mock",
    };
  }

  return request<HealthOverviewResponse>("/health/overview");
}
