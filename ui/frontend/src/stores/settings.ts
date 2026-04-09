import { ref } from "vue";
import { defineStore } from "pinia";
import {
  buildUnavailableSettingsOverview,
  fetchSettingsOverview,
  fetchTestbedDumpOverview,
  importTestbedDump,
  summarizeSettingsRequestError,
} from "@/api/settings";
import type {
  SettingsCapability,
  SettingsOverviewResponse,
  SettingsSection,
  TestbedDumpImportResponse,
  TestbedDumpOverviewResponse,
} from "@/api/types/settings";
import { ApiClientError } from "@/api/client";

export const useSettingsStore = defineStore("settings", () => {
  const overview = ref<SettingsOverviewResponse | null>(null);
  const sections = ref<SettingsSection[]>([]);
  const capabilities = ref<SettingsCapability[]>([]);
  const isLoading = ref(false);
  const capabilitySummary = ref("Settings capability has not been inspected yet.");
  const capabilityState = ref<SettingsOverviewResponse["capabilityState"]>("NOT_IMPLEMENTED");
  const mocked = ref(false);
  const testbedDump = ref<TestbedDumpOverviewResponse | null>(null);
  const testbedImportResult = ref<TestbedDumpImportResponse | null>(null);
  const isImporting = ref(false);
  const importError = ref<string | null>(null);

  async function load(): Promise<void> {
    isLoading.value = true;
    try {
      const response = await fetchSettingsOverview();
      overview.value = response.data;
      sections.value = response.data.sections;
      capabilities.value = response.data.capabilities;
      capabilitySummary.value = response.data.summary;
      capabilityState.value = response.data.capabilityState;
      mocked.value = response.mocked;
    } catch (caughtError) {
      const safeSummary = summarizeSettingsRequestError(caughtError);
      const fallbackOverview = buildUnavailableSettingsOverview(safeSummary);

      overview.value = fallbackOverview;
      sections.value = fallbackOverview.sections;
      capabilities.value = fallbackOverview.capabilities;
      capabilitySummary.value = fallbackOverview.summary;
      capabilityState.value = fallbackOverview.capabilityState;
      mocked.value = false;
    } finally {
      try {
        const response = await fetchTestbedDumpOverview();
        testbedDump.value = response.data;
      } catch (caughtError) {
        if (caughtError instanceof ApiClientError && caughtError.payload.status === 404) {
          testbedDump.value = null;
        } else {
          testbedDump.value = null;
        }
      }
      isLoading.value = false;
    }
  }

  async function triggerTestbedDumpImport(payload: {
    path: string | null;
    format: string;
    force: boolean;
  }): Promise<TestbedDumpImportResponse | null> {
    isImporting.value = true;
    importError.value = null;
    try {
      const response = await importTestbedDump(payload);
      testbedImportResult.value = response.data;
      return response.data;
    } catch (caughtError) {
      if (caughtError instanceof ApiClientError) {
        importError.value = caughtError.payload.message;
      } else {
        importError.value = "Testbed dump import failed.";
      }
      return null;
    } finally {
      isImporting.value = false;
    }
  }

  return {
    capabilities,
    capabilityState,
    capabilitySummary,
    importError,
    isImporting,
    isLoading,
    load,
    mocked,
    overview,
    sections,
    testbedDump,
    testbedImportResult,
    triggerTestbedDumpImport,
  };
});
