import { computed, ref } from "vue";
import { defineStore } from "pinia";
import { ApiClientError } from "@/api/client";
import {
  applyCatalogRemediation,
  applyMissingAssetRemovals,
  fetchCatalogRemediationFindings,
  deleteMissingAssetRestorePoints,
  fetchCatalogConsistencyJob,
  fetchMissingAssetFindings,
  fetchMissingAssetRestorePoints,
  previewBrokenDbOriginalRemediation,
  previewFuseHiddenRemediation,
  previewMissingAssetRemovals,
  restoreMissingAssetRestorePoints,
  startCatalogConsistencyJob,
} from "@/api/consistency";
import type { CatalogValidationReport, CatalogWorkflowJobRecord } from "@/api/types/catalog";
import type {
  CatalogRemediationApplyResponse,
  CatalogRemediationPreviewRequest,
  CatalogRemediationPreviewResponse,
  CatalogRemediationScanResponse,
  MissingAssetApplyResponse,
  MissingAssetPreviewRequest,
  MissingAssetPreviewResponse,
  MissingAssetReferenceFinding,
  MissingAssetRestorePointDeleteRequest,
  MissingAssetRestorePointDeleteResponse,
  MissingAssetRestorePointsResponse,
  MissingAssetRestoreRequest,
  MissingAssetRestoreResponse,
  MissingAssetScanResponse,
} from "@/api/types/consistency";

function toErrorMessage(caughtError: unknown): string {
  return caughtError instanceof ApiClientError ? caughtError.payload.message : "Unknown error.";
}

type CatalogReadinessState =
  | "ready"
  | "indexing"
  | "waiting_for_index"
  | "rebuilding"
  | "compare_running"
  | "error";

function catalogBlockedBy(job: CatalogWorkflowJobRecord | null): Record<string, unknown> | null {
  const result = job?.result;
  if (!result || typeof result !== "object") {
    return null;
  }
  const blockedBy = result.blockedBy;
  return blockedBy && typeof blockedBy === "object" ? (blockedBy as Record<string, unknown>) : null;
}

function catalogRequiresScan(job: CatalogWorkflowJobRecord | null): boolean {
  const result = job?.result;
  return Boolean(result && typeof result === "object" && result.requiresScan);
}

