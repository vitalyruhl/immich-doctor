import { ref } from "vue";
import { defineStore } from "pinia";
import { ApiClientError } from "@/api/client";
import { fetchDatabaseOverview } from "@/api/database";
import type { DatabaseOverviewResponse } from "@/api/types/database";

export const useDatabaseStore = defineStore("database", () => {
  const overview = ref<DatabaseOverviewResponse | null>(null);
  const isLoading = ref(false);
  const error = ref<string | null>(null);

  async function load(): Promise<void> {
    isLoading.value = true;
    error.value = null;
    try {
      const response = await fetchDatabaseOverview();
      overview.value = response.data;
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
    overview,
  };
});
