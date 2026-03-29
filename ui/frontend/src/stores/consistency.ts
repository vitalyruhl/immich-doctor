import { computed, ref } from "vue";
import { defineStore } from "pinia";
import { ApiClientError } from "@/api/client";
import {
  applyMissingAssetRemovals,
  deleteMissingAssetRestorePoints,
  fetchMissingAssetFindings,
  fetchMissingAssetScanStatus,
  fetchMissingAssetRestorePoints,
  previewMissingAssetRemovals,
  restoreMissingAssetRestorePoints,
  triggerMissingAssetScan,
} from "@/api/consistency";
import type {
  MissingAssetApplyRequest,
  MissingAssetApplyResponse,
  MissingAssetCompletedScanSummary,
  MissingAssetPreviewRequest,
  MissingAssetPreviewResponse,
  MissingAssetReferenceFinding,
  MissingAssetRestorePointDeleteRequest,
  MissingAssetRestorePointDeleteResponse,
  MissingAssetRestorePointsResponse,
  MissingAssetRestoreRequest,
  MissingAssetRestoreResponse,
  MissingAssetScanResponse,
  MissingAssetScanState,
  MissingAssetScanStatusResponse,
} from "@/api/types/consistency";

function toErrorMessage(caughtError: unknown): string {
  return caughtError instanceof ApiClientError ? caughtError.payload.message : "Unknown error.";
}

