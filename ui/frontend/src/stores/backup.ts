import { computed, ref } from "vue";
import { defineStore } from "pinia";
import { ApiClientError } from "@/api/client";
import { fetchBackupSnapshots } from "@/api/backup";
import { fetchQuarantineSummary } from "@/api/repair";
import type { BackupSnapshotsResponse } from "@/api/types/backup";
import type { QuarantineSummaryResponse } from "@/api/types/repair";

export const useBackupStore = defineStore("backup", () => {
  const snapshots = ref<BackupSnapshotsResponse | null>(null);
  const quarantine = ref<QuarantineSummaryResponse | null>(null);
  const isLoading = ref(false);
  const error = ref<string | null>(null);

  async function load(): Promise<void> {
    isLoading.value = true;
    error.value = null;
    try {
      const [snapshotsResponse, quarantineResponse] = await Promise.all([
        fetchBackupSnapshots(),
        fetchQuarantineSummary(),
      ]);
      snapshots.value = snapshotsResponse.data;
      quarantine.value = quarantineResponse.data;
    } catch (caughtError) {
      error.value =
        caughtError instanceof ApiClientError ? caughtError.payload.message : "Unknown error.";
    } finally {
      isLoading.value = false;
    }
  }

  const snapshotItems = computed(() => snapshots.value?.items ?? []);

  return {
    error,
    isLoading,
    load,
    quarantine,
    snapshotItems,
    snapshots,
  };
});
