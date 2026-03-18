import { computed, ref } from "vue";
import { defineStore } from "pinia";
import { ApiClientError } from "@/api/client";
import {
  cancelManualBackupExecution,
  collectBackupSizeEstimate,
  createBackupTarget,
  deleteBackupTarget,
  fetchBackupSizeEstimate,
  fetchBackupSnapshots,
  fetchBackupTargetValidation,
  fetchBackupTargets,
  fetchCurrentBackupExecution,
  startBackupTargetValidation,
  startManualBackupExecution,
  updateBackupTarget,
} from "@/api/backup";
import { fetchQuarantineSummary } from "@/api/repair";
import type {
  BackupExecutionStatusResponse,
  BackupJobState,
  BackupSizeEstimateResponse,
  BackupSnapshotSummary,
  BackupSnapshotsResponse,
  BackupTargetConfig,
  BackupTargetDraft,
  BackupTargetValidationResponse,
  BackupTargetsOverviewResponse,
} from "@/api/types/backup";
import type { QuarantineSummaryResponse } from "@/api/types/repair";

const TERMINAL_JOB_STATES: BackupJobState[] = ["completed", "partial", "failed", "unsupported", "canceled"];

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function errorMessage(caughtError: unknown): string {
  return caughtError instanceof ApiClientError ? caughtError.payload.message : "Unknown error.";
}

