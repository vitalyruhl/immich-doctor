import { computed, ref } from "vue";
import { defineStore } from "pinia";
import { ApiClientError } from "@/api/client";
import {
  fetchQuarantineSummary,
  fetchRepairRunDetail,
  fetchRepairRuns,
} from "@/api/repair";
import type {
  QuarantineSummaryResponse,
  RepairRunDetailResponse,
  RepairRunsResponse,
} from "@/api/types/repair";

export const useRepairStore = defineStore("repair", () => {
  const runs = ref<RepairRunsResponse | null>(null);
  const selectedRun = ref<RepairRunDetailResponse | null>(null);
  const quarantine = ref<QuarantineSummaryResponse | null>(null);
  const isLoading = ref(false);
  const error = ref<string | null>(null);

  async function load(): Promise<void> {
    isLoading.value = true;
    error.value = null;
    try {
      const [runsResponse, quarantineResponse] = await Promise.all([
        fetchRepairRuns(),
        fetchQuarantineSummary(),
      ]);
      runs.value = runsResponse.data;
      quarantine.value = quarantineResponse.data;
      const firstRunId = runs.value.items[0]?.repairRunId;
      if (firstRunId) {
        await selectRun(firstRunId);
      } else {
        selectedRun.value = null;
      }
    } catch (caughtError) {
      error.value =
        caughtError instanceof ApiClientError ? caughtError.payload.message : "Unknown error.";
    } finally {
      isLoading.value = false;
    }
  }

  async function selectRun(repairRunId: string): Promise<void> {
    try {
      const response = await fetchRepairRunDetail(repairRunId);
      selectedRun.value = response.data;
    } catch (caughtError) {
      error.value =
        caughtError instanceof ApiClientError ? caughtError.payload.message : "Unknown error.";
    }
  }

  const runItems = computed(() => runs.value?.items ?? []);

  return {
    error,
    isLoading,
    load,
    quarantine,
    runItems,
    runs,
    selectRun,
    selectedRun,
  };
});
