import { request } from "./client";
import type { ApiResponse } from "./types/common";
import type { SettingsResponse } from "./types/settings";

const MOCK_SETTINGS: SettingsResponse = {
  mocked: true,
  sections: [
    {
      id: "immich",
      title: "Immich",
      description: "Connection and API defaults for the Immich backend.",
      fields: [],
    },
    {
      id: "database",
      title: "Database",
      description: "PostgreSQL connectivity and safety boundaries.",
      fields: [],
    },
    {
      id: "storage",
      title: "Storage",
      description: "Storage roots, mounts, and path safety settings.",
      fields: [],
    },
    {
      id: "backup",
      title: "Backup",
      description: "Backup targets and retention-related placeholders.",
      fields: [],
    },
    {
      id: "scheduler-runtime",
      title: "Scheduler / Runtime",
      description: "Runtime environment and scheduled task placeholders.",
      fields: [],
    },
  ],
};

export async function fetchSettings(): Promise<ApiResponse<SettingsResponse>> {
  if (import.meta.env.VITE_USE_MOCK_API === "true") {
    return {
      data: MOCK_SETTINGS,
      mocked: true,
      source: "mock",
    };
  }

  return request<SettingsResponse>("/settings");
}