export const useBackupStore = defineStore("backup", () => {
  const snapshots = ref<BackupSnapshotsResponse | null>(null);
  const quarantine = ref<QuarantineSummaryResponse | null>(null);
  const targetsOverview = ref<BackupTargetsOverviewResponse | null>(null);
  const sizeEstimate = ref<BackupSizeEstimateResponse | null>(null);
  const currentExecution = ref<BackupExecutionStatusResponse | null>(null);
  const activeValidation = ref<BackupTargetValidationResponse | null>(null);
  const isLoading = ref(false);
  const isSavingTarget = ref(false);
  const isExecuting = ref(false);
  const isValidatingTarget = ref(false);
  const error = ref<string | null>(null);
  const targetError = ref<string | null>(null);
  const executionError = ref<string | null>(null);
  const validationError = ref<string | null>(null);
  const selectedTargetId = ref<string | null>(null);

  const snapshotItems = computed<BackupSnapshotSummary[]>(() => snapshots.value?.items ?? []);
  const targets = computed<BackupTargetConfig[]>(() => targetsOverview.value?.items ?? []);
  const selectedTarget = computed<BackupTargetConfig | null>(
    () => targets.value.find((item) => item.targetId === selectedTargetId.value) ?? null,
  );
  const storageEstimate = computed(() => sizeEstimate.value?.scopes.find((scope) => scope.scope === "storage") ?? null);
  const databaseEstimate = computed(() => sizeEstimate.value?.scopes.find((scope) => scope.scope === "database") ?? null);
  const hasTargets = computed(() => targets.value.length > 0);
  const isSizeCollectionRunning = computed(() =>
    sizeEstimate.value ? !TERMINAL_JOB_STATES.includes(sizeEstimate.value.state) : false,
  );
  const isExecutionRunning = computed(() =>
    currentExecution.value ? !TERMINAL_JOB_STATES.includes(currentExecution.value.state) : false,
  );

  async function load(): Promise<void> {
    isLoading.value = true;
    error.value = null;
    try {
      const [snapshotsResponse, quarantineResponse, targetsResponse, sizeResponse, executionResponse] =
        await Promise.all([
          fetchBackupSnapshots(),
          fetchQuarantineSummary(),
          fetchBackupTargets(),
          fetchBackupSizeEstimate(),
          fetchCurrentBackupExecution(),
        ]);
      snapshots.value = snapshotsResponse.data;
      quarantine.value = quarantineResponse.data;
      targetsOverview.value = targetsResponse.data;
      sizeEstimate.value = sizeResponse.data;
      currentExecution.value = executionResponse.data;
      if (!selectedTargetId.value && targetsResponse.data.items.length > 0) {
        selectedTargetId.value = targetsResponse.data.items[0]?.targetId ?? null;
      }
      if (!sizeEstimate.value || sizeEstimate.value.state === "pending" || sizeEstimate.value.stale) {
        void refreshSizeEstimate();
      }
    } catch (caughtError) {
      error.value = errorMessage(caughtError);
    } finally {
      isLoading.value = false;
    }
  }

  async function refreshTargets(): Promise<void> {
    const response = await fetchBackupTargets();
    targetsOverview.value = response.data;
    if (!selectedTargetId.value && response.data.items.length > 0) {
      selectedTargetId.value = response.data.items[0]?.targetId ?? null;
    }
  }

  async function refreshSnapshots(): Promise<void> {
    snapshots.value = (await fetchBackupSnapshots()).data;
  }

  async function refreshSizeEstimate(force = false): Promise<void> {
    sizeEstimate.value = (await collectBackupSizeEstimate(force)).data;
    if (!sizeEstimate.value.jobId) {
      return;
    }
    while (sizeEstimate.value && !TERMINAL_JOB_STATES.includes(sizeEstimate.value.state)) {
      await sleep(800);
      sizeEstimate.value = (await fetchBackupSizeEstimate()).data;
    }
  }

  async function saveTarget(payload: BackupTargetDraft, targetId?: string): Promise<void> {
    isSavingTarget.value = true;
    targetError.value = null;
    try {
      if (targetId) {
        await updateBackupTarget(targetId, payload);
      } else {
        await createBackupTarget(payload);
      }
      await refreshTargets();
    } catch (caughtError) {
      targetError.value = errorMessage(caughtError);
    } finally {
      isSavingTarget.value = false;
    }
  }

  async function removeTarget(targetId: string): Promise<void> {
    isSavingTarget.value = true;
    targetError.value = null;
    try {
      await deleteBackupTarget(targetId);
      if (selectedTargetId.value === targetId) {
        selectedTargetId.value = null;
      }
      await refreshTargets();
    } catch (caughtError) {
      targetError.value = errorMessage(caughtError);
    } finally {
      isSavingTarget.value = false;
    }
  }

  async function validateTarget(targetId: string): Promise<void> {
    isValidatingTarget.value = true;
    validationError.value = null;
    try {
      activeValidation.value = (await startBackupTargetValidation(targetId)).data;
      while (activeValidation.value && !TERMINAL_JOB_STATES.includes(activeValidation.value.state)) {
        await sleep(800);
        activeValidation.value = (await fetchBackupTargetValidation(targetId)).data;
      }
      await refreshTargets();
    } catch (caughtError) {
      validationError.value = errorMessage(caughtError);
    } finally {
      isValidatingTarget.value = false;
    }
  }

  async function startExecution(targetId: string, kind: "manual" | "pre_repair" = "manual"): Promise<void> {
    isExecuting.value = true;
    executionError.value = null;
    try {
      currentExecution.value = (await startManualBackupExecution(targetId, kind)).data;
      while (currentExecution.value && !TERMINAL_JOB_STATES.includes(currentExecution.value.state)) {
        await sleep(1000);
        currentExecution.value = (await fetchCurrentBackupExecution()).data;
      }
      await Promise.all([refreshTargets(), refreshSnapshots()]);
    } catch (caughtError) {
      executionError.value = errorMessage(caughtError);
    } finally {
      isExecuting.value = false;
    }
  }

  async function cancelExecution(): Promise<void> {
    executionError.value = null;
    try {
      currentExecution.value = (await cancelManualBackupExecution()).data;
      while (currentExecution.value && !TERMINAL_JOB_STATES.includes(currentExecution.value.state)) {
        await sleep(600);
        currentExecution.value = (await fetchCurrentBackupExecution()).data;
      }
    } catch (caughtError) {
      executionError.value = errorMessage(caughtError);
    }
  }

  function selectTarget(targetId: string): void {
    selectedTargetId.value = targetId;
  }

  return {
    activeValidation,
    cancelExecution,
    currentExecution,
    databaseEstimate,
    error,
    executionError,
    hasTargets,
    isExecuting,
    isExecutionRunning,
    isLoading,
    isSavingTarget,
    isSizeCollectionRunning,
    isValidatingTarget,
    load,
    quarantine,
    refreshSizeEstimate,
    removeTarget,
    saveTarget,
    selectedTarget,
    selectedTargetId,
    selectTarget,
    sizeEstimate,
    snapshotItems,
    snapshots,
    startExecution,
    storageEstimate,
    targetError,
    targets,
    targetsOverview,
    validateTarget,
    validationError,
  };
});
