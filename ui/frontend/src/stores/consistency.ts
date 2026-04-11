import { computed, ref } from "vue";
import { defineStore } from "pinia";
import { ApiClientError } from "@/api/client";
import {
  applyCatalogBrokenDbActionDirect,
  deleteCatalogQuarantine,
  fetchCatalogConsistencyJob,
  fetchCatalogIgnoredFindings,
  fetchCatalogQuarantine,
  fetchCatalogRemediationFindings,
  ignoreCatalogFindings,
  quarantineCatalogFindings,
  refreshCatalogRemediationFindings,
  releaseCatalogIgnoredFindings,
  restoreCatalogQuarantine,
  startCatalogConsistencyJob,
} from "@/api/consistency";
import type {
  CatalogValidationReport,
  CatalogWorkflowJobRecord,
} from "@/api/types/catalog";
import type {
  BrokenDbOriginalFinding,
  CatalogIgnoredFindingsResponse,
  CatalogQuarantineResponse,
  CatalogRemediationActionResponse,
  CatalogRemediationScanResponse,
  CatalogRemediationStateItemPayload,
  FuseHiddenOrphanFinding,
  IgnoredFindingItem,
  QuarantineItemView,
  ZeroByteFinding,
} from "@/api/types/consistency";

function toErrorMessage(caughtError: unknown): string {
  return caughtError instanceof ApiClientError
    ? caughtError.payload.message
    : "Unknown error.";
}

type CatalogReadinessState =
  | "ready"
  | "indexing"
  | "waiting_for_index"
  | "rebuilding"
  | "compare_running"
  | "error";

function catalogBlockedBy(
  job: CatalogWorkflowJobRecord | null,
): Record<string, unknown> | null {
  const result = job?.result;
  if (!result || typeof result !== "object") {
    return null;
  }
  const blockedBy = result.blockedBy;
  return blockedBy && typeof blockedBy === "object"
    ? (blockedBy as Record<string, unknown>)
    : null;
}

function catalogRequiresScan(job: CatalogWorkflowJobRecord | null): boolean {
  const result = job?.result;
  return Boolean(result && typeof result === "object" && result.requiresScan);
}

function sectionRows(
  report: CatalogValidationReport | null,
  sectionName: string,
): Array<Record<string, unknown>> {
  const section = report?.sections.find((candidate) => candidate.name === sectionName);
  return section ? (section.rows as Array<Record<string, unknown>>) : [];
}

