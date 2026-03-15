import { ref } from "vue";
import { defineStore } from "pinia";
import { ApiClientError } from "@/api/client";
import { fetchSettings } from "@/api/settings";
import type { SettingsSection } from "@/api/types/settings";

export const useSettingsStore = defineStore("settings", () => {
  const sections = ref<SettingsSection[]>([]);
  const isLoading = ref(false);
  const error = ref<string | null>(null);
  const mocked = ref(false);

  async function load(): Promise<void> {
    isLoading.value = true;
    error.value = null;
    try {
      const response = await fetchSettings();
      sections.value = response.data.sections;
      mocked.value = response.mocked;
    } catch (caughtError) {
      error.value =
        caughtError instanceof ApiClientError ? caughtError.payload.message : "Unknown error.";
    } finally {
      isLoading.value = false;
    }
  }

  return {
    error,
    isLoading,
    load,
    mocked,
    sections,
  };
});
