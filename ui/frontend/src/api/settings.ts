import { ApiClientError, request } from "./client";
import type { ApiResponse } from "./types/common";
import type {
  SettingsOverviewResponse,
  TestbedDumpImportResponse,
  TestbedDumpOverviewResponse,
} from "./types/settings";

const MOCK_SETTINGS: SettingsOverviewResponse = {
  generatedAt: new Date().toISOString(),
  schemaVersion: "v1",
  capabilityState: "PARTIAL",
  summary: "[MOCKED!] Settings read/schema are mocked. Mutation remains disabled.",
  capabilities: [
    {
      id: "read_settings",
      title: "Read settings",
      state: "READY",
      summary: "[MOCKED!] Settings overview is available in mock mode.",
      details: "[MOCKED!] Replace with GET /api/settings for real backend state.",
      blocking: false,
    },
    {
      id: "settings_schema",
      title: "Read settings schema",
      state: "READY",
      summary: "[MOCKED!] Settings schema is available in mock mode.",
      details: "[MOCKED!] Replace with GET /api/settings/schema for real backend state.",
      blocking: false,
    },
    {
      id: "update_settings",
      title: "Update settings",
      state: "NOT_IMPLEMENTED",
      summary: "[MOCKED!] Mutation remains disabled in this phase.",
      details: "[MOCKED!] No settings persistence exists in mock mode either.",
      blocking: true,
    },
  ],
  sections: [
    {
      id: "immich",
      title: "Immich",
      description: "Connection and API defaults for the Immich backend.",
      state: "PARTIAL",
      summary: "[MOCKED!] Immich path settings are visible, but API connectivity is not implemented.",
      fields: [],
    },
    {
      id: "database",
      title: "Database",
      description: "PostgreSQL connectivity and safety boundaries.",
      state: "PARTIAL",
      summary: "[MOCKED!] Database settings shell only.",
      fields: [],
    },
    {
      id: "storage",
      title: "Storage",
      description: "Storage roots, mounts, and path safety settings.",
      state: "PARTIAL",
      summary: "[MOCKED!] Storage settings shell only.",
      fields: [],
    },
    {
      id: "backup",
      title: "Backup",
      description: "Backup targets and retention-related placeholders.",
      state: "PARTIAL",
      summary: "[MOCKED!] Backup settings shell only.",
      fields: [],
    },
    {
      id: "scheduler-runtime",
      title: "Scheduler / Runtime",
      description: "Runtime environment and scheduled task placeholders.",
      state: "NOT_IMPLEMENTED",
      summary: "[MOCKED!] Scheduler settings are not implemented.",
      fields: [],
    },
  ],
};

export async function fetchSettingsOverview(): Promise<ApiResponse<SettingsOverviewResponse>> {
  if (import.meta.env.VITE_USE_MOCK_API === "true") {
    return {
      data: MOCK_SETTINGS,
      mocked: true,
      source: "mock",
    };
  }

  return request<SettingsOverviewResponse>("/settings");
}

export async function fetchTestbedDumpOverview(): Promise<ApiResponse<TestbedDumpOverviewResponse>> {
  return request<TestbedDumpOverviewResponse>("/settings/testbed/dump");
}

export async function importTestbedDump(payload: {
  path: string | null;
  format: string;
  force: boolean;
}): Promise<ApiResponse<TestbedDumpImportResponse>> {
  return request<TestbedDumpImportResponse>(
    "/settings/testbed/dump/import",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    600000,
  );
}

export function buildUnavailableSettingsOverview(reason: string): SettingsOverviewResponse {
  return {
    generatedAt: new Date().toISOString(),
    schemaVersion: "unknown",
    capabilityState: "NOT_IMPLEMENTED",
    summary: reason,
    capabilities: [
      {
        id: "read_settings",
        title: "Read settings",
        state: "NOT_IMPLEMENTED",
        summary: "Settings overview is unavailable from the current backend.",
        details: reason,
        blocking: false,
      },
      {
        id: "settings_schema",
        title: "Read settings schema",
        state: "NOT_IMPLEMENTED",
        summary: "Settings schema is unavailable from the current backend.",
        details: reason,
        blocking: false,
      },
      {
        id: "update_settings",
        title: "Update settings",
        state: "NOT_IMPLEMENTED",
        summary: "Settings mutation is unavailable from the current backend.",
        details: "No write capability is exposed while the backend route is unavailable.",
        blocking: true,
      },
    ],
    sections: [],
  };
}

export function summarizeSettingsRequestError(error: unknown): string {
  if (!(error instanceof ApiClientError)) {
    return "Settings capability is unavailable. Showing safe fallback state.";
  }

  if (error.payload.status === 404) {
    return "Settings capability is not implemented in this backend build yet.";
  }

  if (error.payload.code === "timeout") {
    return "Settings request timed out. Showing safe fallback state.";
  }

  if (error.payload.code === "network_error") {
    return "Settings backend could not be reached. Showing safe fallback state.";
  }

  return "Settings capability could not be confirmed. Showing safe fallback state.";
}
