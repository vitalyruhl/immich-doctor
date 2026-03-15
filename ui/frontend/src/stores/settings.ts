import { ref } from "vue";
import { defineStore } from "pinia";
import {
  buildUnavailableSettingsOverview,
  fetchSettingsOverview,
  summarizeSettingsRequestError,
} from "@/api/settings";
import type { SettingsCapability, SettingsOverviewResponse, SettingsSection } from "@/api/types/settings";

export const useSettingsStore = defineStore("settings", () => {
  const overview = ref<SettingsOverviewResponse | null>(null);
  const sections = ref<SettingsSection[]>([]);
  const capabilities = ref<SettingsCapability[]>([]);
  const isLoading = ref(false);
  const capabilitySummary = ref("Settings capability has not been inspected yet.");
  const capabilityState = ref<SettingsOverviewResponse["capabilityState"]>("NOT_IMPLEMENTED");
  const mocked = ref(false);

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
      isLoading.value = false;
    }
  }

  return {
    capabilities,
    capabilityState,
    capabilitySummary,
    isLoading,
    load,
    mocked,
    overview,
    sections,
  };
});
