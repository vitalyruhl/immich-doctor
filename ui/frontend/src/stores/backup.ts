import { computed, ref } from "vue";
import { defineStore } from "pinia";
import { ApiClientError } from "@/api/client";
import {
  cancelManualBackupExecution,
  collectBackupSizeEstimate,
  createBackupTarget,
  deleteBackupTarget,
  fetchBackupAssetWorkflowOverview,
  fetchBackupSizeEstimate,
  fetchBackupSnapshots,
  fetchBackupTargetValidation,
  fetchBackupTargets,
  fetchCurrentBackupExecution,
  runBackupRestoreAction,
  runBackupTestCopy,
  startBackupTargetValidation,
  startManualBackupExecution,
  updateBackupTarget,
} from "@/api/backup";
import { fetchQuarantineSummary } from "@/api/repair";
import type {
  BackupAssetComparisonItem,
  BackupAssetWorkflowOverviewResponse,
  BackupExecutionStatusResponse,
  BackupJobState,
  BackupSizeEstimateStatus,
  BackupRestoreActionResponse,
  BackupSizeEstimateResponse,
  BackupSnapshotSummary,
  BackupSnapshotsResponse,
  BackupTestCopyResponse,
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

function isTerminalJobState(state: BackupJobState | null | undefined): boolean {
  return state ? TERMINAL_JOB_STATES.includes(state) : false;
}

export const useBackupStore = defineStore("backup", () => {
  const snapshots = ref<BackupSnapshotsResponse | null>(null);
  const quarantine = ref<QuarantineSummaryResponse | null>(null);
  const targetsOverview = ref<BackupTargetsOverviewResponse | null>(null);
  const sizeEstimate = ref<BackupSizeEstimateResponse | null>(null);
  const currentExecution = ref<BackupExecutionStatusResponse | null>(null);
  const activeValidation = ref<BackupTargetValidationResponse | null>(null);
  const workflowOverview = ref<BackupAssetWorkflowOverviewResponse | null>(null);
  const lastTestCopy = ref<BackupTestCopyResponse | null>(null);
  const restorePreview = ref<BackupRestoreActionResponse | null>(null);
  const lastRestoreResult = ref<BackupRestoreActionResponse | null>(null);
  const isLoading = ref(false);
  const isSavingTarget = ref(false);
  const isExecuting = ref(false);
  const isValidatingTarget = ref(false);
  const isLoadingWorkflow = ref(false);
  const isRunningTestCopy = ref(false);
  const isRunningRestore = ref(false);
  const error = ref<string | null>(null);
  const targetError = ref<string | null>(null);
  const executionError = ref<string | null>(null);
  const validationError = ref<string | null>(null);
  const workflowError = ref<string | null>(null);
  const restoreError = ref<string | null>(null);
  const selectedTargetId = ref<string | null>(null);
  const selectedAssetIds = ref<string[]>([]);
  const validatingTargetId = ref<string | null>(null);

  const snapshotItems = computed<BackupSnapshotSummary[]>(() => snapshots.value?.items ?? []);
  const targets = computed<BackupTargetConfig[]>(() => targetsOverview.value?.items ?? []);
  const selectedTarget = computed<BackupTargetConfig | null>(
    () => targets.value.find((item) => item.targetId === selectedTargetId.value) ?? null,
  );
  const storageEstimate = computed(() => sizeEstimate.value?.scopes.find((scope) => scope.scope === "storage") ?? null);
  const databaseEstimate = computed(() => sizeEstimate.value?.scopes.find((scope) => scope.scope === "database") ?? null);
  const hasTargets = computed(() => targets.value.length > 0);
  const isSizeCollectionRunning = computed(() =>
    sizeEstimate.value ? !isTerminalJobState(sizeEstimate.value.state) : false,
  );
  const isExecutionRunning = computed(() =>
    currentExecution.value ? !TERMINAL_JOB_STATES.includes(currentExecution.value.state) : false,
  );
  const workflowItems = computed<BackupAssetComparisonItem[]>(() => workflowOverview.value?.comparison.items ?? []);
  const selectedWorkflowItems = computed<BackupAssetComparisonItem[]>(() =>
    workflowItems.value.filter((item) => selectedAssetIds.value.includes(item.assetId)),
  );
  const restorableItems = computed<BackupAssetComparisonItem[]>(() =>
    workflowItems.value.filter((item) => item.restoreEligible),
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
      if (selectedTargetId.value) {
        await refreshWorkflowOverview(selectedTargetId.value);
      }
      if (!sizeEstimate.value) {
        void refreshSizeEstimate();
      } else if (isTerminalJobState(sizeEstimate.value.state)) {
        if (["unknown", "stale"].includes(sizeEstimate.value.status)) {
          void refreshSizeEstimate();
        }
      } else {
        void waitForSizeEstimateCompletion();
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
    if (selectedTargetId.value) {
      await refreshWorkflowOverview(selectedTargetId.value);
    }
  }

  async function refreshSnapshots(): Promise<void> {
    snapshots.value = (await fetchBackupSnapshots()).data;
  }

  async function waitForSizeEstimateCompletion(): Promise<void> {
    while (sizeEstimate.value && !isTerminalJobState(sizeEstimate.value.state)) {
      await sleep(800);
      sizeEstimate.value = (await fetchBackupSizeEstimate()).data;
    }
  }

  async function refreshSizeEstimate(force = false): Promise<void> {
    sizeEstimate.value = (await collectBackupSizeEstimate(force)).data;
    if (!sizeEstimate.value) {
      return;
    }
    const status = sizeEstimate.value.status as BackupSizeEstimateStatus;
    if (!isTerminalJobState(sizeEstimate.value.state) || ["unknown", "stale"].includes(status)) {
      await waitForSizeEstimateCompletion();
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
    validatingTargetId.value = targetId;
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
      validatingTargetId.value = null;
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
      await refreshWorkflowOverview(targetId);
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

  async function refreshWorkflowOverview(targetId: string): Promise<void> {
    isLoadingWorkflow.value = true;
    workflowError.value = null;
    try {
      workflowOverview.value = (await fetchBackupAssetWorkflowOverview(targetId)).data;
      selectedAssetIds.value = selectedAssetIds.value.filter((assetId) =>
        workflowOverview.value?.comparison.items.some((item) => item.assetId === assetId),
      );
    } catch (caughtError) {
      workflowError.value = errorMessage(caughtError);
    } finally {
      isLoadingWorkflow.value = false;
    }
  }

  async function startTestCopy(targetId: string): Promise<void> {
    isRunningTestCopy.value = true;
    workflowError.value = null;
    try {
      lastTestCopy.value = (await runBackupTestCopy(targetId)).data;
      await refreshWorkflowOverview(targetId);
    } catch (caughtError) {
      workflowError.value = errorMessage(caughtError);
    } finally {
      isRunningTestCopy.value = false;
    }
  }

  function toggleAssetSelection(assetId: string): void {
    if (selectedAssetIds.value.includes(assetId)) {
      selectedAssetIds.value = selectedAssetIds.value.filter((item) => item !== assetId);
      return;
    }
    selectedAssetIds.value = [...selectedAssetIds.value, assetId];
  }

  function clearAssetSelection(): void {
    selectedAssetIds.value = [];
  }

  async function previewRestore(targetId: string, assetIds: string[]): Promise<void> {
    isRunningRestore.value = true;
    restoreError.value = null;
    try {
      restorePreview.value = (await runBackupRestoreAction(targetId, assetIds, false)).data;
    } catch (caughtError) {
      restoreError.value = errorMessage(caughtError);
    } finally {
      isRunningRestore.value = false;
    }
  }

  async function applyRestore(targetId: string, assetIds: string[]): Promise<void> {
    isRunningRestore.value = true;
    restoreError.value = null;
    try {
      lastRestoreResult.value = (await runBackupRestoreAction(targetId, assetIds, true)).data;
      restorePreview.value = null;
      await refreshWorkflowOverview(targetId);
    } catch (caughtError) {
      restoreError.value = errorMessage(caughtError);
    } finally {
      isRunningRestore.value = false;
    }
  }

  function selectTarget(targetId: string): void {
    selectedTargetId.value = targetId;
    selectedAssetIds.value = [];
    lastTestCopy.value = null;
    restorePreview.value = null;
    lastRestoreResult.value = null;
    void refreshWorkflowOverview(targetId);
  }

  return {
    activeValidation,
    applyRestore,
    cancelExecution,
    clearAssetSelection,
    currentExecution,
    databaseEstimate,
    error,
    executionError,
    hasTargets,
    isExecuting,
    isExecutionRunning,
    isLoading,
    isLoadingWorkflow,
    isRunningRestore,
    isRunningTestCopy,
    isSavingTarget,
    isSizeCollectionRunning,
    isValidatingTarget,
    lastRestoreResult,
    lastTestCopy,
    load,
    previewRestore,
    quarantine,
    refreshWorkflowOverview,
    refreshSizeEstimate,
    removeTarget,
    restoreError,
    restorePreview,
    restorableItems,
    saveTarget,
    selectedAssetIds,
    selectedTarget,
    selectedTargetId,
    selectedWorkflowItems,
    selectTarget,
    sizeEstimate,
    snapshotItems,
    snapshots,
    startExecution,
    startTestCopy,
    storageEstimate,
    targetError,
    toggleAssetSelection,
    targets,
    targetsOverview,
    validateTarget,
    validatingTargetId,
    validationError,
    workflowError,
    workflowItems,
    workflowOverview,
  };
});