export const useConsistencyStore = defineStore("consistency", () => {
  const remediationScanResult = ref<CatalogRemediationScanResponse | null>(null);
  const catalogJob = ref<CatalogWorkflowJobRecord | null>(null);
  const ignoredState = ref<CatalogIgnoredFindingsResponse | null>(null);
  const quarantineState = ref<CatalogQuarantineResponse | null>(null);

  const isLoading = ref(false);
  const isCatalogLoading = ref(false);
  const isCatalogStarting = ref(false);
  const isLoadingRemediation = ref(false);
  const isRefreshingRemediation = ref(false);
  const isLoadingIgnored = ref(false);
  const isLoadingQuarantine = ref(false);
  const isApplyingAction = ref(false);

  const catalogJobError = ref<string | null>(null);
  const remediationError = ref<string | null>(null);
  const ignoredError = ref<string | null>(null);
  const quarantineError = ref<string | null>(null);
  const actionError = ref<string | null>(null);
  const lastActionSummary = ref<string | null>(null);

  const catalogReport = computed<CatalogValidationReport | null>(() => {
    const candidate = catalogJob.value?.result?.report;
    return candidate && typeof candidate === "object"
      ? (candidate as CatalogValidationReport)
      : null;
  });

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
    const result =
      job.result && typeof job.result === "object"
        ? (job.result as Record<string, unknown>)
        : null;
    if (job.state === "pending" && result && Boolean(result.stale)) {
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

  async function load(): Promise<void> {
    isLoading.value = true;
    try {
      await Promise.all([
        loadCatalogJob(),
        loadRemediation(),
        loadIgnored(),
        loadQuarantine(),
      ]);
    } finally {
      isLoading.value = false;
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

  async function startCatalog(
    force = true,
  ): Promise<CatalogWorkflowJobRecord | null> {
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

  async function refreshRemediation(): Promise<CatalogRemediationScanResponse | null> {
    isRefreshingRemediation.value = true;
    remediationError.value = null;
    try {
      const response = await refreshCatalogRemediationFindings();
      remediationScanResult.value = response.data;
      return response.data;
    } catch (caughtError) {
      remediationError.value = toErrorMessage(caughtError);
      return null;
    } finally {
      isRefreshingRemediation.value = false;
    }
  }

  async function loadIgnored(): Promise<CatalogIgnoredFindingsResponse | null> {
    isLoadingIgnored.value = true;
    ignoredError.value = null;
    try {
      const response = await fetchCatalogIgnoredFindings();
      ignoredState.value = response.data;
      return response.data;
    } catch (caughtError) {
      ignoredError.value = toErrorMessage(caughtError);
      return null;
    } finally {
      isLoadingIgnored.value = false;
    }
  }

  async function loadQuarantine(): Promise<CatalogQuarantineResponse | null> {
    isLoadingQuarantine.value = true;
    quarantineError.value = null;
    try {
      const response = await fetchCatalogQuarantine();
      quarantineState.value = response.data;
      return response.data;
    } catch (caughtError) {
      quarantineError.value = toErrorMessage(caughtError);
      return null;
    } finally {
      isLoadingQuarantine.value = false;
    }
  }

  async function runWorkspaceAction(
    runner: () => Promise<CatalogRemediationActionResponse | CatalogIgnoredFindingsResponse | Record<string, unknown>>,
  ): Promise<void> {
    isApplyingAction.value = true;
    actionError.value = null;
    lastActionSummary.value = null;
    try {
      const result = await runner();
      lastActionSummary.value =
        typeof result === "object" && result !== null && "summary" in result
          ? String(result.summary)
          : "Action completed.";
      await Promise.all([loadIgnored(), loadQuarantine(), loadRemediation()]);
    } catch (caughtError) {
      actionError.value = toErrorMessage(caughtError);
    } finally {
      isApplyingAction.value = false;
    }
  }

  async function ignoreItems(items: CatalogRemediationStateItemPayload[]): Promise<void> {
    await runWorkspaceAction(async () => {
      const response = await ignoreCatalogFindings({ items });
      return response.data;
    });
  }

  async function quarantineItems(items: CatalogRemediationStateItemPayload[]): Promise<void> {
    await runWorkspaceAction(async () => {
      const response = await quarantineCatalogFindings({ items });
      return response.data;
    });
  }

  async function releaseIgnoredItems(ignoredItemIds: string[]): Promise<void> {
    await runWorkspaceAction(async () => {
      const response = await releaseCatalogIgnoredFindings({
        ignored_item_ids: ignoredItemIds,
      });
      return response.data;
    });
  }

  async function restoreQuarantineItems(quarantineItemIds: string[]): Promise<void> {
    await runWorkspaceAction(async () => {
      const response = await restoreCatalogQuarantine({
        quarantine_item_ids: quarantineItemIds,
      });
      return response.data;
    });
  }

  async function deleteQuarantineItemsPermanently(quarantineItemIds: string[]): Promise<void> {
    await runWorkspaceAction(async () => {
      const response = await deleteCatalogQuarantine({
        quarantine_item_ids: quarantineItemIds,
      });
      return response.data;
    });
  }

  async function applyBrokenDbAction(
    assetIds: string[],
    actionKind: "broken_db_cleanup" | "broken_db_path_fix",
  ): Promise<void> {
    isApplyingAction.value = true;
    actionError.value = null;
    lastActionSummary.value = null;
    try {
      const response = await applyCatalogBrokenDbActionDirect({
        asset_ids: assetIds,
        action_kind: actionKind,
      });
      lastActionSummary.value =
        typeof response.data.summary === "string"
          ? response.data.summary
          : "Action completed.";
      await Promise.all([loadCatalogJob(), loadIgnored(), loadQuarantine(), refreshRemediation()]);
    } catch (caughtError) {
      actionError.value = toErrorMessage(caughtError);
    } finally {
      isApplyingAction.value = false;
    }
  }

  const brokenDbOriginals = computed<BrokenDbOriginalFinding[]>(
    () => remediationScanResult.value?.broken_db_originals ?? [],
  );
  const zeroByteFindings = computed<ZeroByteFinding[]>(
    () => remediationScanResult.value?.zero_byte_findings ?? [],
  );
  const fuseHiddenOrphans = computed<FuseHiddenOrphanFinding[]>(
    () => remediationScanResult.value?.fuse_hidden_orphans ?? [],
  );
  const storageOriginalsMissingInDb = computed(() =>
    sectionRows(catalogReport.value, "STORAGE_ORIGINALS_MISSING_IN_DB"),
  );
  const orphanDerivatives = computed(() =>
    sectionRows(catalogReport.value, "ORPHAN_DERIVATIVES_WITHOUT_ORIGINAL"),
  );
  const unmappedDatabasePaths = computed(() =>
    sectionRows(catalogReport.value, "UNMAPPED_DATABASE_PATHS"),
  );
  const ignoredFindings = computed<IgnoredFindingItem[]>(
    () => ignoredState.value?.items ?? [],
  );
  const quarantinedItems = computed<QuarantineItemView[]>(
    () => quarantineState.value?.items ?? [],
  );
  const hiddenFindingIds = computed(() => {
    const ids = new Set<string>();
    for (const item of ignoredFindings.value) {
      ids.add(item.finding_id);
    }
    for (const item of quarantinedItems.value) {
      if (item.finding_id) {
        ids.add(item.finding_id);
      }
    }
    return ids;
  });

  return {
    actionError,
    applyBrokenDbAction,
    brokenDbOriginals,
    catalogJob,
    catalogJobError,
    catalogReadinessMessage,
    catalogReadinessState,
    catalogReadinessTitle,
    catalogReport,
    deleteQuarantineItemsPermanently,
    fuseHiddenOrphans,
    hiddenFindingIds,
    ignoreItems,
    ignoredError,
    ignoredFindings,
    ignoredState,
    isApplyingAction,
    isCatalogLoading,
    isCatalogStarting,
    isLoading,
    isLoadingIgnored,
    isLoadingQuarantine,
    isLoadingRemediation,
    isRefreshingRemediation,
    isWaitingOnCatalog,
    lastActionSummary,
    load,
    loadCatalogJob,
    loadIgnored,
    loadQuarantine,
    loadRemediation,
    orphanDerivatives,
    quarantineError,
    quarantineItems,
    quarantineState,
    quarantinedItems,
    remediationError,
    remediationScanResult,
    refreshRemediation,
    releaseIgnoredItems,
    restoreQuarantineItems,
    startCatalog,
    storageOriginalsMissingInDb,
    unmappedDatabasePaths,
    zeroByteFindings,
  };
});
