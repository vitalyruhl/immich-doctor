import { request } from "./client";
import type { ApiResponse } from "./types/common";
import type { HealthItem, HealthOverviewResponse } from "./types/health";

function buildMockHealthItems(): HealthItem[] {
  return [
    {
      id: "immich-configured",
      title: "Immich configured",
      status: "unknown",
      summary: "[MOCKED!] Immich API settings are not wired yet.",
      details: "Mock adapter is enabled for local UI foundation work.",
      updatedAt: new Date().toISOString(),
      blocking: true,
      source: "[MOCKED!] ui/local-adapter",
    },
    {
      id: "immich-reachable",
      title: "Immich reachable",
      status: "unknown",
      summary: "[MOCKED!] Immich reachability is not wired yet.",
      details: "Mock adapter is enabled for local UI foundation work.",
      updatedAt: new Date().toISOString(),
      blocking: true,
      source: "[MOCKED!] ui/local-adapter",
    },
    {
      id: "db-reachability",
      title: "DB reachable",
      status: "unknown",
      summary: "[MOCKED!] PostgreSQL health is not wired yet.",
      details: "No real backend call has been executed.",
      updatedAt: new Date().toISOString(),
      blocking: true,
      source: "[MOCKED!] ui/local-adapter",
    },
    {
      id: "storage-reachability",
      title: "Storage reachable",
      status: "warning",
      summary: "[MOCKED!] Storage mounts need backend verification.",
      details: "Placeholder state is intentionally not green.",
      updatedAt: new Date().toISOString(),
      blocking: true,
      source: "[MOCKED!] ui/local-adapter",
    },
    {
      id: "path-readiness",
      title: "Path readiness",
      status: "unknown",
      summary: "[MOCKED!] Path readiness is not connected yet.",
      details: "Future backend source: storage and runtime path checks.",
      updatedAt: new Date().toISOString(),
      blocking: false,
      source: "[MOCKED!] ui/local-adapter",
    },
    {
      id: "consistency-readiness",
      title: "Consistency readiness",
      status: "warning",
      summary: "[MOCKED!] Consistency is waiting for a current storage index.",
      details: "Catalog-backed compare remains pending until indexing completes.",
      updatedAt: new Date().toISOString(),
      blocking: false,
      source: "[MOCKED!] ui/local-adapter",
    },
    {
      id: "backup-readiness",
      title: "Backup readiness",
      status: "unknown",
      summary: "[MOCKED!] Backup readiness is not wired yet.",
      details: "No fake success is shown.",
      updatedAt: new Date().toISOString(),
      blocking: false,
      source: "[MOCKED!] ui/local-adapter",
    },
    {
      id: "scheduler-runtime-readiness",
      title: "Scheduler / runtime readiness",
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
        generatedAt: new Date().toISOString(),
        overallStatus: "unknown",
        items: buildMockHealthItems(),
      },
      mocked: true,
      source: "mock",
    };
  }

  return request<HealthOverviewResponse>("/health/overview");
}