export const useConsistencyStore = defineStore("consistency", () => {
  const scanResult = ref<MissingAssetScanResponse | null>(null);
  const scanStatusResult = ref<MissingAssetScanStatusResponse | null>(null);
  const restorePointsResult = ref<MissingAssetRestorePointsResponse | null>(null);
  const applyResult = ref<MissingAssetApplyResponse | null>(null);
  const restoreResult = ref<MissingAssetRestoreResponse | null>(null);
  const deleteResult = ref<MissingAssetRestorePointDeleteResponse | null>(null);

  const isLoading = ref(false);
  const isScanning = ref(false);
  const isLoadingScanStatus = ref(false);
  const isLoadingRestorePoints = ref(false);
  const isPreviewing = ref(false);
  const isApplying = ref(false);
  const isRestoring = ref(false);
  const isDeletingRestorePoints = ref(false);

  const scanError = ref<string | null>(null);
  const restorePointsError = ref<string | null>(null);
  const previewError = ref<string | null>(null);
  const applyError = ref<string | null>(null);
  const restoreError = ref<string | null>(null);
  const deleteError = ref<string | null>(null);

  async function load(): Promise<void> {
    isLoading.value = true;
    scanError.value = null;
    restorePointsError.value = null;
    try {
      await Promise.allSettled([loadScanStatus(), loadFindings(), loadRestorePoints()]);
    } finally {
      isLoading.value = false;
    }
  }

  async function loadScanStatus(): Promise<MissingAssetScanStatusResponse | null> {
    isLoadingScanStatus.value = true;
    scanError.value = null;
    try {
      const response = await fetchMissingAssetScanStatus();
      scanStatusResult.value = response.data;
      if (shouldReloadFindings(response.data)) {
        await loadFindings();
      }
      return response.data;
    } catch (caughtError) {
      scanError.value = toErrorMessage(caughtError);
      return null;
    } finally {
      isLoadingScanStatus.value = false;
    }
  }

  async function loadFindings(): Promise<MissingAssetScanResponse | null> {
    scanError.value = null;
    try {
      const response = await fetchMissingAssetFindings();
      scanResult.value = response.data;
      return response.data;
    } catch (caughtError) {
      scanError.value = toErrorMessage(caughtError);
      return null;
    }
  }

  async function scan(): Promise<MissingAssetScanStatusResponse | null> {
    isScanning.value = true;
    scanError.value = null;
    previewError.value = null;
    try {
      const response = await triggerMissingAssetScan();
      scanStatusResult.value = response.data;
      if (response.data.latest_completed && !scanResult.value) {
        await loadFindings();
      }
      return response.data;
    } catch (caughtError) {
      scanError.value = toErrorMessage(caughtError);
      return null;
    } finally {
      isScanning.value = false;
    }
  }

  async function loadRestorePoints(): Promise<MissingAssetRestorePointsResponse | null> {
    isLoadingRestorePoints.value = true;
    restorePointsError.value = null;
    try {
      const response = await fetchMissingAssetRestorePoints();
      restorePointsResult.value = response.data;
      return response.data;
    } catch (caughtError) {
      restorePointsError.value = toErrorMessage(caughtError);
      return null;
    } finally {
      isLoadingRestorePoints.value = false;
    }
  }

  async function preview(
    payload: MissingAssetPreviewRequest,
  ): Promise<MissingAssetPreviewResponse | null> {
    isPreviewing.value = true;
    previewError.value = null;
    try {
      const response = await previewMissingAssetRemovals(payload);
      return response.data;
    } catch (caughtError) {
      previewError.value = toErrorMessage(caughtError);
      return null;
    } finally {
      isPreviewing.value = false;
    }
  }

  async function apply(repairRunId: string): Promise<MissingAssetApplyResponse | null> {
    if (!repairRunId) {
      applyError.value = "A previewed repair run is required before apply.";
      return null;
    }
    isApplying.value = true;
    applyError.value = null;
    try {
      const response = await applyMissingAssetRemovals({ repair_run_id: repairRunId });
      applyResult.value = response.data;
      await Promise.allSettled([loadScanStatus(), loadFindings(), loadRestorePoints()]);
      return response.data;
    } catch (caughtError) {
      applyError.value = toErrorMessage(caughtError);
      return null;
    } finally {
      isApplying.value = false;
    }
  }

  async function restore(
    payload: MissingAssetRestoreRequest,
  ): Promise<MissingAssetRestoreResponse | null> {
    isRestoring.value = true;
    restoreError.value = null;
    try {
      const response = await restoreMissingAssetRestorePoints(payload);
      restoreResult.value = response.data;
      await Promise.allSettled([loadScanStatus(), loadFindings(), loadRestorePoints()]);
      return response.data;
    } catch (caughtError) {
      restoreError.value = toErrorMessage(caughtError);
      return null;
    } finally {
      isRestoring.value = false;
    }
  }

  async function deleteRestorePoints(
    payload: MissingAssetRestorePointDeleteRequest,
  ): Promise<MissingAssetRestorePointDeleteResponse | null> {
    isDeletingRestorePoints.value = true;
    deleteError.value = null;
    try {
      const response = await deleteMissingAssetRestorePoints(payload);
      deleteResult.value = response.data;
      await loadRestorePoints();
      return response.data;
    } catch (caughtError) {
      deleteError.value = toErrorMessage(caughtError);
      return null;
    } finally {
      isDeletingRestorePoints.value = false;
    }
  }

  const findings = computed<MissingAssetReferenceFinding[]>(
    () => scanResult.value?.findings ?? [],
  );

  const currentScanState = computed<MissingAssetScanState>(
    () => scanStatusResult.value?.scan_state ?? "idle",
  );
  const activeScan = computed(() => scanStatusResult.value?.active_scan ?? null);
  const latestCompletedScan = computed<MissingAssetCompletedScanSummary | null>(
    () => scanStatusResult.value?.latest_completed ?? null,
  );
  const hasCompletedScan = computed(
    () =>
      latestCompletedScan.value !== null ||
      scanResult.value?.metadata?.has_completed_result === true,
  );
  const isScanActive = computed(
    () => currentScanState.value === "pending" || currentScanState.value === "running",
  );
  const restorePoints = computed(() => restorePointsResult.value?.items ?? []);

  function shouldReloadFindings(status: MissingAssetScanStatusResponse): boolean {
    const statusScanId = status.latest_completed?.scan_id;
    const currentScanId = currentCompletedScanId();
    if (!statusScanId) {
      return scanResult.value === null && status.metadata?.has_completed_result === true;
    }
    return statusScanId !== currentScanId;
  }

  function currentCompletedScanId(): string | null {
    const latestCompleted = scanResult.value?.metadata?.latest_completed;
    if (latestCompleted && typeof latestCompleted === "object" && "scan_id" in latestCompleted) {
      const scanId = latestCompleted.scan_id;
      return typeof scanId === "string" && scanId.length > 0 ? scanId : null;
    }
    return null;
  }

  return {
    activeScan,
    apply,
    applyError,
    applyResult,
    currentScanState,
    deleteError,
    deleteResult,
    deleteRestorePoints,
    findings,
    hasCompletedScan,
    isApplying,
    isDeletingRestorePoints,
    isLoading,
    isLoadingScanStatus,
    isLoadingRestorePoints,
    isPreviewing,
    isRestoring,
    isScanActive,
    isScanning,
    latestCompletedScan,
    load,
    loadFindings,
    loadScanStatus,
    loadRestorePoints,
    preview,
    previewError,
    restore,
    restoreError,
    restorePoints,
    restorePointsError,
    restorePointsResult,
    restoreResult,
    scan,
    scanError,
    scanResult,
    scanStatusResult,
  };
});
