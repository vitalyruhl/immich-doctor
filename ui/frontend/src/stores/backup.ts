import { computed, ref } from "vue";
import { defineStore } from "pinia";
import { ApiClientError } from "@/api/client";
import { fetchBackupSnapshots, runBackupFiles } from "@/api/backup";
import { fetchQuarantineSummary } from "@/api/repair";
import type { BackupExecutionResponse, BackupSnapshotsResponse } from "@/api/types/backup";
import type { QuarantineSummaryResponse } from "@/api/types/repair";

export const useBackupStore = defineStore("backup", () => {
  const snapshots = ref<BackupSnapshotsResponse | null>(null);
  const quarantine = ref<QuarantineSummaryResponse | null>(null);
  const isLoading = ref(false);
  const isExecuting = ref(false);
  const activeExecutionKind = ref<"manual" | "pre_repair" | null>(null);
  const error = ref<string | null>(null);
  const executionError = ref<string | null>(null);
  const lastExecution = ref<BackupExecutionResponse | null>(null);

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

  async function executeBackup(kind: "manual" | "pre_repair"): Promise<void> {
    isExecuting.value = true;
    activeExecutionKind.value = kind;
    executionError.value = null;

    try {
      const response = await runBackupFiles(kind);
      lastExecution.value = response.data;
      await load();
    } catch (caughtError) {
      executionError.value =
        caughtError instanceof ApiClientError ? caughtError.payload.message : "Unknown error.";
    } finally {
      isExecuting.value = false;
      activeExecutionKind.value = null;
    }
  }

  const snapshotItems = computed(() => snapshots.value?.items ?? []);

  return {
    activeExecutionKind,
    error,
    executeBackup,
    executionError,
    isLoading,
    isExecuting,
    lastExecution,
    load,
    quarantine,
    snapshotItems,
    snapshots,
  };
});