export const useConsistencyStore = defineStore("consistency", () => {
  const remediationScanResult = ref<CatalogRemediationScanResponse | null>(null);
  const remediationPreviewResult = ref<CatalogRemediationPreviewResponse | null>(null);
  const remediationApplyResult = ref<CatalogRemediationApplyResponse | null>(null);
  const scanResult = ref<MissingAssetScanResponse | null>(null);
  const restorePointsResult = ref<MissingAssetRestorePointsResponse | null>(null);
  const catalogJob = ref<CatalogWorkflowJobRecord | null>(null);
  const applyResult = ref<MissingAssetApplyResponse | null>(null);
  const restoreResult = ref<MissingAssetRestoreResponse | null>(null);
  const deleteResult = ref<MissingAssetRestorePointDeleteResponse | null>(null);

  const isLoading = ref(false);
  const isScanning = ref(false);
  const isCatalogLoading = ref(false);
  const isCatalogStarting = ref(false);
  const isLoadingRestorePoints = ref(false);
  const isLoadingRemediation = ref(false);
  const isPreviewing = ref(false);
  const isApplying = ref(false);
  const isRestoring = ref(false);
  const isDeletingRestorePoints = ref(false);

  const scanError = ref<string | null>(null);
  const catalogJobError = ref<string | null>(null);
  const remediationError = ref<string | null>(null);
  const remediationPreviewError = ref<string | null>(null);
  const remediationApplyError = ref<string | null>(null);
  const restorePointsError = ref<string | null>(null);
  const previewError = ref<string | null>(null);
  const applyError = ref<string | null>(null);
  const restoreError = ref<string | null>(null);
  const deleteError = ref<string | null>(null);

  const catalogReadinessState = computed<CatalogReadinessState>(() => {
    if (catalogJobError.value) {
      return "error";
    }
    const job = catalogJob.value;
    if (!job) {
      return "ready";
    }
    const blockedBy = catalogBlockedBy(job);
    if (blockedBy?.jobType === "catalog_inventory_scan") {
      return "indexing";
    }
    if (job.state === "running") {
      return "compare_running";
    }
    if (catalogRequiresScan(job)) {
      return "waiting_for_index";
    }
    const result = job.result && typeof job.result === "object"
      ? (job.result as Record<string, unknown>)
      : null;
    if (
      job.state === "pending" &&
      result &&
      Boolean(result.stale)
    ) {
      return "rebuilding";
    }
    return "ready";
  });

  const isWaitingOnCatalog = computed(
    () =>
      catalogReadinessState.value === "indexing" ||
      catalogReadinessState.value === "waiting_for_index" ||
      catalogReadinessState.value === "rebuilding" ||
      catalogReadinessState.value === "compare_running",
  );

  const catalogReadinessTitle = computed(() => {
    switch (catalogReadinessState.value) {
      case "indexing":
        return "Consistency is waiting for storage indexing";
      case "waiting_for_index":
        return "Consistency is waiting for a current storage index";
      case "rebuilding":
        return "Consistency is rebuilding after the storage index changed";
      case "compare_running":
        return "Consistency compare is running";
      case "error":
        return "Consistency readiness could not be determined";
      default:
        return "Consistency data is ready";
    }
  });

  const catalogReadinessMessage = computed(() => {
    if (catalogJobError.value) {
      return catalogJobError.value;
    }
    if (catalogJob.value?.summary) {
      return catalogJob.value.summary;
    }
    return "Consistency findings become current after the catalog-backed storage index is ready.";
  });

  const shouldSkipMissingAssetScan = computed(
    () => isWaitingOnCatalog.value && !scanResult.value,
  );

  async function load(): Promise<void> {
    isLoading.value = true;
    scanError.value = null;
    catalogJobError.value = null;
    restorePointsError.value = null;
    try {
      await loadCatalogJob();
      if (isWaitingOnCatalog.value) {
        scanResult.value = null;
        scanError.value = null;
      }
      await Promise.allSettled([
        loadRemediation(),
        loadRestorePoints(),
        shouldSkipMissingAssetScan.value ? Promise.resolve(null) : scan(),
      ]);
    } finally {
      isLoading.value = false;
    }
  }

  async function scan(): Promise<MissingAssetScanResponse | null> {
    isScanning.value = true;
    scanError.value = null;
    previewError.value = null;
    try {
      const response = await fetchMissingAssetFindings();
      scanResult.value = response.data;
      return response.data;
    } catch (caughtError) {
      scanError.value = toErrorMessage(caughtError);
      return null;
    } finally {
      isScanning.value = false;
    }
  }

  async function loadCatalogJob(): Promise<CatalogWorkflowJobRecord | null> {
    isCatalogLoading.value = true;
    catalogJobError.value = null;
    try {
      const response = await fetchCatalogConsistencyJob();
      catalogJob.value = response.data;
      return response.data;
    } catch (caughtError) {
      catalogJobError.value = toErrorMessage(caughtError);
      return null;
    } finally {
      isCatalogLoading.value = false;
    }
  }

  async function startCatalog(force = true): Promise<CatalogWorkflowJobRecord | null> {
    isCatalogStarting.value = true;
    catalogJobError.value = null;
    try {
      const response = await startCatalogConsistencyJob({ force });
      catalogJob.value = response.data;
      return response.data;
    } catch (caughtError) {
      catalogJobError.value = toErrorMessage(caughtError);
      return null;
    } finally {
      isCatalogStarting.value = false;
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

  async function loadRemediation(): Promise<CatalogRemediationScanResponse | null> {
    isLoadingRemediation.value = true;
    remediationError.value = null;
    try {
      const response = await fetchCatalogRemediationFindings();
      remediationScanResult.value = response.data;
      return response.data;
    } catch (caughtError) {
      remediationError.value = toErrorMessage(caughtError);
      return null;
    } finally {
      isLoadingRemediation.value = false;
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
      await Promise.allSettled([scan(), loadRestorePoints()]);
      return response.data;
    } catch (caughtError) {
      applyError.value = toErrorMessage(caughtError);
      return null;
    } finally {
      isApplying.value = false;
    }
  }

  async function previewBrokenDbOriginals(
    payload: CatalogRemediationPreviewRequest,
  ): Promise<CatalogRemediationPreviewResponse | null> {
    isPreviewing.value = true;
    remediationPreviewError.value = null;
    try {
      const response = await previewBrokenDbOriginalRemediation(payload);
      remediationPreviewResult.value = response.data;
      return response.data;
    } catch (caughtError) {
      remediationPreviewError.value = toErrorMessage(caughtError);
      return null;
    } finally {
      isPreviewing.value = false;
    }
  }

  async function previewFuseHidden(
    payload: CatalogRemediationPreviewRequest,
  ): Promise<CatalogRemediationPreviewResponse | null> {
    isPreviewing.value = true;
    remediationPreviewError.value = null;
    try {
      const response = await previewFuseHiddenRemediation(payload);
      remediationPreviewResult.value = response.data;
      return response.data;
    } catch (caughtError) {
      remediationPreviewError.value = toErrorMessage(caughtError);
      return null;
    } finally {
      isPreviewing.value = false;
    }
  }

  async function applyRemediation(
    repairRunId: string,
  ): Promise<CatalogRemediationApplyResponse | null> {
    if (!repairRunId) {
      remediationApplyError.value = "A previewed repair run is required before apply.";
      return null;
    }
    isApplying.value = true;
    remediationApplyError.value = null;
    try {
      const response = await applyCatalogRemediation(repairRunId);
      remediationApplyResult.value = response.data;
      await Promise.allSettled([loadRemediation(), scan(), loadRestorePoints()]);
      return response.data;
    } catch (caughtError) {
      remediationApplyError.value = toErrorMessage(caughtError);
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
      await Promise.allSettled([scan(), loadRestorePoints()]);
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

  const catalogReport = computed<CatalogValidationReport | null>(() => {
    const candidate = catalogJob.value?.result?.report;
    return candidate && typeof candidate === "object"
      ? (candidate as CatalogValidationReport)
      : null;
  });

  const findings = computed<MissingAssetReferenceFinding[]>(
    () => scanResult.value?.findings ?? [],
  );
  const brokenDbOriginals = computed(
    () => remediationScanResult.value?.broken_db_originals ?? [],
  );
  const fuseHiddenOrphans = computed(
    () => remediationScanResult.value?.fuse_hidden_orphans ?? [],
  );
  const restorePoints = computed(() => restorePointsResult.value?.items ?? []);

  return {
    apply,
    applyRemediation,
    applyError,
    applyResult,
    brokenDbOriginals,
    catalogJob,
    catalogJobError,
    catalogReadinessMessage,
    catalogReadinessState,
    catalogReadinessTitle,
    catalogReport,
    deleteError,
    deleteResult,
    deleteRestorePoints,
    fuseHiddenOrphans,
    findings,
    isApplying,
    isCatalogLoading,
    isCatalogStarting,
    isDeletingRestorePoints,
    isLoading,
    isLoadingRemediation,
    isLoadingRestorePoints,
    isPreviewing,
    isRestoring,
    isScanning,
    isWaitingOnCatalog,
    load,
    loadCatalogJob,
    loadRemediation,
    loadRestorePoints,
    preview,
    previewBrokenDbOriginals,
    previewFuseHidden,
    previewError,
    remediationApplyError,
    remediationApplyResult,
    remediationError,
    remediationPreviewError,
    remediationPreviewResult,
    remediationScanResult,
    restore,
    restoreError,
    restorePoints,
    restorePointsError,
    restorePointsResult,
    restoreResult,
    scan,
    scanError,
    scanResult,
    shouldSkipMissingAssetScan,
    startCatalog,
  };
});
